"""测试 WebSocket API v2/account.status 接口的主动轮询能力

目的：
- 验证是否可以通过 WebSocket API 主动查询账户状态（而不是被动接收事件）
- 测试定期轮询持仓变化的可行性
- 对比 User Data Stream（事件驱动）与 WebSocket API（请求-响应）的区别
"""
import sys
import os
import json
import time
import hmac
import hashlib
import websocket
import threading
from typing import Dict, Any, Set
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_config
from monitor_module.utils.logger import get_logger

logger = get_logger('test_ws_polling')


class BinanceWebSocketAPITester:
    """币安 WebSocket API 测试器"""
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.api_key = config['env']['binance_api_key']
        self.api_secret = config['env']['binance_api_secret']
        
        # WebSocket API 端点（不是 User Data Stream）
        self.ws_api_url = "wss://fstream.binance.com/ws-fapi/v1"
        
        self.ws: websocket.WebSocketApp = None
        self.is_running = False
        self.ws_thread: threading.Thread = None
        
        # 存储历史持仓状态（用于对比变化）
        self.previous_positions: Dict[str, Dict] = {}
        self.current_positions: Dict[str, Dict] = {}
        
        # 统计
        self.request_count = 0
        self.response_count = 0
        self.position_changes: list = []
    
    def _generate_signature(self, params: str) -> str:
        """生成签名
        
        Args:
            params: 参数字符串（如 "timestamp=1702620814781"）
            
        Returns:
            签名字符串
        """
        return hmac.new(
            self.api_secret.encode('utf-8'),
            params.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _build_account_status_request(self) -> Dict[str, Any]:
        """构建 v2/account.status 请求
        
        Returns:
            请求消息字典
        """
        timestamp = int(time.time() * 1000)
        
        # 构建参数字符串（用于签名）
        params_str = f"timestamp={timestamp}"
        signature = self._generate_signature(params_str)
        
        # 构建请求消息
        request = {
            "id": f"test_{self.request_count}",
            "method": "v2/account.status",
            "params": {
                "apiKey": self.api_key,
                "timestamp": timestamp,
                "signature": signature
            }
        }
        
        return request
    
    def _on_open(self, ws):
        """WebSocket 连接建立回调"""
        logger.info("=" * 60)
        logger.info("WebSocket API 连接已建立")
        logger.info(f"端点: {self.ws_api_url}")
        logger.info("=" * 60)
        
        # 立即发送第一次查询
        self._send_account_status_request()
    
    def _on_message(self, ws, message):
        """接收消息回调"""
        try:
            data = json.loads(message)
            self.response_count += 1
            
            # 检查是否是 v2/account.status 的响应
            if data.get('id', '').startswith('test_'):
                self._handle_account_status_response(data)
            else:
                logger.debug(f"收到其他消息: {data.get('id')}")
        
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    def _on_error(self, ws, error):
        """错误回调"""
        logger.error(f"WebSocket 错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭回调"""
        logger.warning(f"WebSocket 连接关闭: {close_status_code} - {close_msg}")
    
    def _send_account_status_request(self):
        """发送账户状态查询请求"""
        if not self.is_running or not self.ws:
            return
        
        try:
            request = self._build_account_status_request()
            self.request_count += 1
            
            logger.info(f"\n📤 发送请求 #{self.request_count}")
            logger.info(f"   时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            
            self.ws.send(json.dumps(request))
        
        except Exception as e:
            logger.error(f"发送请求失败: {e}")
    
    def _handle_account_status_response(self, data: Dict[str, Any]):
        """处理账户状态响应
        
        Args:
            data: 响应数据
        """
        try:
            status = data.get('status')
            if status != 200:
                logger.error(f"❌ 请求失败: status={status}")
                logger.error(f"   响应: {json.dumps(data, indent=2)}")
                return
            
            result = data.get('result', {})
            positions = result.get('positions', [])
            
            logger.info(f"\n📥 收到响应 #{self.response_count}")
            logger.info(f"   时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            logger.info(f"   总持仓数: {len(positions)}")
            
            # 解析持仓数据
            self._parse_positions(positions)
            
            # 检测持仓变化
            self._detect_position_changes()
            
            # 显示当前持仓
            self._display_current_positions()
        
        except Exception as e:
            logger.error(f"处理响应失败: {e}", exc_info=True)
    
    def _parse_positions(self, positions: list):
        """解析持仓数据
        
        Args:
            positions: 持仓列表
        """
        # 保存上一次的持仓
        self.previous_positions = self.current_positions.copy()
        
        # 更新当前持仓
        self.current_positions.clear()
        
        for pos in positions:
            symbol = pos.get('symbol')
            position_amt = float(pos.get('positionAmt', 0))
            
            # 只记录有持仓的（非0）
            if position_amt != 0:
                self.current_positions[symbol] = {
                    'positionAmt': position_amt,
                    'unrealizedProfit': float(pos.get('unrealizedProfit', 0)),
                    'positionSide': pos.get('positionSide'),
                    'updateTime': pos.get('updateTime')
                }
    
    def _detect_position_changes(self):
        """检测持仓变化"""
        if not self.previous_positions:
            # 第一次查询，没有对比基准
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
                logger.warning(f"🆕 新增持仓: {symbol} 数量={change['amount']}")
        
        # 检测持仓消失（这是关键！）
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
                logger.warning(f"🚨 持仓消失: {symbol} （之前数量={change['previous_amount']}）")
                logger.warning(f"   → 可触发清理对立订单！")
        
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
                logger.info(f"📊 {symbol} 数量变化: {prev_amt} → {curr_amt}")
    
    def _display_current_positions(self):
        """显示当前持仓"""
        if not self.current_positions:
            logger.info("   当前无持仓")
            return
        
        logger.info(f"   当前持仓:")
        for symbol, pos_info in self.current_positions.items():
            amt = pos_info['positionAmt']
            pnl = pos_info['unrealizedProfit']
            side = "多" if amt > 0 else "空"
            logger.info(f"     • {symbol}: {side}仓 {abs(amt)} (未实现盈亏: {pnl:.2f})")
    
    def _polling_loop(self):
        """轮询循环（在单独线程中运行）"""
        logger.info("\n🔄 轮询线程已启动")
        poll_interval = 10  # 每10秒查询一次
        
        while self.is_running:
            try:
                time.sleep(poll_interval)
                
                if not self.is_running:
                    break
                
                # 发送查询请求
                self._send_account_status_request()
            
            except Exception as e:
                logger.error(f"轮询失败: {e}")
        
        logger.info("🔄 轮询线程已退出")
    
    def start(self, duration_seconds: int = 60):
        """启动测试
        
        Args:
            duration_seconds: 测试持续时间（秒）
        """
        logger.info("\n" + "=" * 60)
        logger.info("开始测试 WebSocket API 主动轮询")
        logger.info("=" * 60)
        logger.info(f"测试时长: {duration_seconds} 秒")
        logger.info(f"轮询间隔: 10 秒")
        logger.info(f"预计请求次数: {duration_seconds // 10 + 1} 次")
        
        # 创建 WebSocket 连接
        self.ws = websocket.WebSocketApp(
            self.ws_api_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        self.is_running = True
        
        # 启动 WebSocket 线程
        self.ws_thread = threading.Thread(
            target=lambda: self.ws.run_forever(ping_interval=20, ping_timeout=10),
            daemon=True
        )
        self.ws_thread.start()
        
        # 等待连接建立
        time.sleep(2)
        
        # 启动轮询线程
        polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
        polling_thread.start()
        
        # 等待指定时间
        try:
            logger.info(f"\n⏳ 测试运行中... (将持续 {duration_seconds} 秒)")
            logger.info("   提示: 此期间可以手动平仓某个持仓，观察是否能检测到变化\n")
            
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
        
        self.is_running = False
        
        if self.ws:
            self.ws.close()
        
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2)
        
        # 输出统计
        self._print_summary()
    
    def _print_summary(self):
        """输出测试总结"""
        logger.info("\n" + "=" * 60)
        logger.info("测试结果总结")
        logger.info("=" * 60)
        
        logger.info(f"\n📊 统计信息:")
        logger.info(f"   发送请求数: {self.request_count}")
        logger.info(f"   收到响应数: {self.response_count}")
        logger.info(f"   成功率: {self.response_count / self.request_count * 100:.1f}%" if self.request_count > 0 else "   成功率: N/A")
        
        logger.info(f"\n🔍 持仓变化记录 ({len(self.position_changes)} 条):")
        if self.position_changes:
            for change in self.position_changes:
                logger.info(f"   [{change['time']}] {change['type']}: {change['symbol']}")
        else:
            logger.info("   无持仓变化")
        
        logger.info(f"\n✅ 结论:")
        logger.info(f"   • WebSocket API v2/account.status 可用性: {'✓ 正常' if self.response_count > 0 else '✗ 失败'}")
        logger.info(f"   • 主动轮询能力: {'✓ 支持' if self.response_count > 0 else '✗ 不支持'}")
        logger.info(f"   • 持仓变化检测: {'✓ 可检测 ({} 次变化)'.format(len(self.position_changes)) if self.position_changes else '- 测试期间无变化'}")
        
        logger.info(f"\n💡 建议:")
        if self.response_count > 0:
            logger.info(f"   ✓ 可以使用 WebSocket API 替代 REST API 进行定时轮询")
            logger.info(f"   ✓ 优势: 长连接、低延迟、减少握手开销")
            logger.info(f"   ✓ 结合 User Data Stream (事件驱动) + WebSocket API (主动轮询) = 双保险")
        else:
            logger.info(f"   ✗ 连接或认证失败，请检查 API Key 和 Secret")


def load_current_positions_from_state() -> Dict[str, Any]:
    """从 trade_state.json 加载当前持仓（用于对比）
    
    Returns:
        持仓字典
    """
    try:
        state_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'agent',
            'trade_state.json'
        )
        
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return state.get('positions', {})
    except Exception as e:
        logger.warning(f"无法加载 trade_state.json: {e}")
    
    return {}


def main():
    """主函数"""
    print("\n🧪 WebSocket API 主动轮询测试\n")
    
    try:
        # 加载配置
        config = load_config()
        logger.info("✓ 配置加载成功")
        
        # 显示当前本地持仓（用于对比）
        local_positions = load_current_positions_from_state()
        if local_positions:
            logger.info(f"\n📋 本地记录的持仓 (trade_state.json): {len(local_positions)} 个")
            for symbol in local_positions.keys():
                logger.info(f"   • {symbol}")
        else:
            logger.info("\n📋 本地记录: 无持仓")
        
        # 创建测试器
        tester = BinanceWebSocketAPITester(config)
        
        # 运行测试（60秒）
        tester.start(duration_seconds=60)
    
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return False
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

