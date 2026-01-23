"""资产打点记录器：每10分钟记录一次账户总资产"""
import os
import json
import time
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from monitor_module.utils.logger import setup_logger

logger = setup_logger()


class AssetTracker:
    """资产打点记录器"""
    
    def __init__(self, timeline_file: str, max_days: int = 7):
        """初始化资产打点记录器
        
        Args:
            timeline_file: 时间线数据文件路径
            max_days: 保留最近N天的数据，默认7天
        """
        self.timeline_file = Path(timeline_file)
        self.max_days = max_days
        
        # 确保目录存在
        self.timeline_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件不存在，初始化
        if not self.timeline_file.exists():
            self._init_file()
        
        logger.info(f"AssetTracker 初始化: {self.timeline_file}")
    
    def _init_file(self):
        """初始化时间线文件"""
        initial_data = {
            "timeline": []
        }
        with open(self.timeline_file, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)
        logger.info(f"已初始化资产时间线文件: {self.timeline_file}")
    
    def record_snapshot(self, trade_state: Dict[str, Any]) -> bool:
        """记录资产快照
        
        Args:
            trade_state: trade_state.json 的数据
            
        Returns:
            是否记录成功
        """
        try:
            # 提取账户信息
            account = trade_state.get('account', {})
            
            snapshot = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'equity': round(account.get('equity', 0.0), 2),
                'balance': round(account.get('balance', 0.0), 2),
                'unrealized_pnl': round(account.get('unrealized_pnl', 0.0), 2),
                'realized_pnl': round(account.get('realized_pnl', 0.0), 2),
                'reserved_margin': round(account.get('reserved_margin_sum', 0.0), 2),
                'positions_count': account.get('positions_count', 0),
            }
            
            # 读取现有数据
            try:
                with open(self.timeline_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"timeline": []}
            
            timeline = data.get('timeline', [])
            
            # 添加新快照
            timeline.append(snapshot)
            
            # 清理过期数据（保留最近max_days天）
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.max_days)
            timeline = [
                s for s in timeline
                if datetime.fromisoformat(s['timestamp'].replace('Z', '+00:00')) > cutoff_time
            ]
            
            # 写回文件
            data['timeline'] = timeline
            with open(self.timeline_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(
                f"✓ 资产快照已记录: equity=${snapshot['equity']:.2f}, "
                f"时间线共{len(timeline)}个点"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"✗ 记录资产快照失败: {e}", exc_info=True)
            return False
    
    def get_timeline(self) -> Dict[str, Any]:
        """获取完整时间线数据
        
        Returns:
            时间线数据字典
        """
        try:
            with open(self.timeline_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"timeline": []}

