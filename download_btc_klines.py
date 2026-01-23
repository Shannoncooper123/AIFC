
import os
import csv
import time
import logging
from datetime import datetime, timezone

# 由于脚本在项目根目录，我们需要将 monitor_module 添加到 sys.path
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from monitor_module.clients.binance_rest import BinanceRestClient

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_all_klines(client, symbol, interval, start_str, end_str):
    """
    获取指定时间范围内的所有K线数据。

    Args:
        client: BinanceRestClient 实例。
        symbol: 交易对，例如 'BTCUSDT'。
        interval: K线间隔，例如 '1d'。
        start_str: 起始日期字符串 'YYYY-MM-DD'。
        end_str: 结束日期字符串 'YYYY-MM-DD'。

    Returns:
        一个包含所有K线数据的列表。
    """
    # 将日期字符串转换为毫秒时间戳
    start_ts = int(datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)

    all_klines = []
    current_start_ts = start_ts

    logging.info(f"开始从币安获取 {symbol} 的 {interval} K线数据...")
    logging.info(f"时间范围: {start_str} to {end_str}")

    while current_start_ts < end_ts:
        try:
            logging.info(f"正在获取从 {datetime.fromtimestamp(current_start_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} 开始的数据...")
            
            klines = client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=1500,
                start_time=current_start_ts,
                end_time=end_ts
            )

            if not klines:
                logging.info("没有更多数据，或已到达时间范围末尾。")
                break

            all_klines.extend(klines)
            
            # 更新下一次请求的起始时间为最后一条K线的开盘时间 + 1毫秒
            last_kline_ts = klines[-1][0]
            current_start_ts = last_kline_ts + 1

            logging.info(f"成功获取 {len(klines)} 条K线数据，最后一条时间为: {datetime.fromtimestamp(last_kline_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")

            # 遵循币安API的请求频率限制，稍作等待
            time.sleep(0.5)

        except Exception as e:
            logging.error(f"获取K线数据时发生错误: {e}")
            logging.info("将在5秒后重试...")
            time.sleep(5)
    
    logging.info(f"总共获取了 {len(all_klines)} 条K线数据。")
    return all_klines

def save_to_csv(klines, filename):
    """
    将K线数据保存到CSV文件。

    Args:
        klines: K线数据列表。
        filename: 输出的CSV文件名。
    """
    if not klines:
        logging.warning("没有K线数据可以保存。")
        return

    header = [
        'open_time', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'quote_asset_volume', 'number_of_trades', 
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ]

    logging.info(f"正在将数据写入到 {filename}...")

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            
            for kline in klines:
                # 将开盘和收盘时间戳转换为人类可读的日期时间格式
                kline[0] = datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                kline[6] = datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow(kline)
        
        logging.info(f"数据成功保存到 {filename}")

    except IOError as e:
        logging.error(f"写入CSV文件时发生错误: {e}")


if __name__ == "__main__":
    # --- 配置 ---
    # 主流加密货币列表（币安合约交易对）
    SYMBOLS = [
        'ETHUSDT' 
    ]
    
    # K线间隔: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
    INTERVAL = '3m'
    START_DATE = '2020-01-01'  # 起始日期
    END_DATE = '2025-11-24'    # 结束日期
    
    # 创建数据存储目录
    DATA_DIR = 'data/klines_15m'
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.info(f"数据将保存到目录: {DATA_DIR}")

    # --- 初始化客户端 ---
    # 为BinanceRestClient创建一个模拟的配置字典
    # 注意：对于公共数据接口，API Key和Secret不是必需的
    config = {
        'api': {
            'base_url': 'https://fapi.binance.com', # 合约API地址
            'timeout': 10,
            'retry_times': 3
        },
        'env': {
            'binance_api_key': '',
            'binance_api_secret': ''
        }
    }
    
    binance_client = BinanceRestClient(config)

    # --- 批量下载所有币种的K线数据 ---
    total_symbols = len(SYMBOLS)
    successful_downloads = []
    failed_downloads = []
    
    logging.info(f"=" * 80)
    logging.info(f"开始批量下载 {total_symbols} 个币种的 {INTERVAL} K线数据")
    logging.info(f"时间范围: {START_DATE} 到 {END_DATE}")
    logging.info(f"=" * 80)
    
    for idx, symbol in enumerate(SYMBOLS, 1):
        try:
            logging.info(f"\n[{idx}/{total_symbols}] 正在处理 {symbol}...")
            
            # 构建输出文件路径
            output_file = os.path.join(DATA_DIR, f"{symbol.lower()}_{INTERVAL}_{START_DATE}_to_{END_DATE}.csv")
            
            # 检查文件是否已存在
            if os.path.exists(output_file):
                logging.warning(f"文件 {output_file} 已存在，跳过下载。如需重新下载，请先删除该文件。")
                successful_downloads.append(symbol)
                continue
            
            # 获取K线数据
            all_klines_data = get_all_klines(binance_client, symbol, INTERVAL, START_DATE, END_DATE)
            
            # 保存到CSV
            save_to_csv(all_klines_data, output_file)
            
            successful_downloads.append(symbol)
            logging.info(f"✓ {symbol} 下载完成！")
            
            # 每个币种下载完成后稍作等待，避免触发API限制
            if idx < total_symbols:
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"✗ 下载 {symbol} 时发生错误: {e}")
            failed_downloads.append((symbol, str(e)))
            # 发生错误后等待更长时间
            time.sleep(5)
    
    # --- 打印下载总结 ---
    logging.info(f"\n" + "=" * 80)
    logging.info(f"下载任务完成！")
    logging.info(f"=" * 80)
    logging.info(f"成功下载: {len(successful_downloads)}/{total_symbols}")
    logging.info(f"失败下载: {len(failed_downloads)}/{total_symbols}")
    
    if successful_downloads:
        logging.info(f"\n成功下载的币种:")
        for symbol in successful_downloads:
            logging.info(f"  ✓ {symbol}")
    
    if failed_downloads:
        logging.warning(f"\n失败的币种:")
        for symbol, error in failed_downloads:
            logging.warning(f"  ✗ {symbol}: {error}")
    
    logging.info(f"\n所有数据已保存到目录: {DATA_DIR}")
