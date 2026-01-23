"""统一配置加载器"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class KlineConfig(BaseModel):
    """K线配置"""
    interval: str = "15m"
    history_size: int = 100
    warmup_size: int = 150


class IndicatorsConfig(BaseModel):
    """技术指标配置"""
    atr_period: int = 14
    stddev_period: int = 20
    volume_ma_period: int = 20
    bb_period: int = 20
    bb_std_multiplier: float = 2.0
    rsi_period: int = 14
    ema_fast_period: int = 12
    ema_slow_period: int = 26


class ThresholdsConfig(BaseModel):
    """异常检测阈值配置"""
    atr_zscore: float = 2.5
    price_change_zscore: float = 2.5
    volume_zscore: float = 3.0
    min_indicators_triggered: int = 3
    rsi_overbought: int = 70
    rsi_oversold: int = 30


class AlertConfig(BaseModel):
    """告警配置"""
    cooldown_minutes: int = 0
    send_delay_seconds: int = 3
    max_batch_size: int = 10
    send_email: bool = False


class WebSocketConfig(BaseModel):
    """WebSocket配置"""
    base_url: str = "wss://fstream.binance.com"
    max_streams_per_connection: int = 1024
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 10
    ping_interval: int = 180


class APIConfig(BaseModel):
    """REST API配置"""
    base_url: str = "https://fapi.binance.com"
    timeout: int = 10
    retry_times: int = 3


class TradingConfig(BaseModel):
    """交易配置"""
    mode: str = "simulator"
    max_leverage: int = 10
    history_sync_days: int = 0


class AgentConfig(BaseModel):
    """Agent配置"""
    default_interval_min: int = 30
    alerts_jsonl_path: str = "modules/data/alerts.jsonl"
    reports_json_path: str = "modules/data/agent_reports.json"
    position_history_path: str = "modules/data/position_history.json"
    state_path: str = "modules/data/state.json"
    trade_state_path: str = "modules/data/trade_state.json"
    workflow_trace_path: str = "modules/data/workflow_trace.jsonl"
    workflow_artifacts_dir: str = "modules/data/artifacts"


class Settings(BaseSettings):
    """应用设置"""
    app_name: str = "Crypto Monitor"
    debug: bool = False
    
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    
    agent_model: Optional[str] = None
    agent_api_key: Optional[str] = None
    agent_base_url: Optional[str] = None
    
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    alert_email: Optional[str] = None
    log_level: Optional[str] = None
    faas_url: Optional[str] = None
    logprobs_enabled: Optional[bool] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


_config_cache: Optional[Dict[str, Any]] = None
_settings_cache: Optional[Settings] = None


def load_yaml_config() -> Dict[str, Any]:
    """加载YAML配置文件"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    
    return _config_cache


def get_settings() -> Settings:
    """获取应用设置"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


def get_config(section: Optional[str] = None) -> Any:
    """获取配置
    
    Args:
        section: 配置节名称，如 'kline', 'indicators' 等。为 None 时返回全部配置。
    
    Returns:
        配置字典或指定节的配置
    """
    config = load_yaml_config()
    if section is None:
        return config
    return config.get(section, {})


def get_kline_config() -> KlineConfig:
    """获取K线配置"""
    return KlineConfig(**get_config("kline"))


def get_indicators_config() -> IndicatorsConfig:
    """获取指标配置"""
    return IndicatorsConfig(**get_config("indicators"))


def get_thresholds_config() -> ThresholdsConfig:
    """获取阈值配置"""
    return ThresholdsConfig(**get_config("thresholds"))


def get_alert_config() -> AlertConfig:
    """获取告警配置"""
    return AlertConfig(**get_config("alert"))


def get_websocket_config() -> WebSocketConfig:
    """获取WebSocket配置"""
    return WebSocketConfig(**get_config("websocket"))


def get_api_config() -> APIConfig:
    """获取API配置"""
    return APIConfig(**get_config("api"))


def get_trading_config() -> TradingConfig:
    """获取交易配置"""
    return TradingConfig(**get_config("trading"))


def get_agent_config() -> AgentConfig:
    """获取Agent配置"""
    return AgentConfig(**get_config("agent"))
