"""日志配置模块"""
import logging
import sys
from typing import Optional


class FlushingStreamHandler(logging.StreamHandler):
    """每次写入后自动刷新的 StreamHandler"""
    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logger(name: str = 'crypto-monitor', level: str = 'INFO') -> logging.Logger:
    """配置并返回日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    console_handler = FlushingStreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    logger.propagate = False
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取日志记录器
    
    Args:
        name: 日志记录器名称，None则返回根记录器
        
    Returns:
        日志记录器
    """
    if name:
        full_name = f'crypto-monitor.{name}'
        child_logger = logging.getLogger(full_name)
        
        root_logger = logging.getLogger('crypto-monitor')
        if not root_logger.handlers:
            setup_logger()
        
        return child_logger
    return logging.getLogger('crypto-monitor')
