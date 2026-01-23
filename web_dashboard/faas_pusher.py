"""FaaS 数据推送器"""
import requests
from typing import Dict, Any
import time
import sys
import os

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from monitor_module.utils.logger import setup_logger

logger = setup_logger()


class FaaSPusher:
    """FaaS 数据推送器"""
    
    def __init__(self, faas_url: str, timeout: int = 5, retry_times: int = 3):
        self.faas_url = faas_url.rstrip('/')
        self.timeout = timeout
        self.retry_times = retry_times
        self.enabled = True
        
        self.endpoints = {
            'trade_state': f'{self.faas_url}/api/push/trade_state',
            'position_history': f'{self.faas_url}/api/push/position_history',
            'agent_reports': f'{self.faas_url}/api/push/agent_reports',
            'pending_orders': f'{self.faas_url}/api/push/pending_orders',
            'asset_timeline': f'{self.faas_url}/api/push/asset_timeline',
        }
    
    def push_data(self, data_type: str, data: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        
        endpoint = self.endpoints.get(data_type)
        if not endpoint:
            logger.error(f"Unknown data type: {data_type}")
            return False
        
        payload = {
            "data": data
        }
        
        for attempt in range(self.retry_times):
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    timeout=self.timeout,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    logger.info(f"✓ Successfully pushed {data_type} to FaaS (attempt {attempt + 1})")
                    return True
                else:
                    logger.warning(f"✗ Failed to push {data_type}: HTTP {response.status_code} (attempt {attempt + 1})")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"✗ Timeout pushing {data_type} to FaaS (attempt {attempt + 1})")
                
            except requests.exceptions.ConnectionError:
                logger.warning(f"✗ Connection error pushing {data_type} to FaaS (attempt {attempt + 1})")
                
            except Exception as e:
                logger.error(f"✗ Error pushing {data_type} to FaaS: {e} (attempt {attempt + 1})")
            
            if attempt < self.retry_times - 1:
                time.sleep(0.5)
        
        return False
    
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f'{self.faas_url}/ping',
                timeout=self.timeout
            )
            if response.status_code == 200:
                logger.info(f"✓ FaaS connection test successful: {self.faas_url}")
                return True
            else:
                logger.error(f"✗ FaaS connection test failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"✗ FaaS connection test failed: {e}")
            return False
    
    def enable(self):
        """启用推送"""
        self.enabled = True
        logger.info("FaaS pusher enabled")
    
    def disable(self):
        """禁用推送"""
        self.enabled = False
        logger.warning("FaaS pusher disabled")

