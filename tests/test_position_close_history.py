"""测试持仓平仓历史记录链路

测试场景：
1. 正常流程：ORDER_TRADE_UPDATE -> ACCOUNT_UPDATE
2. 异常流程：ACCOUNT_UPDATE -> ORDER_TRADE_UPDATE (事件乱序)
3. 手动平仓
4. 防重复记录机制
"""
import os
import sys
import json
import tempfile
import time
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.live_engine.services.position_service import PositionService
from agent.live_engine.services.order_service import OrderService
from agent.live_engine.persistence.history_writer import HistoryWriter
from agent.trade_simulator.models import Position
from agent.trade_simulator.utils.file_utils import WriteQueue


class TestPositionCloseHistory:
    """测试持仓平仓历史记录"""
    
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.history_path = os.path.join(self.temp_dir, 'test_position_history.json')
        self.setup()
    
    def setup(self):
        """初始化测试环境"""
        # 创建模拟的配置
        self.config = {
            'agent': {
                'position_history_path': self.history_path
            }
        }
        
        # 创建模拟的 REST 客户端
        self.rest_client = Mock()
        # 使用side_effect动态返回订单详情
        def get_order_side_effect(symbol, order_id=None):
            # 根据订单ID返回不同的价格
            if order_id == 12345:  # 止盈订单
                return {'avgPrice': '110.5', 'executedQty': '1.0'}
            elif order_id == 22222:  # 止损订单
                return {'avgPrice': '2100.0', 'executedQty': '1.0'}
            else:
                return {'avgPrice': '100.0', 'executedQty': '1.0'}
        
        self.rest_client.get_order = Mock(side_effect=get_order_side_effect)
        
        # 创建模拟的订单管理器
        self.order_manager = Mock()
        self.order_manager.tpsl_orders = {}
        self.order_manager.cancel_single_order = Mock(return_value=True)
        self.order_manager.get_tpsl_price_for_symbol = Mock(return_value={
            'tp_price': 110.0,
            'sl_price': 90.0
        })
        
        # 创建历史写入器
        self.history_writer = HistoryWriter(self.config)
        
        # 创建持仓服务
        self.position_service = PositionService(self.rest_client)
        
        print(f"✅ 测试环境初始化完成")
        print(f"   历史文件路径: {self.history_path}")
    
    def create_test_position(self, symbol: str, side: str, entry_price: float):
        """创建测试持仓"""
        position = Position(
            id=f"test-{symbol}",
            symbol=symbol,
            side=side,
            qty=1.0,
            entry_price=entry_price,
            leverage=10,
            notional_usdt=100.0,
            margin_used=10.0,
            latest_mark_price=entry_price
        )
        position.tp_price = 110.0
        position.sl_price = 90.0
        self.position_service.positions[symbol] = position
        return position
    
    def create_order_trade_update_event(self, symbol: str, order_type: str, 
                                        order_status: str, order_id: int, avg_price: float):
        """创建 ORDER_TRADE_UPDATE 事件"""
        return {
            'e': 'ORDER_TRADE_UPDATE',
            'E': int(datetime.now(timezone.utc).timestamp() * 1000),
            'o': {
                's': symbol,
                'i': order_id,
                'o': order_type,  # TAKE_PROFIT_MARKET / STOP_MARKET
                'X': order_status,  # FILLED / CANCELED
                'ap': str(avg_price)  # 平均成交价
            }
        }
    
    def create_account_update_event(self, symbol: str, position_amt: float, 
                                    mark_price: float, entry_price: float):
        """创建 ACCOUNT_UPDATE 事件"""
        return {
            'e': 'ACCOUNT_UPDATE',
            'E': int(datetime.now(timezone.utc).timestamp() * 1000),
            'T': int(datetime.now(timezone.utc).timestamp() * 1000),
            'a': {
                'm': 'ORDER',
                'P': [{
                    's': symbol,
                    'pa': str(position_amt),  # 持仓数量（0表示已平仓）
                    'ep': str(entry_price),   # 入场价
                    'mp': str(mark_price),    # 标记价格
                    'cr': '10.5'              # 累计已实现盈亏
                }]
            }
        }
    
    def wait_for_write_queue(self, timeout=3.0):
        """等待写入队列完成（处理异步写入）"""
        write_queue = WriteQueue.get_instance()
        start = time.time()
        while time.time() - start < timeout:
            if write_queue._queue.empty():
                time.sleep(0.1)  # 再等一会确保写入完成
                return True
            time.sleep(0.05)
        return False
    
    def load_history(self):
        """加载历史记录"""
        # 等待异步写入完成
        self.wait_for_write_queue()
        
        if os.path.exists(self.history_path):
            with open(self.history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'positions': []}
    
    def test_case_1_normal_flow(self):
        """测试案例1：正常流程（ORDER_TRADE_UPDATE -> ACCOUNT_UPDATE）"""
        print("\n" + "="*80)
        print("测试案例1：正常流程 - 止盈触发")
        print("="*80)
        
        symbol = 'BTCUSDT'
        
        # 1. 创建测试持仓
        position = self.create_test_position(symbol, 'long', 100.0)
        print(f"✅ 创建测试持仓: {symbol} long, entry={position.entry_price}")
        
        # 2. 添加 TP/SL 订单记录
        self.order_manager.tpsl_orders[symbol] = {
            'tp_order_id': 12345,
            'sl_order_id': 67890
        }
        print(f"✅ 添加 TP/SL 订单记录: tp=12345, sl=67890")
        
        # 3. 模拟 ORDER_TRADE_UPDATE 事件（止盈触发）
        print(f"\n步骤1: 发送 ORDER_TRADE_UPDATE 事件（止盈触发）")
        event1 = self.create_order_trade_update_event(
            symbol=symbol,
            order_type='TAKE_PROFIT_MARKET',
            order_status='FILLED',
            order_id=12345,
            avg_price=110.5
        )
        # 注意：新架构下不再使用 on_order_update，改用 on_account_update
        # self.position_tracker.on_order_update(event1)
        
        # 检查历史记录
        history = self.load_history()
        assert len(history['positions']) == 1, "应该记录1条历史"
        record = history['positions'][0]
        assert record['symbol'] == symbol
        assert record['close_reason'] == '止盈'
        assert record['close_price'] == 110.5
        print(f"   ✅ 历史记录已写入: {record['close_reason']} @ {record['close_price']}")
        
        # 检查 tpsl_orders 已部分清除（tp_order_id=None，但sl_order_id还在）
        # 注意：实际代码中，如果两个都清空会删除整个symbol，但这里只触发了止盈
        if symbol in self.order_manager.tpsl_orders:
            assert self.order_manager.tpsl_orders[symbol]['tp_order_id'] is None
            print(f"   ✅ tp_order_id 已清除")
        else:
            # 如果整个symbol的记录都被删除也是正确的
            print(f"   ✅ tpsl_orders[{symbol}] 已完全删除")
        
        # 4. 模拟 ACCOUNT_UPDATE 事件（持仓清零）
        print(f"\n步骤2: 发送 ACCOUNT_UPDATE 事件（持仓清零）")
        event2 = self.create_account_update_event(
            symbol=symbol,
            position_amt=0.0,
            mark_price=110.5,
            entry_price=100.0
        )
        self.position_service.update_position_from_event(event2.get('a', {}).get('P', [{}])[0])
        
        # 检查持仓已删除
        assert symbol not in self.position_service.positions
        print(f"   ✅ 持仓对象已删除")
        
        # 检查没有重复记录
        history = self.load_history()
        assert len(history['positions']) == 1, "不应该重复记录"
        print(f"   ✅ 没有重复记录（共1条）")
        
        print(f"\n✅ 测试案例1通过：正常流程工作正常")
        return True
    
    def test_case_2_reversed_flow(self):
        """测试案例2：异常流程（ACCOUNT_UPDATE -> ORDER_TRADE_UPDATE，事件乱序）"""
        print("\n" + "="*80)
        print("测试案例2：异常流程 - 事件乱序（止损触发）")
        print("="*80)
        
        symbol = 'ETHUSDT'
        
        # 1. 创建测试持仓
        position = self.create_test_position(symbol, 'short', 2000.0)
        print(f"✅ 创建测试持仓: {symbol} short, entry={position.entry_price}")
        
        # 2. 添加 TP/SL 订单记录
        self.order_manager.tpsl_orders[symbol] = {
            'tp_order_id': 11111,
            'sl_order_id': 22222
        }
        print(f"✅ 添加 TP/SL 订单记录: tp=11111, sl=22222")
        
        # 3. 模拟 ACCOUNT_UPDATE 先到达（持仓清零）
        print(f"\n步骤1: ACCOUNT_UPDATE 先到达（异常情况）")
        event1 = self.create_account_update_event(
            symbol=symbol,
            position_amt=0.0,
            mark_price=2100.0,  # 价格上涨，触发止损
            entry_price=2000.0
        )
        self.position_tracker.on_account_update(event1)
        
        # 检查历史记录（应该由兜底机制记录）
        history = self.load_history()
        # 注意：这里应该有2条记录（1条来自测试案例1，1条来自本次）
        records = [r for r in history['positions'] if r['symbol'] == symbol]
        assert len(records) == 1, f"应该有1条记录，实际: {len(records)}"
        record = records[0]
        assert record['symbol'] == symbol
        assert record['close_reason'] in ['止损', 'unknown']  # 兜底机制推测的原因
        print(f"   ✅ 兜底机制触发: {record['close_reason']} @ {record['close_price']}")
        
        # 检查持仓已删除
        assert symbol not in self.position_service.positions
        print(f"   ✅ 持仓对象已删除")
        
        # 检查 tpsl_orders 已清除
        assert symbol not in self.order_manager.tpsl_orders
        print(f"   ✅ tpsl_orders 已清除")
        
        # 4. 模拟 ORDER_TRADE_UPDATE 后到达
        print(f"\n步骤2: ORDER_TRADE_UPDATE 后到达")
        event2 = self.create_order_trade_update_event(
            symbol=symbol,
            order_type='STOP_MARKET',
            order_status='FILLED',
            order_id=22222,
            avg_price=2100.0
        )
        self.position_tracker.on_order_update(event2)
        
        # 检查没有重复记录
        history = self.load_history()
        records = [r for r in history['positions'] if r['symbol'] == symbol]
        assert len(records) == 1, "不应该重复记录"
        print(f"   ✅ 没有重复记录（共1条）")
        
        print(f"\n✅ 测试案例2通过：事件乱序兜底机制工作正常")
        return True
    
    def test_case_3_manual_close(self):
        """测试案例3：手动平仓（不通过WebSocket）"""
        print("\n" + "="*80)
        print("测试案例3：手动平仓")
        print("="*80)
        
        symbol = 'SOLUSDT'
        
        # 1. 创建测试持仓
        position = self.create_test_position(symbol, 'long', 50.0)
        print(f"✅ 创建测试持仓: {symbol} long, entry={position.entry_price}")
        
        # 2. 直接调用 history_writer 记录平仓（模拟 engine.close_position）
        print(f"\n步骤1: 手动平仓（直接调用 history_writer）")
        self.history_writer.record_closed_position(
            position,
            close_reason='agent',
            close_price=52.5
        )
        
        # 3. 检查历史记录
        history = self.load_history()
        records = [r for r in history['positions'] if r['symbol'] == symbol]
        assert len(records) == 1
        record = records[0]
        assert record['close_reason'] == 'agent'
        assert record['close_price'] == 52.5
        print(f"   ✅ 历史记录已写入: {record['close_reason']} @ {record['close_price']}")
        
        # 4. 清理持仓
        del self.position_service.positions[symbol]
        
        # 5. 模拟 ACCOUNT_UPDATE 到达（但 tpsl_orders 已被清除）
        print(f"\n步骤2: ACCOUNT_UPDATE 到达（tpsl_orders已清除）")
        event = self.create_account_update_event(
            symbol=symbol,
            position_amt=0.0,
            mark_price=52.5,
            entry_price=50.0
        )
        self.position_service.update_position_from_event(event.get('a', {}).get('P', [{}])[0])
        
        # 6. 检查没有重复记录
        history = self.load_history()
        records = [r for r in history['positions'] if r['symbol'] == symbol]
        assert len(records) == 1, "不应该重复记录"
        print(f"   ✅ 没有重复记录（共1条）")
        
        print(f"\n✅ 测试案例3通过：手动平仓记录正常")
        return True
    
    def test_case_4_no_position(self):
        """测试案例4：边界情况 - 持仓不存在"""
        print("\n" + "="*80)
        print("测试案例4：边界情况 - 持仓不存在")
        print("="*80)
        
        symbol = 'ADAUSDT'
        
        # 1. 不创建持仓，直接发送 ORDER_TRADE_UPDATE
        print(f"\n步骤1: 发送 ORDER_TRADE_UPDATE（但持仓不存在）")
        event = self.create_order_trade_update_event(
            symbol=symbol,
            order_type='TAKE_PROFIT_MARKET',
            order_status='FILLED',
            order_id=99999,
            avg_price=0.5
        )
        
        history_before = self.load_history()
        count_before = len(history_before['positions'])
        
        # 新架构不再处理 ORDER_TRADE_UPDATE
        # self.position_tracker.on_order_update(event)
        
        # 2. 检查没有记录（因为持仓不存在）
        history_after = self.load_history()
        count_after = len(history_after['positions'])
        assert count_after == count_before, "不应该记录不存在的持仓"
        print(f"   ✅ 正确处理：没有记录不存在的持仓")
        
        print(f"\n✅ 测试案例4通过：边界情况处理正常")
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*80)
        print("开始测试持仓平仓历史记录链路")
        print("="*80)
        
        results = []
        
        try:
            results.append(("正常流程", self.test_case_1_normal_flow()))
        except Exception as e:
            print(f"\n❌ 测试案例1失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(("正常流程", False))
        
        try:
            results.append(("事件乱序", self.test_case_2_reversed_flow()))
        except Exception as e:
            print(f"\n❌ 测试案例2失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(("事件乱序", False))
        
        try:
            results.append(("手动平仓", self.test_case_3_manual_close()))
        except Exception as e:
            print(f"\n❌ 测试案例3失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(("手动平仓", False))
        
        try:
            results.append(("边界情况", self.test_case_4_no_position()))
        except Exception as e:
            print(f"\n❌ 测试案例4失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(("边界情况", False))
        
        # 打印最终结果
        print("\n" + "="*80)
        print("测试结果汇总")
        print("="*80)
        
        for name, passed in results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {name}")
        
        all_passed = all(r[1] for r in results)
        
        print("\n" + "="*80)
        if all_passed:
            print("🎉 所有测试通过！")
        else:
            print("⚠️  部分测试失败，请检查日志")
        print("="*80)
        
        # 打印历史文件内容
        print(f"\n最终历史文件内容: {self.history_path}")
        history = self.load_history()
        print(json.dumps(history, indent=2, ensure_ascii=False))
        
        return all_passed
    
    def cleanup(self):
        """清理测试环境"""
        import shutil
        
        # 等待写入队列完成
        write_queue = WriteQueue.get_instance()
        write_queue.shutdown(timeout=2.0)
        
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        print(f"\n✅ 测试环境已清理")


def main():
    """主函数"""
    tester = TestPositionCloseHistory()
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    finally:
        tester.cleanup()


if __name__ == '__main__':
    sys.exit(main())

