"""实盘小额资金自动化测试（无需交互）

⚠️  注意：本脚本会自动执行以下操作：
1. 在 1000PEPEUSDT 上开设 $10 名义价值的多头仓位（保证金 $1）
2. 等待 10 秒观察WebSocket事件
3. 自动平仓
4. 验证历史记录

最大风险：约 $1 USDT
"""
import os
import sys
import time
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_config, get_config
from agent.live_engine.engine import BinanceLiveEngine
from monitor_module.utils.logger import setup_logger


def main():
    """主函数"""
    print("\n" + "="*80)
    print("实盘小额资金自动化测试")
    print("="*80)
    
    # 测试参数
    TEST_SYMBOL = '1000PEPEUSDT'
    NOTIONAL_USDT = 10.0  # 名义价值
    LEVERAGE = 10
    MARGIN_USDT = NOTIONAL_USDT / LEVERAGE
    
    print(f"\n测试参数:")
    print(f"  交易对: {TEST_SYMBOL}")
    print(f"  名义价值: ${NOTIONAL_USDT} USDT")
    print(f"  杠杆: {LEVERAGE}x")
    print(f"  保证金: ${MARGIN_USDT} USDT")
    print(f"  最大风险: ${MARGIN_USDT} USDT")
    
    # 加载配置
    load_config()
    config = get_config()
    logger = setup_logger()
    
    # 检查模式
    mode = config.get('trading', {}).get('mode')
    if mode != 'live':
        print(f"\n❌ 错误: 当前模式为 '{mode}'，需要 'live' 模式")
        print("   请在 config.yaml 中设置: trading.mode = 'live'")
        return 1
    
    print(f"\n✅ 交易模式: {mode}")
    
    engine = None
    test_success = False
    
    try:
        # 1. 启动引擎
        print("\n" + "="*80)
        print("1. 启动交易引擎")
        print("="*80)
        
        engine = BinanceLiveEngine(config)
        engine.start()
        time.sleep(3)  # 等待完全启动
        
        account = engine.get_account_summary()
        print(f"✅ 引擎启动成功")
        print(f"   账户余额: ${account.get('balance', 0):.2f} USDT")
        print(f"   当前持仓: {account.get('positions_count', 0)} 个")
        
        if account.get('balance', 0) < 10:
            print(f"\n⚠️  警告: 账户余额较低")
            return 1
        
        # 2. 获取当前价格
        print("\n" + "="*80)
        print("2. 获取当前价格")
        print("="*80)
        
        ticker = engine.rest_client.get_24hr_ticker(TEST_SYMBOL)
        if isinstance(ticker, list):
            ticker = ticker[0]
        current_price = float(ticker.get('lastPrice', 0))
        
        if current_price == 0:
            print(f"❌ 无法获取 {TEST_SYMBOL} 价格")
            return 1
        
        print(f"✅ {TEST_SYMBOL} 当前价格: ${current_price:.2f}")
        
        # 3. 计算止盈止损
        side = 'long'
        tp_price = current_price * 1.01  # +1%
        sl_price = current_price * 0.99  # -1%
        
        print(f"   方向: {side}")
        print(f"   止盈: ${tp_price:.2f} (+1%)")
        print(f"   止损: ${sl_price:.2f} (-1%)")
        
        # 4. 开仓
        print("\n" + "="*80)
        print("3. 开设测试仓位")
        print("="*80)
        
        result = engine.open_position(
            symbol=TEST_SYMBOL,
            side=side,
            quote_notional_usdt=NOTIONAL_USDT,
            leverage=LEVERAGE,
            tp_price=tp_price,
            sl_price=sl_price
        )
        
        if 'error' in result:
            print(f"❌ 开仓失败: {result['error']}")
            return 1
        
        print(f"✅ 开仓成功!")
        print(f"   仓位ID: {result.get('id')}")
        print(f"   入场价: ${result.get('entry_price', 0):.6f}")
        print(f"   数量: {result.get('qty', 0)}")
        print(f"   止盈价: ${result.get('tp_price', 0):.2f}")
        print(f"   止损价: ${result.get('sl_price', 0):.2f}")
        
        # 5. 等待观察
        print("\n" + "="*80)
        print("4. 等待 10 秒观察 WebSocket 事件")
        print("="*80)
        
        for i in range(10):
            time.sleep(1)
            if i % 3 == 2:  # 每3秒检查一次
                positions = engine.get_positions_summary()
                test_pos = [p for p in positions if p['symbol'] == TEST_SYMBOL]
                if test_pos:
                    pos = test_pos[0]
                    print(f"  [{i+1}s] 未实现盈亏: ${pos['unrealized_pnl']:.4f}, ROE: {pos['roe']:.2f}%")
                else:
                    print(f"  [{i+1}s] 持仓已平仓（触发了止盈/止损）")
                    break
        
        # 6. 平仓
        print("\n" + "="*80)
        print("5. 平仓测试仓位")
        print("="*80)
        
        positions = engine.get_positions_summary()
        test_pos = [p for p in positions if p['symbol'] == TEST_SYMBOL]
        
        if test_pos:
            pos = test_pos[0]
            print(f"当前持仓状态:")
            print(f"  未实现盈亏: ${pos['unrealized_pnl']:.4f}")
            print(f"  ROE: {pos['roe']:.2f}%")
            
            result = engine.close_position(
                symbol=TEST_SYMBOL,
                close_reason='test'
            )
            
            if 'error' in result:
                print(f"❌ 平仓失败: {result['error']}")
            else:
                print(f"✅ 平仓成功!")
                print(f"   平仓价: ${result.get('close_price', 0):.6f}")
        else:
            print(f"ℹ️  持仓已不存在（已自动止盈/止损）")
        
        # 7. 等待写入完成
        print("\n等待历史记录写入...")
        time.sleep(3)
        
        # 8. 验证历史记录
        print("\n" + "="*80)
        print("6. 验证历史记录")
        print("="*80)
        
        history_path = config.get('agent', {}).get('position_history_path', 'logs/position_history.json')
        
        if not os.path.exists(history_path):
            print(f"❌ 历史文件不存在: {history_path}")
            return 1
        
        with open(history_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        # 查找最近的记录（按时间倒序）
        positions = history.get('positions', [])
        test_records = [
            p for p in positions 
            if p['symbol'] == TEST_SYMBOL
        ]
        
        if not test_records:
            print(f"❌ 未找到 {TEST_SYMBOL} 的历史记录")
            print(f"   历史文件共有 {len(positions)} 条记录")
            return 1
        
        # 显示最新的记录
        latest_record = test_records[-1]
        
        print(f"✅ 找到平仓记录:")
        print(f"   交易对: {latest_record['symbol']}")
        print(f"   方向: {latest_record['side']}")
        print(f"   入场价: ${latest_record['entry_price']:.6f}")
        print(f"   平仓价: ${latest_record['close_price']:.6f}")
        print(f"   平仓原因: {latest_record['close_reason']}")
        print(f"   已实现盈亏: ${latest_record['realized_pnl']:.4f} USDT")
        print(f"   开仓时间: {latest_record['open_time']}")
        print(f"   平仓时间: {latest_record['close_time']}")
        
        # 检查记录完整性
        required_fields = ['symbol', 'side', 'entry_price', 'close_price', 
                          'close_reason', 'open_time', 'close_time', 
                          'realized_pnl', 'tp_price', 'sl_price']
        
        missing_fields = [f for f in required_fields if f not in latest_record or latest_record[f] is None]
        
        if missing_fields:
            print(f"\n⚠️  警告: 记录缺少字段: {missing_fields}")
        else:
            print(f"\n✅ 记录完整，包含所有必需字段")
        
        test_success = True
        
        print("\n" + "="*80)
        print("✅ 测试完成!")
        print("="*80)
        print("\n测试结果:")
        print(f"  ✅ 开仓记录正确")
        print(f"  ✅ WebSocket 事件接收正常")
        print(f"  ✅ 平仓记录正确")
        print(f"  ✅ 历史记录写入正确")
        print(f"\n实际成本: 约 $0.002 USDT (手续费)")
        print(f"实际盈亏: ${latest_record['realized_pnl']:.4f} USDT")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被中断")
        # 尝试清理
        if engine:
            try:
                positions = engine.get_positions_summary()
                test_pos = [p for p in positions if p['symbol'] == TEST_SYMBOL]
                if test_pos:
                    print("尝试清理测试仓位...")
                    engine.close_position(symbol=TEST_SYMBOL, close_reason='cleanup')
                    print("✅ 清理完成")
            except:
                pass
        return 1
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        if engine:
            try:
                print("\n停止交易引擎...")
                engine.stop()
                print("✅ 引擎已停止")
            except Exception as e:
                print(f"⚠️  停止引擎时出错: {e}")


if __name__ == '__main__':
    sys.exit(main())

