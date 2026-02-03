"""检查当前账户的条件单数量，并测试超过限制时的情况

运行方式：
    cd /Users/bytedance/Desktop/crypto_agentx/backend
    python -m tests.check_algo_orders
"""

import os
import time
import hmac
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests

load_dotenv()

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
BASE_URL = 'https://fapi.binance.com'

SYMBOL = 'DOGEUSDT'
QUANTITY = 100
TRIGGER_PRICE = 0.12


def sign_request(params: dict) -> str:
    """生成请求签名"""
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(
        BINANCE_API_SECRET.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


def get_headers() -> dict:
    """获取请求头"""
    return {
        'X-MBX-APIKEY': BINANCE_API_KEY,
        'Content-Type': 'application/x-www-form-urlencoded'
    }


def get_algo_open_orders() -> list:
    """获取所有活跃的条件单"""
    url = f"{BASE_URL}/fapi/v1/openAlgoOrders"
    params = {'timestamp': int(time.time() * 1000)}
    params['signature'] = sign_request(params)
    
    response = requests.get(url, params=params, headers=get_headers())
    response.raise_for_status()
    return response.json()


def create_conditional_order(symbol: str, trigger_price: float, quantity: float) -> dict:
    """创建做多条件单"""
    url = f"{BASE_URL}/fapi/v1/algoOrder"
    
    expiration_ms = int((datetime.now() + timedelta(days=1)).timestamp() * 1000)
    
    params = {
        'symbol': symbol,
        'side': 'BUY',
        'algoType': 'CONDITIONAL',
        'triggerPrice': trigger_price,
        'quantity': quantity,
        'type': 'STOP_MARKET',
        'workingType': 'CONTRACT_PRICE',
        'positionSide': 'LONG',
        'goodTillDate': expiration_ms,
        'timestamp': int(time.time() * 1000)
    }
    params['signature'] = sign_request(params)
    
    response = requests.post(url, params=params, headers=get_headers())
    return {
        'success': response.ok,
        'status_code': response.status_code,
        'response': response.json() if response.ok else response.text
    }


def cancel_algo_order(algo_id: int) -> bool:
    """取消条件单"""
    url = f"{BASE_URL}/fapi/v1/algoOrder"
    params = {
        'algoId': algo_id,
        'timestamp': int(time.time() * 1000)
    }
    params['signature'] = sign_request(params)
    
    response = requests.delete(url, params=params, headers=get_headers())
    return response.ok


def show_current_orders():
    """显示当前条件单"""
    orders = get_algo_open_orders()
    
    print(f"\n📊 总条件单数量: {len(orders)}")
    print(f"   账户限制: 100 个")
    print()
    
    by_symbol = defaultdict(list)
    for order in orders:
        symbol = order.get('symbol', 'UNKNOWN')
        by_symbol[symbol].append(order)
    
    print("按交易对分组:")
    print("-" * 50)
    for symbol, symbol_orders in sorted(by_symbol.items()):
        print(f"\n📈 {symbol}: {len(symbol_orders)} 个条件单 (限制: 10 个)")
        for order in symbol_orders:
            algo_id = order.get('algoId')
            side = order.get('side')
            order_type = order.get('type')
            trigger_price = order.get('triggerPrice')
            status = order.get('algoStatus')
            position_side = order.get('positionSide', 'BOTH')
            
            print(f"    - algoId={algo_id} | {side} {position_side} | "
                  f"type={order_type} | trigger={trigger_price} | status={status}")
    
    return orders, by_symbol


def main():
    print("=" * 70)
    print("Binance 条件单数量检查 & 超限测试")
    print("=" * 70)
    
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("❌ 请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return
    
    orders, by_symbol = show_current_orders()
    
    current_count = len(by_symbol.get(SYMBOL, []))
    remaining = 10 - current_count
    
    print("\n" + "=" * 70)
    print(f"📋 {SYMBOL} 当前条件单: {current_count}/10")
    print(f"   还可创建: {remaining} 个")
    print("=" * 70)
    
    print(f"\n🧪 测试: 尝试创建条件单直到超过限制")
    print(f"   交易对: {SYMBOL}")
    print(f"   触发价: {TRIGGER_PRICE}")
    print(f"   方向: BUY LONG")
    
    print(f"\n要创建多少个条件单来测试? (输入数字，或 'q' 退出): ", end='')
    choice = input().strip()
    
    if choice.lower() == 'q':
        print("已退出")
        return
    
    try:
        num_to_create = int(choice)
    except ValueError:
        print("无效输入")
        return
    
    created_orders = []
    
    print(f"\n开始创建 {num_to_create} 个条件单...")
    print("-" * 50)
    
    for i in range(num_to_create):
        trigger = TRIGGER_PRICE + (i * 0.001)
        print(f"\n[{i+1}/{num_to_create}] 创建条件单 @ {trigger}...")
        
        result = create_conditional_order(SYMBOL, trigger, QUANTITY)
        
        if result['success']:
            algo_id = result['response'].get('algoId')
            print(f"    ✅ 成功! algoId={algo_id}")
            created_orders.append(algo_id)
        else:
            print(f"    ❌ 失败!")
            print(f"    状态码: {result['status_code']}")
            print(f"    响应: {result['response']}")
            
            if '-4131' in str(result['response']):
                print("\n    ⚠️  错误码 -4131: 超过该交易对的条件单数量限制 (10个)")
            elif '-4132' in str(result['response']):
                print("\n    ⚠️  错误码 -4132: 超过账户总条件单数量限制 (100个)")
        
        time.sleep(0.3)
    
    print("\n" + "=" * 70)
    print("测试结果")
    print("=" * 70)
    print(f"成功创建: {len(created_orders)} 个")
    print(f"失败: {num_to_create - len(created_orders)} 个")
    
    print("\n当前条件单状态:")
    show_current_orders()
    
    if created_orders:
        print(f"\n是否取消本次测试创建的 {len(created_orders)} 个条件单? (y/n): ", end='')
        choice = input().strip().lower()
        
        if choice == 'y':
            print("\n正在取消...")
            for algo_id in created_orders:
                if cancel_algo_order(algo_id):
                    print(f"    ✅ 已取消 algoId={algo_id}")
                else:
                    print(f"    ❌ 取消失败 algoId={algo_id}")
            
            print("\n取消后的条件单状态:")
            show_current_orders()
        else:
            print(f"\n⚠️  条件单未取消，请手动在 Binance 取消")
    
    print("\n" + "=" * 70)
    print("限制说明:")
    print("  - 每个交易对最多 10 个条件单 (错误码: -4131)")
    print("  - 账户总计最多 100 个条件单 (错误码: -4132)")
    print("  - 每个开仓记录会占用 2 个条件单（止盈 + 止损）")
    print("=" * 70)


if __name__ == '__main__':
    main()
