from typing import Dict, Any
import os

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from modules.agent.state import AgentState
from modules.agent.tools.write_report_tool import write_report_tool
from modules.agent.utils.model_factory import get_model_factory, with_retry
from modules.agent.utils.trace_agent import create_trace_agent
from modules.agent.utils.trace_utils import traced_node
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.reporting')


@traced_node("reporting")
def reporting_node(state: AgentState, *, config: RunnableConfig):
    """
    汇总前序节点输出，使用 Reporting 子Agent 生成结构化总结，并直接调用 write_report 工具归档。
    此节点不返回任何内容。
    """
    logger.info("=" * 60)
    logger.info("报告节点执行")
    logger.info("=" * 60)
    
    try:
        market_context_str = f"市场宏观背景分析:\n{state.market_context}\n\n"
        
        pos_summary_str = "当前持仓管理总结:\n"
        if state.position_management_results:
            for symbol, result in state.position_management_results.items():
                pos_summary_str += f"- {symbol}: {result}\n"
        else:
            pos_summary_str += "无持仓或无操作。"
        pos_summary_str += "\n\n"

        analysis_results_str = "各交易对技术分析结论:\n"
        if state.analysis_results:
            for symbol, result in state.analysis_results.items():
                analysis_results_str += f"- {symbol}: {result}\n"
        else:
            analysis_results_str += "无新的技术分析结论。\n"
        analysis_results_str += "\n"

        opening_decision_str = "各交易对开仓决策结果:\n"
        if state.opening_decision_results:
            for symbol, result in state.opening_decision_results.items():
                opening_decision_str += f"- {symbol}: {result}\n"
        else:
            opening_decision_str += "无开仓决策执行。\n"

        reporting_input = (
            market_context_str
            + pos_summary_str
            + analysis_results_str
            + opening_decision_str
        )
        logger.info(f"向 Reporting Agent 提供输入:\n{reporting_input}")

        tools = [write_report_tool]

        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/reporting_prompt.md')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read().strip()

        model = get_model_factory().get_reporting_model()

        reporting_agent = create_trace_agent(
            model=model,
            tools=tools,
            system_prompt=prompt_template,
            node_name="reporting",
        )

        logger.info("开始调用 Reporting Agent...")
        subagent_messages = [HumanMessage(content=reporting_input)]
        
        @with_retry(max_retries=5, retryable_exceptions=(Exception,))
        def _invoke_with_retry():
            return reporting_agent.invoke({"messages": subagent_messages}, config=config)
        
        _invoke_with_retry()
        logger.info("Reporting Agent 调用完成，报告已在内部处理。")

    except Exception as e:
        logger.error(f"Reporting Agent 执行出错: {e}", exc_info=True)

    return {}
