"""告警发送回调封装：解耦聚合告警写入与邮件发送"""
import os
import json
from datetime import datetime, timezone
from typing import List, Dict

from .notifier import EmailNotifier
from ..data.models import AnomalyResult
from ..utils.logger import get_logger

logger = get_logger('alerts')


def create_send_alerts_callback(notifier: EmailNotifier, config: Dict):
    """创建聚合告警发送回调
    负责：
    - 调用邮件发送
    - 将聚合告警以结构化JSON写入JSONL供旁路Agent读取
    """
    def _callback(alerts: List[AnomalyResult]):
        # 检查邮件功能是否启用（环境变量配置）
        email_env_enabled = config.get('env', {}).get('email_enabled', False)
        # 检查是否启用告警邮件发送（config.yaml配置）
        send_email_enabled = email_env_enabled and config.get('alert', {}).get('send_email', True)
        
        email_status = '启用' if send_email_enabled else ('禁用(缺少SMTP配置)' if not email_env_enabled else '禁用(config.yaml)')
        logger.info(f"📧 聚合告警 ({len(alerts)}个币种) [邮件发送: {email_status}]")
        
        # 使用普通监控的告警路径（规则策略使用独立的实时告警）
        agent_cfg = config.get('agent', {})
        jsonl_path = agent_cfg.get('alerts_jsonl_path', 'modules/data/alerts.jsonl')
        
        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        now_utc = datetime.now(timezone.utc)
        
        if not alerts:
            # 无告警也记录到JSONL
            try:
                record = {
                    'type': 'aggregate',
                    'ts': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'interval': config['kline']['interval'],
                    'symbols': [],
                    'entries': [],
                    'email_subject': '异动告警 (0)',
                    'email_excerpt': '本次周期检查无币种触发阈值报警',
                    'alert_window_start': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'alert_window_end': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'pending_count': 0,
                    'source': 'monitor',
                }
                with open(jsonl_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
                logger.info(f"  ✓ 无告警记录已写入JSONL: {jsonl_path}")
            except Exception as w_err:
                logger.error(f"写入alerts.jsonl失败(无告警): {w_err}")
            return
        
        # 根据配置决定是否发送邮件
        email_sent = False
        if send_email_enabled:
            email_sent = notifier.send_alert(alerts)
            if email_sent:
                logger.info("  ✓ 邮件已发送")
            else:
                logger.error("  ✗ 邮件发送失败")
        else:
            logger.info("  ⊘ 邮件发送已禁用（仅写入JSONL）")
            email_sent = True  # 标记为成功，继续写入JSONL
        
        if email_sent:
            # 写入JSONL（有告警）
            try:
                # 生成主题与简要摘要
                email_subject = f"异动告警 ({len(alerts)})"
                top_symbols = [a.symbol for a in alerts[:5]]
                email_excerpt = f"本次聚合包含 {len(alerts)} 个币种：{', '.join(top_symbols)}"
                # 计算窗口时间（按告警时间戳）
                ts_list = [a.timestamp for a in alerts if a.timestamp]
                window_start = min(ts_list) if ts_list else int(now_utc.timestamp() * 1000)
                window_end = max(ts_list) if ts_list else int(now_utc.timestamp() * 1000)
                # 构建entries
                entries = []
                for a in alerts:
                    reasons = []
                    for t in a.triggered_indicators:
                        if t == 'ATR':
                            reasons.append('ATR波动超阈值')
                        elif t == 'PRICE':
                            reasons.append('价格变化超阈值')
                        elif t == 'VOLUME':
                            reasons.append('成交量异常')
                        elif t == 'ENGULFING':
                            reasons.append(f'{a.engulfing_type}')
                        elif t == 'OI_SURGE':
                            reasons.append('持仓量激增')
                        elif t == 'OI_ZSCORE':
                            reasons.append('持仓量Z-Score异常')
                        elif t == 'OI_BULLISH_DIVERGENCE':
                            reasons.append('持仓量看涨背离')
                        elif t == 'OI_BEARISH_DIVERGENCE':
                            reasons.append('持仓量看跌背离')
                        elif t == 'OI_MOMENTUM':
                            reasons.append('持仓量动量异常')
                    entries.append({
                        'symbol': a.symbol,
                        'price': a.price,
                        'price_change_rate': a.price_change_rate,
                        'atr_zscore': a.atr_zscore,
                        'price_change_zscore': a.price_change_zscore,
                        'volume_zscore': a.volume_zscore,
                        'engulfing_type': a.engulfing_type,
                        'triggered_indicators': a.triggered_indicators,
                        'anomaly_level': a.anomaly_level,
                        'reasons': reasons,
                    })
                record = {
                    'type': 'aggregate',
                    'ts': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'interval': config['kline']['interval'],
                    'symbols': [a.symbol for a in alerts],
                    'entries': entries,
                    'email_subject': email_subject,
                    'email_excerpt': email_excerpt,
                    'alert_window_start': datetime.fromtimestamp(window_start/1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'alert_window_end': datetime.fromtimestamp(window_end/1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'pending_count': len(alerts),
                    'source': 'monitor',
                }
                with open(jsonl_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
                logger.info(f"  ✓ 已写入JSONL: {jsonl_path}")
            except Exception as w_err:
                logger.error(f"写入alerts.jsonl失败: {w_err}")
    
    return _callback