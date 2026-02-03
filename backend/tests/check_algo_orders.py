"""检查当前账户的条件单数量

运行方式：
    cd /Users/bytedance/Desktop/crypto_agentx/backend
    python -m tests.check_algo_orders
"""

import os
import time
import hmac
import hashlib
from collections import defaultdict
from dotenv import load_dotenv
import requests

load_dotenv()

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
BASE_URL = 'https://fapi.binance.com'


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


def main():
    print("=" * 70)
    print("Binance 条件单数量检查")
    print("=" * 70)
    
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("❌ 请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return
    
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
    
    print("\n" + "=" * 70)
    print("限制说明:")
    print("  - 每个交易对最多 10 个条件单")
    print("  - 账户总计最多 100 个条件单")
    print("  - 每个开仓记录会占用 2 个条件单（止盈 + 止损）")
    print("=" * 70)


if __name__ == '__main__':
    main()
