"""数据访问层 (Repository)

提供统一的数据 CRUD 接口，与业务逻辑解耦。
"""

from .record_repository import RecordRepository
from .order_repository import OrderRepository

__all__ = [
    'RecordRepository',
    'OrderRepository',
]
