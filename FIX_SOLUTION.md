# 修复加仓次数限制的方案

## 问题根源

在 `strategy_executor.py` 第 341-343 行：

```python
# 检查是否已经是 Level 2
if pos.level >= 2:
    logger.debug(f"⊘ {symbol} 已经是 Level {pos.level}，不再加仓")
    return
```

这个检查**在第一次加仓后就失效了**，因为：
1. 第一次加仓后，`pos.level` 被设置为 2
2. 但如果价格继续下跌，再次收到 Level 2 信号时
3. 这个 `if` 判断会执行 `return`，**理论上应该阻止加仓**

但实际上出现了 4-5 次加仓，说明：**这个检查被跳过了，或者持仓状态没有正确同步**

## 深层原因分析

查看代码流程：

1. `_handle_addon_signal` 在第 335 行获取持仓：
   ```python
   pos = self.pyramid_mgr.get_position(symbol)
   ```

2. 在第 400 行更新加仓状态：
   ```python
   self.pyramid_mgr.add_level2(symbol, current_price, position_id_l2)
   ```

**问题可能是：**
- TradeSimulatorEngine 的 `open_position` 方法被调用多次
- 但 PyramidManager 的状态没有即时持久化
- 或者在多线程环境下，状态检查和更新之间存在竞态条件

## 解决方案

### 方案1：在 PyramidManager 中添加严格的次数限制（推荐）

修改 `pyramid_manager.py`:

```python
def can_add_level2(self, symbol: str, current_price: float, 
                   addon_atr_drop: float) -> bool:
    """判断是否可以加仓 Level 2"""
    pos = self.positions.get(symbol)
    
    # 🔒 严格检查：必须是 Level 1，且从未加过仓
    if not pos:
        return False
    
    if pos.level != 1:  # 只有 Level 1 可以升级到 Level 2
        logger.debug(f"{symbol} 当前 Level {pos.level}，不允许加仓")
        return False
    
    # 检查价格是否下跌足够
    price_drop = pos.entry_price_l1 - current_price
    threshold = pos.atr * addon_atr_drop
    
    if price_drop < threshold:
        return False
    
    logger.info(f"{symbol} 满足 Level 2 加仓条件")
    return True


def add_level2(self, symbol: str, entry_price_l2: float, position_id_l2: str):
    """更新为 Level 2"""
    pos = self.positions[symbol]
    
    # 🔒 再次验证
    if pos.level != 1:
        raise ValueError(f"{symbol} 已经是 Level {pos.level}，不能再加仓")
    
    pos.level = 2
    pos.entry_price_l2 = entry_price_l2
    pos.position_id_l2 = position_id_l2
    
    # 重新计算平均价格（假设 50%:50% 仓位）
    pos.avg_price = (pos.entry_price_l1 + entry_price_l2) / 2
    
    logger.info(f"{symbol} 已升级到 Level 2，均价={pos.avg_price:.6f}")
```

### 方案2：在 StrategyExecutor 中使用 can_add_level2() 方法

修改 `strategy_executor.py` 的 `_handle_addon_signal`:

```python
def _handle_addon_signal(self, symbol: str, entry: Dict):
    """处理 Level 2 加仓信号"""
    current_price = entry.get('price', 0)
    current_rsi = entry.get('rsi', 999)
    
    if current_price == 0:
        logger.warning(f"⚠️  {symbol} 价格为0，跳过加仓")
        return
    
    pos = self.pyramid_mgr.get_position(symbol)
    if not pos:
        logger.warning(f"⚠️  {symbol} 未找到持仓信息")
        return
    
    # 🔒 使用 PyramidManager 的方法检查，而不是自己判断
    addon_atr_drop = self.rule_cfg['pyramid']['addon_atr_drop']
    if not self.pyramid_mgr.can_add_level2(symbol, current_price, addon_atr_drop):
        logger.debug(f"⊘ {symbol} 不满足加仓条件或已加过仓")
        return
    
    logger.info(
        f"✅ {symbol} 满足 Level 2 加仓条件: RSI={current_rsi:.1f} < 30"
    )
    
    try:
        # ... 执行加仓逻辑 ...
        
        # 🔒 加仓成功后，立即保存状态
        self.pyramid_mgr.save_state(str(self.state_file))
        logger.info(f"💾 已保存加仓后的状态")
        
    except Exception as e:
        logger.error(f"❌ {symbol} Level 2 加仓失败: {e}", exc_info=True)
```

### 方案3：添加线程锁（如果存在并发问题）

```python
class PyramidManager:
    def __init__(self):
        self.positions: Dict[str, PyramidPosition] = {}
        self._lock = threading.RLock()  # 添加锁
    
    def can_add_level2(self, symbol: str, current_price: float, 
                       addon_atr_drop: float) -> bool:
        with self._lock:  # 使用锁保护
            pos = self.positions.get(symbol)
            
            if not pos or pos.level != 1:
                return False
            
            price_drop = pos.entry_price_l1 - current_price
            threshold = pos.atr * addon_atr_drop
            
            return price_drop >= threshold
    
    def add_level2(self, symbol: str, entry_price_l2: float, position_id_l2: str):
        with self._lock:  # 使用锁保护
            pos = self.positions[symbol]
            
            if pos.level != 1:
                raise ValueError(f"{symbol} 已经是 Level {pos.level}，不能再加仓")
            
            pos.level = 2
            pos.entry_price_l2 = entry_price_l2
            pos.position_id_l2 = position_id_l2
            pos.avg_price = (pos.entry_price_l1 + entry_price_l2) / 2
```

## 立即执行的修复步骤

1. ✅ **修改 `pyramid_manager.py` 的 `can_add_level2()` 和 `add_level2()`**
   - 将 `pos.level >= 2` 改为 `pos.level != 1`
   - 添加异常处理，防止重复加仓

2. ✅ **修改 `strategy_executor.py` 的 `_handle_addon_signal()`**
   - 使用 `can_add_level2()` 方法而不是自己判断
   - 加仓成功后立即保存状态

3. ✅ **添加日志**
   - 记录每次加仓尝试
   - 记录拒绝加仓的原因

4. ⚠️ **监控和测试**
   - 运行修复后的代码
   - 观察是否还会出现超额加仓
   - 如果还有问题，考虑添加线程锁

## 资金对账问题的处理

关于 -60 USDT 的差异，建议：

1. **备份当前的 position_history.json**
   ```bash
   cp logs/position_history.json logs/position_history_backup_$(date +%Y%m%d).json
   ```

2. **启用更详细的日志记录**
   - 记录每次开仓的手续费
   - 记录每次平仓的 PNL 和手续费
   - 记录账户余额的每次变化

3. **定期对账**
   - 每天对比账户余额和历史记录
   - 如果发现差异，立即告警

4. **检查 state_manager.py**
   - 确保每次平仓都正确写入 position_history.json
   - 使用追加模式而不是覆盖模式
