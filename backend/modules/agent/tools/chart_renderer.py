"""图表渲染器 - 使用进程池隔离 Matplotlib 操作以支持高并发

Matplotlib 不是线程安全的，多线程并发调用会产生严重的锁竞争。
本模块将图表绑制操作放到独立进程中执行，每个进程有独立的 Matplotlib 实例，
从而实现真正的并行绑制。
"""
from __future__ import annotations

import base64
import io
import os
import warnings
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.chart_renderer')

_process_pool: Optional[ProcessPoolExecutor] = None


def _get_process_pool() -> ProcessPoolExecutor:
    """获取或创建进程池（懒加载）
    
    不限制 max_workers，让系统根据 CPU 核心数自动决定。
    默认为 min(32, os.cpu_count() + 4)
    """
    global _process_pool
    if _process_pool is None:
        _process_pool = ProcessPoolExecutor()
        logger.info(f"图表渲染进程池已创建")
    return _process_pool


def shutdown_chart_renderer():
    """关闭进程池（用于程序退出时清理）"""
    global _process_pool
    if _process_pool is not None:
        _process_pool.shutdown(wait=False)
        _process_pool = None
        logger.info("图表渲染进程池已关闭")


def _render_chart_in_process(
    kline_data: List[Dict[str, Any]],
    symbol: str,
    interval: str,
    visible_count: int
) -> str:
    """在独立进程中渲染图表（此函数在子进程中执行）
    
    Args:
        kline_data: K线数据列表（字典格式，因为 Kline 对象不能跨进程传递）
        symbol: 交易对
        interval: 时间周期
        visible_count: 显示的K线数量
    
    Returns:
        base64 编码的 PNG 图像
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import matplotlib.gridspec as gridspec
    from matplotlib.ticker import MaxNLocator
    
    if not kline_data:
        raise ValueError("没有K线数据可以绘制")
    
    visible_count = min(visible_count, len(kline_data))
    
    closes = [k['close'] for k in kline_data]
    volumes = [k['volume'] for k in kline_data]
    
    def ema_list(data: List[float], period: int) -> List[Optional[float]]:
        result = []
        multiplier = 2 / (period + 1)
        ema = None
        for i, val in enumerate(data):
            if i < period - 1:
                result.append(None)
            elif i == period - 1:
                ema = sum(data[:period]) / period
                result.append(ema)
            else:
                ema = (val - ema) * multiplier + ema
                result.append(ema)
        return result
    
    ema_fast = ema_list(closes, 7)
    ema_slow = ema_list(closes, 25)
    
    bb_period = 20
    bb_std_mult = 2.0
    bb_upper, bb_middle, bb_lower = [], [], []
    
    for i in range(len(closes)):
        if i >= bb_period - 1:
            window = closes[i - bb_period + 1:i + 1]
            middle = sum(window) / len(window)
            std = (sum((x - middle) ** 2 for x in window) / len(window)) ** 0.5
            bb_upper.append(middle + bb_std_mult * std)
            bb_middle.append(middle)
            bb_lower.append(middle - bb_std_mult * std)
        else:
            bb_upper.append(None)
            bb_middle.append(None)
            bb_lower.append(None)
    
    def macd_list(data: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast_line = ema_list(data, fast)
        ema_slow_line = ema_list(data, slow)
        macd_line = []
        for f, s in zip(ema_fast_line, ema_slow_line):
            if f is not None and s is not None:
                macd_line.append(f - s)
            else:
                macd_line.append(None)
        valid_macd = [v for v in macd_line if v is not None]
        signal_line_raw = ema_list(valid_macd, signal) if valid_macd else []
        signal_line = [None] * (len(macd_line) - len(signal_line_raw)) + signal_line_raw
        histogram = []
        for m, s in zip(macd_line, signal_line):
            if m is not None and s is not None:
                histogram.append(m - s)
            else:
                histogram.append(None)
        return macd_line, signal_line, histogram
    
    macd_line, signal_line, histogram = macd_list(closes)
    
    def rsi_list(data: List[float], period: int = 14) -> List[Optional[float]]:
        if len(data) < period + 1:
            return [None] * len(data)
        result = [None] * period
        gains, losses = [], []
        for i in range(1, len(data)):
            change = data[i] - data[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                result.append(100.0)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - (100 / (1 + rs)))
        return result
    
    rsi = rsi_list(closes, 14)
    
    def slice_data(data_list, count):
        if not data_list:
            return []
        return data_list[-count:]
    
    plot_klines = slice_data(kline_data, visible_count)
    plot_volumes = slice_data(volumes, visible_count)
    plot_ema_fast = slice_data(ema_fast, visible_count)
    plot_ema_slow = slice_data(ema_slow, visible_count)
    plot_bb_upper = slice_data(bb_upper, visible_count)
    plot_bb_middle = slice_data(bb_middle, visible_count)
    plot_bb_lower = slice_data(bb_lower, visible_count)
    plot_macd = slice_data(macd_line, visible_count)
    plot_signal = slice_data(signal_line, visible_count)
    plot_hist = slice_data(histogram, visible_count)
    plot_rsi = slice_data(rsi, visible_count)
    
    fig = plt.figure(figsize=(14, 16))
    gs = gridspec.GridSpec(4, 1, height_ratios=[4, 1, 1, 1], hspace=0.12)
    
    fig.suptitle(f"{symbol} {interval} Technical Analysis", fontsize=16, fontweight='bold', y=0.96)
    
    indices = list(range(len(plot_klines)))
    
    intraday = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h']
    fmt = '%m-%d %H:%M' if interval in intraday else '%Y-%m-%d'
    date_labels = [datetime.utcfromtimestamp(k['timestamp'] / 1000.0).strftime(fmt) for k in plot_klines]
    step = max(1, len(indices) // 7)
    xticks = list(range(0, len(indices), step))
    xtick_labels = [date_labels[i] for i in xticks]
    
    up_color = '#26a69a'
    down_color = '#ef5350'
    
    ax_main = plt.subplot(gs[0])
    ax_main.set_title(f"Price Action & Overlays ({len(plot_klines)} candles)", loc='left', fontsize=11, fontweight='bold')
    ax_main.grid(True, which='major', linestyle='--', linewidth=0.6, alpha=0.5, zorder=0)
    
    width = 0.6
    for idx in indices:
        k = plot_klines[idx]
        o, h, l, c = k['open'], k['high'], k['low'], k['close']
        ax_main.plot([idx, idx], [l, h], color='#555555', linewidth=0.8, zorder=2)
        if c >= o:
            color = up_color
            height = max(c - o, 1e-10)
            y = o
        else:
            color = down_color
            height = max(o - c, 1e-10)
            y = c
        rect = patches.Rectangle((idx - width/2, y), width, height, facecolor=color, edgecolor=color, zorder=3)
        ax_main.add_patch(rect)
    
    valid_bb = [i for i in indices if i < len(plot_bb_upper) and plot_bb_upper[i] is not None]
    if valid_bb:
        ax_main.plot(valid_bb, [plot_bb_upper[i] for i in valid_bb], color='#9c27b0', alpha=0.4, linewidth=1, label='BB Upper', zorder=4)
        ax_main.plot(valid_bb, [plot_bb_middle[i] for i in valid_bb], color='#9c27b0', alpha=0.6, linewidth=1.2, linestyle='--', label='BB Mid', zorder=4)
        ax_main.plot(valid_bb, [plot_bb_lower[i] for i in valid_bb], color='#9c27b0', alpha=0.4, linewidth=1, label='BB Lower', zorder=4)
        ax_main.fill_between(valid_bb, [plot_bb_upper[i] for i in valid_bb], [plot_bb_lower[i] for i in valid_bb], color='#9c27b0', alpha=0.05, zorder=1)
    
    valid_ema_fast = [i for i in indices if i < len(plot_ema_fast) and plot_ema_fast[i] is not None]
    if valid_ema_fast:
        ax_main.plot(valid_ema_fast, [plot_ema_fast[i] for i in valid_ema_fast], color='#ff9800', linewidth=1.2, label='EMA7', zorder=5)
    
    valid_ema_slow = [i for i in indices if i < len(plot_ema_slow) and plot_ema_slow[i] is not None]
    if valid_ema_slow:
        ax_main.plot(valid_ema_slow, [plot_ema_slow[i] for i in valid_ema_slow], color='#2196f3', linewidth=1.2, label='EMA25', zorder=5)
    
    highs = [k['high'] for k in plot_klines]
    lows = [k['low'] for k in plot_klines]
    if highs and lows:
        p_min, p_max = min(lows), max(highs)
        pad = (p_max - p_min) * 0.05
        ax_main.set_ylim(p_min - pad, p_max + pad)
        ax_main.yaxis.set_major_locator(MaxNLocator(nbins=15))
        ax_main.tick_params(axis='y', labelright=True)
    
    ax_main.set_xlim(-1, len(indices))
    ax_main.set_ylabel('Price', fontsize=10)
    ax_main.legend(loc='upper left', fontsize=8, framealpha=0.8)
    ax_main.set_xticklabels([])
    
    ax_vol = plt.subplot(gs[1], sharex=ax_main)
    ax_vol.set_title("Volume", loc='left', fontsize=10, fontweight='bold')
    ax_vol.grid(True, alpha=0.3, linestyle='--')
    vol_colors = [up_color if plot_klines[i]['close'] >= plot_klines[i]['open'] else down_color for i in indices]
    ax_vol.bar(indices, plot_volumes, color=vol_colors, alpha=0.8, width=0.6)
    ax_vol.set_ylabel('Volume', fontsize=9)
    ax_vol.tick_params(axis='y', labelright=True)
    plt.setp(ax_vol.get_xticklabels(), visible=False)
    
    ax_macd = plt.subplot(gs[2], sharex=ax_main)
    ax_macd.set_title("MACD (12, 26, 9)", loc='left', fontsize=10, fontweight='bold')
    ax_macd.grid(True, alpha=0.3, linestyle='--')
    ax_macd.axhline(y=0, color='gray', linewidth=0.6, linestyle='--', alpha=0.5)
    
    valid_hist = [i for i in indices if i < len(plot_hist) and plot_hist[i] is not None]
    if valid_hist:
        colors = ['#26a69a' if plot_hist[i] >= 0 else '#ef5350' for i in valid_hist]
        ax_macd.bar(valid_hist, [plot_hist[i] for i in valid_hist], color=colors, alpha=0.6, width=0.8, label='Histogram')
    
    valid_macd = [i for i in indices if i < len(plot_macd) and plot_macd[i] is not None]
    if valid_macd:
        ax_macd.plot(valid_macd, [plot_macd[i] for i in valid_macd], color='#2196f3', linewidth=1.2, label='MACD')
        valid_signal = [i for i in valid_macd if i < len(plot_signal) and plot_signal[i] is not None]
        if valid_signal:
            ax_macd.plot(valid_signal, [plot_signal[i] for i in valid_signal], color='#ff9800', linewidth=1.2, label='Signal')
    
    ax_macd.set_ylabel('MACD', fontsize=9)
    ax_macd.legend(loc='upper left', fontsize=7, framealpha=0.8)
    ax_macd.tick_params(axis='y', labelright=True)
    plt.setp(ax_macd.get_xticklabels(), visible=False)
    
    ax_rsi = plt.subplot(gs[3], sharex=ax_main)
    ax_rsi.set_title("RSI (14)", loc='left', fontsize=10, fontweight='bold')
    ax_rsi.grid(True, alpha=0.3, linestyle='--')
    ax_rsi.axhline(y=70, color='#ef5350', linewidth=0.6, linestyle='--', alpha=0.5)
    ax_rsi.axhline(y=30, color='#26a69a', linewidth=0.6, linestyle='--', alpha=0.5)
    ax_rsi.axhline(y=50, color='gray', linewidth=0.6, linestyle='--', alpha=0.3)
    ax_rsi.fill_between(indices, 70, 100, color='#ef5350', alpha=0.1)
    ax_rsi.fill_between(indices, 0, 30, color='#26a69a', alpha=0.1)
    
    valid_rsi = [i for i in indices if i < len(plot_rsi) and plot_rsi[i] is not None]
    if valid_rsi:
        ax_rsi.plot(valid_rsi, [plot_rsi[i] for i in valid_rsi], color='#9c27b0', linewidth=1.2, label='RSI')
    
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel('RSI', fontsize=9)
    ax_rsi.set_xlabel('Candle Index', fontsize=9)
    ax_rsi.legend(loc='upper left', fontsize=7, framealpha=0.8)
    ax_rsi.tick_params(axis='y', labelright=True)
    ax_rsi.set_xticks(xticks)
    ax_rsi.set_xticklabels(xtick_labels, rotation=30, fontsize=8)
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        plt.tight_layout(rect=[0, 0.01, 1, 0.97])
    
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=90)
    plt.close(fig)
    buffer.seek(0)
    
    return base64.b64encode(buffer.read()).decode('utf-8')


def render_kline_chart(
    klines: List[Any],
    symbol: str,
    interval: str,
    visible_count: int = 200,
    timeout: float = 120.0
) -> str:
    """渲染K线图（在独立进程中执行）
    
    Args:
        klines: Kline 对象列表
        symbol: 交易对
        interval: 时间周期
        visible_count: 显示的K线数量
        timeout: 超时时间（秒）
    
    Returns:
        base64 编码的 PNG 图像
    
    Raises:
        TimeoutError: 渲染超时
        Exception: 渲染失败
    """
    kline_data = [
        {
            'timestamp': k.timestamp,
            'open': k.open,
            'high': k.high,
            'low': k.low,
            'close': k.close,
            'volume': k.volume,
        }
        for k in klines
    ]
    
    pool = _get_process_pool()
    
    try:
        future = pool.submit(_render_chart_in_process, kline_data, symbol, interval, visible_count)
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        logger.error(f"图表渲染超时: {symbol} {interval}")
        raise TimeoutError(f"图表渲染超时（{timeout}秒）")
    except Exception as e:
        logger.error(f"图表渲染失败: {symbol} {interval} - {e}")
        raise
