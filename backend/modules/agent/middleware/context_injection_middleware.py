"""上下文注入Middleware：在agent开始前构造包含K线数据的详细上下文"""
from typing import Any, List, Dict
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
import os

from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.config.settings import get_config
from modules.monitor.utils.logger import setup_logger
from datetime import datetime, timezone
from modules.agent.engine import get_engine
from modules.agent.utils.state import load_state
from modules.agent.trade_simulator.storage import load_position_history


logger = setup_logger()


class ContextInjectionMiddleware(AgentMiddleware):
    """
    在agent执行前注入包含详细上下文的消息。
    
    功能：
    - 读取告警数据（币种、触发指标、价格等）
    - 为所有信号币种获取K线数据（按信号强度排序）
    - 构造包含完整信息的context消息
    - 注入到conversation开始，避免agent需要迭代调用工具
    
    优势：
    - 减少agent的工具调用次数
    - 提供更完整的初始上下文
    - 加快决策速度
    """
    
    def __init__(
        self,
        latest_alert: Dict[str, Any],
        kline_limit: int = 15,
    ):
        """
        初始化上下文注入中间件。
        
        Args:
            latest_alert: 最新的告警数据（原始数据，包含 ts, interval, entries）
            kline_limit: 每个币种获取的K线根数，默认15
        """
        super().__init__()
        self.latest_alert = latest_alert
        self.kline_limit = kline_limit
    
    def _get_klines_for_symbol(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        """
        获取指定币种的K线数据。
        
        复用 get_kline_tool 的底层逻辑。
        
        Args:
            symbol: 交易对（如 BTCUSDT）
            interval: K线间隔（如 15m）
            limit: K线根数
        
        Returns:
            K线数据列表，每个元素包含 time, open, high, low, close, volume
        """
        try:
            cfg = get_config()
            client = BinanceRestClient(cfg)
            raw = client.get_klines(symbol, interval, limit)
            if not raw:
                logger.warning(f"未获取到 {symbol} 的K线数据")
                return []
            
            klines = []
            for item in raw:
                k = Kline.from_rest_api(item)
                dt = datetime.fromtimestamp(k.timestamp / 1000.0, tz=timezone.utc)
                klines.append({
                    "time": dt.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                })
            return klines
        except Exception as e:
            logger.error(f"获取 {symbol} K线失败: {e}")
            return []
    
    
    
    def _load_position_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        加载最近的历史仓位记录。
        
        Args:
            limit: 返回的仓位数量，默认10个
        
        Returns:
            最近的历史仓位列表
        """
        try:
            cfg = get_config()
            position_history_path = cfg['agent']['position_history_path']
            
            if not os.path.exists(position_history_path):
                logger.warning(f"历史仓位文件不存在: {position_history_path}")
                return []
            data = load_position_history(position_history_path)
            positions = data.get('positions', [])
            
            # 按 close_time 倒序排序，获取最近的 limit 个
            sorted_positions = sorted(
                positions,
                key=lambda x: x.get('close_time', ''),
                reverse=True
            )
            
            return sorted_positions[:limit]
        
        except Exception as e:
            logger.error(f"读取历史仓位失败: {e}")
            return []
    
    def _format_kline_data_inline(self, symbol: str, klines: List[Dict[str, Any]]) -> str:
        """
        格式化K线数据为内联可读文本（用于结构化输出）。
        
        Args:
            symbol: 币种名称
            klines: K线数据列表
        
        Returns:
            格式化的K线文本
        """
        if not klines:
            return f"  K线数据: (无数据)\n"
        
        lines = [f"  K线数据({len(klines)}根):"]
        for i, k in enumerate(klines, start=1):
            lines.append(
                f"    [{i:2d}] {k['time']}: "
                f"O={k['open']:.6f} H={k['high']:.6f} L={k['low']:.6f} C={k['close']:.6f} V={k['volume']:.2f}"
            )
        
        return "\n".join(lines)
    
    def _build_context_message(self) -> str:
        """
        构造完整的上下文消息。
        
        自包含地处理所有数据准备工作：
        1. 获取账户和持仓摘要
        2. 处理和排序告警数据
        3. 获取K线数据
        4. 构造结构化上下文
        
        Returns:
            包含告警信息、K线数据、账户信息的完整上下文
        """
        # 1. 获取账户、持仓和挂单摘要
        account_summary = get_engine().get_account_summary() if get_engine() else {}
        positions_summary = get_engine().get_positions_summary() if get_engine() else []
        pending_orders = get_engine().get_pending_orders_summary() if get_engine() else []
        
        # 2. 处理告警数据
        ts = self.latest_alert.get('ts', 'UNKNOWN')
        interval = self.latest_alert.get('interval', '15m')
        entries = self.latest_alert.get('entries', [])
        
        # 按信号强度排序
        def get_sort_key(entry):
            triggered_count = len(entry.get('triggered_indicators', []))
            # 信号强度越大越优先(所以用负值)
            return -triggered_count
        
        sorted_entries = sorted(entries, key=get_sort_key)
        
        # 指标名称映射
        indicator_names = {
            'ATR': 'ATR波动异常',
            'PRICE': '价格变化异常',
            'VOLUME': '成交量异常',
            'ENGULFING': '外包线',
            'RSI_OVERBOUGHT': 'RSI超买',
            'RSI_OVERSOLD': 'RSI超卖',
            'RSI_ZSCORE': 'RSI异常',
            'BB_BREAKOUT_UPPER': '布林带上轨突破',
            'BB_BREAKOUT_LOWER': '布林带下轨突破',
            'BB_SQUEEZE_EXPAND': '布林带挤压后扩张',
            'BB_WIDTH_ZSCORE': '布林带宽度异常',
            'MA_BULLISH_CROSS': '均线金叉',
            'MA_BEARISH_CROSS': '均线死叉',
            'MA_DEVIATION_ZSCORE': '均线乖离异常',
            'LONG_UPPER_WICK': '长上影线',
            'LONG_LOWER_WICK': '长下影线',
            'OI_SURGE': '持仓量激增',
            'OI_ZSCORE': '持仓量异常',
            'OI_BULLISH_DIVERGENCE': '持仓量看涨背离',
            'OI_BEARISH_DIVERGENCE': '持仓量看跌背离',
            'OI_MOMENTUM': '持仓量动量异常',
        }
        
        # 获取所有信号币种的K线数据并构造结构化信息
        logger.info(
            f"开始获取 {len(sorted_entries)} 个信号币种的 {interval} K线数据（已按信号强度排序）"
        )
        
        structured_symbols = []
        for idx, entry in enumerate(sorted_entries, 1):
            symbol = entry.get('symbol', 'UNKNOWN')
            anomaly_level = entry.get('anomaly_level', 0)
            price = entry.get('price', 0.0)
            price_change_rate = entry.get('price_change_rate', 0.0) * 100
            triggered = entry.get('triggered_indicators', [])
            engulfing = entry.get('engulfing_type', '非外包')
            
            # 格式化指标描述
            if 'ENGULFING' in triggered and engulfing != '非外包':
                # 替换 ENGULFING 为具体的外包类型
                triggered_display = [indicator_names.get(t, t) if t != 'ENGULFING' else engulfing for t in triggered[:6]]
            else:
                triggered_display = [indicator_names.get(t, t) for t in triggered[:6]]
            
            indicators_desc = ', '.join(triggered_display)
            if len(triggered) > 6:
                indicators_desc += f' 等{len(triggered)}个'
            
            # 获取该币种的K线数据
            klines = self._get_klines_for_symbol(symbol, interval, self.kline_limit)
            kline_text = self._format_kline_data_inline(symbol, klines)
            
            # 构造该币种的完整信息块
            symbol_block = (
                f"[币种 #{idx}] {symbol} (信号强度: {len(triggered)}个指标)\n"
                f"  告警信息:\n"
                f"    价格: ${price:.6f} ({price_change_rate:+.2f}%)\n"
                f"    触发指标({len(triggered)}个): {indicators_desc}\n"
                f"{kline_text}\n"
            )
            structured_symbols.append(symbol_block)
        
        # 拼接完整上下文
        context_parts = [
            "【当前市场告警与持仓状态】",
            f"告警时间: {ts} (UTC)",
            f"告警周期: {interval}",
            f"信号币种总数: {len(sorted_entries)}个",
            "",
            f"信号币种详情（按信号强度排序，每个币种{self.kline_limit}根K线）",
            "",
        ]
        
        context_parts.extend(structured_symbols)
        
        # 格式化账户信息，突出显示保证金利用率
        margin_usage = account_summary.get('margin_usage_rate', 0.0)
        balance = account_summary.get('balance', 0.0)
        equity = account_summary.get('equity', 0.0)
        reserved_margin = account_summary.get('reserved_margin_sum', 0.0)
        unrealized_pnl = account_summary.get('unrealized_pnl', 0.0)
        positions_count = account_summary.get('positions_count', 0)
        available_margin = balance - reserved_margin  # 计算剩余可用保证金
        
        # 根据保证金利用率给出状态提示
        if margin_usage < 50:
            usage_status = "【资金利用率较低】"
        elif margin_usage <= 80:
            usage_status = "【资金利用率正常】"
        else:
            usage_status = "【资金利用率过高】"
        
        context_parts.extend([
            "【账户状态】",
            f"  余额: ${balance:.2f}",
            f"  权益: ${equity:.2f}",
            f"  未实现盈亏: ${unrealized_pnl:.2f}",
            f"  已用保证金: ${reserved_margin:.2f}",
            f"  剩余可用保证金: ${available_margin:.2f}",
            f"  保证金利用率: {margin_usage:.2f}% {usage_status}",
            f"  持仓数量: {positions_count}个",
            "",
        ])
        
        # 添加详细持仓和挂单信息
        if positions_summary and len(positions_summary) > 0:
            # 统计多空仓位
            long_count = sum(1 for p in positions_summary if p.get('side') == 'long')
            short_count = sum(1 for p in positions_summary if p.get('side') == 'short')
            
            context_parts.extend([
                "【当前持仓与挂单详情】",
                f"  多头仓位: {long_count}个 | 空头仓位: {short_count}个",
                "",
            ])
            
            for idx, pos in enumerate(positions_summary, 1):
                symbol = pos.get('symbol', 'UNKNOWN')
                side = pos.get('side', 'unknown')
                side_cn = "做多" if side == 'long' else "做空"
                
                # 计算仓位大小（notional_usdt）
                qty = pos.get('qty', 0.0)
                mark_price = pos.get('mark_price', 0.0)
                notional_usdt = qty * mark_price
                
                entry_price = pos.get('entry_price', 0.0)
                leverage = pos.get('leverage', 1)
                tp_price = pos.get('tp_price')
                sl_price = pos.get('sl_price')
                unrealized_pnl_pos = pos.get('unrealized_pnl', 0.0)
                roe = pos.get('roe', 0.0)
                
                # 格式化止盈止损
                tp_str = f"${tp_price:.6f}" if tp_price else "未设置"
                sl_str = f"${sl_price:.6f}" if sl_price else "未设置"
                
                # 盈亏状态标识
                pnl_status = "✓ 盈利" if unrealized_pnl_pos > 0 else "✗ 亏损" if unrealized_pnl_pos < 0 else "持平"
                
                context_parts.append(
                    f"  [{idx}] {symbol} ({side_cn})\n"
                    f"      仓位: ${notional_usdt:.2f} (数量: {qty:.6f}, 杠杆: {leverage}x)\n"
                    f"      入场价: ${entry_price:.6f} | 标记价: ${mark_price:.6f}\n"
                    f"      止盈: {tp_str} | 止损: {sl_str}\n"
                    f"      盈亏: ${unrealized_pnl_pos:.2f} (收益率: {roe:.2f}%) {pnl_status}"
                )
            
            context_parts.append("")
        else:
            context_parts.extend([
                "【当前持仓与挂单详情】",
                "  无持仓",
                "",
            ])
        
        # 添加待成交挂单信息
        if pending_orders:
            context_parts.extend([
                "【待成交挂单】",
                f"  共 {len(pending_orders)} 个挂单",
                "",
            ])
            
            for idx, order in enumerate(pending_orders, 1):
                symbol = order.get('symbol', 'UNKNOWN')
                side = order.get('side', 'unknown')
                side_cn = "做多" if side == 'long' else "做空"
                limit_price = order.get('limit_price', 0.0)
                margin_usdt = order.get('margin_usdt', 0.0)
                leverage = order.get('leverage', 10)
                tp_price = order.get('tp_price')
                sl_price = order.get('sl_price')
                create_time = order.get('create_time', '')
                
                # 格式化止盈止损
                tp_str = f"${tp_price:.6f}" if tp_price else "未设置"
                sl_str = f"${sl_price:.6f}" if sl_price else "未设置"
                
                # 格式化创建时间
                try:
                    create_dt = datetime.fromisoformat(create_time.replace('Z', '+00:00'))
                    create_time_str = create_dt.strftime('%m-%d %H:%M')
                except:
                    create_time_str = create_time[:16] if create_time else 'N/A'
                
                context_parts.append(
                    f"  [{idx}] {symbol} {side_cn}挂单 @ ${limit_price:.6f}\n"
                    f"      保证金: ${margin_usdt:.2f} (杠杆{leverage}x)\n"
                    f"      止盈: {tp_str} | 止损: {sl_str}\n"
                    f"      创建时间: {create_time_str}"
                )
            
            context_parts.append("")
        
        # 添加最近的历史仓位信息
        position_history = self._load_position_history(limit=10)
        if position_history:
            context_parts.extend([
                "【最近10个已平仓位】",
                "",
            ])
            
            # 统计盈亏情况
            win_count = sum(1 for p in position_history if p.get('realized_pnl', 0) > 0)
            loss_count = sum(1 for p in position_history if p.get('realized_pnl', 0) < 0)
            total_pnl = sum(p.get('realized_pnl', 0) for p in position_history)
            
            context_parts.append(
                f"  统计：{win_count}盈/{loss_count}亏，累计盈亏: ${total_pnl:.2f}"
            )
            context_parts.append("")
            
            for idx, pos in enumerate(position_history, 1):
                symbol = pos.get('symbol', 'UNKNOWN')
                side = pos.get('side', 'unknown')
                side_cn = "做多" if side == 'long' else "做空"
                notional_usdt = pos.get('notional_usdt', 0.0)
                realized_pnl = pos.get('realized_pnl', 0.0)
                close_reason = pos.get('close_reason', '未知')
                close_time = pos.get('close_time', '')
                
                # 格式化平仓时间（只显示日期和时间，去掉时区）
                try:
                    close_dt = datetime.fromisoformat(close_time.replace('Z', '+00:00'))
                    close_time_str = close_dt.strftime('%m-%d %H:%M')
                except:
                    close_time_str = close_time[:16] if close_time else 'N/A'
                
                # 盈亏状态
                pnl_status = "✓" if realized_pnl > 0 else "✗"
                
                context_parts.append(
                    f"  [{idx}] {symbol} ({side_cn}) 仓位${notional_usdt:.0f} | "
                    f"盈亏: ${realized_pnl:.2f} {pnl_status} | {close_reason} ({close_time_str})"
                )
            
            context_parts.append("")
        
        # 添加上次分析的下次关注重点
        try:
            cfg = get_config()
            state = load_state(cfg['agent']['state_path'])
            next_focus = state.get('next_focus', '')
            if next_focus:
                context_parts.extend([
                    "【上次分析的本轮需要重点关注的事情】",
                    f"  {next_focus}",
                    "",
                ])
        except Exception as e:
            logger.warning(f"读取 next_focus 失败: {e}")
        
        return "\n".join(context_parts)
    
    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """
        在agent开始执行前注入完整的初始消息（上下文 + 触发消息）。
        
        根据 factory.py line 1190-1203 的实现，before_agent hook 只在 agent 启动时
        执行一次（entry_node runs once at start），agent 的循环从 loop_entry_node 
        开始（excludes before_agent），因此不需要额外的标志位来防止重复执行。
        
        消息注入顺序：
        1. 上下文消息（告警信息、K线数据、账户状态）
        2. 触发消息（指示agent开始分析）
        
        Args:
            state: Agent状态，包含messages等字段
            runtime: 运行时上下文
        
        Returns:
            包含要注入的消息的字典，会被框架merge到state中
        """
        logger.info("ContextInjectionMiddleware: 开始构造并注入完整初始消息")
        
        # 构造上下文消息
        context_text = self._build_context_message()
        
        # 输出构造的上下文内容到日志
        logger.info("构造的上下文内容:")
        logger.info(context_text)
        
        # 创建消息列表：先上下文，后触发
        messages = [
            HumanMessage(content=context_text),
            HumanMessage(content="请基于以上信息开始分析当前市场状况并做出交易决策。")
        ]
        
        # 返回要注入的消息列表
        return {"messages": messages}
    
    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """
        异步版本的before_agent hook。
        
        由于当前实现不涉及异步I/O，直接调用同步版本。
        """
        return self.before_agent(state, runtime)
