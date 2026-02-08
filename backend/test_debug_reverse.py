#!/usr/bin/env python3
"""测试智能下单逻辑（限价单 vs 条件单）"""
import sys
sys.path.insert(0, '.')

from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
from modules.agent.engine import set_engine, reset_context_engine
from modules.agent.tools.create_limit_order_tool import create_limit_order_tool

config = {
    'api': {'base_url': 'https://fapi.binance.com', 'timeout': 30, 'retry_times': 3},
    'websocket': {'url': 'wss://fstream.binance.com', 'max_streams_per_connection': 200, 'reconnect_delay': 5},
    'agent': {'simulator': {'initial_balance': 10000.0, 'max_leverage': 10}, 'disable_persistence': True},
    'trading': {'fixed_margin_usdt': 50.0, 'max_leverage': 10}
}

def test_smart_order():
    """测试智能下单：根据当前价格自动选择限价单或条件单"""
    
    print('=' * 70)
    print('智能下单测试：限价单 (Maker) vs 条件单 (Taker)')
    print('=' * 70)
    
    # 场景 1: 做多，当前价格高于触发价 → 应该创建限价单
    print('\n📌 测试 1: 做多，当前价 > 触发价 → 限价单 (Maker)')
    print('   当前价: 0.32, 触发价: 0.30')
    engine = BacktestTradeEngine(config=config, backtest_id='test1', initial_balance=10000.0, 
                                  fixed_margin_usdt=50.0, fixed_leverage=10, reverse_mode=False)
    engine.start()
    engine.set_simulated_price('TESTUSDT', 0.32)
    
    token = set_engine(engine, thread_local=True)
    try:
        create_limit_order_tool.invoke({
            'symbol': 'TESTUSDT', 'side': 'BUY', 'limit_price': 0.30, 
            'tp_price': 0.35, 'sl_price': 0.28
        })
        order = list(engine.limit_order_manager.orders.values())[0]
        if order.order_kind == 'LIMIT':
            print('   ✅ 正确：创建了限价单 (Maker)')
        else:
            print(f'   ❌ 错误：应该是限价单，实际是 {order.order_kind}')
    finally:
        reset_context_engine(token)
        engine.stop()
    
    # 场景 2: 做多，当前价格低于触发价 → 应该创建条件单
    print('\n📌 测试 2: 做多，当前价 < 触发价 → 条件单 (Taker)')
    print('   当前价: 0.28, 触发价: 0.30')
    engine = BacktestTradeEngine(config=config, backtest_id='test2', initial_balance=10000.0,
                                  fixed_margin_usdt=50.0, fixed_leverage=10, reverse_mode=False)
    engine.start()
    engine.set_simulated_price('TESTUSDT', 0.28)
    
    token = set_engine(engine, thread_local=True)
    try:
        create_limit_order_tool.invoke({
            'symbol': 'TESTUSDT', 'side': 'BUY', 'limit_price': 0.30,
            'tp_price': 0.35, 'sl_price': 0.28
        })
        order = list(engine.limit_order_manager.orders.values())[0]
        if order.order_kind == 'CONDITIONAL':
            print('   ✅ 正确：创建了条件单 (Taker)')
        else:
            print(f'   ❌ 错误：应该是条件单，实际是 {order.order_kind}')
    finally:
        reset_context_engine(token)
        engine.stop()
    
    # 场景 3: 做空，当前价格低于触发价 → 应该创建限价单
    print('\n📌 测试 3: 做空，当前价 < 触发价 → 限价单 (Maker)')
    print('   当前价: 0.28, 触发价: 0.30')
    engine = BacktestTradeEngine(config=config, backtest_id='test3', initial_balance=10000.0,
                                  fixed_margin_usdt=50.0, fixed_leverage=10, reverse_mode=False)
    engine.start()
    engine.set_simulated_price('TESTUSDT', 0.28)
    
    token = set_engine(engine, thread_local=True)
    try:
        create_limit_order_tool.invoke({
            'symbol': 'TESTUSDT', 'side': 'SELL', 'limit_price': 0.30,
            'tp_price': 0.25, 'sl_price': 0.32
        })
        order = list(engine.limit_order_manager.orders.values())[0]
        if order.order_kind == 'LIMIT':
            print('   ✅ 正确：创建了限价单 (Maker)')
        else:
            print(f'   ❌ 错误：应该是限价单，实际是 {order.order_kind}')
    finally:
        reset_context_engine(token)
        engine.stop()
    
    # 场景 4: 做空，当前价格高于触发价 → 应该创建条件单
    print('\n📌 测试 4: 做空，当前价 > 触发价 → 条件单 (Taker)')
    print('   当前价: 0.32, 触发价: 0.30')
    engine = BacktestTradeEngine(config=config, backtest_id='test4', initial_balance=10000.0,
                                  fixed_margin_usdt=50.0, fixed_leverage=10, reverse_mode=False)
    engine.start()
    engine.set_simulated_price('TESTUSDT', 0.32)
    
    token = set_engine(engine, thread_local=True)
    try:
        create_limit_order_tool.invoke({
            'symbol': 'TESTUSDT', 'side': 'SELL', 'limit_price': 0.30,
            'tp_price': 0.25, 'sl_price': 0.32
        })
        order = list(engine.limit_order_manager.orders.values())[0]
        if order.order_kind == 'CONDITIONAL':
            print('   ✅ 正确：创建了条件单 (Taker)')
        else:
            print(f'   ❌ 错误：应该是条件单，实际是 {order.order_kind}')
    finally:
        reset_context_engine(token)
        engine.stop()
    
    print('\n' + '=' * 70)
    print('测试完成!')
    print('=' * 70)

if __name__ == '__main__':
    test_smart_order()
