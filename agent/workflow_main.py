"""LangGraph 工作流主入口 - 基于告警文件监控触发"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import signal
from datetime import datetime, timezone

from config.settings import load_config, get_config
from monitor_module.utils.logger import setup_logger
from agent.utils.alert_watcher import AlertFileWatcher
from agent.builder import create_workflow
from agent.state import AgentState
from langchain_core.runnables import RunnableConfig

# 全局标志：用于优雅退出
_shutdown_requested = False

def _request_shutdown(signum, frame):
    """信号处理器：标记需要退出"""
    global _shutdown_requested
    logger = setup_logger()
    logger.info(f"收到信号 {signum}，准备优雅退出...")
    logger.info("⏳ 等待当前工作流执行完成...")
    _shutdown_requested = True

def _init_trading_engine():
    """初始化交易引擎"""
    cfg = get_config()
    logger = setup_logger()
    try:
        trading_mode = cfg.get('trading', {}).get('mode', 'simulator')
        if trading_mode == 'live':
            from agent.live_engine import BinanceLiveEngine
            from agent.engine import set_engine
            eng = BinanceLiveEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("⚠️  实盘交易引擎已启动")
            return eng
        else:
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

def _wrap_config(latest_alert: dict | None, base_cfg: dict) -> RunnableConfig:
    """统一将配置包装为 RunnableConfig，稳固类型一致性。"""
    return RunnableConfig(
        configurable={"latest_alert": latest_alert} if latest_alert else {},
        recursion_limit=100,
        tags=["workflow"],
        run_name="workflow_run",
        metadata={"env": base_cfg.get('env', {})}
    )


def main():
    """主入口：启动交易引擎、创建工作流，并监控告警文件触发分析"""
    global _shutdown_requested
    
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    
    load_config()
    cfg = get_config()
    logger = setup_logger(level=cfg['env']['log_level'])
    
    logger.info("LangGraph Agent 启动，信号处理器已注册")
    
    engine = _init_trading_engine()
    if not engine:
        logger.error("交易引擎启动失败，退出程序")
        return

    try:
        graph = create_workflow(cfg)
        app = graph.compile()
        logger.info("LangGraph 工作流创建并编译完成")
    except Exception as e:
        logger.error(f"LangGraph 工作流创建失败: {e}", exc_info=True)
        return

    # 告警文件监控器
    watcher = None
    
    try:
        # 定义告警触发回调
        def on_new_alert(alert_record: dict):
            """当检测到新告警时的回调函数"""
            if _shutdown_requested:
                logger.info("系统正在关闭，跳过本次告警处理")
                return
            
            try:
                symbols = alert_record.get('symbols', [])
                pending_count = alert_record.get('pending_count', 0)
                
                logger.info(f"=== 触发工作流分析 ({pending_count} 个币种) ===")
                logger.info(f"  币种: {', '.join(symbols[:5])}{' ...' if len(symbols) > 5 else ''}")
                
                # 执行工作流，将告警记录作为上下文传入
                app.invoke(
                    AgentState(), 
                    config=_wrap_config(alert_record, cfg)
                )
                
                logger.info("=== 工作流分析完成 ===")
            except Exception as e:
                logger.error(f"执行工作流时出错: {e}", exc_info=True)
        
        # 启动告警文件监控器
        alerts_file_path = cfg['agent']['alerts_jsonl_path']
        watcher = AlertFileWatcher(alerts_file_path, on_new_alert)
        watcher.start()
        
        logger.info("=" * 60)
        logger.info(f"✅ 告警监控已启动 | 监控文件: {alerts_file_path}")
        logger.info(f"   交易引擎: {cfg.get('trading', {}).get('mode', 'simulator')}")
        logger.info("=" * 60)
        
        # 主循环：等待中断信号
        while not _shutdown_requested:
            time.sleep(1)
        
        logger.info("检测到退出信号，准备关闭...")
    
    except KeyboardInterrupt:
        logger.info("收到键盘中断（Ctrl+C）")
    except Exception as e:
        logger.error(f"主循环异常: {e}", exc_info=True)
    finally:
        logger.info("开始优雅退出...")
        
        # 停止文件监控器
        if watcher:
            watcher.stop()
        
        # 停止交易引擎
        engine.stop()
        
        logger.info("优雅退出完成")

if __name__ == '__main__':
    main()