"""工作流节点：市场上下文注入"""
import os
from typing import Any, Dict, List, Set

from langchain_core.runnables import RunnableConfig

from modules.agent.engine import get_engine
from modules.agent.state import AgentState
from modules.agent.utils.state import load_state
from modules.agent.trade_simulator.storage import load_position_history
from modules.config.settings import get_config
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import setup_logger
from modules.agent.utils.trace_decorators import traced_node

logger = setup_logger()


def _load_position_history(limit: int = 10) -> List[Dict[str, Any]]:
    try:
        cfg = get_config()
        position_history_path = cfg['agent']['position_history_path']
        if not os.path.exists(position_history_path):
            logger.warning(f"历史仓位文件不存在: {position_history_path}")
            return []
        data = load_position_history(position_history_path)
        positions = data.get('positions', [])
        sorted_positions = sorted(positions, key=lambda x: x.get('close_time', ''), reverse=True)
        return sorted_positions[:limit]
    except Exception as e:
        logger.error(f"读取历史仓位失败: {e}")
        return []


def _build_symbol_block(entry: Dict[str, Any]) -> str:
    symbol = entry.get('symbol', 'UNKNOWN')
    price = entry.get('price', 0.0)
    price_change_rate = entry.get('price_change_rate', 0.0) * 100
    triggered = entry.get('triggered_indicators', [])
    engulfing = entry.get('engulfing_type', '非外包')
    indicator_names = {
        'ATR': 'ATR波动异常','PRICE':'价格变化异常','VOLUME':'成交量异常','ENGULFING':'外包线','RSI_OVERBOUGHT':'RSI超买','RSI_OVERSOLD':'RSI超卖','RSI_ZSCORE':'RSI异常','BB_BREAKOUT_UPPER':'布林带上轨突破','BB_BREAKOUT_LOWER':'布林带下轨突破','BB_SQUEEZE_EXPAND':'布林带挤压后扩张','BB_WIDTH_ZSCORE':'布林带宽度异常','MA_BULLISH_CROSS':'均线金叉','MA_BEARISH_CROSS':'均线死叉','MA_DEVIATION_ZSCORE':'均线乖离异常','LONG_UPPER_WICK':'长上影线','LONG_LOWER_WICK':'长下影线','OI_SURGE':'持仓量激增','OI_ZSCORE':'持仓量异常','OI_BULLISH_DIVERGENCE':'持仓量看涨背离','OI_BEARISH_DIVERGENCE':'持仓量看跌背离','OI_MOMENTUM':'持仓量动量异常',
    }
    if 'ENGULFING' in triggered and engulfing != '非外包':
        triggered_display = [indicator_names.get(t, t) if t != 'ENGULFING' else engulfing for t in triggered[:6]]
    else:
        triggered_display = [indicator_names.get(t, t) for t in triggered[:6]]
    indicators_desc = ', '.join(triggered_display)
    if len(triggered) > 6:
        indicators_desc += f' 等{len(triggered)}个'
    block = (
        f"[币种] {symbol}\n"
        f"  告警信息: 价格 ${price:.6f} ({price_change_rate:+.2f}%)\n"
        f"  指标: {indicators_desc}\n"
    )
    return block


@traced_node("context_injection")
def context_injection_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    构造并注入包含市场告警、K线、账户状态等的上下文：
    - market_context: 总览文本（用于机会筛选）
    - symbol_contexts: 每个币种的上下文文本（供单币种分析使用）
    - 账户与持仓/挂单/历史等结构化字段
    - previous_run_focus: 上一轮的分析重点
    """
    configurable: Dict[str, Any] = config.get("configurable", {}) if config else {}
    latest_alert = configurable.get("latest_alert")
    if not latest_alert:
        return {"error": "context_injection_node: 未能从配置中获取 latest_alert。"}

    run_id = configurable.get("run_id")

    account_summary = get_engine().get_account_summary() if get_engine() else {}
    positions_summary = get_engine().get_positions_summary() if get_engine() else []
    pending_orders = get_engine().get_pending_orders_summary() if get_engine() else []

    ts = latest_alert.get('ts', 'UNKNOWN')
    interval = latest_alert.get('interval', '15m')
    entries = latest_alert.get('entries', [])

    overview_parts = [
        "【当前市场告警总览】",
        f"告警时间: {ts} (UTC)",
        f"告警周期: {interval}",
        f"信号币种总数: {len(entries)}个",
        "",
    ]

    # 构建每个symbol的上下文，并填入 symbol_contexts
    symbol_contexts: Dict[str, str] = {}
    for entry in entries:
        block = _build_symbol_block(entry)
        symbol = entry.get('symbol', 'UNKNOWN')
        symbol_contexts[symbol] = block
        # 在总览中只添加简要的行，避免冗长
        overview_parts.append(f"- {symbol}: 触发指标 {len(entry.get('triggered_indicators', []))} 个")
    overview_text = "\n".join(overview_parts)

    # 历史已平仓位（列表结构保存在状态）
    position_history = _load_position_history(limit=10)
    
    # 建立币种持仓映射
    symbol_positions_map: Dict[str, Dict[str, Any]] = {}
    
    for pos in positions_summary:
        symbol = pos.get('symbol', '')
        if symbol:
            symbol_positions_map[symbol] = pos
    
    cfg = get_config()
    state_path = cfg['agent']['state_path']
    previous_state = load_state(state_path)
    # 加载下一轮持仓关注重点
    position_next_focus = previous_state.get('position_next_focus', '')
    last_symbols = previous_state.get('last_symbols', [])
    previous_symbol_focus_map = previous_state.get('symbol_focus_map', {}) or {}

    # 汇总所有需要分析的币种：上一轮关注 + 本轮告警，去重保序
    all_symbols: List[str] = []
    seen = set()
    # 1) 上一轮关注币种
    for sym in last_symbols:
        if sym and sym.upper() not in seen:
            all_symbols.append(sym.upper())
            seen.add(sym.upper())
    # 2) 本轮告警币种
    for entry in entries:
        sym = entry.get('symbol')
        if sym and sym.upper() not in seen:
            all_symbols.append(sym.upper())
            seen.add(sym.upper())

    # 返回部分状态更新
    result = {
        "market_context": overview_text,
        "symbol_contexts": symbol_contexts,
        "account_summary": account_summary,
        "positions_summary": positions_summary,
        "pending_orders": pending_orders,
        "position_history": position_history,
        "symbol_positions_map": symbol_positions_map,
        "position_next_focus": position_next_focus,
        "previous_symbol_focus_map": previous_symbol_focus_map,
        "opportunities": all_symbols,  # 直接作为后续分发的币种列表
    }
    if run_id:
        result["run_id"] = run_id
    
    return result
