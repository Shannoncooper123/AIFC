"""邮件通知器"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from datetime import datetime
from ..data.models import AnomalyResult
from ..utils.helpers import format_price, format_percentage, get_anomaly_stars, get_binance_kline_url


class EmailNotifier:
    """QQ邮箱通知器"""
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        env = config['env']
        self.enabled = env.get('email_enabled', False)
        self.smtp_host = env.get('smtp_host', '')
        self.smtp_port = env.get('smtp_port', 587)
        self.smtp_user = env.get('smtp_user', '')
        self.smtp_password = env.get('smtp_password', '')
        self.smtp_use_tls = env.get('smtp_use_tls', True)
        self.alert_email = env.get('alert_email', '')
    
    def is_enabled(self) -> bool:
        """检查邮件功能是否启用
        
        Returns:
            是否启用
        """
        return self.enabled
    
    def send_test_email(self) -> bool:
        """发送测试邮件
        
        Returns:
            是否成功
        """
        if not self.enabled:
            print("邮件功能未启用（缺少SMTP配置），跳过测试邮件发送")
            return True
        
        try:
            subject = "加密货币监控系统 - 测试邮件"
            body = f"""
            <html>
            <body>
                <h2>系统测试成功</h2>
                <p>这是一封测试邮件，您的QQ邮箱配置正确。</p>
                <p>发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>系统已准备好开始监控。</p>
            </body>
            </html>
            """
            return self._send_html_email(subject, body)
        except Exception as e:
            print(f"发送测试邮件失败: {e}")
            return False
    
    def send_alert(self, alerts: List[AnomalyResult]) -> bool:
        """发送告警邮件
        
        Args:
            alerts: 告警列表
            
        Returns:
            是否成功
        """
        if not self.enabled:
            return True
        
        if not alerts:
            return False
        
        try:
            subject = f"异动告警 ({len(alerts)})"
            body = self.format_html_email(alerts)
            return self._send_html_email(subject, body)
        except Exception as e:
            print(f"发送告警邮件失败: {e}")
            return False
    
    def format_html_email(self, alerts: List[AnomalyResult]) -> str:
        """格式化HTML邮件内容
        
        Args:
            alerts: 告警列表
            
        Returns:
            HTML字符串
        """
        # 按触发指标数量和异常等级排序（优先级：触发指标数 > 异常等级）
        sorted_alerts = sorted(
            alerts,
            key=lambda x: (len(x.triggered_indicators), x.anomaly_level),
            reverse=True
        )
        
        # 生成告警列表HTML
        alert_items = []
        for idx, alert in enumerate(sorted_alerts, 1):
            stars = get_anomaly_stars(alert.anomaly_level)
            price_str = format_price(alert.price) if alert.price > 0 else "N/A"
            price_change_str = format_percentage(alert.price_change_rate)
            
            # 构建指标信息
            indicator_details = []
            for trig in alert.triggered_indicators:
                if trig == 'ATR':
                    indicator_details.append(f"ATR ZS: <b>{alert.atr_zscore:.2f}</b>")
                elif trig == 'PRICE':
                    indicator_details.append(f"价格 ZS: <b>{alert.price_change_zscore:.2f}</b>")
                elif trig == 'VOLUME':
                    indicator_details.append(f"成交量 ZS: <b>{alert.volume_zscore:.2f}</b>")
                elif trig == 'ENGULFING':
                    engulfing_icon = '📈' if '看涨' in alert.engulfing_type else '📉' if '看跌' in alert.engulfing_type else '📊'
                    indicator_details.append(f"<span style='color: #e74c3c; font-weight: bold;'>{engulfing_icon}{alert.engulfing_type}</span>")
                elif trig == 'RSI_OVERBOUGHT':
                    indicator_details.append("RSI超买")
                elif trig == 'RSI_OVERSOLD':
                    indicator_details.append("RSI超卖")
                elif trig == 'RSI_ZSCORE':
                    indicator_details.append("RSI Z-Score 异常")
                elif trig == 'BB_BREAKOUT_UPPER':
                    indicator_details.append("布林带上轨突破")
                elif trig == 'BB_BREAKOUT_LOWER':
                    indicator_details.append("布林带下轨突破")
                elif trig == 'BB_SQUEEZE_EXPAND':
                    indicator_details.append("布林带挤压后扩张")
                elif trig == 'BB_WIDTH_ZSCORE':
                    indicator_details.append("布林带带宽 Z-Score 异常")
                elif trig == 'MA_BULLISH_CROSS':
                    indicator_details.append("均线金叉")
                elif trig == 'MA_BEARISH_CROSS':
                    indicator_details.append("均线死叉")
                elif trig == 'MA_DEVIATION_ZSCORE':
                    indicator_details.append("均线乖离 Z-Score 异常")
                elif trig == 'LONG_UPPER_WICK':
                    indicator_details.append("长上影线")
                elif trig == 'LONG_LOWER_WICK':
                    indicator_details.append("长下影线")
                elif trig == 'OI_SURGE':
                    indicator_details.append("<span style='color: #e67e22; font-weight: bold;'>持仓量激增</span>")
                elif trig == 'OI_ZSCORE':
                    indicator_details.append("持仓量 Z-Score 异常")
                elif trig == 'OI_BULLISH_DIVERGENCE':
                    indicator_details.append("<span style='color: #27ae60; font-weight: bold;'>📈持仓量看涨背离</span>")
                elif trig == 'OI_BEARISH_DIVERGENCE':
                    indicator_details.append("<span style='color: #c0392b; font-weight: bold;'>📉持仓量看跌背离</span>")
                elif trig == 'OI_MOMENTUM':
                    indicator_details.append("持仓量动量异常")
            indicators_html = " | ".join(indicator_details)
            
            # 触发指标数量标签
            trigger_count = len(alert.triggered_indicators)
            priority_badge = f"""<span style="background: {'#c0392b' if trigger_count >= 4 else '#e74c3c' if trigger_count == 3 else '#f39c12'}; 
                                color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px;">
                                {trigger_count}个指标</span>"""
            
            alert_item = f"""
            <div style="border-left: 4px solid {'#c0392b' if trigger_count >= 4 else '#e74c3c' if trigger_count == 3 else '#f39c12'}; 
                        background: #fff; padding: 15px; margin: 10px 0; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: #2c3e50;">
                        {idx}. {alert.symbol} {stars}
                    </h3>
                    {priority_badge}
                </div>
                <p style="margin: 10px 0 5px 0; font-size: 16px; color: #e74c3c;">
                    <b>{price_str}</b> <span style="color: {'#27ae60' if alert.price_change_rate > 0 else '#e74c3c'};">{price_change_str}</span>
                </p>
                <p style="margin: 5px 0; font-size: 14px; color: #7f8c8d;">
                    {indicators_html}
                </p>
            </div>
            """
            alert_items.append(alert_item)
        
        alerts_html = "\n".join(alert_items)
        
        html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 700px; margin: 0 auto; background: white; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            </style>
        </head>
        <body>
            <div class="container">
                {alerts_html}
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _send_html_email(self, subject: str, html_body: str) -> bool:
        """发送HTML邮件
        
        Args:
            subject: 邮件主题
            html_body: HTML正文
            
        Returns:
            是否成功
        """
        if not self.enabled:
            return True
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.smtp_user
        msg['To'] = self.alert_email
        
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)
        
        try:
            if self.smtp_use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_user, [self.alert_email], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            raise Exception(f"SMTP发送失败: {e}")

