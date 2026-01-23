"""交易 Agent 核心类：封装 Agent 的创建和执行逻辑"""
import os
from typing import Dict, Any, List, Optional, Callable
from monitor_module.utils.logger import setup_logger
from agent.utils.log_reader import read_latest_aggregate

# LangChain / Agents
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langgraph.errors import GraphRecursionError

# 中间件
from agent.middleware import (
    ContextInjectionMiddleware,
    SessionManagementMiddleware,
    ToolCallTracingMiddleware,
    DecisionVerificationMiddleware,
)

# 工具
from agent.tools.write_report_tool import write_report_tool



class TradeAgent:
    """交易 Agent
    
    职责：
    - 封装 Agent 的创建逻辑
    - 提供统一的分析接口
    - 管理提示词、模型、工具、中间件
    """
    
    def __init__(self, config: Dict[str, Any]):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = setup_logger(level=config['env']['log_level'])
        
        # 加载主控prompt
        self.supervisor_prompt = self._load_prompt('prompts/supervisor_prompt.md')
        
        # 初始化模型
        self.model = self._init_model()
        
        # 主控Agent的工具: SubAgent工具 + write_report
        from agent.sub_agents import (
            analyze_and_open_positions_tool,
            manage_and_protect_positions_tool,
        )
        
        self.supervisor_tools = [
            analyze_and_open_positions_tool,
            manage_and_protect_positions_tool,
            write_report_tool,
        ]
    
    def _load_prompt(self, relative_path: str) -> str:
        """加载prompt文件
        
        Args:
            relative_path: 相对于agent目录的路径
        
        Returns:
            prompt内容
        """
        prompt_path = os.path.join(os.path.dirname(__file__), relative_path)
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    
    def _init_model(self) -> ChatOpenAI:
        """初始化 LLM 模型
        
        Returns:
            ChatOpenAI 实例
        """
        model_name = os.getenv('AGENT_MODEL')
        base_url = os.getenv('AGENT_BASE_URL')
        api_key = os.getenv('AGENT_API_KEY')
        
        if not model_name or not api_key:
            raise ValueError("缺少必需的环境变量: AGENT_MODEL 或 AGENT_API_KEY")
        
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url or None,
            temperature=0.0,
            timeout=60,
            max_tokens=16000,
            logprobs=True,
            extra_body={
                "thinking": {
                    "type": "disabled",
                }
            },
        )
    
    def _create_middlewares(self, latest_alert: Dict[str, Any]) -> List:
        """创建中间件链
        
        Args:
            latest_alert: 最新告警数据
            
        Returns:
            中间件列表
        """
        # Session 管理中间件（负责 session 生命周期）
        session_middleware = SessionManagementMiddleware(latest_alert=latest_alert)
        
        # 决策验证中间件（负责基于 logprobs 验证工具调用）
        verification_config = self.config.get('agent', {}).get('decision_verification')
        verification_middleware = DecisionVerificationMiddleware(config=verification_config)
        
        # Tool 调用追踪中间件（负责记录工具调用）
        tracing_middleware = ToolCallTracingMiddleware()
        
        # 上下文注入中间件（所有数据准备工作在middleware内部完成）
        context_middleware = ContextInjectionMiddleware(
            latest_alert=latest_alert,
            kline_limit=15,  # 每个币种获取15根K线
        )
        
        # 工具调用限制中间件
        limit_middleware = ToolCallLimitMiddleware(run_limit=30)
        
        # 注意：middleware 执行顺序为列表顺序
        # - session_middleware 放在最前面初始化 session
        # - verification_middleware 在工具调用前进行决策验证
        # - tracing_middleware 记录工具调用（包含验证结果）
        # - context_middleware 注入上下文数据
        # - limit_middleware 限制工具调用次数
        return [
            session_middleware,
            verification_middleware,
            tracing_middleware,
            context_middleware,
            limit_middleware,
        ]
    
    def analyze_latest_alert(self, shutdown_flag: Optional[Callable[[], bool]] = None) -> bool:
        """分析最新的聚合告警
        
        Args:
            shutdown_flag: 退出标志检查函数（返回 True 表示需要退出）
            
        Returns:
            是否成功执行分析
        """
        # 读取最新聚合JSONL
        latest_alert = read_latest_aggregate(self.config['agent']['alerts_jsonl_path'])
        if not latest_alert:
            self.logger.warning("未找到最新聚合告警记录，跳过本次分析")
            return False
        
        interval = latest_alert.get('interval')
        ts = latest_alert.get('ts')
        entries = latest_alert.get('entries', [])
        symbols = [entry['symbol'] for entry in entries]
        self.logger.info(f"最新聚合告警: ts={ts}, interval={interval}, symbols={', '.join(symbols) if symbols else '无'}")
        
        return self.analyze(latest_alert, shutdown_flag)
    
    def analyze(self, alert_data: Dict[str, Any], shutdown_flag: Optional[Callable[[], bool]] = None) -> bool:
        """执行 Agent 分析 (双SubAgent并行架构)
        
        Args:
            alert_data: 告警数据
            shutdown_flag: 退出标志检查函数（返回 True 表示需要退出）
            
        Returns:
            是否成功执行分析
        """
        # 在开始分析前检查退出标志
        if shutdown_flag and shutdown_flag():
            self.logger.info("检测到退出信号，跳过 Agent 分析")
            return False
        
        try:
            # 创建中间件链
            middlewares = self._create_middlewares(alert_data)
            
            # 创建主控Agent (SubAgent作为普通工具)
            supervisor_agent = create_agent(
                self.model,
                tools=self.supervisor_tools,
                debug=False,
                system_prompt=self.supervisor_prompt,
                middleware=middlewares
            )
            self.logger.info("主控Agent已创建 (双SubAgent并行架构)")
            
            # 执行分析
            self.logger.info("开始执行主控Agent分析...")
            input_state = {"messages": []}
            _ = supervisor_agent.invoke(
                input_state, 
                {"recursion_limit": 100}
            )
            self.logger.info("主控Agent分析完成 (SubAgent traces将被合并)")
            
            return True
        
        except GraphRecursionError as e:
            self.logger.warning(f"Agent 递归超限（GraphRecursionError）: {e}. 本轮分析跳过。")
            return False
        
        except Exception as e:
            self.logger.error(f"Agent 调用异常: {e}", exc_info=True)
            return False

