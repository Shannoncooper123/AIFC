"""实盘小额资金测试持仓平仓历史记录链路

⚠️  注意事项：
1. 使用极小金额（1-2 USDT名义价值，保证金仅0.1-0.2 USDT）
2. 会产生真实交易，虽然金额很小但仍有风险
3. 需要确保账户余额充足
4. 测试完成后会自动平仓

测试流程：
1. 连接实盘交易引擎
2. 开设小额测试仓位（设置紧密的止盈止损）
3. 等待10秒观察WebSocket事件
4. 手动平仓
5. 验证 position_history.json 是否正确记录
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


class LivePositionCloseTest:
    """实盘持仓平仓测试"""
    
    def __init__(self):
        load_config()
        self.config = get_config()
        self.logger = setup_logger()
        self.engine = None
        self.test_symbol = None
        
    def check_prerequisites(self):
        """检查前置条件"""
        print("\n" + "="*80)
        print("前置条件检查")
        print("="*80)
        
        # 1. 检查交易模式
        mode = self.config.get('trading', {}).get('mode')
        if mode != 'live':
            print(f"❌ 当前交易模式为 '{mode}'，需要设置为 'live'")
            print("   请在 config.yaml 中设置: trading.mode = 'live'")
            return False
        print(f"✅ 交易模式: {mode}")
        
        # 2. 检查API密钥
        api_key = self.config.get('env', {}).get('binance_api_key')
        if not api_key or len(api_key) < 10:
            print(f"❌ 未配置币安API密钥")
            print("   请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
            return False
        print(f"✅ API密钥已配置")
        
        # 3. 检查历史记录文件路径
        history_path = self.config.get('agent', {}).get('position_history_path', 'logs/position_history.json')
        print(f"✅ 历史记录路径: {history_path}")
        
        return True
    
    def initialize_engine(self):
        """初始化交易引擎"""
        print("\n" + "="*80)
        print("初始化实盘交易引擎")
        print("="*80)
        
        try:
            self.engine = BinanceLiveEngine(self.config)
            self.engine.start()
            
            # 等待引擎完全启动
            time.sleep(2)
            
            # 检查账户信息
            account = self.engine.get_account_summary()
            balance = account.get('balance', 0)
            
            print(f"✅ 引擎启动成功")
            print(f"   账户余额: ${balance:.2f} USDT")
            print(f"   当前持仓: {account.get('positions_count', 0)} 个")
            
            if balance < 10:
                print(f"\n⚠️  警告: 账户余额较低 (${balance:.2f})")
                print("   建议至少保持 $10 以上余额进行测试")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ 引擎启动失败: {e}")
            return False
    
    def choose_test_symbol(self):
        """选择测试交易对（选择流动性好、波动小的）"""
        # 推荐使用主流币种，波动相对可控
        recommended_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
        
        print("\n" + "="*80)
        print("选择测试交易对")
        print("="*80)
        print("推荐使用主流币种（流动性好，滑点小）：")
        for i, symbol in enumerate(recommended_symbols, 1):
            print(f"  {i}. {symbol}")
        
        try:
            choice = input(f"\n请选择 [1-{len(recommended_symbols)}] 或输入其他交易对: ").strip()
            
            if choice.isdigit() and 1 <= int(choice) <= len(recommended_symbols):
                self.test_symbol = recommended_symbols[int(choice) - 1]
            else:
                self.test_symbol = choice.upper()
                if not self.test_symbol.endswith('USDT'):
                    self.test_symbol += 'USDT'
            
            print(f"✅ 选择交易对: {self.test_symbol}")
            return True
            
        except Exception as e:
            print(f"❌ 选择失败: {e}")
            return False
    
    def get_current_price(self):
        """获取当前价格"""
        try:
            ticker = self.engine.rest_client.get_24hr_ticker(self.test_symbol)
            if isinstance(ticker, list) and len(ticker) > 0:
                ticker = ticker[0]
            return float(ticker.get('lastPrice', 0))
        except Exception as e:
            print(f"❌ 获取价格失败: {e}")
            return None
    
    def open_test_position(self):
        """开设测试仓位"""
        print("\n" + "="*80)
        print("开设测试仓位")
        print("="*80)
        
        try:
            # 获取当前价格
            current_price = self.get_current_price()
            if not current_price:
                return False
            
            print(f"当前价格: ${current_price:.6f}")
            
            # 使用极小的名义价值（2 USDT，杠杆10x，保证金仅0.2 USDT）
            notional_usdt = 2.0
            leverage = 10
            margin_usdt = notional_usdt / leverage
            
            # 选择方向（做多更安全，因为加密货币长期趋势向上）
            side = 'long'
            
            # 设置紧密的止盈止损（1%的价格波动）
            tp_price = current_price * 1.01  # 止盈：+1%
            sl_price = current_price * 0.99  # 止损：-1%
            
            print(f"\n仓位参数:")
            print(f"  方向: {side}")
            print(f"  名义价值: ${notional_usdt:.2f} USDT")
            print(f"  杠杆: {leverage}x")
            print(f"  保证金: ${margin_usdt:.2f} USDT")
            print(f"  入场价: ${current_price:.6f}")
            print(f"  止盈价: ${tp_price:.6f} (+1%)")
            print(f"  止损价: ${sl_price:.6f} (-1%)")
            print(f"\n最大风险: ${margin_usdt:.2f} USDT（保证金全损）")
            print(f"预期盈利: ${margin_usdt * 0.01:.4f} USDT（1%波动）")
            
            # 确认
            confirm = input(f"\n确认开仓？[y/N]: ").strip().lower()
            if confirm != 'y':
                print("已取消")
                return False
            
            # 开仓
            print(f"\n开仓中...")
            result = self.engine.open_position(
                symbol=self.test_symbol,
                side=side,
                quote_notional_usdt=notional_usdt,
                leverage=leverage,
                tp_price=tp_price,
                sl_price=sl_price
            )
            
            if 'error' in result:
                print(f"❌ 开仓失败: {result['error']}")
                return False
            
            print(f"✅ 开仓成功!")
            print(f"   仓位ID: {result.get('id')}")
            print(f"   入场价: ${result.get('entry_price', 0):.6f}")
            print(f"   数量: {result.get('qty', 0)}")
            
            return True
            
        except Exception as e:
            print(f"❌ 开仓异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def wait_for_events(self, duration=10):
        """等待WebSocket事件"""
        print("\n" + "="*80)
        print(f"等待 {duration} 秒，观察WebSocket事件...")
        print("="*80)
        print("说明：此时会监听 ORDER_TRADE_UPDATE 和 ACCOUNT_UPDATE 事件")
        
        for i in range(duration):
            time.sleep(1)
            if i % 5 == 4:
                # 每5秒检查一次持仓状态
                positions = self.engine.get_positions_summary()
                test_pos = [p for p in positions if p['symbol'] == self.test_symbol]
                if test_pos:
                    pos = test_pos[0]
                    print(f"  [{i+1}s] 持仓状态: 未实现盈亏=${pos['unrealized_pnl']:.4f}, ROE={pos['roe']:.2f}%")
                else:
                    print(f"  [{i+1}s] 持仓已平仓（可能触发了止盈/止损）")
                    return True
        
        print(f"✅ 观察完成")
        return True
    
    def close_test_position(self):
        """平仓测试仓位"""
        print("\n" + "="*80)
        print("平仓测试仓位")
        print("="*80)
        
        try:
            # 检查持仓是否还存在
            positions = self.engine.get_positions_summary()
            test_pos = [p for p in positions if p['symbol'] == self.test_symbol]
            
            if not test_pos:
                print(f"ℹ️  {self.test_symbol} 持仓已不存在（可能已自动止盈/止损）")
                return True
            
            pos = test_pos[0]
            print(f"当前持仓:")
            print(f"  数量: {pos['qty']}")
            print(f"  入场价: ${pos['entry_price']:.6f}")
            print(f"  当前价: ${pos['mark_price']:.6f}")
            print(f"  未实现盈亏: ${pos['unrealized_pnl']:.4f}")
            print(f"  ROE: {pos['roe']:.2f}%")
            
            # 确认平仓
            confirm = input(f"\n确认平仓？[y/N]: ").strip().lower()
            if confirm != 'y':
                print("已取消（持仓保留）")
                return False
            
            # 平仓
            print(f"\n平仓中...")
            result = self.engine.close_position(
                symbol=self.test_symbol,
                close_reason='test'
            )
            
            if 'error' in result:
                print(f"❌ 平仓失败: {result['error']}")
                return False
            
            print(f"✅ 平仓成功!")
            print(f"   平仓价: ${result.get('close_price', 0):.6f}")
            
            return True
            
        except Exception as e:
            print(f"❌ 平仓异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def verify_history(self):
        """验证历史记录"""
        print("\n" + "="*80)
        print("验证历史记录")
        print("="*80)
        
        # 等待异步写入完成
        time.sleep(2)
        
        try:
            history_path = self.config.get('agent', {}).get('position_history_path', 'logs/position_history.json')
            
            if not os.path.exists(history_path):
                print(f"❌ 历史文件不存在: {history_path}")
                return False
            
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # 查找本次测试的记录
            positions = history.get('positions', [])
            test_records = [
                p for p in positions 
                if p['symbol'] == self.test_symbol 
                and 'close_time' in p
            ]
            
            if not test_records:
                print(f"❌ 未找到 {self.test_symbol} 的平仓记录")
                print(f"   历史文件共有 {len(positions)} 条记录")
                return False
            
            # 显示最新的记录
            latest_record = test_records[-1]
            print(f"✅ 找到平仓记录:")
            print(f"   交易对: {latest_record['symbol']}")
            print(f"   方向: {latest_record['side']}")
            print(f"   入场价: ${latest_record['entry_price']:.6f}")
            print(f"   平仓价: ${latest_record['close_price']:.6f}")
            print(f"   平仓原因: {latest_record['close_reason']}")
            print(f"   已实现盈亏: ${latest_record['realized_pnl']:.4f}")
            print(f"   开仓时间: {latest_record['open_time']}")
            print(f"   平仓时间: {latest_record['close_time']}")
            print(f"   止盈价: ${latest_record.get('tp_price', 0):.6f}")
            print(f"   止损价: ${latest_record.get('sl_price', 0):.6f}")
            
            return True
            
        except Exception as e:
            print(f"❌ 验证异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def cleanup(self):
        """清理资源"""
        if self.engine:
            try:
                print("\n停止交易引擎...")
                self.engine.stop()
                print("✅ 引擎已停止")
            except Exception as e:
                print(f"⚠️  停止引擎时出错: {e}")
    
    def run(self):
        """运行测试"""
        print("\n" + "="*80)
        print("实盘小额资金测试 - 持仓平仓历史记录链路")
        print("="*80)
        print("\n⚠️  风险提示:")
        print("  - 本测试会产生真实交易（虽然金额很小）")
        print("  - 使用名义价值 $2 USDT，保证金约 $0.2 USDT")
        print("  - 最大风险：保证金全损（约 $0.2 USDT）")
        print("  - 测试完成后会立即平仓")
        
        confirm = input(f"\n理解风险并继续？[y/N]: ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return False
        
        try:
            # 1. 前置条件检查
            if not self.check_prerequisites():
                return False
            
            # 2. 初始化引擎
            if not self.initialize_engine():
                return False
            
            # 3. 选择测试交易对
            if not self.choose_test_symbol():
                return False
            
            # 4. 开设测试仓位
            if not self.open_test_position():
                return False
            
            # 5. 等待WebSocket事件
            self.wait_for_events(duration=10)
            
            # 6. 平仓测试仓位
            self.close_test_position()
            
            # 7. 验证历史记录
            self.verify_history()
            
            print("\n" + "="*80)
            print("✅ 测试完成！")
            print("="*80)
            
            return True
            
        except KeyboardInterrupt:
            print("\n\n⚠️  测试被中断")
            # 尝试平仓
            if self.test_symbol:
                print("尝试清理测试仓位...")
                try:
                    self.close_test_position()
                except:
                    pass
            return False
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            self.cleanup()


def main():
    """主函数"""
    tester = LivePositionCloseTest()
    success = tester.run()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

