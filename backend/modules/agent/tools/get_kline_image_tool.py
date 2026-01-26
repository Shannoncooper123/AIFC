"""获取K线图图像的工具（含技术指标）"""
import base64
import io
import warnings
from datetime import datetime
from typing import Dict, Any, List, Optional
from langchain.tools import tool
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator

from modules.agent.tools.tool_utils import validate_symbol, validate_interval
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

from modules.monitor.indicators.volatility import (
    calculate_ema_list,
    calculate_rsi_list,
    calculate_bollinger_bands,
    calculate_macd_list,
)

logger = get_logger('agent.tool.get_kline_image')


def _plot_candlestick_chart(klines: List[Kline], symbol: str, interval: str, visible_count: int) -> str:
    """
    生成单周期K线图（含技术指标）并返回base64编码的PNG图像
    
    Args:
        klines: Kline对象列表（包含用于计算指标的历史数据）
        symbol: 交易对名称
        interval: 时间周期
        visible_count: 实际显示的K线数量（从末尾截取）
        
    Returns:
        base64编码的PNG图像字符串
    """
    if not klines:
        raise ValueError("没有K线数据可以绘制")
    
    # 确保visible_count不超过数据总量
    visible_count = min(visible_count, len(klines))
    
    # 计算技术指标（在切片前计算，确保指标数据的完整性）
    closes = [k.close for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    volumes = [k.volume for k in klines]
    
    # EMA (7, 25)
    ema_fast = calculate_ema_list(closes, 7)
    ema_slow = calculate_ema_list(closes, 25)
    
    # Bollinger Bands - 逐点计算  
    bb_period = 20
    bb_std = 2.0
    bb_upper_list = []
    bb_middle_list = []
    bb_lower_list = []
    
    for i in range(len(closes)):
        if i >= bb_period - 1:
            window = closes[i - bb_period + 1:i + 1]
            middle = sum(window) / len(window)
            std = (sum((x - middle) ** 2 for x in window) / len(window)) ** 0.5
            bb_upper_list.append(middle + bb_std * std)
            bb_middle_list.append(middle)
            bb_lower_list.append(middle - bb_std * std)
        else:
            bb_upper_list.append(None)
            bb_middle_list.append(None)
            bb_lower_list.append(None)
    
    # MACD
    macd_line, signal_line, histogram = calculate_macd_list(closes, 12, 26, 9)
    
    # RSI - 需要特殊处理对齐
    rsi_raw = calculate_rsi_list(closes, 14)
    # calculate_rsi_list 返回的长度比输入短，需要前面补None对齐
    # 假设 rsi_raw 长度为 L_rsi，closes 长度为 L_closes
    # 缺失的数量 = L_closes - L_rsi
    rsi = [None] * (len(closes) - len(rsi_raw)) + rsi_raw
    
    # === 数据切片：只保留最后 visible_count 个数据用于绘图 ===
    
    # 切片函数
    def slice_data(data_list, count):
        if not data_list:
            return []
        return data_list[-count:]
    
    plot_klines = slice_data(klines, visible_count)
    plot_volumes = slice_data(volumes, visible_count)
    plot_ema_fast = slice_data(ema_fast, visible_count)
    plot_ema_slow = slice_data(ema_slow, visible_count)
    plot_bb_upper = slice_data(bb_upper_list, visible_count)
    plot_bb_middle = slice_data(bb_middle_list, visible_count)
    plot_bb_lower = slice_data(bb_lower_list, visible_count)
    plot_macd = slice_data(macd_line, visible_count)
    plot_signal = slice_data(signal_line, visible_count)
    plot_hist = slice_data(histogram, visible_count)
    plot_rsi = slice_data(rsi, visible_count)
    
    # 创建图表
    fig = plt.figure(figsize=(16, 20))
    gs = gridspec.GridSpec(4, 1, height_ratios=[4, 1, 1, 1], hspace=0.15)
    
    fig.suptitle(f"{symbol} {interval} Technical Analysis", fontsize=18, fontweight='bold', y=0.95)
    
    # X轴索引（0 到 visible_count-1）
    indices = list(range(len(plot_klines)))
    from modules.constants import INTRADAY_INTERVALS
    fmt = '%m-%d %H:%M' if interval in INTRADAY_INTERVALS else '%Y-%m-%d'
    date_labels = [datetime.utcfromtimestamp(k.timestamp / 1000.0).strftime(fmt) for k in plot_klines]
    step = max(1, len(indices) // 7)
    xticks = list(range(0, len(indices), step))
    xtick_labels = [date_labels[i] for i in xticks]
    
    # 定义颜色
    up_color = '#26a69a'    # 青绿色 - 上涨
    down_color = '#ef5350'  # 红色 - 下跌
    
    # === 主图：K线 + EMA + BB ===
    ax_main = plt.subplot(gs[0])
    ax_main.set_title(f"Price Action & Overlays ({len(plot_klines)} candles)", loc='left', fontsize=12, fontweight='bold')
    
    # 优化网格线：增加密度和可见度
    ax_main.grid(True, which='major', linestyle='--', linewidth=0.8, alpha=0.6, zorder=0)
    ax_main.grid(True, which='minor', linestyle=':', linewidth=0.5, alpha=0.4, zorder=0)
    
    # 绘制蜡烛图
    width = 0.6
    
    for idx in indices:
        k = plot_klines[idx]
        o, h, l, c = k.open, k.high, k.low, k.close
        
        # 影线
        ax_main.plot([idx, idx], [l, h], color='#555555', linewidth=1.0, zorder=2)
        
        # 实体
        if c >= o:
            color = up_color
            height = max(c - o, 0.00000001)
            y = o
        else:
            color = down_color
            height = max(o - c, 0.00000001)
            y = c
        
        rect = patches.Rectangle(
            (idx - width/2, y), width, height,
            facecolor=color, edgecolor=color, alpha=1.0, zorder=3
        )
        ax_main.add_patch(rect)
    
    # 绘制Bollinger Bands
    valid_indices = [i for i in indices if i < len(plot_bb_upper) and plot_bb_upper[i] is not None]
    if valid_indices:
        ax_main.plot(valid_indices, [plot_bb_upper[i] for i in valid_indices], 
                    color='#9c27b0', alpha=0.4, linewidth=1, label='BB Upper', zorder=4)
        valid_mid = [i for i in valid_indices if i < len(plot_bb_middle) and plot_bb_middle[i] is not None]
        if valid_mid:
            ax_main.plot(valid_mid, [plot_bb_middle[i] for i in valid_mid], 
                        color='#9c27b0', alpha=0.6, linewidth=1.5, linestyle='--', label='BB Mid', zorder=4)
        valid_lower = [i for i in valid_indices if i < len(plot_bb_lower) and plot_bb_lower[i] is not None]
        if valid_lower:
            ax_main.plot(valid_lower, [plot_bb_lower[i] for i in valid_lower], 
                        color='#9c27b0', alpha=0.4, linewidth=1, label='BB Lower', zorder=4)
        common_indices = [i for i in valid_indices if i < len(plot_bb_lower) and plot_bb_lower[i] is not None]
        if common_indices:
            ax_main.fill_between(common_indices, 
                                [plot_bb_upper[i] for i in common_indices],
                                [plot_bb_lower[i] for i in common_indices],
                                color='#9c27b0', alpha=0.05, zorder=1)
    
    # 绘制EMA
    valid_indices = [i for i in indices if i < len(plot_ema_fast) and plot_ema_fast[i] is not None]
    if valid_indices:
        ax_main.plot(valid_indices, [plot_ema_fast[i] for i in valid_indices], 
                    color='#ff9800', linewidth=1.5, label='EMA7', zorder=5)
    
    valid_indices = [i for i in indices if i < len(plot_ema_slow) and plot_ema_slow[i] is not None]
    if valid_indices:
        ax_main.plot(valid_indices, [plot_ema_slow[i] for i in valid_indices], 
                    color='#2196f3', linewidth=1.5, label='EMA25', zorder=5)
    
    # 设置Y轴
    highs = [k.high for k in plot_klines]
    lows = [k.low for k in plot_klines]
    if highs and lows:
        p_min, p_max = min(lows), max(highs)
        pad = (p_max - p_min) * 0.05
        ax_main.set_ylim(p_min - pad, p_max + pad)
        
        # 增加Y轴刻度密度
        ax_main.yaxis.set_major_locator(MaxNLocator(nbins=20))
        ax_main.tick_params(axis='y', labelright=True)
    
    ax_main.set_xlim(-1, len(indices))
    ax_main.set_ylabel('Price', fontsize=11)
    ax_main.legend(loc='upper left', fontsize=9, framealpha=0.8)
    ax_main.set_xticklabels([])
    
    # === 成交量图 ===
    ax_vol = plt.subplot(gs[1], sharex=ax_main)
    ax_vol.set_title("Volume", loc='left', fontsize=10, fontweight='bold')
    ax_vol.grid(True, alpha=0.3, linestyle='--')
    
    vol_colors = []
    for idx in indices:
        k = plot_klines[idx]
        if k.close >= k.open:
            vol_colors.append(up_color)
        else:
            vol_colors.append(down_color)
            
    ax_vol.bar(indices, plot_volumes, color=vol_colors, alpha=0.8, width=0.6)
    ax_vol.set_ylabel('Volume', fontsize=10)
    ax_vol.tick_params(axis='y', labelright=True)
    plt.setp(ax_vol.get_xticklabels(), visible=False)

    # === MACD图 ===
    ax_macd = plt.subplot(gs[2], sharex=ax_main)
    ax_macd.set_title("MACD (12, 26, 9)", loc='left', fontsize=10, fontweight='bold')
    ax_macd.grid(True, alpha=0.3, linestyle='--')
    ax_macd.axhline(y=0, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
    
    has_macd_legend = False
    if plot_hist:
        valid_indices = [i for i in indices if i < len(plot_hist)]
        if valid_indices:
            colors = ['#26a69a' if plot_hist[i] >= 0 else '#ef5350' for i in valid_indices]
            ax_macd.bar(valid_indices, [plot_hist[i] for i in valid_indices], 
                       color=colors, alpha=0.6, width=0.8, label='Histogram')
            has_macd_legend = True
    
    if plot_macd:
        valid_indices = [i for i in indices if i < len(plot_macd)]
        if valid_indices:
            ax_macd.plot(valid_indices, [plot_macd[i] for i in valid_indices], 
                        color='#2196f3', linewidth=1.5, label='MACD')
            has_macd_legend = True
            if plot_signal:
                valid_signal_indices = [i for i in valid_indices if i < len(plot_signal)]
                if valid_signal_indices:
                    ax_macd.plot(valid_signal_indices, [plot_signal[i] for i in valid_signal_indices], 
                                color='#ff9800', linewidth=1.5, label='Signal')
    
    if not has_macd_legend:
        ax_macd.text(0.5, 0.5, 'Insufficient data for MACD', transform=ax_macd.transAxes,
                    ha='center', va='center', fontsize=10, color='gray', alpha=0.7)
    
    ax_macd.set_ylabel('MACD', fontsize=10)
    if has_macd_legend:
        ax_macd.legend(loc='upper left', fontsize=8, framealpha=0.8)
    ax_macd.tick_params(axis='y', labelright=True)
    plt.setp(ax_macd.get_xticklabels(), visible=False)
    
    # === RSI图 ===
    ax_rsi = plt.subplot(gs[3], sharex=ax_main)
    ax_rsi.set_title("RSI (14)", loc='left', fontsize=10, fontweight='bold')
    ax_rsi.grid(True, alpha=0.3, linestyle='--')
    ax_rsi.axhline(y=70, color='#ef5350', linewidth=0.8, linestyle='--', alpha=0.5)
    ax_rsi.axhline(y=30, color='#26a69a', linewidth=0.8, linestyle='--', alpha=0.5)
    ax_rsi.axhline(y=50, color='gray', linewidth=0.8, linestyle='--', alpha=0.3)
    
    ax_rsi.fill_between(indices, 70, 100, color='#ef5350', alpha=0.1)
    ax_rsi.fill_between(indices, 0, 30, color='#26a69a', alpha=0.1)
    
    has_rsi_legend = False
    if plot_rsi:
        valid_indices = [i for i in indices if i < len(plot_rsi) and plot_rsi[i] is not None]
        if valid_indices:
            ax_rsi.plot(valid_indices, [plot_rsi[i] for i in valid_indices], 
                       color='#9c27b0', linewidth=1.5, label='RSI')
            has_rsi_legend = True
    
    if not has_rsi_legend:
        ax_rsi.text(0.5, 0.5, 'Insufficient data for RSI', transform=ax_rsi.transAxes,
                   ha='center', va='center', fontsize=10, color='gray', alpha=0.7)
    
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel('RSI', fontsize=10)
    ax_rsi.set_xlabel('Candle Index', fontsize=10)
    if has_rsi_legend:
        ax_rsi.legend(loc='upper left', fontsize=8, framealpha=0.8)
    ax_rsi.tick_params(axis='y', labelright=True)
    ax_rsi.set_xticks(xticks)
    ax_rsi.set_xticklabels(xtick_labels, rotation=30, fontsize=9)
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        plt.tight_layout(rect=[0, 0.01, 1, 0.98])
    
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    
    return image_base64


@tool("get_kline_image", description="获取K线图图像数据（含技术指标）", parse_docstring=True)
def get_kline_image_tool(
    symbol: str,
    interval: str = "1h",
    feedback: str = "",
) -> List[Dict[str, Any]]:
    """获取单周期K线图并进行视觉分析（含技术指标：EMA、MACD、RSI、Bollinger Bands）。
    
    该工具生成指定时间周期的K线图，返回多模态内容（文本描述+图像），供模型进行视觉分析。
    返回格式为 list[dict]，包含文本和图像内容块。错误时返回包含错误信息的文本块。
    
    Args:
        symbol: 交易对，如 "BTCUSDT"
        interval: 时间周期，如 "15m"、"1h"、"4h"、"1d"。默认为 "1h"。注意：仅支持单个周期。
        feedback: 分析进度笔记。请填写：1) 上一周期分析的关键结论（趋势方向、关键位、动能状态）；2) 本次调用的分析目的（如"验证4h趋势是否与1d一致"或"寻找1h级别的入场触发信号"）。
    """
    def _make_error(msg: str) -> List[Dict[str, Any]]:
        return [{"type": "text", "text": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}]
    
    def _make_runtime_error(msg: str) -> List[Dict[str, Any]]:
        return [{"type": "text", "text": f"TOOL_RUNTIME_ERROR: {msg}"}]
    
    try:
        limit = 200
        
        logger.info(f"get_kline_image_tool 被调用 - symbol={symbol}, interval={interval}, limit={limit}")
        
        error = validate_symbol(symbol)
        if error:
            return _make_error(error)
        
        error = validate_interval(interval)
        if error:
            return _make_error(error)
        
        if ',' in interval:
             return _make_error("参数 interval 仅支持单个周期，请不要使用逗号分隔。如需多个周期请多次调用。")
        
        interval = interval.strip()
        
        from modules.agent.tools.tool_utils import get_binance_client
        fetch_limit = limit + 100
        client = get_binance_client()
        
        logger.info(f"获取 {symbol} {interval} K线数据，数量={fetch_limit} (显示{limit})")
        raw = client.get_klines(symbol, interval, fetch_limit)
        
        if not raw:
            return _make_runtime_error(f"未获取到 {symbol} {interval} 的K线数据")
            
        klines = [Kline.from_rest_api(item) for item in raw]
        
        logger.info(f"生成 {symbol} {interval} K线图（含技术指标）")
        image_base64 = _plot_candlestick_chart(klines, symbol, interval, limit)
        
        return [
            {
                "type": "text",
                "text": f"K线图生成成功\n交易对: {symbol}\n时间周期: {interval}\nK线数量: {limit}"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                    "detail": "high"
                }
            }
        ]
        
    except Exception as e:
        logger.error(f"K线图分析失败: {e}", exc_info=True)
        return _make_runtime_error(f"生成K线图失败 - {str(e)}")
