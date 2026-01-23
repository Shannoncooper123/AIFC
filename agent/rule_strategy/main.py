"""规则交易策略 - 主入口

基于回测最优参数的 BB+RSI 金字塔策略

使用方法:
    python -m agent.rule_strategy.main
"""
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import load_config
from agent.trade_simulator.engine.simulator import TradeSimulatorEngine
from agent.rule_strategy.strategy_executor import StrategyExecutor
from monitor_module.utils.logger import get_logger

logger = get_logger('rule_strategy.main')


def signal_handler(sig, frame):
    """处理退出信号"""
    logger.info("收到退出信号，正在关闭...")
    sys.exit(0)


def main():
    """主函数"""
    # 首先初始化logger
    from monitor_module.utils.logger import setup_logger
    setup_logger(name='crypto-monitor', level='INFO')
    
    logger.info("=" * 80)
    logger.info("BB+RSI 金字塔规则交易策略")
    logger.info("=" * 80)
    
    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        return
    
    # 检查是否启用
    if not config.get('rule_strategy', {}).get('enabled', False):
        logger.error("规则策略未启用！")
        logger.error("请在 config.yaml 中设置: rule_strategy.enabled = true")
        return
    
    logger.info("✅ 规则策略已启用")
    
    # 打印策略配置
    rule_cfg = config['rule_strategy']
    logger.info("")
    logger.info("策略参数:")
    logger.info(f"  入场: RSI < {rule_cfg['entry']['rsi_entry']}, Close < BB_Lower")
    logger.info(f"  加仓: RSI < {rule_cfg['entry']['rsi_addon']}, 价格下跌 {rule_cfg['pyramid']['addon_atr_drop']}×ATR")
    logger.info(f"  金字塔: {rule_cfg['pyramid']['levels']}层, 仓位分配 {rule_cfg['pyramid']['position_sizes']}")
    logger.info(f"  TP/SL: {rule_cfg['tp_sl']['tp_atr_multiplier']}×ATR / {rule_cfg['tp_sl']['sl_atr_multiplier']}×ATR")
    logger.info(f"  时间限制: {rule_cfg['time_limit']['bars']}根K线 ({rule_cfg['time_limit']['bars']*15//60}小时)")
    logger.info(f"  仓位管理: 每币种{rule_cfg['position']['max_position_pct']*100}%总资金, {rule_cfg['position']['leverage']}倍杠杆")
    logger.info("")
    
    # 初始化交易引擎
    logger.info("初始化交易模拟引擎...")
    try:
        trade_engine = TradeSimulatorEngine(config)
        trade_engine.start()
        logger.info("✅ 交易引擎启动成功")
    except Exception as e:
        logger.error(f"❌ 交易引擎启动失败: {e}", exc_info=True)
        return
    
    # 初始化策略执行器
    logger.info("初始化策略执行器...")
    try:
        executor = StrategyExecutor(trade_engine)
    except Exception as e:
        logger.error(f"❌ 策略执行器初始化失败: {e}", exc_info=True)
        trade_engine.stop()
        return
    
    # 注册退出信号
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动策略
    try:
        executor.start()
    except Exception as e:
        logger.error(f"策略执行异常: {e}", exc_info=True)
    finally:
        logger.info("正在关闭交易引擎...")
        executor.stop()
        trade_engine.stop()
        logger.info("程序已退出")


if __name__ == "__main__":
    main()
