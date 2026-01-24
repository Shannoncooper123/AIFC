"""加密货币异动监控系统 - 主程序"""
import signal
import sys
import time
import os
import json
from typing import Dict, List
from datetime import datetime, timezone

from modules.config.settings import load_config
from modules.monitor.utils.logger import setup_logger, get_logger
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.clients.binance_ws import MultiConnectionManager
from modules.monitor.core.exchange_manager import ExchangeManager
from modules.monitor.core.initializer import SystemInitializer
from modules.monitor.core.symbol_updater import SymbolUpdater
from modules.monitor.data.kline_manager import KlineManager
from modules.monitor.data.models import Kline, AnomalyResult
from modules.monitor.indicators.calculator import IndicatorCalculator
from modules.monitor.detection.detector import AnomalyDetector
from modules.monitor.alerts.manager import AlertManager
from modules.monitor.alerts.notifier import EmailNotifier
from modules.monitor.alerts.callbacks import create_send_alerts_callback

logger = None
ws_manager = None
symbol_updater = None


def signal_handler(sig, frame):
    """信号处理器（优雅关闭）"""
    logger.info("\n接收到中断信号，正在关闭系统...")
    
    if symbol_updater:
        symbol_updater.stop()
    
    if ws_manager:
        ws_manager.close_all()
    
    logger.info("系统已关闭")
    sys.exit(0)


def initialize_system(config: Dict):
    """初始化系统"""
    logger.info("=" * 60)
    logger.info("加密货币异动监控系统启动")
    logger.info("=" * 60)
    
    # 1. REST客户端
    logger.info("1. 初始化币安REST API...")
    rest_client = BinanceRestClient(config)
    logger.info("   ✓ API连接成功")
    
    # 2. K线管理器
    logger.info("2. 初始化K线管理器...")
    kline_manager = KlineManager(history_size=config['kline']['history_size'])
    logger.info(f"   ✓ 保留{config['kline']['history_size']}根K线")
    
    # 3. 获取交易对
    logger.info("3. 获取交易对列表...")
    exchange_manager = ExchangeManager(rest_client, config)
    symbols = exchange_manager.get_tradable_symbols()
    logger.info(f"   ✓ {len(symbols)}个USDT永续合约")
    
    # 4. 加载历史数据
    logger.info("4. 加载历史K线数据...")
    initializer = SystemInitializer(rest_client, kline_manager, config)
    initializer.initialize_historical_data(symbols)
    logger.info(f"   ✓ 历史数据就绪")
    
    # 5. 指标计算器
    logger.info("5. 初始化指标计算器...")
    indicator_calculator = IndicatorCalculator(kline_manager, config, rest_client)
    logger.info(f"   ✓ ATR={config['indicators']['atr_period']}, "
                f"StdDev={config['indicators']['stddev_period']}, "
                f"OI={'启用' if config.get('open_interest', {}).get('enabled') else '禁用'}")
    
    # 6. 异常检测器
    logger.info("6. 初始化异常检测器...")
    detector = AnomalyDetector(config)
    logger.info(f"   ✓ 阈值 ATR={config['thresholds']['atr_zscore']}, "
                f"Price={config['thresholds']['price_change_zscore']}, "
                f"Volume={config['thresholds']['volume_zscore']}")
    
    # 7. 邮件通知器
    logger.info("7. 初始化QQ邮箱...")
    notifier = EmailNotifier(config)
    notifier.send_test_email()
    logger.info(f"   ✓ {config['env']['smtp_user']}")
    
    # 8. 告警管理器
    logger.info("8. 初始化告警管理器...")
    alert_manager = AlertManager(config)
    
    # 8.1 设置聚合告警回调（解耦）
    alert_manager.set_send_callback(create_send_alerts_callback(notifier, config))
    logger.info(f"   ✓ 防抖={config['alert'].get('debounce_seconds', 10)}秒")
    
    return {
        'rest_client': rest_client,
        'kline_manager': kline_manager,
        'symbols': symbols,
        'initializer': initializer,
        'indicator_calculator': indicator_calculator,
        'detector': detector,
        'alert_manager': alert_manager,
        'notifier': notifier,
    }


def process_kline(symbol: str, kline_data: Dict, components: Dict):
    """处理K线数据"""
    # 1. 更新K线
    kline = Kline.from_dict(kline_data)
    components['kline_manager'].update(symbol, kline)
    
    # 2. 实时K线处理（未收盘）
    if not kline.is_closed:
        # 更新实时最低价
        components['kline_manager'].update_realtime_low(symbol, kline.low)
        return  # 未收盘K线不进行后续处理
    
    # 3. K线收盘：清除实时最低价
    components['kline_manager'].clear_realtime_low(symbol)
    
    # 4. 计算指标
    indicators = components['indicator_calculator'].calculate_all(symbol)
    if not indicators:
        return
    
    # 5. 异常检测
    anomaly = components['detector'].detect(indicators)
    if not anomaly:
        return
    
    anomaly.price = kline.close
    
    # 6. 冷却检查
    if not components['alert_manager'].should_alert(symbol):
        return
    
    # 7. 加入队列（防抖机制会在10秒内无新告警后自动触发发送）
    components['alert_manager'].add_alert(anomaly)
    
    # 记录日志
    stars = '⭐' * anomaly.anomaly_level
    engulfing_tag = f" [{anomaly.engulfing_type}]" if anomaly.engulfing_type != '非外包' else ""
    
    # 动态格式化价格
    if kline.close >= 1:
        price_str = f"${kline.close:,.4f}"
    else:
        price_str = f"${kline.close:.8f}"
    
    logger.warning(f"异常 {stars} {symbol} {price_str} ({anomaly.price_change_rate*100:+.2f}%){engulfing_tag} "
                   f"ATR={anomaly.atr_zscore:.1f} Price={anomaly.price_change_zscore:.1f} "
                   f"Vol={anomaly.volume_zscore:.1f} [{', '.join(anomaly.triggered_indicators)}]")
    logger.info(f"  → 队列: {components['alert_manager'].get_pending_count()}个")


def main():
    """主函数"""
    global logger, ws_manager, symbol_updater
    
    try:
        # 加载配置
        config = load_config()
        
        # 设置日志
        logger = setup_logger(level=config['env']['log_level'])
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 初始化系统
        components = initialize_system(config)
        
        # 创建WebSocket回调函数
        def on_kline_callback(symbol: str, kline_data: Dict):
            process_kline(symbol, kline_data, components)
        
        # 9. 建立WebSocket
        logger.info("9. 建立WebSocket...")
        ws_manager = MultiConnectionManager(config, on_kline_callback)
        ws_manager.connect_all(components['symbols'], config['kline']['interval'])
        time.sleep(2)
        logger.info("   ✓ 连接成功")
        
        # 10. 启动动态更新器
        logger.info("10. 启动动态更新器...")
        
        def on_symbols_changed(added: List[str], removed: List[str]):
            ws_manager.update_symbols(added, removed)
            if added:
                components['initializer'].initialize_historical_data(added)
        
        symbol_updater = SymbolUpdater(
            components['rest_client'], config, on_symbols_changed
        )
        symbol_updater.start(components['symbols'])
        logger.info("   ✓ 更新器就绪")
        
        # 11. 开始监控
        logger.info("=" * 60)
        logger.info(f"✅ 监控启动 | {len(components['symbols'])}个交易对 | "
                    f"{config['kline']['interval']}间隔 | {config['env']['alert_email']}")
        logger.info("=" * 60)
        
        # 保持运行
        while True:
            time.sleep(600)  # 每10分钟输出状态
            logger.info(f"运行中: {symbol_updater.get_symbol_count()}个交易对")
    
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"系统错误: {e}", exc_info=True)
    finally:
        if 'components' in locals():
            components['alert_manager'].stop()
            pending = components['alert_manager'].force_send_pending()
            if pending:
                components['notifier'].send_alert(pending)
        
        if symbol_updater:
            symbol_updater.stop()
        if ws_manager:
            ws_manager.close_all()


def run_monitor_service(is_stop_requested, add_log):
    """作为服务线程运行的入口"""
    global logger, ws_manager, symbol_updater
    
    try:
        config = load_config()
        logger = setup_logger(level=config['env']['log_level'])
        
        components = initialize_system(config)
        
        def on_kline_callback(symbol: str, kline_data: Dict):
            process_kline(symbol, kline_data, components)
        
        add_log("建立 WebSocket 连接...")
        ws_manager = MultiConnectionManager(config, on_kline_callback)
        ws_manager.connect_all(components['symbols'], config['kline']['interval'])
        time.sleep(2)
        add_log("WebSocket 连接成功")
        
        add_log("启动动态更新器...")
        
        def on_symbols_changed(added: List[str], removed: List[str]):
            ws_manager.update_symbols(added, removed)
            if added:
                components['initializer'].initialize_historical_data(added)
        
        symbol_updater = SymbolUpdater(
            components['rest_client'], config, on_symbols_changed
        )
        symbol_updater.start(components['symbols'])
        add_log("动态更新器就绪")
        
        add_log(f"监控启动 | {len(components['symbols'])}个交易对 | {config['kline']['interval']}间隔")
        
        while not is_stop_requested():
            time.sleep(1)
        
        add_log("收到停止信号，正在关闭...")
    
    except Exception as e:
        if logger:
            logger.error(f"Monitor 服务异常: {e}", exc_info=True)
        else:
            print(f"Monitor 服务异常 (logger未初始化): {e}")
        raise
    finally:
        if 'components' in locals():
            components['alert_manager'].stop()
            pending = components['alert_manager'].force_send_pending()
            if pending:
                components['notifier'].send_alert(pending)
        
        if symbol_updater:
            symbol_updater.stop()
        if ws_manager:
            ws_manager.close_all()
        
        add_log("Monitor 服务已停止")


if __name__ == '__main__':
    main()
