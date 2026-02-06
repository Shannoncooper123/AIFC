"""工作流节点：开仓决策"""
import os
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from modules.agent.state import SymbolAnalysisState
from modules.agent.tools.create_limit_order_tool import create_limit_order_tool
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.utils.kline_utils import fetch_klines, get_current_price, format_price
from modules.agent.utils.model_factory import get_model_factory, with_retry
from modules.agent.utils.trace_utils import create_trace_agent, traced_node
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.opening_decision')

REVIEW_INTERVALS = ["1h", "15m", "3m"]

HARDCODED_ACCOUNT_SUMMARY_STR = (
    "余额: $10000.00 | 净值: $10000.00 | "
    "保证金利用率: 0.0% | 持仓数: 0"
)

HARDCODED_MAX_MARGIN = 500.0


def _format_account_summary(account: Dict[str, Any]) -> str:
    """格式化账户摘要，始终返回硬编码的账户状态"""
    return HARDCODED_ACCOUNT_SUMMARY_STR


def _get_max_margin_for_new_position() -> float:
    """获取当前可用于新开仓的最大保证金
    
    返回硬编码值，实际金额由引擎层根据配置决定
    
    Returns:
        硬编码的最大可用保证金金额（USDT）
    """
    return HARDCODED_MAX_MARGIN


def _generate_kline_images(symbol: str, intervals: List[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """获取多周期K线图像用于复核
    
    注意：不再在此处保存 artifact，而是通过 HumanMessage.additional_kwargs 传递元数据，
    由 workflow_trace_middleware 统一处理图像保存，实现 trace 层与业务层解耦。
    
    Returns:
        (images, image_metas): images 用于构建消息，image_metas 用于 trace 匹配
    """
    from modules.agent.tools.chart_renderer_pillow import render_kline_chart_pillow
    
    images = []
    image_metas = []
    
    logger.info(f"为 {symbol} 生成 {len(intervals)} 个周期的复核图像: {intervals}")
    
    for interval in intervals:
        try:
            fetch_limit = 300
            display_limit = 200
            
            logger.info(f"{symbol} {interval} 获取K线用于复核图像")
            
            klines, error = fetch_klines(symbol, interval, fetch_limit)
            
            if error or not klines:
                logger.warning(f"未获取到 {symbol} {interval} K线数据: {error}")
                continue
            
            image_base64 = render_kline_chart_pillow(klines, symbol, interval, display_limit)
            
            images.append({
                "interval": interval,
                "image_base64": image_base64,
            })
            image_metas.append({"symbol": symbol, "interval": interval})
            
            logger.info(f"生成 {symbol} {interval} 复核图像成功")
            
        except Exception as e:
            logger.error(f"生成 {symbol} {interval} 图像失败: {e}")
            continue
    
    return images, image_metas


def _build_multimodal_content(symbol: str, account_info: str, analysis_result: str, images: List[Dict[str, Any]], max_margin: float, current_price: float | None) -> List[Dict[str, Any]]:
    """构建多模态消息内容"""
    content = []
    
    margin_info = f"本次开仓可用最大保证金: ${max_margin:.2f} USDT" if max_margin > 0 else "保证金信息不可用"
    price_str = f"${format_price(current_price)}" if current_price else "获取失败"
    
    text_part = f"""【待决策币种】{symbol}
【当前价格】{price_str}

【账户状态】
{account_info}
{margin_info}

【前序分析结论】
{analysis_result}

【多周期K线图像】
以下是 {symbol} 的 1h/15m/3m 三个周期的K线图，请对比前序分析结论进行复核：
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
            create_limit_order_tool,
            calc_metrics_tool,
        ]

        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/opening_decision_prompt.md')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()

        logger.info(f"开始为 {symbol} 生成复核图像...")
        images, image_metas = _generate_kline_images(symbol, REVIEW_INTERVALS)

        current_price = get_current_price(symbol)
        if current_price:
            logger.info(f"{symbol} 当前价格: ${format_price(current_price)}")
        else:
            logger.warning(f"{symbol} 无法获取当前价格")

        model = get_model_factory().get_decision_model()

        subagent = create_trace_agent(
            model=model,
            tools=tools,
            system_prompt=prompt,
            node_name="opening_decision",
        )
        
        max_margin = _get_max_margin_for_new_position()
        margin_info = f"本次开仓可用最大保证金: ${max_margin:.2f} USDT" if max_margin > 0 else "保证金信息不可用"
        price_str = f"${format_price(current_price)}" if current_price else "获取失败"
        
        if not images:
            logger.warning(f"{symbol} 无法生成复核图像，使用纯文本模式")
            account_info = _format_account_summary(state.account_summary)
            combined_message = f"""【待决策币种】{symbol}
【当前价格】{price_str}

【账户状态】
{account_info}
{margin_info}

【前序分析结论】
{analysis_result}

请基于以上分析结论，审视并决定是否执行开仓操作。"""
            subagent_messages = [HumanMessage(content=combined_message)]
        else:
            logger.info(f"{symbol} 生成 {len(images)} 个周期的复核图像")
            account_info = _format_account_summary(state.account_summary)
            multimodal_content = _build_multimodal_content(symbol, account_info, analysis_result, images, max_margin, current_price)
            subagent_messages = [HumanMessage(
                content=multimodal_content,
                additional_kwargs={"_image_metas": image_metas}
            )]

        @with_retry(max_retries=5, retryable_exceptions=(Exception,))
        def _invoke_with_retry():
            return subagent.invoke({"messages": subagent_messages}, config=config)

        logger.info(f"开始为 {symbol} 执行开仓决策...")
        result = _invoke_with_retry()

        decision_output = result["messages"][-1].content if isinstance(result, dict) else str(result)

        logger.info("=" * 60)
        logger.info(f"{symbol} 开仓决策完成 (返回长度: {len(decision_output)})")
        logger.info("=" * 60)

        return {"opening_decision_results": {symbol: decision_output}}

    except Exception as e:
        logger.error(f"{symbol} 开仓决策执行失败: {e}", exc_info=True)
        return {"opening_decision_results": {symbol: f"决策执行失败: {str(e)}"}}
