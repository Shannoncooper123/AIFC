"""金字塔加仓管理器"""
from typing import Dict, Optional
from dataclasses import dataclass, asdict
import time
from monitor_module.utils.logger import get_logger

logger = get_logger('rule_strategy.pyramid')


@dataclass
class PyramidPosition:
    """金字塔持仓信息"""
    symbol: str
    level: int                         # 当前层级（1 或 2）
    entry_price_l1: float              # Level 1 入场价
    entry_price_l2: Optional[float]    # Level 2 入场价（未加仓为 None）
    avg_price: float                   # 平均成本
    atr: float                         # ATR 值
    position_id_l1: str                # Level 1 的 position_id
    position_id_l2: Optional[str]      # Level 2 的 position_id（未加仓为 None）
    open_time: float                   # 开仓时间戳
    expire_time: float                 # 到期时间戳
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


class PyramidManager:
    """管理所有金字塔持仓状态"""
    
    def __init__(self):
        self.positions: Dict[str, PyramidPosition] = {}
    
    def add_position(self, symbol: str, entry_price: float, atr: float, 
                     position_id: str, max_hold_seconds: int) -> PyramidPosition:
        """添加 Level 1 持仓
        
        Args:
            symbol: 交易对
            entry_price: 入场价格
            atr: ATR 值
            position_id: 持仓 ID
            max_hold_seconds: 最大持仓时间（秒）
            
        Returns:
            PyramidPosition 对象
        """
        now = time.time()
        pos = PyramidPosition(
            symbol=symbol,
            level=1,
            entry_price_l1=entry_price,
            entry_price_l2=None,
            avg_price=entry_price,
            atr=atr,
            position_id_l1=position_id,
            position_id_l2=None,
            open_time=now,
            expire_time=now + max_hold_seconds
        )
        self.positions[symbol] = pos
        return pos
    
    def get_position(self, symbol: str) -> Optional[PyramidPosition]:
        """获取持仓信息"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """检查是否有持仓"""
        return symbol in self.positions
    
    def can_add_level2(self, symbol: str, current_price: float, 
                       addon_atr_drop: float) -> bool:
        """判断是否可以加仓 Level 2
        
        Args:
            symbol: 交易对
            current_price: 当前价格
            addon_atr_drop: 加仓触发：价格下跌 ATR 倍数
            
        Returns:
            是否可以加仓
        """
        pos = self.positions.get(symbol)
        
        # 严格检查：必须存在持仓且必须是 Level 1（从未加过仓）
        if not pos:
            logger.debug(f"{symbol} 没有持仓，不能加仓")
            return False
        
        if pos.level != 1:
            logger.debug(f"{symbol} 当前 Level {pos.level}，只有 Level 1 可以加仓")
            return False
        
        # 检查价格是否下跌足够
        price_drop = pos.entry_price_l1 - current_price
        threshold = pos.atr * addon_atr_drop
        
        if price_drop < threshold:
            logger.debug(f"{symbol} 价格下跌不足: {price_drop:.6f} < {threshold:.6f}")
            return False
        
        logger.info(f"{symbol} 满足 Level 2 加仓条件: 价格下跌 {price_drop:.6f} >= {threshold:.6f}")
        return True
    
    def add_level2(self, symbol: str, entry_price_l2: float, position_id_l2: str):
        """更新为 Level 2
        
        Args:
            symbol: 交易对
            entry_price_l2: Level 2 入场价
            position_id_l2: Level 2 持仓 ID
        """
        pos = self.positions[symbol]
        
        # 严格验证：只有 Level 1 可以升级到 Level 2
        if pos.level != 1:
            error_msg = f"{symbol} 已经是 Level {pos.level}，不能再加仓到 Level 2"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        pos.level = 2
        pos.entry_price_l2 = entry_price_l2
        pos.position_id_l2 = position_id_l2
        
        # 重新计算平均价格（假设 50%:50% 仓位）
        pos.avg_price = (pos.entry_price_l1 + entry_price_l2) / 2
        
        logger.info(f"{symbol} 已升级到 Level 2: 均价 {pos.avg_price:.6f} (L1: {pos.entry_price_l1:.6f}, L2: {entry_price_l2:.6f})")
    
    def remove_position(self, symbol: str):
        """移除持仓"""
        if symbol in self.positions:
            del self.positions[symbol]
    
    def is_expired(self, symbol: str) -> bool:
        """检查持仓是否到期
        
        Args:
            symbol: 交易对
            
        Returns:
            是否到期
        """
        pos = self.positions.get(symbol)
        if not pos:
            return False
        return time.time() >= pos.expire_time
    
    def get_all_positions(self) -> Dict[str, PyramidPosition]:
        """获取所有持仓"""
        return self.positions.copy()
    
    def count(self) -> int:
        """持仓数量"""
        return len(self.positions)
    
    def save_state(self, filepath: str):
        """保存金字塔状态到文件
        
        Args:
            filepath: 保存路径
        """
        import json
        from pathlib import Path
        
        state = {
            'positions': {
                symbol: pos.to_dict() 
                for symbol, pos in self.positions.items()
            },
            'saved_at': time.time()
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def load_state(self, filepath: str) -> int:
        """从文件加载金字塔状态
        
        Args:
            filepath: 文件路径
            
        Returns:
            恢复的持仓数量
        """
        import json
        from pathlib import Path
        
        if not Path(filepath).exists():
            return 0
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            positions_data = state.get('positions', {})
            count = 0
            
            for symbol, pos_dict in positions_data.items():
                # 重建 PyramidPosition 对象
                pos = PyramidPosition(
                    symbol=pos_dict['symbol'],
                    level=pos_dict['level'],
                    entry_price_l1=pos_dict['entry_price_l1'],
                    entry_price_l2=pos_dict.get('entry_price_l2'),
                    avg_price=pos_dict['avg_price'],
                    atr=pos_dict['atr'],
                    position_id_l1=pos_dict['position_id_l1'],
                    position_id_l2=pos_dict.get('position_id_l2'),
                    open_time=pos_dict['open_time'],
                    expire_time=pos_dict['expire_time']
                )
                self.positions[symbol] = pos
                count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"加载金字塔状态失败: {e}")
            return 0
