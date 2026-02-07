"""配置加载器 - 统一加载.env和config.yaml"""
import os
import yaml
from typing import Dict, Any
from dotenv import load_dotenv

from modules.constants import VALID_INTERVALS, DEFAULT_LEVERAGE


class ConfigLoader:
    """配置加载器（单例模式）"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load(self, config_path: str = 'config.yaml', env_path: str = '.env') -> Dict[str, Any]:
        """加载配置
        
        Args:
            config_path: YAML配置文件路径
            env_path: 环境变量文件路径
            
        Returns:
            完整的配置字典
        """
        if self._config is not None:
            return self._config
        
        # 0. 统一路径（支持从任意工作目录运行）
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isabs(config_path):
            config_path = os.path.join(base_dir, config_path)
        if not os.path.isabs(env_path):
            env_path = os.path.join(base_dir, env_path)
        
        # 1. 加载环境变量（override=True 确保覆盖系统环境变量）
        load_dotenv(env_path, override=True)
        
        # 2. 加载YAML配置（config.yaml 是必需的）
        config = self._load_yaml(config_path)
        
        # 4. 添加环境变量配置（仅敏感信息）
        config['env'] = self._load_env_vars()
        
        # 4.1 Agent 敏感配置增强（仅从环境变量读取模型 API 相关）
        if 'agent' not in config:
            raise ValueError("config.yaml 中缺少 'agent' 配置节")
        
        agent_cfg = config['agent']
        
        # 模型配置（敏感信息，仅从环境变量读取）
        agent_cfg['model'] = os.getenv('AGENT_MODEL', '')
        agent_cfg['base_url'] = os.getenv('AGENT_BASE_URL', '')
        agent_cfg['api_key'] = os.getenv('AGENT_API_KEY', '')
        
        # 报告邮件（回退到系统告警邮箱）
        agent_cfg['report_email'] = config['env']['alert_email']
        
        # 路径配置（从 config.yaml 读取，转换为绝对路径）
        # base_dir 应该是 backend 目录（settings.py 在 backend/modules/config/ 下，需要向上 3 层）
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path_keys = ['alerts_jsonl_path', 'reports_json_path', 'position_history_path', 
                     'state_path', 'trade_state_path']
        for key in path_keys:
            if key not in agent_cfg:
                raise ValueError(f"config.yaml 的 agent 节缺少 '{key}' 配置")
            # 将相对路径转换为绝对路径（相对于 backend 目录）
            if not os.path.isabs(agent_cfg[key]):
                agent_cfg[key] = os.path.join(backend_dir, agent_cfg[key])
        
        optional_path_keys = ['workflow_trace_path', 'workflow_artifacts_dir', 
                              'workflow_index_path', 'workflow_traces_dir']
        for key in optional_path_keys:
            if key in agent_cfg and not os.path.isabs(agent_cfg[key]):
                agent_cfg[key] = os.path.join(backend_dir, agent_cfg[key])
        
        # 持久化路径配置（转换为绝对路径）
        persistence_cfg = agent_cfg.get('persistence', {})
        persistence_path_keys = ['trade_records_path', 'pending_orders_path', 'trade_history_path']
        for key in persistence_path_keys:
            if key in persistence_cfg and not os.path.isabs(persistence_cfg[key]):
                persistence_cfg[key] = os.path.join(backend_dir, persistence_cfg[key])
        agent_cfg['persistence'] = persistence_cfg
        
        # 反向交易引擎配置（转换为绝对路径）
        reverse_cfg = agent_cfg.get('reverse', {})
        if 'config_path' in reverse_cfg and not os.path.isabs(reverse_cfg['config_path']):
            reverse_cfg['config_path'] = os.path.join(backend_dir, reverse_cfg['config_path'])
        agent_cfg['reverse'] = reverse_cfg
        
        # 验证 simulator 配置存在（数值配置从 config.yaml 读取）
        if 'simulator' not in agent_cfg:
            raise ValueError("config.yaml 的 agent 节中缺少 'simulator' 配置")
        
        config['agent'] = agent_cfg
        
        # 5. 验证配置
        self._validate_config(config)
        
        self._config = config
        return config
    
    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """加载YAML文件（config.yaml 是必需的）"""
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"配置文件 {path} 不存在。请确保 config.yaml 文件存在于项目根目录。"
            )
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if not config:
                    raise ValueError(f"配置文件 {path} 为空")
                return config
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件 {path} 格式错误: {e}")
    
    def _load_env_vars(self) -> Dict[str, Any]:
        """加载环境变量"""
        env_config = {}
        
        # SMTP配置
        env_config['smtp_host'] = os.getenv('SMTP_HOST', 'smtp.qq.com')
        env_config['smtp_port'] = int(os.getenv('SMTP_PORT', '587'))
        env_config['smtp_user'] = os.getenv('SMTP_USER', '')
        env_config['smtp_password'] = os.getenv('SMTP_PASSWORD', '')
        env_config['smtp_use_tls'] = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
        env_config['alert_email'] = os.getenv('ALERT_EMAIL', '')
        
        # 邮件功能是否启用（当SMTP_USER、SMTP_PASSWORD、ALERT_EMAIL都配置时才启用）
        env_config['email_enabled'] = bool(
            env_config['smtp_user'] and 
            env_config['smtp_password'] and 
            env_config['alert_email']
        )
        
        # 日志级别
        env_config['log_level'] = os.getenv('LOG_LEVEL', 'INFO')
        
        # 币安API密钥（仅实盘模式需要）
        env_config['binance_api_key'] = os.getenv('BINANCE_API_KEY', '')
        env_config['binance_api_secret'] = os.getenv('BINANCE_API_SECRET', '')
        
        return env_config
    
    def _validate_config(self, config: Dict[str, Any]):
        """验证配置完整性"""
        env = config['env']
        
        # 邮件配置验证（仅当启用时验证格式）
        if env.get('email_enabled'):
            if '@' not in env['smtp_user'] or '@' not in env['alert_email']:
                raise ValueError("邮箱格式不正确")
        
        # 验证K线间隔
        if config['kline']['interval'] not in VALID_INTERVALS:
            raise ValueError(f"无效的K线间隔: {config['kline']['interval']}")
        
        # 验证持仓量配置
        oi_config = config.get('open_interest')
        if oi_config:
            # 验证历史数据数量
            if oi_config.get('history_size', 0) < 10:
                raise ValueError("持仓量历史数据数量必须 >= 10")
            if oi_config.get('history_size', 0) > 500:
                raise ValueError("持仓量历史数据数量必须 <= 500")
            
            # 验证最小变化率
            if oi_config.get('min_oi_change', 0) < 0:
                raise ValueError("最小持仓量变化率必须 >= 0")
        
        # 验证交易模式配置
        trading_config = config.get('trading')
        if trading_config:
            mode = trading_config.get('mode', 'simulator')
            if mode not in ['simulator', 'live']:
                raise ValueError(f"无效的交易模式: {mode}，仅支持 simulator 或 live")
            
            # 实盘模式需要API密钥
            if mode == 'live':
                env = config['env']
                if not env.get('binance_api_key') or not env.get('binance_api_secret'):
                    raise ValueError(
                        "实盘模式需要设置 BINANCE_API_KEY 和 BINANCE_API_SECRET 环境变量"
                    )
            
            # 验证杠杆
            max_leverage = trading_config.get('max_leverage', DEFAULT_LEVERAGE)
            if max_leverage < 1 or max_leverage > 125:
                raise ValueError("max_leverage 必须在 1-125 之间")
        
        # 验证周期参数
        if config['indicators']['atr_period'] < 2:
            raise ValueError("ATR周期必须 >= 2")
        if config['indicators']['stddev_period'] < 2:
            raise ValueError("标准差周期必须 >= 2")
        
        # 验证 Agent 配置
        agent = config.get('agent')
        if not agent:
            raise ValueError("config.yaml 中缺少 'agent' 配置节")
        
        # 验证必需的 agent 字段
        required_agent_fields = ['default_interval_min', 'alerts_jsonl_path', 'reports_json_path',
                                 'position_history_path', 'state_path', 
                                 'trade_state_path', 'simulator']
        missing_agent = [f for f in required_agent_fields if f not in agent]
        if missing_agent:
            raise ValueError(f"config.yaml 的 agent 节缺少必需字段: {', '.join(missing_agent)}")
        
        # 验证 simulator 配置
        sim = agent.get('simulator')
        if not sim:
            raise ValueError("config.yaml 的 agent 节缺少 'simulator' 配置")
        
        required_sim_fields = ['initial_balance', 'taker_fee_rate', 'max_leverage', 'ws_interval']
        missing_sim = [f for f in required_sim_fields if f not in sim]
        if missing_sim:
            raise ValueError(f"config.yaml 的 agent.simulator 节缺少必需字段: {', '.join(missing_sim)}")
        
        # 验证数值范围
        if sim['initial_balance'] <= 0:
            raise ValueError("初始余额必须 > 0")
        if sim['taker_fee_rate'] < 0 or sim['taker_fee_rate'] > 1:
            raise ValueError("手续费率必须在 0-1 之间")
        if sim['max_leverage'] < 1 or sim['max_leverage'] > 125:
            raise ValueError("最大杠杆必须在 1-125 之间")
        if sim['ws_interval'] not in VALID_INTERVALS:
            raise ValueError(f"无效的 WebSocket 间隔: {sim['ws_interval']}")
        if agent['default_interval_min'] < 1:
            raise ValueError("默认唤醒间隔必须 >= 1 分钟")
        
        # 反向交易引擎配置完全由前端动态管理，无需在此验证
        
        # 验证 decision_verification 配置（可选，但如果存在需要验证格式）
        verification = agent.get('decision_verification')
        if verification:
            if not isinstance(verification.get('enabled'), bool):
                raise ValueError("decision_verification.enabled 必须是布尔值")
            
            threshold = verification.get('threshold')
            if threshold is not None:
                if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
                    raise ValueError("decision_verification.threshold 必须在 0-1 之间")
            
            weights = verification.get('weights')
            if weights:
                if not isinstance(weights, dict):
                    raise ValueError("decision_verification.weights 必须是字典")
                
                # 验证每个工具的权重配置（嵌套格式）
                for tool_name, tool_weights in weights.items():
                    if not isinstance(tool_weights, dict):
                        raise ValueError(
                            f"decision_verification.weights.{tool_name} 必须是字典。"
                            f"新格式要求每个工具有独立的权重配置，例如：\n"
                            f"weights:\n"
                            f"  open_position:\n"
                            f"    multi_timeframe_aligned: 0.27\n"
                            f"    ...\n"
                            f"  close_position:\n"
                            f"    trend_reversed: 0.30\n"
                            f"    ..."
                        )
                    weight_sum = sum(tool_weights.values())
                    if abs(weight_sum - 1.0) > 0.01:
                        raise ValueError(
                            f"decision_verification.weights.{tool_name} 的总和应为 1.0，"
                            f"当前为 {weight_sum:.3f}"
                        )
            
            target_tools = verification.get('target_tools')
            if target_tools and not isinstance(target_tools, list):
                raise ValueError("decision_verification.target_tools 必须是列表")


# 全局函数
_loader = ConfigLoader()


def load_config(config_path: str = 'config.yaml', env_path: str = '.env') -> Dict[str, Any]:
    """加载配置（全局入口）"""
    return _loader.load(config_path, env_path)


def get_config() -> Dict[str, Any]:
    """获取已加载的配置"""
    if _loader._config is None:
        return load_config()
    return _loader._config

