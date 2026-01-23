#!/usr/bin/env python3
"""
策略执行器集成测试
模拟真实的加仓场景，确保不会超过配置的加仓次数
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
import tempfile
import shutil
from pathlib import Path
from agent.rule_strategy.pyramid_manager import PyramidManager


class TestStrategyIntegration(unittest.TestCase):
    """策略执行器集成测试"""
    
    def setUp(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "pyramid_state.json")
        self.manager = PyramidManager()
    
    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_simulated_trading_scenario(self):
        """模拟完整的交易场景"""
        symbol = "BTCUSDT"
        initial_price = 50000.0
        atr = 500.0
        addon_atr_drop = 0.5  # 配置中的值
        
        print(f"\n{'='*60}")
        print(f"模拟交易场景: {symbol}")
        print(f"初始价格: {initial_price}, ATR: {atr}")
        print(f"{'='*60}")
        
        # 场景1: 开仓 Level 1
        print(f"\n[1] 开仓 Level 1 @ {initial_price}")
        self.manager.add_position(symbol, initial_price, atr, "pos_1", 14400)
        pos = self.manager.get_position(symbol)
        self.assertEqual(pos.level, 1)
        print(f"✅ Level 1 开仓成功")
        
        # 场景2: 价格下跌不足，不应该加仓
        price_drop_small = initial_price - (atr * 0.3)  # 下跌150，小于250
        print(f"\n[2] 价格下跌到 {price_drop_small} (下跌不足)")
        can_add = self.manager.can_add_level2(symbol, price_drop_small, addon_atr_drop)
        self.assertFalse(can_add)
        print(f"✅ 正确拒绝加仓（价格下跌不足）")
        
        # 场景3: 价格下跌足够，执行 Level 2 加仓
        price_level2 = initial_price - (atr * 0.6)  # 下跌300，超过250
        print(f"\n[3] 价格下跌到 {price_level2} (满足加仓条件)")
        can_add = self.manager.can_add_level2(symbol, price_level2, addon_atr_drop)
        self.assertTrue(can_add)
        
        self.manager.add_level2(symbol, price_level2, "pos_2")
        pos = self.manager.get_position(symbol)
        self.assertEqual(pos.level, 2)
        print(f"✅ Level 2 加仓成功，平均价: {pos.avg_price}")
        
        # 场景4: 价格继续下跌，尝试第3次加仓（应该被拒绝）
        price_attempt3 = price_level2 - (atr * 0.6)  # 继续下跌
        print(f"\n[4] 价格继续下跌到 {price_attempt3} (尝试第3次加仓)")
        can_add = self.manager.can_add_level2(symbol, price_attempt3, addon_atr_drop)
        self.assertFalse(can_add)
        print(f"✅ 正确拒绝第3次加仓（已经是 Level 2）")
        
        # 场景5: 尝试直接调用 add_level2（应该抛出异常）
        print(f"\n[5] 尝试强制加仓到 Level 3")
        with self.assertRaises(ValueError) as context:
            self.manager.add_level2(symbol, price_attempt3, "pos_3")
        self.assertIn("不能再加仓", str(context.exception))
        print(f"✅ 正确抛出异常，阻止第3次加仓")
        
        # 验证最终状态
        pos = self.manager.get_position(symbol)
        self.assertEqual(pos.level, 2, "最终应该保持 Level 2")
        print(f"\n{'='*60}")
        print(f"✅ 所有场景测试通过！")
        print(f"最终状态: Level {pos.level}")
        print(f"{'='*60}")
    
    def test_multiple_symbols_scenario(self):
        """测试多个交易对同时交易的场景"""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        base_price = 1000.0
        atr = 10.0
        addon_atr_drop = 0.5
        
        print(f"\n{'='*60}")
        print(f"多币种交易场景")
        print(f"{'='*60}")
        
        # 为每个币种开仓
        for i, symbol in enumerate(symbols):
            entry_price = base_price * (i + 1)
            print(f"\n[{symbol}] 开仓 @ {entry_price}")
            self.manager.add_position(symbol, entry_price, atr, f"pos_{i}_1", 14400)
        
        # 所有币种都应该是 Level 1
        for symbol in symbols:
            pos = self.manager.get_position(symbol)
            self.assertEqual(pos.level, 1)
        print(f"✅ {len(symbols)} 个币种都成功开仓")
        
        # BTCUSDT 加仓到 Level 2
        btc_l2_price = base_price - (atr * 0.6)
        print(f"\n[BTCUSDT] 加仓到 Level 2 @ {btc_l2_price}")
        can_add = self.manager.can_add_level2("BTCUSDT", btc_l2_price, addon_atr_drop)
        self.assertTrue(can_add)
        self.manager.add_level2("BTCUSDT", btc_l2_price, "pos_0_2")
        
        # ETHUSDT 和 BNBUSDT 保持 Level 1
        btc_pos = self.manager.get_position("BTCUSDT")
        eth_pos = self.manager.get_position("ETHUSDT")
        bnb_pos = self.manager.get_position("BNBUSDT")
        
        self.assertEqual(btc_pos.level, 2)
        self.assertEqual(eth_pos.level, 1)
        self.assertEqual(bnb_pos.level, 1)
        print(f"✅ BTCUSDT 升级到 Level 2，其他币种保持 Level 1")
        
        # BTCUSDT 不能再加仓
        btc_l3_price = btc_l2_price - (atr * 0.6)
        can_add = self.manager.can_add_level2("BTCUSDT", btc_l3_price, addon_atr_drop)
        self.assertFalse(can_add)
        print(f"✅ BTCUSDT 正确拒绝第3次加仓")
        
        # ETHUSDT 仍然可以加仓（因为它还是 Level 1）
        eth_l2_price = base_price * 2 - (atr * 0.6)
        can_add = self.manager.can_add_level2("ETHUSDT", eth_l2_price, addon_atr_drop)
        self.assertTrue(can_add)
        print(f"✅ ETHUSDT 仍然可以加仓到 Level 2")
        
        print(f"\n{'='*60}")
        print(f"✅ 多币种交易场景测试通过！")
        print(f"{'='*60}")
    
    def test_state_persistence_across_restarts(self):
        """测试重启后状态恢复"""
        symbol = "BTCUSDT"
        entry_price = 50000.0
        atr = 500.0
        addon_atr_drop = 0.5
        
        print(f"\n{'='*60}")
        print(f"状态持久化测试")
        print(f"{'='*60}")
        
        # 创建持仓并加仓到 Level 2
        print(f"\n[1] 创建 Level 2 持仓")
        self.manager.add_position(symbol, entry_price, atr, "pos_1", 14400)
        l2_price = entry_price - (atr * 0.6)
        self.manager.add_level2(symbol, l2_price, "pos_2")
        
        # 保存状态
        self.manager.save_state(self.state_file)
        print(f"✅ 状态已保存到 {self.state_file}")
        
        # 模拟重启：创建新的 manager 并加载
        print(f"\n[2] 模拟重启，加载状态")
        new_manager = PyramidManager()
        count = new_manager.load_state(self.state_file)
        self.assertEqual(count, 1)
        print(f"✅ 成功加载 {count} 个持仓")
        
        # 验证加载的状态仍然阻止第3次加仓
        print(f"\n[3] 验证加载后的限制仍然有效")
        l3_price = l2_price - (atr * 0.6)
        can_add = new_manager.can_add_level2(symbol, l3_price, addon_atr_drop)
        self.assertFalse(can_add)
        print(f"✅ 加载后正确阻止第3次加仓")
        
        # 验证状态详情
        loaded_pos = new_manager.get_position(symbol)
        self.assertEqual(loaded_pos.level, 2)
        self.assertEqual(loaded_pos.entry_price_l1, entry_price)
        self.assertEqual(loaded_pos.entry_price_l2, l2_price)
        print(f"✅ 状态详情正确: Level {loaded_pos.level}, 均价 {loaded_pos.avg_price}")
        
        print(f"\n{'='*60}")
        print(f"✅ 状态持久化测试通过！")
        print(f"{'='*60}")


def run_integration_tests():
    """运行集成测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestStrategyIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("策略执行器集成测试")
    print("="*60)
    
    success = run_integration_tests()
    
    if success:
        print("\n" + "="*60)
        print("✅ 所有集成测试通过！")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ 部分测试失败，请检查上面的错误信息")
        print("="*60)
    
    sys.exit(0 if success else 1)
