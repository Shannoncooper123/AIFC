"""定义 LangGraph 工作流的状态"""
from typing import List, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field


def merge_analysis_results(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    return {**left, **right}


def pick_right(left: Any, right: Any) -> Any:
    return right


class SymbolAnalysisState(BaseModel):
    """
    单币种分析子图的状态定义。
    """
    current_symbol: Annotated[Optional[str], pick_right] = Field(default=None, description="当前分析的币种")
    symbol_contexts: Annotated[Dict[str, str], merge_analysis_results] = Field(default_factory=dict, description="每个币种的上下文片段")
    market_context: Annotated[str, pick_right] = Field(default="", description="市场上下文（备用）")
    account_summary: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="账户状态摘要")
    positions_summary: Annotated[List[Dict[str, Any]], pick_right] = Field(default_factory=list, description="当前币种持仓")
    position_history: Annotated[List[Dict[str, Any]], pick_right] = Field(default_factory=list, description="历史平仓记录")
    
    analysis_results: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="分析结果（子图内部传递）")
    opening_decision_results: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="开仓决策结果")
    error: Annotated[Optional[str], pick_right] = Field(default=None, description="错误信息")


class PositionManagementState(BaseModel):
    """
    单币种持仓管理的状态定义。
    用于 Send 分发时传递单个持仓的上下文。
    """
    current_symbol: Annotated[str, pick_right] = Field(description="当前管理的币种")
    position_info: Annotated[Dict[str, Any], pick_right] = Field(default_factory=dict, description="该币种的持仓信息")
    market_context: Annotated[str, pick_right] = Field(default="", description="市场上下文")
    position_history: Annotated[List[Dict[str, Any]], pick_right] = Field(default_factory=list, description="历史平仓记录（用于参考）")
    position_next_focus: Annotated[str, pick_right] = Field(default="", description="上一轮该币种的关注重点")
    
    position_management_results: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="持仓管理结果")
    error: Annotated[Optional[str], pick_right] = Field(default=None, description="错误信息")


class AgentState(BaseModel):
    """
    LangGraph 工作流的状态定义，用于在不同节点之间传递数据。
    """
    # 上一轮分析总结的关注点
    run_id: Annotated[Optional[str], pick_right] = Field(default=None, description="本次工作流运行ID")
    position_next_focus: Annotated[str, pick_right] = Field(default="", description="下一轮持仓管理关注重点（文本）")
    previous_symbol_focus_map: Annotated[Dict[str, str], merge_analysis_results] = Field(default_factory=dict, description="上一轮每个币种的分析重点映射：symbol → focus 文本")

    # 市场上下文总览（用于机会筛选等）
    market_context: Annotated[str, pick_right] = Field(default="", description="包含市场告警、K线、账户状态等的完整上下文总览")
    
    # 单币种上下文（仅包含该币种的告警与K线等，供单币种分析节点使用）
    symbol_contexts: Annotated[Dict[str, str], merge_analysis_results] = Field(default_factory=dict, description="每个币种的上下文片段，键为symbol")
    
    # 账户与持仓相关上下文（供各节点复用）
    account_summary: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="账户总体状态摘要，如余额、权益、保证金利用率等")
    positions_summary: Annotated[List[Dict[str, Any]], pick_right] = Field(default_factory=list, description="当前持仓列表摘要")
    position_history: Annotated[List[Dict[str, Any]], pick_right] = Field(default_factory=list, description="最近已平仓位的历史记录")
    long_short_ratio: Annotated[str, pick_right] = Field(default="", description="当前持仓的多空比信息")
    symbol_positions_map: Annotated[Dict[str, Dict[str, Any]], merge_analysis_results] = Field(default_factory=dict, description="币种到其持仓摘要的映射，键为symbol")
    
    # 机会筛选节点输出
    opportunities: Annotated[List[str], pick_right] = Field(default_factory=list, description="由机会筛选节点识别出的有交易机会的币种列表")
    
    # 单币种分析结果
    analysis_results: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="存储每个币种的详细分析结果")
    
    # 开仓决策结果
    opening_decision_results: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="存储每个币种的开仓决策结果")

    # 当前正在分析的币种（由 Send 任务注入）
    current_symbol: Annotated[Optional[str], pick_right] = Field(default=None, description="当前分析任务对应的symbol")
    
    # 持仓管理结果（每个币种一个条目，通过 Send 并行执行后合并）
    position_management_results: Annotated[Dict[str, Any], merge_analysis_results] = Field(default_factory=dict, description="持仓管理结果，键为symbol")
    
    # 最终报告
    final_report: Annotated[str, pick_right] = Field(default="", description="所有节点执行完毕后的最终总结报告")
    
    # 错误信息
    error: Annotated[Optional[str], pick_right] = Field(default=None, description="记录工作流执行过程中的错误信息")
