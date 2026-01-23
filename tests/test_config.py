"""配置测试工具"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_config
from monitor_module.clients.binance_rest import BinanceRestClient
from monitor_module.alerts.notifier import EmailNotifier
from monitor_module.utils.logger import setup_logger


def test_config_loading():
    """测试配置加载"""
    print("=" * 50)
    print("1. 测试配置加载")
    print("=" * 50)
    
    try:
        config = load_config()
        print("✓ 配置加载成功")
        
        # 显示关键配置
        print(f"\n配置详情:")
        print(f"  K线间隔: {config['kline']['interval']}")
        print(f"  历史数据量: {config['kline']['history_size']}")
        print(f"  预热数据量: {config['kline']['warmup_size']}")
        print(f"  SMTP服务器: {config['env']['smtp_host']}:{config['env']['smtp_port']}")
        print(f"  发件人: {config['env']['smtp_user']}")
        print(f"  收件人: {config['env']['alert_email']}")
        
        return config
    
    except Exception as e:
        print(f"✗ 配置加载失败: {e}")
        return None


def test_binance_api(config):
    """测试币安API连接"""
    print("\n" + "=" * 50)
    print("2. 测试币安API连接")
    print("=" * 50)
    
    try:
        client = BinanceRestClient(config)
        
        # 测试ping
        if client.test_connection():
            print("✓ API连接成功")
        else:
            print("✗ API连接失败")
            return False
        
        # 获取几个交易对测试
        print("\n获取交易对列表...")
        symbols = client.get_all_usdt_perpetual_symbols(min_volume_24h=1000000)
        print(f"✓ 获取到 {len(symbols)} 个USDT永续合约")
        print(f"  示例: {', '.join(symbols[:5])}")
        
        # 测试获取K线
        print(f"\n测试获取K线数据...")
        test_symbol = symbols[0] if symbols else 'BTCUSDT'
        klines = client.get_klines(test_symbol, '1m', limit=10)
        print(f"✓ 成功获取 {test_symbol} 的 {len(klines)} 根K线")
        
        return True
    
    except Exception as e:
        print(f"✗ 币安API测试失败: {e}")
        return False


def test_email(config):
    """测试邮件发送"""
    print("\n" + "=" * 50)
    print("3. 测试QQ邮箱连接")
    print("=" * 50)
    
    try:
        notifier = EmailNotifier(config)
        
        print("发送测试邮件...")
        if notifier.send_test_email():
            print("✓ 测试邮件发送成功")
            print(f"  请检查收件箱: {config['env']['alert_email']}")
            return True
        else:
            print("✗ 测试邮件发送失败")
            return False
    
    except Exception as e:
        print(f"✗ 邮件测试失败: {e}")
        print("\n常见问题:")
        print("  1. 请确认已开启QQ邮箱的SMTP服务")
        print("  2. 请确认使用的是授权码而非QQ密码")
        print("  3. 请确认授权码正确（16位，区分大小写）")
        return False


def main():
    """主函数"""
    print("\n🔧 加密货币监控系统 - 配置测试工具\n")
    
    # 设置日志
    logger = setup_logger(level='INFO')
    
    # 1. 测试配置加载
    config = test_config_loading()
    if not config:
        print("\n❌ 配置测试失败，请检查.env和config.yaml文件")
        return False
    
    # 2. 测试币安API
    api_ok = test_binance_api(config)
    
    # 3. 测试邮件
    email_ok = test_email(config)
    
    # 总结
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    print(f"配置加载: {'✓ 通过' if config else '✗ 失败'}")
    print(f"币安API: {'✓ 通过' if api_ok else '✗ 失败'}")
    print(f"邮件发送: {'✓ 通过' if email_ok else '✗ 失败'}")
    
    if config and api_ok and email_ok:
        print("\n✅ 所有测试通过！系统已准备就绪")
        print("\n运行命令: poetry run python main.py")
        return True
    else:
        print("\n⚠️ 部分测试未通过，请检查配置")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

