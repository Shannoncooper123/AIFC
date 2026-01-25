"""工作流节点：开仓决策"""
import json
import os
from typing import Any, Dict, List

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from modules.agent.middleware.vision_middleware import VisionMiddleware
from modules.agent.middleware.workflow_trace_middleware import WorkflowTraceMiddleware
from modules.agent.state import SymbolAnalysisState
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.tools.open_position_tool import open_position_tool
from modules.agent.tools.tool_utils import get_binance_client
from modules.agent.utils.trace_decorators import traced_node
from modules.agent.utils.workflow_trace_storage import get_current_run_id, save_image_artifact
from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.opening_decision')

REVIEW_INTERVALS = ["1d", "4h", "1h", "15m"]


def _format_account_summary(account: Dict[str, Any]) -> str:
    """格式化账户摘要"""
    if not account:
        return "账户信息不可用"

    balance = account.get('balance', 0)
    equity = account.get('equity', 0)
    margin_usage = account.get('margin_usage_rate', 0)
    positions_count = account.get('positions_count', 0)

    return (
        f"余额: ${balance:.2f} | 净值: ${equity:.2f} | "
        f"保证金利用率: {margin_usage:.1f}% | 持仓数: {positions_count}"
    )


def _generate_kline_images(symbol: str, intervals: List[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """生成多周期K线图像用于复核，并保存 artifacts
    
    Returns:
        (images, image_metas): images 用于构建消息，image_metas 用于 trace 匹配
    """
    from modules.agent.tools.get_kline_image_tool import _plot_candlestick_chart
    
    images = []
    image_metas = []
    client = get_binance_client()
    run_id = get_current_run_id()
    
    for interval in intervals:
        try:
            fetch_limit = 300
            display_limit = 200
            raw = client.get_klines(symbol, interval, fetch_limit)
            
            if not raw:
                logger.warning(f"未获取到 {symbol} {interval} K线数据")
                continue
                
            klines = [Kline.from_rest_api(item) for item in raw]
            image_base64 = _plot_candlestick_chart(klines, symbol, interval, display_limit)
            
            images.append({
                "interval": interval,
                "image_base64": image_base64,
            })
            
            if run_id:
                save_image_artifact(run_id, symbol, interval, image_base64)
            image_metas.append({"symbol": symbol, "interval": interval})
            
            logger.info(f"生成 {symbol} {interval} 复核图像成功")
            
        except Exception as e:
            logger.error(f"生成 {symbol} {interval} 图像失败: {e}")
            continue
    
    return images, image_metas


def _build_multimodal_content(symbol: str, account_info: str, analysis_result: str, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """构建多模态消息内容"""
    content = []
    
    text_part = f"""【待决策币种】{symbol}

【账户状态】
{account_info}

【前序分析结论】
{analysis_result}

【多周期K线图像】
以下是 {symbol} 的 1d/4h/1h/15m 四个周期的K线图，请对比前序分析结论进行复核：
"""
    content.append({"type": "text", "text": text_part})
    
    for img_data in images:
        interval = img_data["interval"]
        content.append({"type": "text", "text": f"\n--- {interval} 周期 ---"})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img_data['image_base64']}",
                "detail": "high"
            }
        })
    
    content.append({
        "type": "text", 
        "text": "\n请基于以上图像复核前序分析结论，审视并决定是否执行开仓操作。"
    })
    
    return content


@traced_node("opening_decision")
def opening_decision_node(state: SymbolAnalysisState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    审视前序分析节点的结论，决定是否执行开仓操作。
    
    输入：
    - state.current_symbol: 当前分析的币种
    - state.analysis_results[symbol]: 前序节点的分析结论
    - state.account_summary: 账户状态
        
    输出：
    - {"opening_decision_results": {symbol: decision_output}}
    """
    symbol = state.current_symbol
    if not symbol:
        return {"error": "opening_decision_node: 缺少 current_symbol，跳过决策。"}

    logger.info("=" * 60)
    logger.info(f"开仓决策节点执行: {symbol}")
    logger.info("=" * 60)

    analysis_result = state.analysis_results.get(symbol)
    if not analysis_result:
        logger.error(f"{symbol} 开仓决策失败: 缺少前序分析结论")
        return {"opening_decision_results": {symbol: "决策失败: 缺少前序分析结论"}}

    try:
        tools = [
            calc_metrics_tool,
            open_position_tool,
        ]

        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/opening_decision_prompt.md')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()

        logger.info(f"开始为 {symbol} 生成复核图像...")
        images, image_metas = _generate_kline_images(symbol, REVIEW_INTERVALS)
        
        trace_middleware = WorkflowTraceMiddleware("opening_decision")
        if image_metas:
            trace_middleware.set_image_metas(image_metas)
        
        middlewares = [
            VisionMiddleware(),
            trace_middleware,
        ]

        model = ChatOpenAI(
            model=os.getenv('AGENT_MODEL'),
            api_key=os.getenv('AGENT_API_KEY'),
            base_url=os.getenv('AGENT_BASE_URL') or None,
            temperature=0.1,
            timeout=300,
            max_tokens=8000,
        )

        subagent = create_agent(
            model=model,
            tools=tools,
            system_prompt=prompt,
            debug=False,
            middleware=middlewares,
        )
        
        if not images:
            logger.warning(f"{symbol} 无法生成复核图像，使用纯文本模式")
            account_info = _format_account_summary(state.account_summary)
            combined_message = f"""【待决策币种】{symbol}

【账户状态】
{account_info}

【前序分析结论】
{analysis_result}

请基于以上分析结论，审视并决定是否执行开仓操作。"""
            subagent_messages = [HumanMessage(content=combined_message)]
        else:
            logger.info(f"{symbol} 生成 {len(images)} 个周期的复核图像")
            account_info = _format_account_summary(state.account_summary)
            multimodal_content = _build_multimodal_content(symbol, account_info, analysis_result, images)
            subagent_messages = [HumanMessage(content=multimodal_content)]

        logger.info(f"开始为 {symbol} 执行开仓决策...")
        result = subagent.invoke(
            {"messages": subagent_messages},
            config=config,
        )

        decision_output = result["messages"][-1].content if isinstance(result, dict) else str(result)

        logger.info("=" * 60)
        logger.info(f"{symbol} 开仓决策完成 (返回长度: {len(decision_output)})")
        logger.info("=" * 60)

        return {"opening_decision_results": {symbol: decision_output}}

    except Exception as e:
        logger.error(f"{symbol} 开仓决策执行失败: {e}", exc_info=True)
        return {"opening_decision_results": {symbol: f"决策执行失败: {str(e)}"}}
