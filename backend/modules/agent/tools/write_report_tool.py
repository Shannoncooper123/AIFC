"""写入本次分析结论工具"""
from langchain.tools import tool
from modules.agent.utils.state import load_state, save_state, utc_now_ms
from modules.config.settings import get_config
import json
import os
from datetime import datetime, timezone


@tool("write_report", description="归档本次分析结论；包含每个币种的下一轮分析重点映射以及下一轮持仓管理关注点",
      parse_docstring=True)
def write_report_tool(summary: str, symbol_focus_map: dict, position_next_focus: str) -> str | dict:
    """归档本次分析的结论。
    
    Args:
        summary: 分析概览，包含本轮分析的总结与核心决策与理由的简洁文本。
        symbol_focus_map: 每个币种的下一轮分析重点映射（字典：symbol → 关注点/计划/触发条件）。
        position_next_focus: 下一轮持仓管理的关注重点摘要文本（多行或单行，简洁可审计）。
    
    Returns:
        成功时返回字符串 "report_written:<path>"；失败时返回错误字典 {"error": "..."}。
    """
    def _error(msg: str) -> dict:
        return {"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}
    try:
        if not isinstance(summary, str) or not summary.strip():
            return _error("参数 summary 必须为非空字符串")
        # 结构校验：symbol_focus_map 必须是 {symbol(str): focus(str)} 的字典
        if not isinstance(symbol_focus_map, dict):
            return _error("参数 symbol_focus_map 必须是 {symbol(str): focus(str)} 的字典")
        # 每个 key/value 为非空字符串
        for k, v in symbol_focus_map.items():
            if not isinstance(k, str) or not k.strip():
                return _error("symbol_focus_map 的键必须为非空字符串（symbol）")
            if not isinstance(v, str) or not v.strip():
                return _error(f"symbol_focus_map['{k}'] 的值必须为非空字符串（分析重点）")
        # position_next_focus 必须为非空字符串
        if not isinstance(position_next_focus, str) or not position_next_focus.strip():
            return _error("参数 position_next_focus 必须为非空字符串，请简要概括下一轮持仓管理关注点")
        cfg = get_config()
        # 更新state
        state_path = cfg['agent']['state_path']
        st = load_state(state_path)
        st['last_run_ts'] = utc_now_ms()
        st['last_summary'] = summary
        st['symbol_focus_map'] = symbol_focus_map
        st['position_next_focus'] = position_next_focus
        save_state(state_path, st)
        
        # 归档报告（JSON文件追加结构）
        reports_path = cfg['agent']['reports_json_path']
        os.makedirs(os.path.dirname(reports_path), exist_ok=True)
        # 读取已有JSON（如不存在则初始化）
        report_data = {}
        if os.path.exists(reports_path):
            try:
                with open(reports_path, 'r', encoding='utf-8') as rf:
                    report_data = json.load(rf) or {}
            except Exception:
                report_data = {}
        if 'reports' not in report_data:
            report_data['reports'] = []
        
        # 构造报告记录
        report_record = {
            'ts': st['last_run_ts'],
            'ts_readable': datetime.fromtimestamp(st['last_run_ts'] / 1000.0, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'summary': summary,
            'symbol_focus_map': symbol_focus_map,
            'position_next_focus': position_next_focus,
        }
        
        report_data['reports'].append(report_record)
        with open(reports_path, 'w', encoding='utf-8') as wf:
            json.dump(report_data, wf, ensure_ascii=False, indent=2)
        return f"report_written:{reports_path}"
    except Exception as e:
        return {"error": f"TOOL_RUNTIME_ERROR: 写入报告失败 - {str(e)}"}