"""LangGraph 工作流主入口 - 基于告警文件监控触发"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

import time
import signal
from datetime import datetime, timezone

from modules.config.settings import load_config, get_config
from modules.monitor.utils.logger import setup_logger
from modules.agent.utils.alert_watcher import AlertFileWatcher
from modules.agent.builder import create_workflow
from modules.agent.state import AgentState
from langchain_core.runnables import RunnableConfig
from modules.agent.utils.workflow_trace_storage import (
    generate_trace_id,
    record_workflow_start,
    record_workflow_end,
)
from modules.agent.utils.trace_utils import workflow_trace_context

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
            from modules.agent.live_engine import BinanceLiveEngine
            from modules.agent.engine import set_engine
            eng = BinanceLiveEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("⚠️  实盘交易引擎已启动")
            return eng
        else:
            from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
            from modules.agent.engine import set_engine
            eng = TradeSimulatorEngine(cfg)
            set_engine(eng)
            eng.start()
            logger.info("交易模拟引擎已启动")
            return eng
    except Exception as e:
        logger.error(f"交易引擎启动失败: {e}", exc_info=True)
        return None


def _check_reverse_mode():
    """检查反向交易模式状态
    
    反向交易功能已集成到 live_engine 中，通过配置控制。
    """
    logger = setup_logger()
    try:
        from modules.agent.live_engine.config import get_trading_config_manager
        config_mgr = get_trading_config_manager()
        
        if config_mgr.reverse_enabled:
            logger.info("=" * 40)
            logger.info("🔄 反向交易模式已启用")
            logger.info(f"   保证金: {config_mgr.fixed_margin_usdt}U")
            logger.info(f"   杠杆: {config_mgr.fixed_leverage}x")
            logger.info("=" * 40)
            return True
        return False
    except Exception as e:
        logger.error(f"检查反向交易模式失败: {e}", exc_info=True)
        return False

def _wrap_config(latest_alert: dict | None, base_cfg: dict, workflow_run_id: str) -> RunnableConfig:
    """
    统一将配置包装为 RunnableConfig。
    
    trace context 字段：
    - workflow_run_id: 顶层 workflow 的 run ID
    - current_trace_id: 当前层级的 trace ID（初始等于 workflow_run_id）
    """
    configurable = {
        "workflow_run_id": workflow_run_id,
        "current_trace_id": workflow_run_id,
    }
    if latest_alert:
        configurable["latest_alert"] = latest_alert
    
    return RunnableConfig(
        configurable=configurable,
        recursion_limit=100,
        tags=["workflow"],
        run_name="workflow_run",
        metadata={"env": base_cfg.get('env', {}), "workflow_run_id": workflow_run_id}
    )


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


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

    reverse_enabled = _check_reverse_mode()

    try:
        graph = create_workflow(cfg)
        app = graph.compile()
        logger.info("LangGraph 工作流创建并编译完成")
    except Exception as e:
        logger.error(f"LangGraph 工作流创建失败: {e}", exc_info=True)
        return

    watcher = None
    
    try:
        def on_new_alert(alert_record: dict):
            """当检测到新告警时的回调函数"""
            if _shutdown_requested:
                logger.info("系统正在关闭，跳过本次告警处理")
                return

            workflow_run_id = None
            start_time = None
            try:
                workflow_run_id = generate_trace_id("wf")
                start_time = _now_iso()
                
                record_workflow_start(workflow_run_id, alert_record, cfg)
                
                symbols = alert_record.get('symbols', [])
                pending_count = alert_record.get('pending_count', 0)
                
                logger.info(f"=== 触发工作流分析 ({pending_count} 个币种) ===")
                logger.info(f"  币种: {', '.join(symbols[:5])}{' ...' if len(symbols) > 5 else ''}")
                
                with workflow_trace_context(workflow_run_id):
                    app.invoke(
                        AgentState(), 
                        config=_wrap_config(alert_record, cfg, workflow_run_id)
                    )
                
                logger.info("=== 工作流分析完成 ===")
                record_workflow_end(workflow_run_id, start_time, "success", cfg=cfg)
            except Exception as e:
                logger.error(f"执行工作流时出错: {e}", exc_info=True)
                if workflow_run_id and start_time:
                    record_workflow_end(workflow_run_id, start_time, "error", error=str(e), cfg=cfg)
        
        alerts_file_path = cfg['agent']['alerts_jsonl_path']
        watcher = AlertFileWatcher(alerts_file_path, on_new_alert)
        watcher.start()
        
        logger.info("=" * 60)
        logger.info(f"✅ 告警监控已启动 | 监控文件: {alerts_file_path}")
        logger.info(f"   交易引擎: {cfg.get('trading', {}).get('mode', 'simulator')}")
        if reverse_enabled:
            logger.info("   反向交易: 已启用")
        logger.info("=" * 60)
        
        while not _shutdown_requested:
            time.sleep(1)
        
        logger.info("检测到退出信号，准备关闭...")
    
    except KeyboardInterrupt:
        logger.info("收到键盘中断（Ctrl+C）")
    except Exception as e:
        logger.error(f"主循环异常: {e}", exc_info=True)
    finally:
        logger.info("开始优雅退出...")
        
        if watcher:
            watcher.stop()
        
        engine.stop()
        
        logger.info("优雅退出完成")

def run_workflow_service(is_stop_requested, add_log):
    """作为服务线程运行的入口"""
    load_config()
    cfg = get_config()
    logger = setup_logger(level=cfg['env']['log_level'])
    
    add_log("初始化交易引擎...")
    engine = _init_trading_engine()
    if not engine:
        raise RuntimeError("交易引擎启动失败")
    add_log(f"交易引擎已启动: {cfg.get('trading', {}).get('mode', 'simulator')}")

    reverse_enabled = _check_reverse_mode()
    if reverse_enabled:
        add_log("反向交易模式已启用")

    try:
        graph = create_workflow(cfg)
        app = graph.compile()
        add_log("LangGraph 工作流创建并编译完成")
    except Exception as e:
        logger.error(f"LangGraph 工作流创建失败: {e}", exc_info=True)
        raise

    watcher = None
    
    try:
        def on_new_alert(alert_record: dict):
            if is_stop_requested():
                add_log("系统正在关闭，跳过本次告警处理")
                return

            workflow_run_id = None
            start_time = None
            try:
                workflow_run_id = generate_trace_id("wf")
                start_time = _now_iso()
                
                record_workflow_start(workflow_run_id, alert_record, cfg)
                
                symbols = alert_record.get('symbols', [])
                pending_count = alert_record.get('pending_count', 0)
                
                add_log(f"触发工作流分析 ({pending_count} 个币种): {', '.join(symbols[:5])}")
                
                with workflow_trace_context(workflow_run_id):
                    app.invoke(
                        AgentState(), 
                        config=_wrap_config(alert_record, cfg, workflow_run_id)
                    )
                
                add_log("工作流分析完成")
                record_workflow_end(workflow_run_id, start_time, "success", cfg=cfg)
            except Exception as e:
                logger.error(f"执行工作流时出错: {e}", exc_info=True)
                add_log(f"工作流执行失败: {e}")
                if workflow_run_id and start_time:
                    record_workflow_end(workflow_run_id, start_time, "error", error=str(e), cfg=cfg)
        
        alerts_file_path = cfg['agent']['alerts_jsonl_path']
        watcher = AlertFileWatcher(alerts_file_path, on_new_alert)
        watcher.start()
        
        add_log(f"告警监控已启动 | 监控文件: {alerts_file_path}")
        
        while not is_stop_requested():
            time.sleep(1)
        
        add_log("收到停止信号，正在关闭...")
    
    except Exception as e:
        logger.error(f"Workflow 服务异常: {e}", exc_info=True)
        raise
    finally:
        if watcher:
            watcher.stop()
        engine.stop()
        add_log("Workflow 服务已停止")


if __name__ == '__main__':
    main()
