"""浮盈保护计算工具 - 消除position_management_node和get_positions_tool之间的重复代码"""
from typing import Any, Dict

from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.utils.profit_protection')


def fmt6(val) -> str:
    """格式化数值为6位小数
    
    Args:
        val: 要格式化的数值
    
    Returns:
        格式化后的字符串，None返回"-"
    """
    if val is None:
        return "-"
    try:
        return f"{float(val):.6f}"
    except (ValueError, TypeError):
        return "-"


def fmt2(val) -> str:
    """格式化数值为2位小数
    
    Args:
        val: 要格式化的数值
    
    Returns:
        格式化后的字符串，None返回"-"
    """
    if val is None:
        return "-"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "-"


def calculate_protection(pos: Dict[str, Any]) -> str:
    """计算浮盈保护建议
    
    根据当前持仓的浮盈R数和百分比，给出止损调整建议：
    - 浮盈 > 5%: 必须保护至少2%利润
    - 浮盈 > 2R: 必须移动SL至+1R锁定利润
    - 浮盈 > 1R: 必须移动SL至保本
    
    Args:
        pos: 持仓信息字典，需包含以下字段：
            - side: 'long' 或 'short'
            - entry_price: 入场价格
            - mark_price: 当前标记价格
            - sl_price: 当前止损价格
            - original_sl_price: 原始止损价格（可选）
    
    Returns:
        浮盈保护建议字符串
    """
    try:
        side = pos.get('side', '')
        entry_price = float(pos.get('entry_price', 0))
        mark_price = float(pos.get('mark_price', 0))
        current_sl = float(pos.get('sl_price') or 0)
        original_sl = float(pos.get('original_sl_price') or 0)
        
        if current_sl == 0:
            return "未设置止损，无法计算R数"
        
        if original_sl != 0:
            initial_r = abs(entry_price - original_sl)
        else:
            initial_r = abs(entry_price - current_sl)
        
        if initial_r == 0:
            return "SL与入场价相同，无法计算R数"
        
        if side == 'long':
            profit_r = (mark_price - entry_price) / initial_r
            profit_pct = ((mark_price - entry_price) / entry_price) * 100
        else:
            profit_r = (entry_price - mark_price) / initial_r
            profit_pct = ((entry_price - mark_price) / entry_price) * 100
        
        if profit_pct > 5.0:
            if side == 'long':
                min_protected_sl = entry_price * 1.02
                if current_sl < min_protected_sl:
                    return (f"⚠️ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R) → 必须保护至少2%利润 "
                           f"→ 建议移动SL至${min_protected_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R)，已保护至${current_sl:.2f} (≥2%保护线)"
            else:
                min_protected_sl = entry_price * 0.98
                if current_sl > min_protected_sl:
                    return (f"⚠️ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R) → 必须保护至少2%利润 "
                           f"→ 建议移动SL至${min_protected_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_pct:.2f}% ({profit_r:.2f}R)，已保护至${current_sl:.2f} (≤2%保护线)"
        
        elif profit_r > 2.0:
            if side == 'long':
                target_sl = entry_price + initial_r
                if current_sl < target_sl:
                    return (f"⚠️ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%) → 必须移动SL至+1R锁定利润 "
                           f"→ 建议SL=${target_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，已保护至${current_sl:.2f} (≥+1R)"
            else:
                target_sl = entry_price - initial_r
                if current_sl > target_sl:
                    return (f"⚠️ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%) → 必须移动SL至+1R锁定利润 "
                           f"→ 建议SL=${target_sl:.2f}")
                else:
                    return f"✓ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，已保护至${current_sl:.2f} (≤+1R)"
        
        elif profit_r > 1.0:
            if abs(current_sl - entry_price) > (entry_price * 0.0001):
                return (f"⚠️ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%) → 必须移动SL至保本 "
                       f"→ 建议SL=${entry_price:.2f}")
            else:
                return f"✓ 浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，已保本 (SL=${current_sl:.2f})"
        else:
            if profit_r >= 0:
                return f"浮盈{profit_r:.2f}R ({profit_pct:.2f}%)，未达保护阈值，继续持有"
            else:
                return f"浮亏{profit_r:.2f}R ({profit_pct:.2f}%)，需关注止损有效性"
    
    except Exception as e:
        logger.error(f"计算浮盈保护失败: {e}")
        return f"计算失败: {str(e)}"
