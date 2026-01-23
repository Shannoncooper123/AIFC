#!/usr/bin/env python3
"""
金字塔加仓限制测试
测试 PyramidManager 的加仓次数限制是否正确工作
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from agent.rule_strategy.pyramid_manager import PyramidManager, PyramidPosition


class TestPyramidAddOnLimit(unittest.TestCase):
    """测试金字塔加仓次数限制"""
    
    def setUp(self):
        """每个测试前初始化"""
        self.manager = PyramidManager()
    
    def test_level1_can_add_to_level2(self):
        """测试 Level 1 可以加仓到 Level 2"""
        symbol = "BTCUSDT"
        entry_price = 50000.0
        atr = 500.0
        
        # 添加 Level 1 持仓
        self.manager.add_position(symbol, entry_price, atr, "pos_id_1", 3600)
        
        # 价格下跌足够（超过 0.5 * ATR）
        current_price = entry_price - (atr * 0.6)  # 下跌 300，超过阈值 250
        
        # 应该可以加仓
        can_add = self.manager.can_add_level2(symbol, current_price, addon_atr_drop=0.5)
        self.assertTrue(can_add, "Level 1 应该可以加仓到 Level 2")
        
        # 执行加仓
        self.manager.add_level2(symbol, current_price, "pos_id_2")
        
        # 验证状态
        pos = self.manager.get_position(symbol)
        self.assertEqual(pos.level, 2, "加仓后应该是 Level 2")
        self.assertEqual(pos.entry_price_l2, current_price, "Level 2 入场价应该正确")
    
    def test_level2_cannot_add_again(self):
        """测试 Level 2 不能再次加仓"""
        symbol = "BTCUSDT"
        entry_price = 50000.0
        atr = 500.0
        
        # 添加 Level 1 并升级到 Level 2
        self.manager.add_position(symbol, entry_price, atr, "pos_id_1", 3600)
        current_price = entry_price - (atr * 0.6)
        self.manager.add_level2(symbol, current_price, "pos_id_2")
        
        # 价格继续下跌
        lower_price = current_price - (atr * 0.6)
        
        # 不应该能再次加仓
        can_add = self.manager.can_add_level2(symbol, lower_price, addon_atr_drop=0.5)
        self.assertFalse(can_add, "Level 2 不应该能再次加仓")
    
    def test_add_level2_when_already_level2_raises_error(self):
        """测试当已经是 Level 2 时调用 add_level2 会抛出异常"""
        symbol = "BTCUSDT"
        entry_price = 50000.0
        atr = 500.0
        
        # 添加 Level 1 并升级到 Level 2
        self.manager.add_position(symbol, entry_price, atr, "pos_id_1", 3600)
        current_price = entry_price - (atr * 0.6)
        self.manager.add_level2(symbol, current_price, "pos_id_2")
        
        # 尝试再次调用 add_level2 应该抛出 ValueError
        with self.assertRaises(ValueError) as context:
            self.manager.add_level2(symbol, current_price - 100, "pos_id_3")
        
        self.assertIn("不能再加仓", str(context.exception))
    
    def test_price_drop_not_enough(self):
        """测试价格下跌不足时不能加仓"""
        symbol = "BTCUSDT"
        entry_price = 50000.0
        atr = 500.0
        
        # 添加 Level 1 持仓
        self.manager.add_position(symbol, entry_price, atr, "pos_id_1", 3600)
        
        # 价格下跌不足（少于 0.5 * ATR）
        current_price = entry_price - (atr * 0.3)  # 下跌 150，小于阈值 250
        
        # 不应该能加仓
        can_add = self.manager.can_add_level2(symbol, current_price, addon_atr_drop=0.5)
        self.assertFalse(can_add, "价格下跌不足时不应该能加仓")
    
    def test_no_position_cannot_add(self):
        """测试没有持仓时不能加仓"""
        symbol = "BTCUSDT"
        current_price = 50000.0
        
        # 没有持仓
        can_add = self.manager.can_add_level2(symbol, current_price, addon_atr_drop=0.5)
        self.assertFalse(can_add, "没有持仓时不应该能加仓")
    
    def test_avg_price_calculation(self):
        """测试平均价格计算是否正确"""
        symbol = "BTCUSDT"
        entry_price_l1 = 50000.0
        entry_price_l2 = 49500.0
        atr = 500.0
        
        # 添加 Level 1
        self.manager.add_position(symbol, entry_price_l1, atr, "pos_id_1", 3600)
        
        # 升级到 Level 2
        self.manager.add_level2(symbol, entry_price_l2, "pos_id_2")
        
        # 验证平均价格
        pos = self.manager.get_position(symbol)
        expected_avg = (entry_price_l1 + entry_price_l2) / 2
        self.assertEqual(pos.avg_price, expected_avg, "平均价格应该是两个入场价的平均值")
    
    def test_multiple_symbols_independent(self):
        """测试多个交易对的加仓限制相互独立"""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        entry_price = 1000.0
        atr = 10.0
        
        # 为每个交易对添加持仓并加仓
        for i, symbol in enumerate(symbols):
            self.manager.add_position(symbol, entry_price, atr, f"pos_{i}_1", 3600)
            current_price = entry_price - (atr * 0.6)
            
            # 都应该能加仓
            can_add = self.manager.can_add_level2(symbol, current_price, addon_atr_drop=0.5)
            self.assertTrue(can_add, f"{symbol} 应该能加仓")
            
            # 执行加仓
            self.manager.add_level2(symbol, current_price, f"pos_{i}_2")
            
            # 验证是 Level 2
            pos = self.manager.get_position(symbol)
            self.assertEqual(pos.level, 2, f"{symbol} 应该是 Level 2")
        
        # 所有交易对都不应该能再加仓
        for symbol in symbols:
            lower_price = entry_price - (atr * 1.2)
            can_add = self.manager.can_add_level2(symbol, lower_price, addon_atr_drop=0.5)
            self.assertFalse(can_add, f"{symbol} 不应该能再次加仓")


class TestPyramidStatePersistence(unittest.TestCase):
    """测试金字塔状态持久化"""
    
    def setUp(self):
        """每个测试前初始化"""
        self.manager = PyramidManager()
        self.test_file = "/tmp/test_pyramid_state.json"
    
    def tearDown(self):
        """清理测试文件"""
        import os
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    def test_save_and_load_state(self):
        """测试保存和加载状态"""
        symbol = "BTCUSDT"
        entry_price = 50000.0
        atr = 500.0
        
        # 添加持仓
        self.manager.add_position(symbol, entry_price, atr, "pos_id_1", 3600)
        current_price = entry_price - (atr * 0.6)
        self.manager.add_level2(symbol, current_price, "pos_id_2")
        
        # 保存状态
        self.manager.save_state(self.test_file)
        
        # 创建新的 manager 并加载
        new_manager = PyramidManager()
        count = new_manager.load_state(self.test_file)
        
        self.assertEqual(count, 1, "应该加载1个持仓")
        
        # 验证加载的状态
        loaded_pos = new_manager.get_position(symbol)
        self.assertIsNotNone(loaded_pos, "应该能找到加载的持仓")
        self.assertEqual(loaded_pos.level, 2, "加载的持仓应该是 Level 2")
        self.assertEqual(loaded_pos.entry_price_l1, entry_price, "Level 1 价格应该正确")
        self.assertEqual(loaded_pos.entry_price_l2, current_price, "Level 2 价格应该正确")
        
        # 加载后的状态也应该不能再加仓
        can_add = new_manager.can_add_level2(symbol, current_price - 100, addon_atr_drop=0.5)
        self.assertFalse(can_add, "加载后的 Level 2 持仓不应该能再加仓")


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(loader.loadTestsFromTestCase(TestPyramidAddOnLimit))
    suite.addTests(loader.loadTestsFromTestCase(TestPyramidStatePersistence))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回结果
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
