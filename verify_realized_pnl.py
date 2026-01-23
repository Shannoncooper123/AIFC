#!/usr/bin/env python3
"""
脚本用于验证 position_history.json 中的 realized_pnl 计算逻辑
"""
import json
from typing import Dict, List, Tuple


def calculate_realized_pnl(position: Dict) -> Tuple[float, Dict]:
    """
    计算仓位的 realized_pnl
    
    对于多头仓位:
        pnl = (close_price - entry_price) * quantity - fees_open - fees_close
        其中 quantity = notional_usdt / entry_price
    
    对于空头仓位:
        pnl = (entry_price - close_price) * quantity - fees_open - fees_close
        其中 quantity = notional_usdt / entry_price
    
    Returns:
        (计算的pnl, 详细信息字典)
    """
    entry_price = position['entry_price']
    close_price = position['close_price']
    notional_usdt = position['notional_usdt']
    fees_open = position['fees_open']
    fees_close = position['fees_close']
    side = position['side']
    leverage = position.get('leverage', 10)
    
    # 计算数量 (币的数量)
    quantity = notional_usdt / entry_price
    
    # 计算价格差带来的盈亏
    if side == 'long':
        price_pnl = (close_price - entry_price) * quantity
    elif side == 'short':
        price_pnl = (entry_price - close_price) * quantity
    else:
        raise ValueError(f"Unknown side: {side}")
    
    # 减去手续费得到最终 realized_pnl
    calculated_pnl = price_pnl - fees_open - fees_close
    
    details = {
        'entry_price': entry_price,
        'close_price': close_price,
        'notional_usdt': notional_usdt,
        'quantity': quantity,
        'price_diff': close_price - entry_price if side == 'long' else entry_price - close_price,
        'price_pnl': price_pnl,
        'fees_open': fees_open,
        'fees_close': fees_close,
        'total_fees': fees_open + fees_close,
        'calculated_pnl': calculated_pnl,
        'side': side,
        'leverage': leverage
    }
    
    return calculated_pnl, details


def verify_position_history(file_path: str, tolerance: float = 1e-6) -> Dict:
    """
    验证 position_history.json 文件中所有仓位的 realized_pnl
    
    Args:
        file_path: position_history.json 文件路径
        tolerance: 允许的误差范围
    
    Returns:
        验证结果统计
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    positions = data['positions']
    
    results = {
        'total': len(positions),
        'with_fees_correct': 0,
        'without_fees_correct': 0,
        'both_wrong': 0,
        'errors': []
    }
    
    print(f"开始验证 {len(positions)} 个仓位的 realized_pnl 计算...\n")
    print("=" * 120)
    
    for idx, position in enumerate(positions):
        position_id = position['id']
        symbol = position['symbol']
        recorded_pnl = position['realized_pnl']
        
        try:
            calculated_pnl, details = calculate_realized_pnl(position)
            
            # 计算两种可能：含手续费和不含手续费
            pnl_with_fees = calculated_pnl
            pnl_without_fees = details['price_pnl']  # 价格盈亏本身不含手续费
            
            diff_with_fees = abs(pnl_with_fees - recorded_pnl)
            diff_without_fees = abs(pnl_without_fees - recorded_pnl)
            
            is_correct_with_fees = diff_with_fees <= tolerance
            is_correct_without_fees = diff_without_fees <= tolerance
            
            if is_correct_with_fees:
                results['with_fees_correct'] += 1
                status = "✅ 正确 (含手续费)"
            elif is_correct_without_fees:
                results['without_fees_correct'] += 1
                status = "✅ 正确 (不含手续费)"
            else:
                results['both_wrong'] += 1
                status = "❌ 错误"
                results['errors'].append({
                    'position_id': position_id,
                    'symbol': symbol,
                    'recorded_pnl': recorded_pnl,
                    'pnl_with_fees': pnl_with_fees,
                    'pnl_without_fees': pnl_without_fees,
                    'diff_with_fees': diff_with_fees,
                    'diff_without_fees': diff_without_fees,
                    'details': details
                })
            
            # 打印每个仓位的验证结果
            print(f"仓位 #{idx + 1} [{position_id}] {symbol} - {status}")
            print(f"  方向: {details['side']}")
            print(f"  开仓价: {details['entry_price']:.8f}, 平仓价: {details['close_price']:.8f}")
            print(f"  名义金额: {details['notional_usdt']:.2f} USDT, 数量: {details['quantity']:.4f}")
            print(f"  价格差: {details['price_diff']:.8f} -> 价格盈亏: {details['price_pnl']:.8f} USDT")
            print(f"  总手续费: {details['total_fees']:.8f} USDT (开仓: {details['fees_open']:.8f}, 平仓: {details['fees_close']:.8f})")
            print(f"  记录的 PNL: {recorded_pnl:.8f} USDT")
            print(f"  计算的 PNL (含手续费): {pnl_with_fees:.8f} USDT (差异: {diff_with_fees:.10f})")
            print(f"  计算的 PNL (不含手续费): {pnl_without_fees:.8f} USDT (差异: {diff_without_fees:.10f})")
            
            print("-" * 120)
            
        except Exception as e:
            results['errors'].append({
                'position_id': position_id,
                'symbol': symbol,
                'error': str(e)
            })
            print(f"仓位 #{idx + 1} [{position_id}] {symbol} - ❌ 计算出错: {e}")
            print("-" * 120)
    
    # 打印汇总结果
    print("\n" + "=" * 120)
    print("验证结果汇总:")
    print("=" * 120)
    print(f"总仓位数: {results['total']}")
    print(f"✅ 含手续费计算正确: {results['with_fees_correct']} ({results['with_fees_correct']/results['total']*100:.2f}%)")
    print(f"✅ 不含手续费计算正确: {results['without_fees_correct']} ({results['without_fees_correct']/results['total']*100:.2f}%)")
    print(f"❌ 两种方式都不对: {results['both_wrong']} ({results['both_wrong']/results['total']*100:.2f}%)")
    
    # 判断使用的计算方式
    if results['without_fees_correct'] == results['total']:
        print("\n🎯 结论: realized_pnl 的计算逻辑是 **不包含手续费** 的")
        print("   公式: realized_pnl = (close_price - entry_price) * quantity")
    elif results['with_fees_correct'] == results['total']:
        print("\n🎯 结论: realized_pnl 的计算逻辑是 **包含手续费** 的")
        print("   公式: realized_pnl = (close_price - entry_price) * quantity - fees_open - fees_close")
    else:
        print("\n⚠️ 警告: 存在计算逻辑不一致的情况!")
    
    # 如果有错误，详细列出
    if results['errors']:
        print("\n" + "=" * 120)
        print("错误详情 (两种方式都不匹配的仓位):")
        print("=" * 120)
        for error in results['errors']:
            if 'error' in error:
                print(f"\n仓位 [{error['position_id']}] {error['symbol']}")
                print(f"  错误: {error['error']}")
            else:
                print(f"\n仓位 [{error['position_id']}] {error['symbol']}")
                print(f"  记录的 PNL: {error['recorded_pnl']:.8f} USDT")
                print(f"  计算的 PNL (含手续费): {error['pnl_with_fees']:.8f} USDT (差异: {error['diff_with_fees']:.10f})")
                print(f"  计算的 PNL (不含手续费): {error['pnl_without_fees']:.8f} USDT (差异: {error['diff_without_fees']:.10f})")
    
    return results


def main():
    """主函数"""
    import sys
    
    # 默认文件路径
    default_file = '/home/sunfayao/monitor/logs/position_history.json'
    
    # 如果命令行提供了文件路径，则使用提供的路径
    file_path = sys.argv[1] if len(sys.argv) > 1 else default_file
    
    print(f"正在验证文件: {file_path}\n")
    
    try:
        results = verify_position_history(file_path)
        
        # 根据验证结果返回适当的退出码
        if results['both_wrong'] == 0:
            if results['without_fees_correct'] == results['total']:
                print("\n✅ 所有仓位的 realized_pnl 计算都正确！(不含手续费)")
            elif results['with_fees_correct'] == results['total']:
                print("\n✅ 所有仓位的 realized_pnl 计算都正确！(含手续费)")
            sys.exit(0)
        else:
            print(f"\n❌ 发现 {results['both_wrong']} 个仓位的 realized_pnl 计算有误！")
            sys.exit(1)
    
    except FileNotFoundError:
        print(f"❌ 错误: 找不到文件 {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ 错误: JSON 解析失败 - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
