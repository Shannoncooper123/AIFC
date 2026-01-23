"""查询持仓并获取K线数据工具"""
from langchain.tools import tool
from typing import List, Dict, Any

from modules.agent.engine import get_engine
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.get_positions')


@tool("get_positions", description="查询所有持仓币种及其浮盈保护建议，以及待成交限价单", parse_docstring=True)
def get_positions_tool() -> str | Dict[str, str]:
    """查询所有持仓币种及其浮盈保护建议，以及待成交限价单。
    
    获取每个持仓的详细信息（方向、数量、均价、TP/SL、当前价、盈亏、ROE），
    以及根据强制保护规则自动计算的保护建议。
    同时返回所有待成交的限价单信息。
    
    强制保护规则（自动计算）：
    - 浮盈 > 2R: 必须移动SL至入场价+1R，锁定利润
    - 浮盈 > 1R: 必须移动SL至入场价（保本）
    - 浮盈 > 5%: 必须保护至少2%利润
    
    无需传入任何参数，自动获取所有持仓、挂单并分析保护需求。
    
    Returns:
        成功时返回格式化的持仓和挂单信息字符串（包含每个持仓的基本信息、保护建议，以及所有待成交限价单），
        无持仓且无挂单时返回包含 "message" 键的字典。
    """
    try:
        eng = get_engine()
        if eng is None:
            return {"error": "TOOL_RUNTIME_ERROR: 交易引擎未初始化"}
        
        positions = eng.get_positions_summary()
        pending_orders = eng.get_pending_orders_summary()
        
        # 无持仓且无挂单时直接返回
        if not positions and not pending_orders:
            logger.info("get_positions: 当前无持仓且无挂单")
            return {"message": "当前无持仓且无挂单"}
        
        logger.info(f"get_positions: 获取到 {len(positions)} 个持仓")
        
        # 构造完整的持仓信息字符串
        result_parts = []
        result_parts.append(f"【当前持仓概况】共 {len(positions)} 个持仓\n")
        
        for idx, pos in enumerate(positions, 1):
            symbol = pos.get('symbol', 'UNKNOWN')
            side = pos.get('side', 'UNKNOWN')
            qty = pos.get('qty', 0.0)
            entry_price = pos.get('entry_price', 0.0)
            tp_price = pos.get('tp_price', 0.0)
            sl_price = pos.get('sl_price', 0.0)
            mark_price = pos.get('mark_price', 0.0)
            unrealized_pnl = pos.get('unrealized_pnl', 0.0)
            roe = pos.get('roe', 0.0)
            
            # 计算浮盈保护建议
            protection_info = _calculate_protection(pos)
            
            # 格式化持仓信息
            position_block = [
                f"[持仓 #{idx}] {symbol} ({'多头' if side == 'long' else '空头'}持仓)",
                f"  持仓信息:",
                f"    数量: {fmt6(qty)}, 均价: ${fmt6(entry_price)}",
                f"    止盈: ${fmt6(tp_price)}, 止损: ${fmt6(sl_price)}",
                f"    当前价: ${fmt6(mark_price)}",
                f"    未实现盈亏: ${fmt2(unrealized_pnl)}, ROE: {fmt2(roe)}%",
            ]
            
            # 添加保护建议
            if protection_info:
                position_block.append(f"  浮盈保护分析:")
                position_block.append(f"    {protection_info}")
            else:
                position_block.append(f"  浮盈保护分析: 无SL或计算失败")
            
            position_block.append("")  # 空行分隔
            result_parts.append("\n".join(position_block))
        
        # 添加待成交限价单信息
        if pending_orders:
            result_parts.append(f"【待成交限价单】共 {len(pending_orders)} 个挂单\n")
            
            for idx, order in enumerate(pending_orders, 1):
                symbol = order.get('symbol', 'UNKNOWN')
                side = order.get('side', 'UNKNOWN')
                limit_price = order.get('limit_price', 0.0)
                margin_usdt = order.get('margin_usdt', 0.0)
                leverage = order.get('leverage', 10)
                tp_price = order.get('tp_price')
                sl_price = order.get('sl_price')
                
                order_block = [
                    f"[挂单 #{idx}] {symbol} ({'多头' if side == 'long' else '空头'}限价单)",
                    f"  挂单信息:",
                    f"    限价: ${fmt6(limit_price)}",
                    f"    保证金: ${fmt2(margin_usdt)} (杠杆{leverage}x)",
                    f"    止盈: ${fmt6(tp_price) if tp_price else '未设置'}, 止损: ${fmt6(sl_price) if sl_price else '未设置'}",
                    ""
                ]
                result_parts.append("\n".join(order_block))
        
        result = "\n".join(result_parts)
        
        # 打印返回给模型的完整内容
        logger.info(f"get_positions: 成功返回 {len(positions)} 个持仓和 {len(pending_orders)} 个挂单及其数据")
        logger.info("=" * 80)
        logger.info("【get_positions 返回给模型的完整内容】")
        logger.info("=" * 80)
        logger.info(result)
        logger.info("=" * 80)
        
        return result
        
    except Exception as e:
        logger.error(f"get_positions 执行失败: {e}")
        return {"error": f"TOOL_RUNTIME_ERROR: 查询持仓失败 - {str(e)}"}

# 安全格式化函数已移动到模块内，供工具使用
# 安全格式化函数，避免 None 参与数值格式化导致报错
def fmt6(val):
    try:
        return "-" if val is None else f"{float(val):.6f}"
    except Exception:
        return "-"

def fmt2(val):
    try:
        return "-" if val is None else f"{float(val):.2f}"
    except Exception:
        return "-"


def _calculate_protection(pos: Dict[str, Any]) -> str:
    """计算浮盈保护建议
    
    Args:
        pos: 持仓信息字典
        
    Returns:
        保护建议字符串，如果无需保护或计算失败则返回相应说明
    """
    try:
        side = pos.get('side', '')
        entry_price = float(pos.get('entry_price', 0))
        mark_price = float(pos.get('mark_price', 0))
        current_sl = float(pos.get('sl_price') or 0)
        original_sl = float(pos.get('original_sl_price') or 0)
        
        if current_sl == 0:
            return "未设置止损，无法计算R数"
        
        # 使用original_sl_price计算初始R（开仓时的风险），如果没有则使用当前SL
        if original_sl != 0:
            initial_r = abs(entry_price - original_sl)
        else:
            initial_r = abs(entry_price - current_sl)
        
        if initial_r == 0:
            return "SL与入场价相同，无法计算R数"
        
        # 计算浮盈R数和百分比
        if side == 'long':
            profit_r = (mark_price - entry_price) / initial_r
            profit_pct = ((mark_price - entry_price) / entry_price) * 100
        else:  # short
            profit_r = (entry_price - mark_price) / initial_r
            profit_pct = ((entry_price - mark_price) / entry_price) * 100
        
        # 判断保护需求（优先级：5% → 2R → 1R）
        
        # 规则3: 浮盈>5% → 保护至少2%
        if profit_pct > 5.0:
            if side == 'long':
                min_protected_sl = entry_price * 1.02  # 保护2%利润
                if current_sl < min_protected_sl:
                    return (f"⚠️ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R) → 必须保护至少2%利润 "
                           f"→ 建议移动SL至${min_protected_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R)，已保护至${current_sl:.2f} (≥2%保护线)"
            else:  # short
                min_protected_sl = entry_price * 0.98  # 保护2%利润
                if current_sl > min_protected_sl:
                    return (f"⚠️ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R) → 必须保护至少2%利润 "
                           f"→ 建议移动SL至${min_protected_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R)，已保护至${current_sl:.2f} (≤2%保护线)"
        
        # 规则2: 浮盈>2R → 移动至+1R
        elif profit_r > 2.0:
            if side == 'long':
                target_sl = entry_price + initial_r  # +1R
                if current_sl < target_sl:
                    return (f"⚠️ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%) → 必须移动SL至+1R锁定利润 "
                           f"→ 建议SL=${target_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，已保护至${current_sl:.2f} (≥+1R)"
            else:  # short
                target_sl = entry_price - initial_r  # +1R
                if current_sl > target_sl:
                    return (f"⚠️ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%) → 必须移动SL至+1R锁定利润 "
                           f"→ 建议SL=${target_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，已保护至${current_sl:.2f} (≤+1R)"
        
        # 规则1: 浮盈>1R → 移动至保本
        elif profit_r > 1.0:
            if abs(current_sl - entry_price) > (entry_price * 0.0001):  # 允许0.01%误差
                return (f"⚠️ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%) → 必须移动SL至保本 "
                       f"→ 建议SL=${entry_price:.2f}")
            else:
                return f"✓ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，已保本 (SL=${current_sl:.2f})"
        else:
            # 浮盈不足或负浮盈
            if profit_r >= 0:
                return f"浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，未达保护阈值，继续持有"
            else:
                return f"浮亏{profit_r:.2f}R ({profit_pct:.2f}%)，需关注止损有效性"
    
    except Exception as e:
        logger.error(f"计算浮盈保护失败: {e}")
        return f"计算失败: {str(e)}"
