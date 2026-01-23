"""发送报告邮件工具（复用系统通知器）"""
from langchain.tools import tool
from modules.monitor.alerts.notifier import EmailNotifier
from modules.config.settings import get_config


@tool("send_email", description="发送本次分析报告邮件", parse_docstring=True)
def send_email_tool(subject: str, body_html: str) -> bool | dict:
    """发送邮件通知，将分析结论以HTML格式发送到报告邮箱。
    
    当认为有必要发送邮件告知用户当前的仓位和风险以及需要用户进行复查时，调用此工具。
    仅在明确需要人工关注时调用（如 RSI 极值、ATR Z>3、布林带挤压后强突破、量能异常
    伴随趋势确认等）。发送前可先调用 write_report 写入归档，以便后续审计。
    
    Args:
        subject: 邮件主题，应简洁明确。
        body_html: 邮件HTML正文，可包含重点币种、关键指标、风险结论与下一步建议。
    
    Returns:
        True 表示发送成功，False 表示失败；或错误字典 {"error": "..."}。
    """
    def _error(msg: str) -> dict:
        return {"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}
    try:
        if not isinstance(subject, str) or not subject.strip():
            return _error("参数 subject 必须为非空字符串")
        if not isinstance(body_html, str) or not body_html.strip():
            return _error("参数 body_html 必须为非空字符串（HTML）")
        cfg = get_config()
        notifier = EmailNotifier(cfg)
        target = cfg['agent'].get('report_email') or cfg['env']['alert_email']
        if not target:
            return _error("未配置报告收件邮箱：请检查 AGENT_REPORT_EMAIL 或 ALERT_EMAIL")
        notifier.alert_email = target
        ok = notifier._send_html_email(subject, body_html)
        return bool(ok)
    except Exception as e:
        return {"error": f"TOOL_RUNTIME_ERROR: 发送邮件失败 - {str(e)}"}