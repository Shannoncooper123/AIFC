"""告警 API 路由"""
import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Query

from app.core.config import BASE_DIR, get_config
from app.models.schemas import AlertEntry, AlertRecord, AlertsResponse


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def load_alerts_from_jsonl(file_path: Path, limit: int = 100) -> List[AlertRecord]:
    """从 JSONL 文件加载告警记录"""
    alerts = []
    if not file_path.exists():
        return alerts
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries = [
                    AlertEntry(
                        symbol=e.get("symbol", ""),
                        price=e.get("price", 0.0),
                        price_change_rate=e.get("price_change_rate", 0.0),
                        triggered_indicators=e.get("triggered_indicators", []),
                        engulfing_type=e.get("engulfing_type"),
                        timestamp=data.get("ts"),
                    )
                    for e in data.get("entries", [])
                ]
                alerts.append(AlertRecord(
                    ts=data.get("ts", ""),
                    interval=data.get("interval", ""),
                    entries=entries,
                ))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    
    return alerts


@router.get("", response_model=AlertsResponse)
async def get_alerts(
    limit: int = Query(default=50, ge=1, le=500, description="返回的告警数量"),
    symbol: Optional[str] = Query(default=None, description="按币种过滤"),
):
    """获取告警历史"""
    agent_config = get_config("agent")
    alerts_path = BASE_DIR / agent_config.get("alerts_jsonl_path", "modules/data/alerts.jsonl")
    
    alerts = load_alerts_from_jsonl(alerts_path, limit=limit * 2)
    
    if symbol:
        symbol = symbol.upper()
        filtered_alerts = []
        for alert in alerts:
            filtered_entries = [e for e in alert.entries if e.symbol.upper() == symbol]
            if filtered_entries:
                filtered_alerts.append(AlertRecord(
                    ts=alert.ts,
                    interval=alert.interval,
                    entries=filtered_entries,
                ))
        alerts = filtered_alerts
    
    alerts = alerts[:limit]
    
    return AlertsResponse(alerts=alerts, total=len(alerts))


@router.get("/latest", response_model=AlertRecord)
async def get_latest_alert():
    """获取最新告警"""
    agent_config = get_config("agent")
    alerts_path = BASE_DIR / agent_config.get("alerts_jsonl_path", "modules/data/alerts.jsonl")
    
    alerts = load_alerts_from_jsonl(alerts_path, limit=1)
    
    if not alerts:
        return AlertRecord(ts="", interval="", entries=[])
    
    return alerts[0]


@router.get("/symbols")
async def get_alert_symbols():
    """获取所有出现过告警的币种列表"""
    agent_config = get_config("agent")
    alerts_path = BASE_DIR / agent_config.get("alerts_jsonl_path", "modules/data/alerts.jsonl")
    
    alerts = load_alerts_from_jsonl(alerts_path, limit=500)
    
    symbols = set()
    for alert in alerts:
        for entry in alert.entries:
            symbols.add(entry.symbol)
    
    return {"symbols": sorted(list(symbols)), "total": len(symbols)}
