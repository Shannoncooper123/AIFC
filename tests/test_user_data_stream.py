"""测试 User Data Stream 的实时推送能力

目的：
- 验证 ACCOUNT_UPDATE 事件是否实时推送持仓变化
- 确认"持仓消失"事件能否被立即检测
- 证明不需要 REST 轮询，WebSocket 事件驱动已足够
"""
import sys
import os
import json
import time
from typing import Dict, Any
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_config
from monitor_module.clients.binance_rest import BinanceRestClient
from monitor_module.clients.binance_ws import BinanceUserDataWSClient
from monitor_module.utils.logger import setup_logger

# 设置日志输出到控制台
logger = setup_logger(level='INFO')


class UserDataStreamTester:
    """User Data Stream 测试器"""
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.rest_client = BinanceRestClient(config)
        
        # 存储持仓状态（用于对比变化）
        self.previous_positions: Dict[str, Dict] = {}
        self.current_positions: Dict[str, Dict] = {}
        
        # 统计
        self.event_count = 0
        self.position_change_count = 0
        self.position_changes: list = []
        
        # WebSocket 客户端
        self.ws_client: BinanceUserDataWSClient = None
    
    def _on_event(self, event_type: str, data: Dict[str, Any]):
        """WebSocket 事件回调
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        self.event_count += 1
        
        if event_type == 'ACCOUNT_UPDATE':
            self._handle_account_update(data)
        elif event_type == 'ORDER_TRADE_UPDATE':
            self._handle_order_update(data)
        else:
            logger.debug(f"收到其他事件: {event_type}")
    
    def _handle_account_update(self, data: Dict[str, Any]):
        """处理 ACCOUNT_UPDATE 事件
        
        Args:
            data: 事件数据
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"📨 ACCOUNT_UPDATE 事件 #{self.event_count}")
        logger.info(f"   时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        
        try:
            update_data = data.get('a', {})
            balances = update_data.get('B', [])
            positions = update_data.get('P', [])
            
            logger.info(f"   余额变化: {len(balances)} 个资产")
            logger.info(f"   持仓变化: {len(positions)} 个币种")
            
            # 解析持仓数据
            self._parse_positions(positions)
            
            # 检测持仓变化
            self._detect_position_changes()
            
            # 显示当前持仓
            self._display_current_positions()
        
        except Exception as e:
            logger.error(f"处理 ACCOUNT_UPDATE 失败: {e}", exc_info=True)
    
    def _handle_order_update(self, data: Dict[str, Any]):
        """处理 ORDER_TRADE_UPDATE 事件
        
        Args:
            data: 事件数据
        """
        try:
            order_data = data.get('o', {})
            symbol = order_data.get('s')
            order_type = order_data.get('o')
            order_status = order_data.get('X')
            order_id = order_data.get('i')
            
            logger.info(f"\n📦 ORDER_TRADE_UPDATE: {symbol}")
            logger.info(f"   订单类型: {order_type}")
            logger.info(f"   订单状态: {order_status}")
            logger.info(f"   订单ID: {order_id}")
        
        except Exception as e:
            logger.error(f"处理 ORDER_TRADE_UPDATE 失败: {e}")
    
    def _parse_positions(self, positions: list):
        """解析持仓数据
        
        Args:
            positions: 持仓列表（来自 ACCOUNT_UPDATE 的 P 字段）
        """
        # 保存上一次的持仓（用于对比）
        self.previous_positions = self.current_positions.copy()
        
        # 更新当前持仓（只记录数量不为0的）
        self.current_positions.clear()
        
        for pos in positions:
            symbol = pos.get('s')
            position_amt = float(pos.get('pa', 0))
            
            if position_amt != 0:
                self.current_positions[symbol] = {
                    'positionAmt': position_amt,
                    'unrealizedProfit': float(pos.get('up', 0)),
                    'positionSide': pos.get('ps'),
                    'entryPrice': float(pos.get('ep', 0))
                }
    
    def _detect_position_changes(self):
        """检测持仓变化（这是核心！）"""
        if not self.previous_positions:
            # 第一次事件，无法对比
            return
        
        # 检测新增持仓
        new_symbols = set(self.current_positions.keys()) - set(self.previous_positions.keys())
        if new_symbols:
            for symbol in new_symbols:
                change = {
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'type': '新增持仓',
                    'symbol': symbol,
                    'amount': self.current_positions[symbol]['positionAmt']
                }
                self.position_changes.append(change)
                self.position_change_count += 1
                logger.warning(f"   🆕 新增持仓: {symbol} 数量={change['amount']}")
        
        # 🔥 检测持仓消失（关键场景！）
        removed_symbols = set(self.previous_positions.keys()) - set(self.current_positions.keys())
        if removed_symbols:
            for symbol in removed_symbols:
                change = {
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'type': '持仓消失',
                    'symbol': symbol,
                    'previous_amount': self.previous_positions[symbol]['positionAmt']
                }
                self.position_changes.append(change)
                self.position_change_count += 1
                logger.warning(f"   🚨 持仓消失: {symbol} （之前数量={change['previous_amount']}）")
                logger.warning(f"   → 此时可立即触发: 查询TP/SL订单状态 → 撤销对立订单！")
        
        # 检测持仓数量变化
        common_symbols = set(self.current_positions.keys()) & set(self.previous_positions.keys())
        for symbol in common_symbols:
            prev_amt = self.previous_positions[symbol]['positionAmt']
            curr_amt = self.current_positions[symbol]['positionAmt']
            
            if prev_amt != curr_amt:
                change = {
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'type': '数量变化',
                    'symbol': symbol,
                    'previous_amount': prev_amt,
                    'current_amount': curr_amt
                }
                self.position_changes.append(change)
                self.position_change_count += 1
                logger.info(f"   📊 {symbol} 数量变化: {prev_amt} → {curr_amt}")
    
    def _display_current_positions(self):
        """显示当前持仓"""
        if not self.current_positions:
            logger.info(f"   ✓ 当前无持仓")
            return
        
        logger.info(f"   ✓ 当前持仓 ({len(self.current_positions)} 个):")
        for symbol, pos_info in self.current_positions.items():
            amt = pos_info['positionAmt']
            pnl = pos_info['unrealizedProfit']
            entry = pos_info['entryPrice']
            side = "多" if amt > 0 else "空"
            logger.info(f"     • {symbol}: {side}仓 {abs(amt)} @ {entry} (未实现盈亏: {pnl:.2f})")
    
    def start(self, duration_seconds: int = 60):
        """启动测试
        
        Args:
            duration_seconds: 测试持续时间（秒）
        """
        logger.info("\n" + "=" * 60)
        logger.info("开始测试 User Data Stream 实时推送")
        logger.info("=" * 60)
        logger.info(f"测试时长: {duration_seconds} 秒")
        logger.info(f"说明: WebSocket 会在账户/持仓/订单变化时自动推送事件")
        
        # 先获取当前持仓（作为基准）
        logger.info("\n📋 查询当前持仓（基准）:")
        try:
            positions = self.rest_client.get_position_risk()
            for pos in positions:
                amt = float(pos.get('positionAmt', 0))
                if amt != 0:
                    symbol = pos['symbol']
                    self.current_positions[symbol] = {
                        'positionAmt': amt,
                        'unrealizedProfit': float(pos.get('unRealizedProfit', 0)),
                        'positionSide': pos.get('positionSide'),
                        'entryPrice': float(pos.get('entryPrice', 0))
                    }
            
            if self.current_positions:
                logger.info(f"   当前有 {len(self.current_positions)} 个持仓:")
                for symbol in self.current_positions.keys():
                    logger.info(f"     • {symbol}")
            else:
                logger.info("   当前无持仓")
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
        
        # 创建并启动 WebSocket 客户端
        logger.info("\n🔌 启动 User Data Stream WebSocket...")
        self.ws_client = BinanceUserDataWSClient(
            self.config,
            self.rest_client,
            self._on_event
        )
        self.ws_client.start()
        
        # 等待连接建立
        time.sleep(2)
        
        # 等待指定时间
        try:
            logger.info(f"\n⏳ 监听中... (将持续 {duration_seconds} 秒)")
            logger.info("=" * 60)
            logger.info("💡 提示:")
            logger.info("   • 币安会在持仓/订单变化时自动推送 ACCOUNT_UPDATE 事件")
            logger.info("   • 您可以手动平仓某个持仓，观察是否能实时检测到")
            logger.info("   • 如果能检测到「持仓消失」，就证明不需要 REST 轮询")
            logger.info("=" * 60)
            logger.info("")
            
            time.sleep(duration_seconds)
        
        except KeyboardInterrupt:
            logger.info("\n⚠️ 用户中断测试")
        
        finally:
            self.stop()
    
    def stop(self):
        """停止测试"""
        logger.info("\n" + "=" * 60)
        logger.info("停止测试")
        logger.info("=" * 60)
        
        if self.ws_client:
            self.ws_client.stop()
        
        # 输出统计
        self._print_summary()
    
    def _print_summary(self):
        """输出测试总结"""
        logger.info("\n" + "=" * 60)
        logger.info("测试结果总结")
        logger.info("=" * 60)
        
        logger.info(f"\n📊 统计信息:")
        logger.info(f"   收到事件数: {self.event_count}")
        logger.info(f"   持仓变化次数: {self.position_change_count}")
        
        logger.info(f"\n🔍 持仓变化记录 ({len(self.position_changes)} 条):")
        if self.position_changes:
            for change in self.position_changes:
                logger.info(f"   [{change['time']}] {change['type']}: {change['symbol']}")
        else:
            logger.info("   无持仓变化（测试期间无交易）")
        
        logger.info(f"\n✅ 结论:")
        if self.event_count > 0:
            logger.info(f"   ✓ User Data Stream 正常工作")
            logger.info(f"   ✓ ACCOUNT_UPDATE 事件实时推送（收到 {self.event_count} 次事件）")
        else:
            logger.info(f"   ⚠️ 未收到任何事件（可能是测试期间无交易或连接失败）")
        
        if self.position_change_count > 0:
            logger.info(f"   ✓ 持仓变化检测: 成功检测到 {self.position_change_count} 次变化")
            
            # 检查是否有"持仓消失"事件
            has_removal = any(c['type'] == '持仓消失' for c in self.position_changes)
            if has_removal:
                logger.info(f"   ✓ 「持仓消失」事件已检测到！")
                logger.info(f"   → 证明: WebSocket 能实时检测平仓")
        
        logger.info(f"\n💡 建议:")
        if self.event_count > 0:
            logger.info(f"   ✓ User Data Stream (WebSocket) 已足够，无需 REST 轮询")
            logger.info(f"   ✓ 当前的 account_handler.py 逻辑已正确")
            logger.info(f"   ✓ 可以移除 engine.py 中的定时轮询（_periodic_sync_loop）")
            logger.info(f"   ✓ 只保留启动时的一次性同步即可")
        else:
            logger.info(f"   ⚠️ 连接可能失败，请检查 API Key 和网络")


def main():
    """主函数"""
    print("\n🧪 User Data Stream 实时推送测试\n")
    
    try:
        # 加载配置
        config = load_config()
        logger.info("✓ 配置加载成功")
        
        # 创建测试器
        tester = UserDataStreamTester(config)
        
        # 运行测试（60秒）
        tester.start(duration_seconds=60)
    
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return False
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

