"""测试 Binance 双向持仓模式下的条件单类型

验证逻辑：
- BUY LONG（做多开仓）: 使用 STOP_MARKET
- SELL SHORT（做空开仓）: 使用 TAKE_PROFIT_MARKET

测试场景：
1. 在 0.09 创建 DOGEUSDT 做多条件单 (当前价格上方)
2. 在 0.09 创建 DOGEUSDT 做空条件单 (当前价格上方)
3. 在 0.12 创建 DOGEUSDT 做多条件单 (当前价格下方)
4. 在 0.12 创建 DOGEUSDT 做空条件单 (当前价格下方)

运行方式：
    cd /Users/bytedance/Desktop/crypto_agentx/backend
    python -m tests.test_conditional_order_types
"""

import os
import sys
import time
import hmac
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests

load_dotenv()

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
BASE_URL = 'https://fapi.binance.com'

SYMBOL = 'DOGEUSDT'
QUANTITY = 100
LEVERAGE = 10


def sign_request(params: dict) -> str:
    """生成请求签名
    
    注意：Binance 签名需要按参数原始顺序，不能排序
    """
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


def get_mark_price(symbol: str) -> float:
    """获取当前标记价格"""
    url = f"{BASE_URL}/fapi/v1/premiumIndex"
    response = requests.get(url, params={'symbol': symbol})
    response.raise_for_status()
    data = response.json()
    return float(data['markPrice'])


def ensure_dual_position_mode():
    """确保双向持仓模式"""
    url = f"{BASE_URL}/fapi/v1/positionSide/dual"
    params = {'timestamp': int(time.time() * 1000)}
    params['signature'] = sign_request(params)
    
    response = requests.get(url, params=params, headers=get_headers())
    response.raise_for_status()
    data = response.json()
    
    if not data.get('dualSidePosition', False):
        print("⚠️  当前为单向持仓模式，尝试切换为双向持仓模式...")
        params = {
            'dualSidePosition': 'true',
            'timestamp': int(time.time() * 1000)
        }
        params['signature'] = sign_request(params)
        response = requests.post(url, params=params, headers=get_headers())
        if response.ok:
            print("✅ 已切换为双向持仓模式")
        else:
            print(f"❌ 切换失败: {response.text}")
    else:
        print("✅ 已确认为双向持仓模式")


def set_leverage(symbol: str, leverage: int):
    """设置杠杆"""
    url = f"{BASE_URL}/fapi/v1/leverage"
    params = {
        'symbol': symbol,
        'leverage': leverage,
        'timestamp': int(time.time() * 1000)
    }
    params['signature'] = sign_request(params)
    
    response = requests.post(url, params=params, headers=get_headers())
    if response.ok or 'No need to change leverage' in response.text:
        print(f"✅ {symbol} 杠杆已设置为 {leverage}x")
    else:
        print(f"⚠️  设置杠杆: {response.text}")


def create_conditional_order(symbol: str, side: str, position_side: str, 
                             trigger_price: float, order_type: str,
                             quantity: float) -> dict:
    """创建条件单
    
    Args:
        symbol: 交易对
        side: BUY/SELL
        position_side: LONG/SHORT
        trigger_price: 触发价格
        order_type: STOP_MARKET/TAKE_PROFIT_MARKET
        quantity: 数量
    """
    url = f"{BASE_URL}/fapi/v1/algoOrder"
    
    expiration_ms = int((datetime.now() + timedelta(days=1)).timestamp() * 1000)
    
    params = {
        'symbol': symbol,
        'side': side,
        'algoType': 'CONDITIONAL',
        'triggerPrice': trigger_price,
        'quantity': quantity,
        'type': order_type,
        'workingType': 'CONTRACT_PRICE',
        'positionSide': position_side,
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


def test_conditional_orders():
    """测试条件单创建"""
    
    print("=" * 70)
    print("Binance 双向持仓模式条件单类型测试")
    print("=" * 70)
    
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("❌ 请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return
    
    current_price = get_mark_price(SYMBOL)
    print(f"\n📊 当前 {SYMBOL} 标记价格: {current_price}")
    
    ensure_dual_position_mode()
    set_leverage(SYMBOL, LEVERAGE)
    
    # 根据 Binance 条件单触发规则选择正确的订单类型：
    # - STOP_MARKET (BUY): 价格 ≥ trigger 时触发 → 触发价需在当前价上方
    # - STOP_MARKET (SELL): 价格 ≤ trigger 时触发 → 触发价需在当前价下方
    # - TAKE_PROFIT_MARKET (BUY): 价格 ≤ trigger 时触发 → 触发价需在当前价下方
    # - TAKE_PROFIT_MARKET (SELL): 价格 ≥ trigger 时触发 → 触发价需在当前价上方
    
    test_cases = [
        {
            'name': '做多 @ 0.09 (当前价格下方)',
            'trigger_price': 0.09,
            'side': 'BUY',
            'position_side': 'LONG',
            'order_type': 'TAKE_PROFIT_MARKET',  # BUY + 触发价<当前价 → TAKE_PROFIT_MARKET
            'expected': 'BUY + 触发价<当前价 → TAKE_PROFIT_MARKET（等价格跌下来）'
        },
        {
            'name': '做空 @ 0.09 (当前价格下方)',
            'trigger_price': 0.09,
            'side': 'SELL',
            'position_side': 'SHORT',
            'order_type': 'STOP_MARKET',  # SELL + 触发价<当前价 → STOP_MARKET
            'expected': 'SELL + 触发价<当前价 → STOP_MARKET（等价格跌下去）'
        },
        {
            'name': '做多 @ 0.12 (当前价格上方)',
            'trigger_price': 0.12,
            'side': 'BUY',
            'position_side': 'LONG',
            'order_type': 'STOP_MARKET',  # BUY + 触发价>当前价 → STOP_MARKET
            'expected': 'BUY + 触发价>当前价 → STOP_MARKET（等价格涨上去）'
        },
        {
            'name': '做空 @ 0.12 (当前价格上方)',
            'trigger_price': 0.12,
            'side': 'SELL',
            'position_side': 'SHORT',
            'order_type': 'TAKE_PROFIT_MARKET',  # SELL + 触发价>当前价 → TAKE_PROFIT_MARKET
            'expected': 'SELL + 触发价>当前价 → TAKE_PROFIT_MARKET（等价格涨上去）'
        },
    ]
    
    created_orders = []
    
    print("\n" + "=" * 70)
    print("开始测试...")
    print("=" * 70)
    
    for i, tc in enumerate(test_cases, 1):
        print(f"\n--- 测试 {i}: {tc['name']} ---")
        print(f"    触发价: {tc['trigger_price']}")
        print(f"    方向: {tc['side']} {tc['position_side']}")
        print(f"    订单类型: {tc['order_type']}")
        print(f"    预期: {tc['expected']}")
        
        result = create_conditional_order(
            symbol=SYMBOL,
            side=tc['side'],
            position_side=tc['position_side'],
            trigger_price=tc['trigger_price'],
            order_type=tc['order_type'],
            quantity=QUANTITY
        )
        
        if result['success']:
            algo_id = result['response'].get('algoId')
            print(f"    ✅ 创建成功! algoId={algo_id}")
            created_orders.append(algo_id)
        else:
            print(f"    ❌ 创建失败: {result['response']}")
        
        time.sleep(0.5)
    
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    print(f"成功创建: {len(created_orders)}/{len(test_cases)} 个条件单")
    
    if created_orders:
        print("\n是否取消已创建的测试条件单? (y/n): ", end='')
        choice = input().strip().lower()
        
        if choice == 'y':
            print("\n正在取消条件单...")
            for algo_id in created_orders:
                if cancel_algo_order(algo_id):
                    print(f"    ✅ 已取消 algoId={algo_id}")
                else:
                    print(f"    ❌ 取消失败 algoId={algo_id}")
        else:
            print("\n⚠️  条件单未取消，请手动在 Binance 取消")
            print(f"    已创建的 algoIds: {created_orders}")
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)


if __name__ == '__main__':
    test_conditional_orders()
