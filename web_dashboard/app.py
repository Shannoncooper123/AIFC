"""监控数据推送服务：trade_state 定时推送，agent_reports/position_history 按文件变化推送"""
import os
import sys
import time
import signal
import json
import threading
from typing import Dict, Any
from dotenv import load_dotenv

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 加载 .env 文件
load_dotenv(os.path.join(BASE_DIR, '.env'))

from web_dashboard.file_watcher import FileWatcher
from web_dashboard.faas_pusher import FaaSPusher
from web_dashboard.asset_tracker import AssetTracker
from monitor_module.utils.logger import setup_logger

logger = setup_logger()

# 全局变量
file_watcher = None
faas_pusher = None
asset_tracker = None
running = True
timer_thread = None
asset_thread = None

# 监控文件路径
WATCHED_FILES = {
    'trade_state': os.path.join(BASE_DIR, 'agent', 'trade_state.json'),
    'position_history': os.path.join(BASE_DIR, 'logs', 'position_history.json'),
    'agent_reports': os.path.join(BASE_DIR, 'logs', 'agent_reports.json'),
    'pending_orders': os.path.join(BASE_DIR, 'agent', 'pending_orders.json'),
    'asset_timeline': os.path.join(BASE_DIR, 'logs', 'asset_timeline.json'),
}


def read_json_file(file_path: str) -> Dict[str, Any]:
    """读取JSON（带重试）；失败返回 None"""
    max_retries = 3
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(retry_delay * attempt)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                continue
            else:
                return None
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f'✗ 读取文件错误 {file_path}: {e}')
            return None
    
    return None


def push_data_to_faas(file_type: str, data: Dict[str, Any]):
    """推送数据到 FaaS"""
    if faas_pusher and faas_pusher.enabled and data:
        try:
            success = faas_pusher.push_data(file_type, data)
            if not success:
                logger.error(f'✗ 推送 {file_type} 到 FaaS 失败')
        except Exception as e:
            logger.error(f'✗ 推送 {file_type} 时发生错误: {e}')


def unified_push_worker():
    """每 10 秒统一推送一次所有类型数据（trade_state、position_history、agent_reports、pending_orders、asset_timeline）"""
    global running

    logger.info("⏰ 统一定时推送线程已启动（间隔: 10秒，类型: trade_state/position_history/agent_reports/pending_orders/asset_timeline）")

    data_types = ['trade_state', 'position_history', 'agent_reports', 'pending_orders', 'asset_timeline']

    while running:
        try:
            for dt in data_types:
                data = read_json_file(WATCHED_FILES[dt])
                if data:
                    push_data_to_faas(dt, data)
        except Exception as e:
            logger.error(f'✗ 统一定时推送错误: {e}')

        # 等待10秒
        for _ in range(100):  # 分成100次检查，每次0.1秒，方便快速退出
            if not running:
                break
            time.sleep(0.1)

    logger.info("⏰ 统一定时推送线程已停止")


def asset_tracking_worker():
    """每10分钟记录一次资产快照"""
    global running, asset_tracker
    
    logger.info("📊 资产打点线程已启动（间隔: 10分钟）")
    
    while running:
        try:
            # 读取 trade_state
            trade_state_data = read_json_file(WATCHED_FILES['trade_state'])
            if trade_state_data and asset_tracker:
                # 记录资产快照
                success = asset_tracker.record_snapshot(trade_state_data)
                if success:
                    # 读取并推送更新后的 asset_timeline
                    asset_timeline_data = read_json_file(WATCHED_FILES['asset_timeline'])
                    if asset_timeline_data:
                        push_data_to_faas('asset_timeline', asset_timeline_data)
        
        except Exception as e:
            logger.error(f'✗ 资产打点错误: {e}')
        
        # 等待10分钟（600秒）
        for _ in range(6000):  # 分成6000次检查，每次0.1秒，方便快速退出
            if not running:
                break
            time.sleep(0.1)
    
    logger.info("📊 资产打点线程已停止")


def handle_file_update(file_type: str, data: Dict[str, Any]):
    """文件变化时的处理：统一节拍器架构下不再立即推送，仅记录检测日志（保留扩展可能）"""
    logger.info(f'📁 检测到 {file_type} 变化（统一定时推送架构：不做立即推送）')
    # 统一架构下，推送由 unified_push_worker 每 10 秒执行一次。


def signal_handler(sig, frame):
    """优雅退出"""
    global running, timer_thread, asset_thread
    logger.info('\n\n正在关闭服务...')
    running = False
    
    # 等待定时推送线程结束
    if timer_thread and timer_thread.is_alive():
        logger.info('等待定时推送线程结束...')
        timer_thread.join(timeout=2)
    
    # 等待资产打点线程结束
    if asset_thread and asset_thread.is_alive():
        logger.info('等待资产打点线程结束...')
        asset_thread.join(timeout=2)
    
    if file_watcher:
        file_watcher.stop()
    
    logger.info('服务已关闭')
    sys.exit(0)


def start_pusher_service(faas_url: str = None):
    """启动服务"""
    global file_watcher, faas_pusher, asset_tracker, running, timer_thread, asset_thread
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 70)
    logger.info("监控数据推送服务")
    logger.info("=" * 70)
    
    # 从环境变量获取配置
    if faas_url is None:
        faas_url = os.environ.get('FAAS_URL')
        if not faas_url:
            logger.error("✗ 错误: 未设置 FAAS_URL 环境变量")
            logger.error("请在 .env 文件中设置: FAAS_URL=your_faas_url")
            sys.exit(1)
    
    # 创建文件监控器（用于 position_history、agent_reports、pending_orders、asset_timeline）
    file_watcher = FileWatcher(BASE_DIR)
    # 注：统一节拍器架构下，文件监控器可用于未来扩展，但当前不注册回调与不启动观察者，避免变化立推。

    # 创建资产打点记录器
    asset_tracker = AssetTracker(
        timeline_file=WATCHED_FILES['asset_timeline'],
        max_days=7  # 保留最近7天数据
    )

    # 创建FaaS推送器
    if faas_url:
        faas_pusher = FaaSPusher(faas_url, timeout=10, retry_times=3)
        logger.info(f"FaaS 推送已启用: {faas_url}")
        
        # 测试连接
        logger.info("\n测试 FaaS 连接...")
        if faas_pusher.test_connection():
            logger.info("✓ FaaS 连接测试成功")
            # 推送初始数据
            logger.info("\n推送初始数据到 FaaS...")
            for data_type in ['trade_state', 'position_history', 'agent_reports', 'pending_orders', 'asset_timeline']:
                data = read_json_file(WATCHED_FILES[data_type])
                if data:
                    success = faas_pusher.push_data(data_type, data)
                    if success:
                        logger.info(f"✓ 成功推送初始数据: {data_type}")
                    else:
                        logger.error(f"✗ 推送初始数据失败: {data_type}")
        else:
            logger.error("✗ FaaS 连接测试失败，推送功能将被禁用")
            faas_pusher.disable()

    # 统一节拍器架构：不注册文件变化回调、不启动文件监控器，所有类型统一走 10 秒定时推送
    # file_watcher.register_callback(handle_file_update)  # 禁用
    # file_watcher.start()  # 禁用

    # 启动统一定时推送线程（所有类型）
    if faas_pusher and faas_pusher.enabled:
        timer_thread = threading.Thread(target=unified_push_worker, daemon=True)
        timer_thread.start()

    # 启动资产打点线程（保留原有每 10 分钟快照与推送）
    asset_thread = threading.Thread(target=asset_tracking_worker, daemon=True)
    asset_thread.start()

    logger.info("=" * 70)
    logger.info("服务状态:")
    logger.info(f"  - 文件监控: ✗ 已禁用（统一定时推送架构）")
    logger.info(f"  - 定时推送: ✓ 运行中（所有类型，间隔 10秒）")
    logger.info(f"  - 资产打点: ✓ 运行中（asset_timeline，间隔 10分钟）")
    logger.info(f"  - FaaS 推送: ✓ 已启用")
    logger.info(f"  - FaaS 地址: {faas_url}")
    logger.info("=" * 70)
    logger.info("\n监控中... (按 Ctrl+C 退出)\n")

    # 保持运行
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='监控数据推送服务')
    parser.add_argument(
        '--faas-url',
        default=None,
        help='FaaS服务地址 (默认: 从环境变量FAAS_URL读取)'
    )
    
    args = parser.parse_args()
    
    start_pusher_service(faas_url=args.faas_url)
