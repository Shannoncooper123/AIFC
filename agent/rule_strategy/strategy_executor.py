"""规则策略执行器

监控 rule_alerts.jsonl 文件，执行金字塔交易逻辑
"""
import json
import time
import threading
from pathlib import Path
from typing import Dict, Optional, List
from config.settings import get_config
from agent.trade_simulator.engine.simulator import TradeSimulatorEngine
from .pyramid_manager import PyramidManager
from monitor_module.utils.logger import get_logger

logger = get_logger('rule_strategy')


class StrategyExecutor:
    """规则策略执行器"""
    
    def __init__(self, trade_engine: TradeSimulatorEngine):
        self.trade_engine = trade_engine
        self.pyramid_mgr = PyramidManager()
        self.config = get_config()
        self.rule_cfg = self.config['rule_strategy']
        
        # 告警文件路径（绝对路径）
        alerts_path = self.rule_cfg.get('alerts_jsonl_path', 'data/rule_alerts.jsonl')
        if not Path(alerts_path).is_absolute():
            base_dir = Path(__file__).parent.parent.parent
            alerts_path = base_dir / alerts_path
        self.alerts_file = Path(alerts_path)
        
        # 金字塔状态文件路径
        state_path = self.rule_cfg.get('state_file', 'agent/rule_strategy_state.json')
        if not Path(state_path).is_absolute():
            base_dir = Path(__file__).parent.parent.parent
            state_path = base_dir / state_path
        self.state_file = Path(state_path)
        
        # 记录最后读取位置
        self.last_read_pos = 0
        
        # 运行状态
        self.running = False
        
        # 时间限制检查线程
        self.time_check_thread = None
        
        logger.info(f"策略执行器初始化完成")
        logger.info(f"  监控文件: {self.alerts_file}")
        logger.info(f"  仓位分配: 每币种{self.rule_cfg['position']['max_position_pct']*100:.0f}%")
        logger.info(f"  金字塔: {self.rule_cfg['pyramid']['levels']}层 {self.rule_cfg['pyramid']['position_sizes']}")
    
    def start(self):
        """启动策略执行器"""
        logger.info("=" * 60)
        logger.info("规则交易策略启动")
        logger.info("=" * 60)
        
        # 恢复金字塔状态
        restored_count = self.pyramid_mgr.load_state(str(self.state_file))
        if restored_count > 0:
            logger.info(f"✅ 恢复了 {restored_count} 个金字塔持仓状态")
            for symbol, pos in self.pyramid_mgr.get_all_positions().items():
                remain_time = (pos.expire_time - time.time()) / 3600
                logger.info(f"   {symbol}: Level {pos.level}, 剩余时间 {remain_time:.1f} 小时")
        else:
            logger.info("ℹ️  未发现历史金字塔状态，从零开始")
        
        self.running = True
        
        # 启动时间限制检查线程
        self.time_check_thread = threading.Thread(target=self._time_limit_checker, daemon=True)
        self.time_check_thread.start()
        
        # 初始化：跳到文件末尾
        if self.alerts_file.exists():
            with open(self.alerts_file, 'r', encoding='utf-8') as f:
                f.seek(0, 2)  # 移到末尾
                self.last_read_pos = f.tell()
            logger.info(f"告警文件已存在，从当前位置开始监控")
        else:
            logger.info(f"告警文件不存在，将创建: {self.alerts_file}")
            self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self._monitoring_loop()
        except KeyboardInterrupt:
            logger.info("收到退出信号")
        finally:
            self.running = False
            logger.info("策略执行器已停止")
    
    def stop(self):
        """停止策略执行器"""
        self.running = False
    
    def _monitoring_loop(self):
        """监控循环"""
        logger.info("开始监控告警文件...")
        
        last_save_time = time.time()
        save_interval = 60  # 每60秒保存一次状态
        
        while self.running:
            try:
                new_alerts = self._read_new_alerts()
                if new_alerts:
                    self._process_alerts(new_alerts)
                
                # 定期保存状态
                if time.time() - last_save_time >= save_interval:
                    if self.pyramid_mgr.count() > 0:
                        self.pyramid_mgr.save_state(str(self.state_file))
                        logger.debug(f"💾 已保存金字塔状态 ({self.pyramid_mgr.count()} 个持仓)")
                    last_save_time = time.time()
                
                time.sleep(1)  # 每秒轮询一次
                
            except Exception as e:
                logger.error(f"监控循环异常: {e}", exc_info=True)
                time.sleep(5)
        
        # 退出前保存最后状态
        if self.pyramid_mgr.count() > 0:
            self.pyramid_mgr.save_state(str(self.state_file))
            logger.info(f"💾 已保存最终金字塔状态 ({self.pyramid_mgr.count()} 个持仓)")
    
    def _time_limit_checker(self):
        """时间限制检查器（检查持仓是否到期）"""
        logger.info("时间限制检查器启动")
        
        check_interval = 30  # 每30秒检查一次
        
        while self.running:
            try:
                time.sleep(check_interval)
                
                # 检查所有持仓是否到期
                for symbol in list(self.pyramid_mgr.positions.keys()):
                    if self.pyramid_mgr.is_expired(symbol):
                        pos = self.pyramid_mgr.get_position(symbol)
                        hold_time = (time.time() - pos.open_time) / 3600  # 小时
                        logger.warning(f"⏰ {symbol} 持仓到期（已持{hold_time:.1f}小时），执行平仓")
                        self._close_position_by_time_limit(symbol)
                        
            except Exception as e:
                logger.error(f"时间限制检查异常: {e}", exc_info=True)
        
        logger.info("时间限制检查器已停止")
    
    def _close_position_by_time_limit(self, symbol: str):
        """因时间限制平仓"""
        try:
            self.trade_engine.close_position(symbol=symbol, close_reason="时间限制")
            self.pyramid_mgr.remove_position(symbol)
            # 保存状态
            self.pyramid_mgr.save_state(str(self.state_file))
            logger.info(f"✅ {symbol} 已因时间限制平仓，状态已更新")
        except Exception as e:
            logger.error(f"❌ {symbol} 时间限制平仓失败: {e}", exc_info=True)
    
    def _read_new_alerts(self) -> List[dict]:
        """读取新增的告警记录"""
        if not self.alerts_file.exists():
            return []
        
        new_alerts = []
        
        try:
            with open(self.alerts_file, 'r', encoding='utf-8') as f:
                f.seek(self.last_read_pos)
                
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        alert = json.loads(line)
                        new_alerts.append(alert)
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON解析失败: {e}")
                
                self.last_read_pos = f.tell()
        
        except Exception as e:
            logger.error(f"读取告警文件失败: {e}")
        
        return new_alerts
    
    def _process_alerts(self, alerts: List[dict]):
        """处理告警记录"""
        for alert in alerts:
            alert_type = alert.get('type')
            
            # 处理实时刺破告警
            if alert_type == 'realtime_breakout':
                symbol = alert.get('symbol')
                logger.info(f"📥 收到实时刺破告警: {symbol}")
                
                # 构造entry格式
                entry = {
                    'symbol': symbol,
                    'price': alert.get('trigger_price'),
                    'rsi': alert.get('rsi'),
                    'bb_lower': alert.get('bb_lower'),
                    'atr': alert.get('atr', 0),  # 使用真实ATR值
                    'triggered_indicators': ['BB_RSI_ENTRY']  # 标记为入场信号
                }
                self._process_entry(entry)
            
            # 处理聚合告警
            elif alert_type == 'aggregate':
                entries = alert.get('entries', [])
                logger.info(f"📥 收到聚合告警: {len(entries)}个币种")
                
                for entry in entries:
                    self._process_entry(entry)
    
    def _process_entry(self, entry: Dict):
        """处理单个币种的告警信号
        
        根据RSI值判断：
        - 30 < RSI < 40: Level 1 入场
        - RSI < 30: Level 2 加仓（或Level 1 入场）
        """
        symbol = entry['symbol']
        rsi = entry.get('rsi', 999)  # 默认很大，避免误触发
        
        # 读取配置
        rsi_entry = self.rule_cfg['entry']['rsi_entry']  # 40
        rsi_addon = self.rule_cfg['entry']['rsi_addon']  # 30
        
        if rsi > rsi_entry:
            # RSI > 40，不应该触发，忽略
            logger.debug(f"⊘ {symbol} RSI={rsi:.1f} > {rsi_entry}，忽略信号")
            return
        
        # 判断是 Level 1 还是 Level 2
        if rsi_addon < rsi <= rsi_entry:
            # 30 < RSI <= 40: Level 1 信号
            if not self.pyramid_mgr.has_position(symbol):
                logger.info(f"📍 {symbol} Level 1 信号 (RSI={rsi:.1f})")
                self._handle_entry_signal(symbol, entry)
            else:
                logger.debug(f"⊘ {symbol} Level 1 信号但已有持仓，忽略")
        else:
            # RSI < 30: Level 2 信号
            if not self.pyramid_mgr.has_position(symbol):
                # 没有持仓，当Level 1处理
                logger.info(f"📍 {symbol} Level 2 信号但无持仓，执行 Level 1 开仓 (RSI={rsi:.1f})")
                self._handle_entry_signal(symbol, entry)
            else:
                # 有持仓，检查是否满足加仓条件
                logger.info(f"📍 {symbol} Level 2 信号 (RSI={rsi:.1f})")
                self._handle_addon_signal(symbol, entry)
    
    def _handle_entry_signal(self, symbol: str, entry: Dict):
        """处理 Level 1 入场信号"""
        try:
            price = entry.get('price', 0)
            atr = entry.get('atr', 0)
            
            if price == 0 or atr == 0:
                logger.warning(f"⚠️  {symbol} 价格或ATR为0，跳过")
                return
            
            # 计算仓位
            account = self.trade_engine.get_account_summary()
            total_equity = account['equity']
            
            # 每个币种分配总资金的10%
            max_position_value = total_equity * self.rule_cfg['position']['max_position_pct']
            
            # Level 1 使用 50% (即总资金的5%)
            l1_value = max_position_value * self.rule_cfg['pyramid']['position_sizes'][0]
            
            leverage = self.rule_cfg['position']['leverage']
            l1_margin = l1_value / leverage
            l1_notional = l1_value
            
            # 计算 TP/SL
            tp_atr = self.rule_cfg['tp_sl']['tp_atr_multiplier']
            sl_atr = self.rule_cfg['tp_sl']['sl_atr_multiplier']
            
            tp_price = price + atr * tp_atr
            sl_price = price - atr * sl_atr
            
            logger.info(f"🔵 {symbol} Level 1 入场")
            logger.info(f"   价格={price:.4f}, ATR={atr:.4f}")
            logger.info(f"   仓位={l1_value:.2f} USDT ({l1_notional/total_equity*100:.1f}%), 保证金={l1_margin:.2f}")
            logger.info(f"   TP={tp_price:.4f}, SL={sl_price:.4f}")
            
            # 开仓
            self.trade_engine.open_position(
                symbol=symbol,
                side='long',
                quote_notional_usdt=l1_notional,
                leverage=leverage,
                tp_price=tp_price,
                sl_price=sl_price
            )
            
            # 获取持仓ID（从最新持仓中查找）
            time.sleep(0.5)  # 等待持仓创建
            positions = self.trade_engine.get_positions_summary()
            position_id = None
            for pos in positions:
                if pos['symbol'] == symbol:
                    position_id = pos['id']
                    break
            
            if position_id:
                # 计算到期时间（秒）
                max_hold_seconds = self.rule_cfg['time_limit']['bars'] * 15 * 60  # bars × 15分钟 × 60秒
                self.pyramid_mgr.add_position(symbol, price, atr, position_id, max_hold_seconds)
                logger.info(f"✅ {symbol} Level 1 入场成功，持仓ID={position_id}，到期时间={max_hold_seconds//3600}小时")
            else:
                logger.warning(f"⚠️  {symbol} 未找到持仓ID，可能开仓失败")
            
        except Exception as e:
            logger.error(f"❌ {symbol} Level 1 入场失败: {e}", exc_info=True)
    
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
        
        # 使用 PyramidManager 的方法进行严格检查
        addon_atr_drop = self.rule_cfg['pyramid']['addon_atr_drop']
        if not self.pyramid_mgr.can_add_level2(symbol, current_price, addon_atr_drop):
            # can_add_level2 内部已经记录了详细的拒绝原因
            return
        
        logger.info(
            f"✅ {symbol} 满足 Level 2 加仓条件: RSI={current_rsi:.1f} < 30"
        )
        
        try:
            # 计算 Level 2 仓位（另外5%总资金）
            account = self.trade_engine.get_account_summary()
            total_equity = account['equity']
            max_position_value = total_equity * self.rule_cfg['position']['max_position_pct']
            l2_value = max_position_value * self.rule_cfg['pyramid']['position_sizes'][1]
            
            leverage = self.rule_cfg['position']['leverage']
            l2_margin = l2_value / leverage
            l2_notional = l2_value
            
            logger.info(f"🟢 {symbol} Level 2 加仓")
            logger.info(f"   价格={current_price:.4f}")
            logger.info(f"   仓位={l2_value:.2f} USDT, 保证金={l2_margin:.2f}")
            
            # 开 Level 2 仓位
            self.trade_engine.open_position(
                symbol=symbol,
                side='long',
                quote_notional_usdt=l2_notional,
                leverage=leverage,
                tp_price=None,
                sl_price=None
            )
            
            # 获取 Level 2 持仓ID
            time.sleep(0.5)
            positions = self.trade_engine.get_positions_summary()
            position_id_l2 = None
            for p in positions:
                if p['symbol'] == symbol and p['id'] != pos.position_id_l1:
                    position_id_l2 = p['id']
                    break
            
            # 更新金字塔状态
            if position_id_l2:
                self.pyramid_mgr.add_level2(symbol, current_price, position_id_l2)
                # 立即保存状态
                self.pyramid_mgr.save_state(str(self.state_file))
                logger.info(f"💾 已保存 {symbol} 加仓后的状态")
            else:
                logger.error(f"❌ {symbol} 未找到 Level 2 持仓ID")
                return
            
            # 重新计算 TP/SL（基于新均价）
            new_avg = pos.avg_price
            new_tp = new_avg + pos.atr * self.rule_cfg['tp_sl']['tp_atr_multiplier']
            new_sl = new_avg - pos.atr * self.rule_cfg['tp_sl']['sl_atr_multiplier']
            
            # 更新所有该币种的持仓 TP/SL
            self.trade_engine.update_tp_sl(symbol, tp_price=new_tp, sl_price=new_sl)
            
            logger.info(f"✅ {symbol} Level 2 加仓完成")
            logger.info(f"   新均价={new_avg:.4f}, TP={new_tp:.4f}, SL={new_sl:.4f}")
            
        except ValueError as e:
            # 捕获 add_level2 可能抛出的验证错误
            logger.error(f"❌ {symbol} Level 2 加仓被拒绝: {e}")
        except Exception as e:
            logger.error(f"❌ {symbol} Level 2 加仓失败: {e}", exc_info=True)
