"""测试查询历史订单和成交记录的数据结构

目的：
1. 从 position_history.json 中选取一些已平仓的持仓
2. 查询这些持仓的历史订单和成交记录
3. 分析返回的数据结构，为简化平仓检测做准备
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import load_config, get_config
from monitor_module.clients.binance_rest import BinanceRestClient


def load_position_history():
    """加载历史持仓记录"""
    history_path = 'logs/position_history.json'
    if not os.path.exists(history_path):
        return []
    
    with open(history_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('positions', [])


def load_current_positions():
    """加载当前持仓"""
    state_path = 'agent/trade_state.json'
    if not os.path.exists(state_path):
        return {}
    
    with open(state_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('positions', {})


def query_symbol_history(client: BinanceRestClient, symbol: str, position_record: dict):
    """查询某个币种的历史订单和成交"""
    print(f"\n{'='*80}")
    print(f"查询 {symbol} 的历史数据")
    print(f"{'='*80}")
    
    # 解析持仓时间范围
    open_time = position_record.get('open_time')
    close_time = position_record.get('close_time')
    
    if open_time:
        open_dt = datetime.fromisoformat(open_time.replace('Z', '+00:00'))
        # 向前延伸1小时
        start_time = int((open_dt - timedelta(hours=1)).timestamp() * 1000)
    else:
        # 默认查询最近7天
        start_time = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
    
    if close_time:
        close_dt = datetime.fromisoformat(close_time.replace('Z', '+00:00'))
        # 向后延伸1小时
        end_time = int((close_dt + timedelta(hours=1)).timestamp() * 1000)
    else:
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    print(f"\n持仓信息:")
    print(f"  开仓时间: {open_time}")
    print(f"  平仓时间: {close_time}")
    print(f"  方向: {position_record.get('side')}")
    print(f"  入场价: {position_record.get('entry_price')}")
    print(f"  平仓价: {position_record.get('close_price')}")
    print(f"  平仓原因: {position_record.get('close_reason')}")
    print(f"  止盈价: {position_record.get('tp_price')}")
    print(f"  止损价: {position_record.get('sl_price')}")
    
    # 1. 查询历史订单
    print(f"\n{'─'*80}")
    print("1. 查询历史订单 (allOrders)")
    print(f"{'─'*80}")
    try:
        orders = client.get_all_orders(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=100
        )
        
        print(f"\n找到 {len(orders)} 个订单:")
        for i, order in enumerate(orders[:5], 1):  # 只显示前5个
            print(f"\n  订单 #{i}:")
            print(f"    订单ID: {order.get('orderId')}")
            print(f"    类型: {order.get('type')}")
            print(f"    方向: {order.get('side')}")
            print(f"    状态: {order.get('status')}")
            print(f"    数量: {order.get('origQty')}")
            print(f"    成交数量: {order.get('executedQty')}")
            print(f"    价格: {order.get('price')}")
            print(f"    成交均价: {order.get('avgPrice')}")
            print(f"    止损价: {order.get('stopPrice')}")
            print(f"    创建时间: {datetime.fromtimestamp(order.get('time', 0)/1000, tz=timezone.utc)}")
            print(f"    更新时间: {datetime.fromtimestamp(order.get('updateTime', 0)/1000, tz=timezone.utc)}")
        
        if len(orders) > 5:
            print(f"\n  ... 还有 {len(orders) - 5} 个订单未显示")
        
        # 保存完整数据到文件
        output_file = f'tests/output_history_{symbol}_orders.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)
        print(f"\n✅ 完整订单数据已保存到: {output_file}")
    
    except Exception as e:
        print(f"❌ 查询订单失败: {e}")
    
    # 2. 查询成交记录
    print(f"\n{'─'*80}")
    print("2. 查询成交记录 (userTrades)")
    print(f"{'─'*80}")
    try:
        trades = client.get_user_trades(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=100
        )
        
        print(f"\n找到 {len(trades)} 笔成交:")
        for i, trade in enumerate(trades[:5], 1):  # 只显示前5笔
            print(f"\n  成交 #{i}:")
            print(f"    成交ID: {trade.get('id')}")
            print(f"    订单ID: {trade.get('orderId')}")
            print(f"    方向: {trade.get('side')}")
            print(f"    价格: {trade.get('price')}")
            print(f"    数量: {trade.get('qty')}")
            print(f"    手续费: {trade.get('commission')} {trade.get('commissionAsset')}")
            print(f"    成交时间: {datetime.fromtimestamp(trade.get('time', 0)/1000, tz=timezone.utc)}")
            print(f"    是否Maker: {trade.get('maker')}")
        
        if len(trades) > 5:
            print(f"\n  ... 还有 {len(trades) - 5} 笔成交未显示")
        
        # 保存完整数据到文件
        output_file = f'tests/output_history_{symbol}_trades.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
        print(f"\n✅ 完整成交数据已保存到: {output_file}")
    
    except Exception as e:
        print(f"❌ 查询成交失败: {e}")


def main():
    print("="*80)
    print("历史订单和成交数据结构测试")
    print("="*80)
    
    # 加载配置
    load_config()
    config = get_config()
    client = BinanceRestClient(config)
    
    # 加载历史持仓
    history_positions = load_position_history()
    print(f"\n历史持仓总数: {len(history_positions)}")
    
    # 加载当前持仓
    current_positions = load_current_positions()
    print(f"当前持仓总数: {len(current_positions)}")
    
    # 选择一些有止盈止损的历史持仓进行测试
    print(f"\n{'='*80}")
    print("选择测试样本:")
    print(f"{'='*80}")
    
    test_samples = []
    
    # 1. 找一个止盈平仓的
    for pos in reversed(history_positions):  # 从最新的开始找
        if pos.get('close_reason') == '止盈':
            test_samples.append(('止盈平仓', pos))
            print(f"\n✓ 找到止盈平仓样本: {pos['symbol']}")
            break
    
    # 2. 找一个止损平仓的
    for pos in reversed(history_positions):
        if pos.get('close_reason') == '止损':
            test_samples.append(('止损平仓', pos))
            print(f"✓ 找到止损平仓样本: {pos['symbol']}")
            break
    
    # 3. 找一个手动平仓的
    for pos in reversed(history_positions):
        if pos.get('close_reason') == 'agent':
            test_samples.append(('手动平仓', pos))
            print(f"✓ 找到手动平仓样本: {pos['symbol']}")
            break
    
    # 4. 找一个当前持仓
    if current_positions:
        symbol = list(current_positions.keys())[0]
        pos = current_positions[symbol]
        pos['symbol'] = symbol  # 添加 symbol 字段
        test_samples.append(('当前持仓', pos))
        print(f"✓ 找到当前持仓样本: {symbol}")
    
    if not test_samples:
        print("\n❌ 没有找到合适的测试样本")
        return
    
    # 查询每个样本的数据
    for label, pos in test_samples:
        symbol = pos.get('symbol')
        if not symbol:
            continue
        
        print(f"\n\n{'#'*80}")
        print(f"# {label}: {symbol}")
        print(f"{'#'*80}")
        
        query_symbol_history(client, symbol, pos)
    
    print(f"\n\n{'='*80}")
    print("测试完成!")
    print(f"{'='*80}")
    print("\n数据文件已保存到 tests/ 目录，文件名格式:")
    print("  - output_history_{SYMBOL}_orders.json  (历史订单)")
    print("  - output_history_{SYMBOL}_trades.json  (成交记录)")


if __name__ == '__main__':
    main()

