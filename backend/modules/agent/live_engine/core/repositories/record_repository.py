"""交易记录数据访问层

负责 TradeRecord 的 CRUD 操作和持久化。
"""

import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from modules.agent.live_engine.core.models import RecordStatus, TradeRecord
from modules.agent.live_engine.core.persistence import JsonStateManager
from modules.monitor.utils.logger import get_logger

logger = get_logger('shared.record_repository')


def _get_default_state_file() -> str:
    """从配置文件获取默认状态文件路径"""
    try:
        from modules.config.settings import get_config
        config = get_config()
        persistence = config.get('agent', {}).get('persistence', {})
        return persistence.get('trade_records_path', 'modules/data/trade_records.json')
    except Exception as e:
        logger.warning(f"获取配置路径失败，使用默认值: {e}")
        return 'modules/data/trade_records.json'


class RecordRepository:
    """交易记录数据仓库

    职责：
    - TradeRecord 的 CRUD 操作
    - 数据持久化（使用 JsonStateManager）
    - 按条件查询和过滤

    不包含业务逻辑（如 TP/SL 处理），业务逻辑由 RecordService 处理。
    """

    def __init__(self, state_file: Optional[str] = None):
        """初始化

        Args:
            state_file: 持久化文件路径（可选，默认从配置文件读取）
        """
        self._lock = threading.RLock()
        file_path = state_file or _get_default_state_file()
        self._state_manager = JsonStateManager(file_path)
        self._records: Dict[str, TradeRecord] = {}

        logger.info(f"[RecordRepository] 使用存储文件: {file_path}")
        self._load_state()

    def _load_state(self):
        """从文件加载状态"""
        data = self._state_manager.load()
        records_data = data.get('records', [])

        for record_data in records_data:
            try:
                record = TradeRecord.from_dict(record_data)
                self._records[record.id] = record
            except Exception as e:
                logger.warning(f"[RecordRepository] 加载记录失败: {e}")

        logger.info(f"[RecordRepository] 已加载 {len(self._records)} 条记录")

    def _save_state(self):
        """保存状态到文件"""
        records_data = [r.to_dict() for r in self._records.values()]
        self._state_manager.save({'records': records_data})

    def create(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        leverage: int = 10,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        source: str = 'live',
        entry_order_id: Optional[int] = None,
        entry_algo_id: Optional[str] = None,
        agent_order_id: Optional[str] = None,
        extra_data: Optional[Dict] = None
    ) -> TradeRecord:
        """创建新记录

        Args:
            symbol: 交易对
            side: 方向
            qty: 数量
            entry_price: 入场价格
            leverage: 杠杆
            tp_price: 止盈价
            sl_price: 止损价
            source: 来源（live/reverse）
            entry_order_id: 入场订单 ID
            entry_algo_id: 入场条件单 ID
            agent_order_id: 关联的 Agent 订单 ID
            extra_data: 额外数据

        Returns:
            新创建的记录
        """
        margin_usdt = (entry_price * qty) / leverage if leverage > 0 else 0
        notional_usdt = entry_price * qty

        record = TradeRecord(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            margin_usdt=margin_usdt,
            notional_usdt=notional_usdt,
            status=RecordStatus.OPEN,
            source=source,
            entry_order_id=entry_order_id,
            entry_algo_id=entry_algo_id,
            agent_order_id=agent_order_id,
            extra_data=extra_data or {},
        )

        with self._lock:
            self._records[record.id] = record
            self._save_state()

        logger.info(f"[RecordRepository] 创建记录: {record.id} {symbol} {side} @ {entry_price}")
        return record

    def get(self, record_id: str) -> Optional[TradeRecord]:
        """获取记录

        Args:
            record_id: 记录 ID

        Returns:
            记录，不存在返回 None
        """
        with self._lock:
            return self._records.get(record_id)

    def get_all(self) -> List[TradeRecord]:
        """获取所有记录"""
        with self._lock:
            return list(self._records.values())

    def get_open_records(self, source: Optional[str] = None) -> List[TradeRecord]:
        """获取所有开仓记录

        Args:
            source: 按来源过滤（live/reverse 或 None 表示全部）

        Returns:
            开仓记录列表
        """
        with self._lock:
            records = [r for r in self._records.values() if r.status == RecordStatus.OPEN]
            if source:
                records = [r for r in records if r.source == source]
            return records

    def find_by_symbol(self, symbol: str, source: Optional[str] = None) -> List[TradeRecord]:
        """按交易对查找记录

        Args:
            symbol: 交易对
            source: 来源过滤

        Returns:
            记录列表
        """
        with self._lock:
            records = [r for r in self._records.values() if r.symbol == symbol]
            if source:
                records = [r for r in records if r.source == source]
            return records

    def find_by_tp_order_id(self, tp_order_id: int) -> Optional[TradeRecord]:
        """按止盈限价单 ID 查找记录"""
        with self._lock:
            for record in self._records.values():
                if record.tp_order_id == tp_order_id:
                    return record
            return None

    def find_by_tp_algo_id(self, tp_algo_id: str) -> Optional[TradeRecord]:
        """按止盈条件单 ID 查找记录"""
        with self._lock:
            for record in self._records.values():
                if record.tp_algo_id == tp_algo_id:
                    return record
            return None

    def find_by_sl_algo_id(self, sl_algo_id: str) -> Optional[TradeRecord]:
        """按止损条件单 ID 查找记录"""
        with self._lock:
            for record in self._records.values():
                if record.sl_algo_id == sl_algo_id:
                    return record
            return None

    def find_by_entry_order_id(self, order_id: int) -> Optional[TradeRecord]:
        """按入场订单 ID 查找记录"""
        with self._lock:
            for record in self._records.values():
                if record.entry_order_id == order_id:
                    return record
            return None

    def find_by_entry_algo_id(self, algo_id: str) -> Optional[TradeRecord]:
        """按入场条件单 ID 查找记录"""
        with self._lock:
            for record in self._records.values():
                if record.entry_algo_id == algo_id:
                    return record
            return None

    def update(self, record_id: str, **kwargs) -> Optional[TradeRecord]:
        """更新记录

        Args:
            record_id: 记录 ID
            **kwargs: 要更新的字段

        Returns:
            更新后的记录，不存在返回 None
        """
        with self._lock:
            record = self._records.get(record_id)
            if not record:
                return None

            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)

            self._save_state()
            return record

    def update_tpsl_ids(
        self,
        record_id: str,
        tp_order_id: Optional[int] = None,
        tp_algo_id: Optional[str] = None,
        sl_algo_id: Optional[str] = None
    ) -> bool:
        """更新 TP/SL 订单 ID

        Args:
            record_id: 记录 ID
            tp_order_id: 止盈限价单 ID
            tp_algo_id: 止盈条件单 ID
            sl_algo_id: 止损条件单 ID

        Returns:
            是否成功
        """
        with self._lock:
            record = self._records.get(record_id)
            if not record:
                return False

            if tp_order_id is not None:
                record.tp_order_id = tp_order_id
            if tp_algo_id is not None:
                record.tp_algo_id = tp_algo_id
            if sl_algo_id is not None:
                record.sl_algo_id = sl_algo_id

            self._save_state()
            return True

    def clear_tpsl_ids(self, record_id: str) -> bool:
        """清除 TP/SL ID"""
        with self._lock:
            record = self._records.get(record_id)
            if not record:
                return False

            record.tp_order_id = None
            record.tp_algo_id = None
            record.sl_algo_id = None

            self._save_state()
            return True

    def close(
        self,
        record_id: str,
        close_price: float,
        close_reason: str,
        realized_pnl: Optional[float] = None
    ) -> Optional[TradeRecord]:
        """关闭记录

        Args:
            record_id: 记录 ID
            close_price: 关闭价格
            close_reason: 关闭原因
            realized_pnl: 实现盈亏（如不提供则自动计算）

        Returns:
            关闭后的记录
        """
        with self._lock:
            record = self._records.get(record_id)
            if not record:
                return None

            if record.status != RecordStatus.OPEN:
                logger.warning(f"[RecordRepository] 记录 {record_id} 已关闭，跳过")
                return record

            if realized_pnl is None:
                if record.side.upper() in ('LONG', 'BUY'):
                    realized_pnl = (close_price - record.entry_price) * record.qty
                else:
                    realized_pnl = (record.entry_price - close_price) * record.qty
                realized_pnl -= record.total_commission

            record.status = RecordStatus(close_reason) if close_reason in [s.value for s in RecordStatus] else RecordStatus.MANUAL_CLOSED
            record.close_price = close_price
            record.close_time = datetime.now().isoformat()
            record.close_reason = close_reason
            record.realized_pnl = realized_pnl

            self._save_state()

            pnl_emoji = '🟢' if realized_pnl > 0 else '🔴'
            logger.info(f"[RecordRepository] {pnl_emoji} 关闭记录: {record.symbol} @ {close_price} PnL={realized_pnl:.4f} reason={close_reason}")

            return record

    def delete(self, record_id: str) -> bool:
        """删除记录

        Args:
            record_id: 记录 ID

        Returns:
            是否成功
        """
        with self._lock:
            if record_id in self._records:
                del self._records[record_id]
                self._save_state()
                return True
            return False

    def update_mark_price(self, symbol: str, mark_price: float):
        """更新指定交易对所有开仓记录的标记价格"""
        with self._lock:
            for record in self._records.values():
                if record.symbol == symbol and record.status == RecordStatus.OPEN:
                    record.latest_mark_price = mark_price
