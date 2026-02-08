"""历史记录写入器：记录已平仓的持仓到 position_history.json

使用 shared/persistence/JsonStateManager 进行 JSON 读写。
"""
from datetime import datetime, timezone
from typing import Any, Dict

from modules.agent.live_engine.core.persistence import JsonStateManager
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.history_writer')


class HistoryWriter:
    """历史记录写入器

    职责：
    - 记录已平仓的持仓到 position_history.json
    - 管理历史文件的读写
    """

    def __init__(self, config: Dict):
        """初始化

        Args:
            config: 配置字典
        """
        self.config = config
        agent_cfg = config.get('agent', {})
        history_path = agent_cfg.get('position_history_path', 'modules/data/position_history.json')

        self._state_manager = JsonStateManager(history_path)

        if not self._state_manager.exists():
            self._init_history_file()

    def _init_history_file(self):
        """初始化空的历史文件"""
        try:
            self._state_manager.save({"positions": []})
            logger.info(f"已创建历史仓位文件: {self._state_manager.file_path}")
        except Exception as e:
            logger.error(f"创建历史文件失败: {e}")

    def record_closed_position(self, position: Any, close_reason: str = 'unknown',
                               close_price: float = None, realized_pnl: float = None,
                               close_order_id: int = None, is_reverse: bool = False):
        """记录已平仓的仓位

        Args:
            position: Position对象
            close_reason: 平仓原因（Agent主动平仓/止盈/止损）
            close_price: 平仓价格
            realized_pnl: 已实现盈亏
            close_order_id: 平仓订单ID（用于复盘）
            is_reverse: 是否为反向交易（用于区分反向交易记录）
        """
        try:
            record = {
                'id': position.id,
                'symbol': position.symbol,
                'side': position.side,
                'qty': position.qty,
                'entry_price': position.entry_price,
                'close_price': close_price or position.latest_mark_price or position.entry_price,
                'leverage': position.leverage,
                'notional_usdt': position.notional_usdt,
                'margin_used': position.margin_used,
                'tp_price': position.tp_price,
                'sl_price': position.sl_price,
                'open_time': position.open_time,
                'close_time': datetime.now(timezone.utc).isoformat(),
                'close_reason': close_reason,
                'close_order_id': close_order_id,
                'realized_pnl': realized_pnl if realized_pnl is not None else position.unrealized_pnl(close_price),
                'fees_open': position.fees_open if hasattr(position, 'fees_open') else 0.0,
                'fees_close': 0.0,
                'is_reverse': is_reverse,
            }

            history = self._load_history()
            history['positions'].append(record)
            self._state_manager.save(history)

            logger.info(f"已记录平仓历史: {position.symbol} {position.side} "
                       f"盈亏=${realized_pnl if realized_pnl is not None else 0:.2f} "
                       f"原因={close_reason}")

        except Exception as e:
            logger.error(f"记录平仓历史失败: {e}", exc_info=True)

    def _load_history(self) -> Dict[str, Any]:
        """加载历史文件（内部使用）"""
        data = self._state_manager.load(default={"positions": []})
        if not isinstance(data, dict) or 'positions' not in data:
            return {"positions": []}
        return data

    def get_history(self, limit: int = 100, is_reverse: bool = None) -> list:
        """获取平仓历史

        Args:
            limit: 最大返回数量
            is_reverse: 过滤条件（True=反向交易, False=正向交易, None=全部）

        Returns:
            历史记录列表
        """
        history = self._load_history()
        positions = history.get('positions', [])

        if is_reverse is not None:
            positions = [p for p in positions if p.get('is_reverse', False) == is_reverse]

        positions.sort(key=lambda x: x.get('close_time', ''), reverse=True)
        return positions[:limit]

    def get_statistics(self, is_reverse: bool = None) -> Dict[str, Any]:
        """获取统计信息

        Args:
            is_reverse: 过滤条件

        Returns:
            统计信息字典
        """
        positions = self.get_history(limit=10000, is_reverse=is_reverse)

        if not positions:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'max_profit': 0,
                'max_loss': 0
            }

        pnl_list = [p.get('realized_pnl', 0) for p in positions]
        total_pnl = sum(pnl_list)
        win_count = sum(1 for pnl in pnl_list if pnl > 0)
        loss_count = sum(1 for pnl in pnl_list if pnl < 0)

        return {
            'total_trades': len(positions),
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': round(win_count / len(positions) * 100, 2) if positions else 0,
            'total_pnl': round(total_pnl, 4),
            'avg_pnl': round(total_pnl / len(positions), 4) if positions else 0,
            'max_profit': round(max(pnl_list), 4) if pnl_list else 0,
            'max_loss': round(min(pnl_list), 4) if pnl_list else 0
        }
