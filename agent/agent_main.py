"""Agent 主入口：生命周期管理和自我唤醒循环"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import signal
from datetime import datetime, timezone

from config.settings import load_config, get_config
from monitor_module.utils.logger import setup_logger
from agent.utils.state import load_state, save_state, utc_now_ms
from agent.builder import create_workflow
from agent.state import AgentState
from agent.trade_simulator.utils.file_utils import WriteQueue
from agent.utils.log_reader import read_latest_aggregate

# 全局标志：用于优雅退出
_shutdown_requested = False


def _request_shutdown(signum, frame):
    """信号处理器：标记需要退出"""
    global _shutdown_requested
    logger = setup_logger()
    logger.info(f"收到信号 {signum}，准备优雅退出...")
    logger.info("⏳ 等待当前 Agent 分析完成（如正在执行）...")
    _shutdown_requested = True


def _sleep_until(ts_ms: int):
    """睡眠直到指定时间，支持提前被信号唤醒"""
    now_ms = utc_now_ms()
    if ts_ms and ts_ms > now_ms:
        delay = (ts_ms - now_ms) / 1000.0
        # 分段睡眠，每0.5秒检查一次退出标志
        while delay > 0 and not _shutdown_requested:
            sleep_time = min(0.5, delay)
            time.sleep(sleep_time)
            delay -= sleep_time
            now_ms = utc_now_ms()
            if ts_ms <= now_ms:
                break


def _graceful_shutdown():
    """优雅退出：确保所有状态已持久化"""
    logger = setup_logger()
    logger.info("=" * 80)
    logger.info("开始优雅退出流程...")
    logger.info("=" * 80)
    
    import time
    shutdown_start = time.time()
    
    try:
        # 1. 先同步持久化当前状态（最重要，优先保证）
        logger.info("[步骤 1/3] 同步持久化最新交易状态...")
        
        # 使用统一的引擎接口
        from agent.engine import get_engine
        eng = get_engine()
        if eng:
            try:
                # 实盘引擎有 state_writer.persist_sync()
                if hasattr(eng, 'state_writer'):
                    eng.state_writer.persist_sync()
                    logger.info("✅ trade_state.json 已同步写入磁盘（实盘引擎）")
                # 模拟引擎有 state_manager.persist_sync()
                elif hasattr(eng, 'state_manager'):
                    eng.state_manager.persist_sync()
                    logger.info("✅ trade_state.json 已同步写入磁盘（模拟引擎）")
                else:
                    logger.warning("引擎无 state_writer/state_manager，跳过持久化")
            except Exception as e:
                logger.error(f"❌ 状态持久化失败: {e}", exc_info=True)
        else:
            logger.warning("交易引擎未初始化，跳过状态持久化")
        
        # 2. 停止交易引擎的WebSocket订阅
        logger.info("[步骤 2/3] 停止 WebSocket 订阅...")
        if eng:
            try:
                eng.stop()
                logger.info("✅ WebSocket 订阅已停止")
            except Exception as e:
                logger.error(f"❌ 停止 WebSocket 失败: {e}", exc_info=True)
        
        # 3. 等待写入队列清空（处理之前的历史记录等）
        logger.info("[步骤 3/3] 等待写入队列清空（最多 5 秒）...")
        try:
            write_queue = WriteQueue.get_instance()
            success = write_queue.shutdown(timeout=5.0)
            
            if success:
                logger.info("✅ 写入队列已清空，所有历史记录已持久化")
            else:
                logger.warning("⚠️ 写入队列未能在 5 秒内清空，部分历史记录可能未保存")
        except Exception as e:
            logger.error(f"❌ 写入队列关闭异常: {e}", exc_info=True)
        
        shutdown_duration = time.time() - shutdown_start
        logger.info("=" * 80)
        logger.info(f"✅ 优雅退出完成，耗时 {shutdown_duration:.1f} 秒")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"优雅退出过程中出现异常: {e}", exc_info=True)


def _init_trading_engine():
    """初始化交易引擎
    
    Returns:
        引擎实例，失败返回 None
    """
    cfg = get_config()
    logger = setup_logger()
    
    try:
        trading_mode = cfg.get('trading', {}).get('mode', 'simulator')
        
        if trading_mode == 'live':
            # 实盘模式
            from agent.live_engine import BinanceLiveEngine
            from agent.engine import set_engine
            eng = BinanceLiveEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("=" * 60)
            logger.info("⚠️  实盘交易引擎已启动")
            logger.info("=" * 60)
            return eng
        else:
            # 模拟模式
            from agent.trade_simulator.engine.simulator import TradeSimulatorEngine
            from agent.engine import set_engine
            eng = TradeSimulatorEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("交易模拟引擎已启动")
            return eng
    
    except Exception as e:
        logger.error(f"交易引擎启动失败: {e}", exc_info=True)
        return None


def main():
    """主入口：启动交易引擎和 Agent 循环"""
    global _shutdown_requested
    
    # 注册信号处理器（优雅退出）
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    
    # 加载配置
    load_config()
    cfg = get_config()
    logger = setup_logger(level=cfg['env']['log_level'])
    
    logger.info("Agent 启动，信号处理器已注册（SIGTERM, SIGINT）")
    
    # 初始化交易引擎
    engine = _init_trading_engine()
    if not engine:
        logger.error("交易引擎启动失败，退出程序")
        _graceful_shutdown()
        return
    
    # 创建并编译工作流
    try:
        workflow = create_workflow(cfg)
        app = workflow.compile()
        logger.info("LangGraph 工作流创建并编译完成")
    except Exception as e:
        logger.error(f"LangGraph 工作流创建失败: {e}", exc_info=True)
        _graceful_shutdown()
        return
    
    try:
        # 启动即分析一次
        if not _shutdown_requested:
            initial_state = AgentState()
            latest_alert = read_latest_aggregate(cfg['agent']['alerts_jsonl_path'])
            if latest_alert:
                cfg["latest_alert"] = latest_alert
                app.invoke(initial_state, config={"recursion_limit": 100})
            else:
                logger.warning("未找到最新聚合告警记录，跳过首次分析")

        # 读取下一次唤醒时间
        st = load_state(cfg['agent']['state_path'])
        # 如未设置，使用默认间隔
        if not st.get('next_wakeup_ts'):
            st['next_wakeup_ts'] = utc_now_ms() + cfg['agent']['default_interval_min'] * 60 * 1000
            save_state(cfg['agent']['state_path'], st)
        
        logger.info("进入自我唤醒循环...")
        
        while not _shutdown_requested:
            # 计算并显示下次唤醒时间
            next_ts_ms = st.get('next_wakeup_ts')
            if next_ts_ms:
                dt = datetime.fromtimestamp(next_ts_ms / 1000.0, tz=timezone.utc)
                human_time = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                now_ms = utc_now_ms()
                wait_seconds = (next_ts_ms - now_ms) / 1000.0 if next_ts_ms > now_ms else 0
                logger.info(f"等待下次唤醒: {human_time} (约 {wait_seconds:.0f} 秒后)")
            
            _sleep_until(st['next_wakeup_ts'])
            
            if _shutdown_requested:
                logger.info("检测到退出信号，中断唤醒循环")
                break
            
            logger.info("=== 唤醒触发，开始新一轮分析 ===")
            latest_alert = read_latest_aggregate(cfg['agent']['alerts_jsonl_path'])
            if latest_alert:
                cfg["latest_alert"] = latest_alert
                app.invoke(AgentState(), config={"recursion_limit": 100})
            else:
                logger.warning("未找到最新聚合告警记录，跳过本次分析")
            st = load_state(cfg['agent']['state_path'])
    
    except KeyboardInterrupt:
        logger.info("收到键盘中断（Ctrl+C）")
    except Exception as e:
        logger.error(f"主循环异常: {e}", exc_info=True)
    finally:
        # 无论如何退出，都执行优雅关闭
        _graceful_shutdown()


if __name__ == '__main__':
    main()
