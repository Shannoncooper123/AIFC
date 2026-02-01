"""轻量级 K 线图渲染器 - 基于 Pillow 实现 (Matplotlib 风格)

相比 Matplotlib 方案的优势：
1. 线程安全 - 不需要子进程隔离
2. 极轻量 - 内存占用小，启动快
3. 高并发友好 - 200+ 线程同时绑制也没问题
"""
from __future__ import annotations

import base64
import io
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.chart_renderer_pillow')

UP_COLOR = (38, 166, 154)
DOWN_COLOR = (239, 83, 80)
GRID_COLOR = (180, 180, 180)
TEXT_COLOR = (40, 40, 40)
BG_COLOR = (255, 255, 255)
AXIS_COLOR = (80, 80, 80)

EMA_FAST_COLOR = (255, 140, 0)
EMA_SLOW_COLOR = (30, 144, 255)
BB_COLOR = (148, 0, 211)
BB_FILL_COLOR = (148, 0, 211, 25)
MACD_COLOR = (30, 144, 255)
SIGNAL_COLOR = (255, 140, 0)
RSI_COLOR = (148, 0, 211)
RSI_OVERBOUGHT_BG = (255, 200, 200, 60)
RSI_OVERSOLD_BG = (200, 255, 200, 60)

SCALE_FACTOR = 2


def _get_price_decimals(price: float) -> int:
    if price >= 1000: return 2
    elif price >= 1: return 4
    elif price >= 0.01: return 6
    elif price >= 0.0001: return 8
    else: return 10


def _format_price(price: float, decimals: int) -> str:
    return f"{price:.{decimals}f}"


def _draw_dashed_line(draw: ImageDraw.Draw, xy: List[Tuple[float, float]], fill: Any, width: int = 1, dash: Tuple[int, int] = (5, 3)):
    x1, y1 = xy[0]
    x2, y2 = xy[1]
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    if dist == 0:
        return
    
    dash_len = dash[0] + dash[1]
    steps = int(dist / dash_len)
    
    for i in range(steps + 1):
        start = i * dash_len
        end = start + dash[0]
        if start > dist: break
        if end > dist: end = dist
        
        t1 = start / dist
        t2 = end / dist
        
        px1 = x1 + dx * t1
        py1 = y1 + dy * t1
        px2 = x1 + dx * t2
        py2 = y1 + dy * t2
        
        draw.line([(px1, py1), (px2, py2)], fill=fill, width=width)


def _calculate_ema(data: List[float], period: int) -> List[Optional[float]]:
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


def _calculate_bollinger(closes: List[float], period: int = 20, std_mult: float = 2.0) -> Tuple[List, List, List]:
    bb_upper, bb_middle, bb_lower = [], [], []
    for i in range(len(closes)):
        if i >= period - 1:
            window = closes[i - period + 1:i + 1]
            middle = sum(window) / len(window)
            std = (sum((x - middle) ** 2 for x in window) / len(window)) ** 0.5
            bb_upper.append(middle + std_mult * std)
            bb_middle.append(middle)
            bb_lower.append(middle - std_mult * std)
        else:
            bb_upper.append(None)
            bb_middle.append(None)
            bb_lower.append(None)
    return bb_upper, bb_middle, bb_lower


def _calculate_macd(data: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _calculate_ema(data, fast)
    ema_slow = _calculate_ema(data, slow)
    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)
    valid_macd = [v for v in macd_line if v is not None]
    signal_line_raw = _calculate_ema(valid_macd, signal) if valid_macd else []
    signal_line = [None] * (len(macd_line) - len(signal_line_raw)) + signal_line_raw
    histogram = []
    for m, s in zip(macd_line, signal_line):
        if m is not None and s is not None:
            histogram.append(m - s)
        else:
            histogram.append(None)
    return macd_line, signal_line, histogram


def _calculate_rsi(data: List[float], period: int = 14) -> List[Optional[float]]:
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


def _try_load_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


class PillowChartRenderer:
    def __init__(
        self,
        width: int = 1800,
        height: int = 2000,
        padding_left: int = 60,
        padding_right: int = 100,
        padding_top: int = 50,
        padding_bottom: int = 30,
    ):
        self.width = width
        self.height = height
        self.padding_left = padding_left
        self.padding_right = padding_right
        self.padding_top = padding_top
        self.padding_bottom = padding_bottom
        
        self.price_area_ratio = 0.40
        self.volume_area_ratio = 0.16
        self.macd_area_ratio = 0.22
        self.rsi_area_ratio = 0.16
        self.x_label_height = 50
        self.legend_height = 20
        self.gap = 8
        
        self.font_small = _try_load_font(11)
        self.font_medium = _try_load_font(13)
        self.font_large = _try_load_font(15)
        self.font_title = _try_load_font(18)
        
        self.scale = SCALE_FACTOR
        self.font_small_hd = _try_load_font(11 * self.scale)
        self.font_medium_hd = _try_load_font(13 * self.scale)
        self.font_title_hd = _try_load_font(18 * self.scale)
    
    def render(
        self,
        kline_data: List[Dict[str, Any]],
        symbol: str,
        interval: str,
        visible_count: int = 100,
    ) -> str:
        if not kline_data:
            raise ValueError("没有K线数据可以绑制")
        
        visible_count = min(visible_count, len(kline_data))
        klines = kline_data[-visible_count:]
        
        closes = [k['close'] for k in kline_data]
        ema_fast = _calculate_ema(closes, 7)[-visible_count:]
        ema_slow = _calculate_ema(closes, 25)[-visible_count:]
        bb_upper, bb_middle, bb_lower = _calculate_bollinger(closes)
        bb_upper = bb_upper[-visible_count:]
        bb_lower = bb_lower[-visible_count:]
        macd_line, signal_line, histogram = _calculate_macd(closes)
        macd_line = macd_line[-visible_count:]
        signal_line = signal_line[-visible_count:]
        histogram = histogram[-visible_count:]
        rsi = _calculate_rsi(closes)[-visible_count:]
        volumes = [k['volume'] for k in klines]
        
        s = self.scale
        hd_width = self.width * s
        hd_height = self.height * s
        
        img = Image.new('RGBA', (hd_width, hd_height), (*BG_COLOR, 255))
        draw = ImageDraw.Draw(img, 'RGBA')
        
        chart_left = self.padding_left * s
        chart_right = hd_width - self.padding_right * s
        chart_width = chart_right - chart_left
        chart_top = self.padding_top * s
        chart_bottom = hd_height - self.padding_bottom * s
        
        legend_h = self.legend_height * s
        x_label_h = self.x_label_height * s
        gap = self.gap * s
        
        total_chart_height = chart_bottom - chart_top - 4 * (legend_h + x_label_h + gap)
        
        price_height = int(total_chart_height * self.price_area_ratio)
        volume_height = int(total_chart_height * self.volume_area_ratio)
        macd_height = int(total_chart_height * self.macd_area_ratio)
        rsi_height = int(total_chart_height * self.rsi_area_ratio)
        
        price_legend_top = chart_top
        price_top = price_legend_top + legend_h
        price_bottom = price_top + price_height
        price_xlabel_bottom = price_bottom + x_label_h
        
        volume_legend_top = price_xlabel_bottom + gap
        volume_top = volume_legend_top + legend_h
        volume_bottom = volume_top + volume_height
        volume_xlabel_bottom = volume_bottom + x_label_h
        
        macd_legend_top = volume_xlabel_bottom + gap
        macd_top = macd_legend_top + legend_h
        macd_bottom = macd_top + macd_height
        macd_xlabel_bottom = macd_bottom + x_label_h
        
        rsi_legend_top = macd_xlabel_bottom + gap
        rsi_top = rsi_legend_top + legend_h
        rsi_bottom = rsi_top + rsi_height
        rsi_xlabel_bottom = rsi_bottom + x_label_h
        
        n = len(klines)
        candle_total_width = chart_width / n
        candle_width = max(4 * s, int(candle_total_width * 0.75))
        
        intraday = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h']
        time_fmt = '%m-%d %H:%M' if interval in intraday else '%Y-%m-%d'
        
        title = f"{symbol} {interval} Technical Analysis"
        bbox = draw.textbbox((0, 0), title, font=self.font_title_hd)
        title_width = bbox[2] - bbox[0]
        draw.text(((hd_width - title_width) // 2, 8 * s), title, fill=TEXT_COLOR, font=self.font_title_hd)
        
        self._draw_legend_row(draw, chart_left, price_legend_top, "Price Action & Overlays", [
            ("EMA7", EMA_FAST_COLOR), ("EMA25", EMA_SLOW_COLOR), ("BB", BB_COLOR)
        ], s)
        
        self._draw_price_chart(
            draw, img, klines, ema_fast, ema_slow, bb_upper, bb_lower,
            chart_left, price_top, chart_width, price_height,
            candle_width, candle_total_width, s
        )
        self._draw_x_axis(draw, klines, chart_left, price_bottom, chart_width, candle_total_width, time_fmt, s)
        
        self._draw_legend_row(draw, chart_left, volume_legend_top, "Volume", [], s)
        self._draw_volume_chart(
            draw, klines, volumes,
            chart_left, volume_top, chart_width, volume_height,
            candle_width, candle_total_width, s
        )
        self._draw_x_axis(draw, klines, chart_left, volume_bottom, chart_width, candle_total_width, time_fmt, s)
        
        self._draw_legend_row(draw, chart_left, macd_legend_top, "MACD (12, 26, 9)", [
            ("MACD", MACD_COLOR), ("Signal", SIGNAL_COLOR), ("Histogram", UP_COLOR)
        ], s)
        self._draw_macd_chart(
            draw, macd_line, signal_line, histogram,
            chart_left, macd_top, chart_width, macd_height,
            candle_width, candle_total_width, s
        )
        self._draw_x_axis(draw, klines, chart_left, macd_bottom, chart_width, candle_total_width, time_fmt, s)
        
        self._draw_legend_row(draw, chart_left, rsi_legend_top, "RSI (14)", [("RSI", RSI_COLOR)], s)
        self._draw_rsi_chart(
            draw, img, rsi,
            chart_left, rsi_top, chart_width, rsi_height,
            candle_width, candle_total_width, s
        )
        self._draw_x_axis(draw, klines, chart_left, rsi_bottom, chart_width, candle_total_width, time_fmt, s)
        
        img_rgb = Image.new('RGB', img.size, BG_COLOR)
        img_rgb.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
        
        final_img = img_rgb.resize((self.width, self.height), Image.LANCZOS)
        
        buffer = io.BytesIO()
        final_img.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')
    
    def _draw_legend_row(self, draw, left: int, top: int, title: str, items: List[Tuple[str, Tuple]], s: int):
        """绘制图例行（在图表外部左上方）"""
        draw.text((left, top), title, fill=TEXT_COLOR, font=self.font_medium_hd)
        
        if items:
            title_bbox = draw.textbbox((0, 0), title, font=self.font_medium_hd)
            curr_x = left + (title_bbox[2] - title_bbox[0]) + 20 * s
            
            for label, color in items:
                draw.rectangle([curr_x, top + 4*s, curr_x + 12*s, top + 12*s], fill=color)
                draw.text((curr_x + 15*s, top), label, fill=TEXT_COLOR, font=self.font_small_hd)
                label_bbox = draw.textbbox((0, 0), label, font=self.font_small_hd)
                curr_x += 15*s + (label_bbox[2] - label_bbox[0]) + 15*s
    
    def _draw_x_axis(self, draw, klines, left, top, width, candle_total_width, fmt, s):
        """绘制X轴时间标签"""
        n = len(klines)
        step = max(1, n // 10)
        
        def get_x(i): return left + i * candle_total_width + candle_total_width / 2
        
        for i in range(0, n, step):
            ts = klines[i]['timestamp']
            dt_str = datetime.utcfromtimestamp(ts / 1000.0).strftime(fmt)
            
            x = get_x(i)
            draw.line([(x, top), (x, top + 5*s)], fill=AXIS_COLOR, width=s)
            
            bbox = draw.textbbox((0, 0), dt_str, font=self.font_small_hd)
            text_width = bbox[2] - bbox[0]
            draw.text((x - text_width // 2, top + 8*s), dt_str, fill=TEXT_COLOR, font=self.font_small_hd)
    
    def _draw_grid_and_ticks(
        self,
        draw: ImageDraw.Draw,
        left: int,
        top: int,
        width: int,
        height: int,
        h_values: List[Tuple[float, str]],
        s: int,
    ):
        right = left + width
        bottom = top + height
        
        draw.rectangle([left, top, right, bottom], outline=AXIS_COLOR, width=s)
        
        tick_len = 5 * s
        
        for val, label in h_values:
            y = bottom - int(val * height)
            
            if 0 < val < 1:
                _draw_dashed_line(draw, [(left, y), (right, y)], fill=GRID_COLOR, width=s, dash=(8*s, 4*s))
            
            draw.line([(right, y), (right + tick_len, y)], fill=AXIS_COLOR, width=s)
            
            if label:
                bbox = draw.textbbox((0, 0), label, font=self.font_small_hd)
                h_text = bbox[3] - bbox[1]
                draw.text((right + tick_len + 3*s, y - h_text // 2), label, fill=TEXT_COLOR, font=self.font_small_hd)

    def _draw_price_chart(
        self,
        draw: ImageDraw.Draw,
        img: Image.Image,
        klines: List[Dict],
        ema_fast: List,
        ema_slow: List,
        bb_upper: List,
        bb_lower: List,
        left: int,
        top: int,
        width: int,
        height: int,
        candle_width: int,
        candle_total_width: float,
        s: int,
    ):
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        p_min, p_max = min(lows), max(highs)
        pad = (p_max - p_min) * 0.03
        p_min -= pad
        p_max += pad
        
        decimals = _get_price_decimals(p_max)
        num_grid = 15
        grid_values = []
        for i in range(num_grid + 1):
            norm_val = i / num_grid
            price = p_min + (p_max - p_min) * norm_val
            grid_values.append((norm_val, _format_price(price, decimals)))
            
        self._draw_grid_and_ticks(draw, left, top, width, height, grid_values, s)
        
        right = left + width
        bottom = top + height
        
        def price_to_y(price: float) -> int:
            if p_max == p_min: return top + height // 2
            return top + height - int((price - p_min) / (p_max - p_min) * height)
        
        def get_x(i: int) -> float:
            return left + i * candle_total_width + candle_total_width / 2
        
        n = len(klines)
        
        bb_fill_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bb_fill_draw = ImageDraw.Draw(bb_fill_img, 'RGBA')
        
        bb_polygon = []
        for i in range(n):
            if bb_upper[i] is not None:
                x = get_x(i)
                y = price_to_y(bb_upper[i])
                y = max(top, min(bottom, y))
                bb_polygon.append((x, y))
        for i in range(n - 1, -1, -1):
            if bb_lower[i] is not None:
                x = get_x(i)
                y = price_to_y(bb_lower[i])
                y = max(top, min(bottom, y))
                bb_polygon.append((x, y))
        
        if len(bb_polygon) > 2:
            bb_fill_draw.polygon(bb_polygon, fill=BB_FILL_COLOR)
            mask = Image.new('L', img.size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rectangle([left, top, right, bottom], fill=255)
            bb_fill_img.putalpha(Image.composite(bb_fill_img.split()[3], Image.new('L', img.size, 0), mask))
            img.paste(bb_fill_img, (0, 0), bb_fill_img)
        
        def draw_clipped_line(data, color, w):
            points = []
            for i in range(n):
                if data[i] is not None:
                    x = get_x(i)
                    y = price_to_y(data[i])
                    y = max(top, min(bottom, y))
                    points.append((x, y))
            if len(points) > 1:
                draw.line(points, fill=color, width=w, joint='curve')
        
        draw_clipped_line(bb_upper, BB_COLOR, s)
        draw_clipped_line(bb_lower, BB_COLOR, s)
        draw_clipped_line(ema_fast, EMA_FAST_COLOR, 2*s)
        draw_clipped_line(ema_slow, EMA_SLOW_COLOR, 2*s)

        for i, k in enumerate(klines):
            x_center = get_x(i)
            x_left = x_center - candle_width / 2
            x_right = x_center + candle_width / 2
            
            y_high = price_to_y(k['high'])
            y_low = price_to_y(k['low'])
            y_open = price_to_y(k['open'])
            y_close = price_to_y(k['close'])
            
            color = UP_COLOR if k['close'] >= k['open'] else DOWN_COLOR
            
            draw.line([(x_center, y_high), (x_center, y_low)], fill=color, width=s)
            
            body_top = min(y_open, y_close)
            body_bottom = max(y_open, y_close)
            if body_bottom - body_top < s: body_bottom = body_top + s
            draw.rectangle([x_left, body_top, x_right, body_bottom], fill=color, outline=color)

    def _draw_volume_chart(self, draw, klines, volumes, left, top, width, height, candle_width, candle_total_width, s):
        v_max = max(volumes) if volumes else 1
        
        num_grid = 4
        grid_values = []
        for i in range(num_grid + 1):
            norm_val = i / num_grid
            vol = v_max * norm_val
            if vol >= 1e9:
                label = f"{vol/1e9:.1f}B"
            elif vol >= 1e6:
                label = f"{vol/1e6:.0f}M"
            elif vol >= 1e3:
                label = f"{vol/1e3:.0f}K"
            else:
                label = f"{vol:.0f}"
            grid_values.append((norm_val, label))
        
        self._draw_grid_and_ticks(draw, left, top, width, height, grid_values, s)
        
        def get_x(i): return left + i * candle_total_width + candle_total_width / 2
        
        bottom = top + height
        for i, (k, v) in enumerate(zip(klines, volumes)):
            x_center = get_x(i)
            x_left = x_center - candle_width / 2
            x_right = x_center + candle_width / 2
            
            bar_h = int((v / v_max) * (height - 5*s))
            color = UP_COLOR if k['close'] >= k['open'] else DOWN_COLOR
            draw.rectangle([x_left, bottom - bar_h, x_right, bottom], fill=color)

    def _draw_macd_chart(self, draw, macd_line, signal_line, histogram, left, top, width, height, candle_width, candle_total_width, s):
        valid = [v for v in macd_line + signal_line + histogram if v is not None]
        v_max = max(abs(v) for v in valid) if valid else 1
        
        num_grid = 6
        grid_values = []
        for i in range(num_grid + 1):
            norm_val = i / num_grid
            val = -v_max + 2 * v_max * norm_val
            grid_values.append((norm_val, f"{val:.5f}"))
        
        self._draw_grid_and_ticks(draw, left, top, width, height, grid_values, s)
        
        mid_y = top + height // 2
        draw.line([(left, mid_y), (left + width, mid_y)], fill=AXIS_COLOR, width=s)
        
        def val_to_y(v): return mid_y - int((v / v_max) * (height // 2 - 5*s))
        def get_x(i): return left + i * candle_total_width + candle_total_width / 2
        
        for i, h in enumerate(histogram):
            if h is not None:
                x_c = get_x(i)
                x_l = x_c - candle_width / 2
                x_r = x_c + candle_width / 2
                y = val_to_y(h)
                color = UP_COLOR if h >= 0 else DOWN_COLOR
                draw.rectangle([x_l, min(y, mid_y), x_r, max(y, mid_y)], fill=color)

        points_m = []
        points_s = []
        for i in range(len(macd_line)):
            if macd_line[i] is not None: points_m.append((get_x(i), val_to_y(macd_line[i])))
            if signal_line[i] is not None: points_s.append((get_x(i), val_to_y(signal_line[i])))
            
        if len(points_m) > 1: draw.line(points_m, fill=MACD_COLOR, width=2*s, joint='curve')
        if len(points_s) > 1: draw.line(points_s, fill=SIGNAL_COLOR, width=2*s, joint='curve')

    def _draw_rsi_chart(self, draw, img, rsi, left, top, width, height, candle_width, candle_total_width, s):
        grid_values = [(0, "0"), (0.2, "20"), (0.3, "30"), (0.5, "50"), (0.7, "70"), (0.8, "80"), (1.0, "100")]
        self._draw_grid_and_ticks(draw, left, top, width, height, grid_values, s)
        
        def val_to_y(v): return top + height - int((v / 100) * height)
        def get_x(i): return left + i * candle_total_width + candle_total_width / 2
        
        y_70 = val_to_y(70)
        y_30 = val_to_y(30)
        right = left + width
        
        bg_img = Image.new('RGBA', img.size, (0,0,0,0))
        bg_draw = ImageDraw.Draw(bg_img, 'RGBA')
        bg_draw.rectangle([left, top, right, y_70], fill=RSI_OVERBOUGHT_BG)
        bg_draw.rectangle([left, y_30, right, top + height], fill=RSI_OVERSOLD_BG)
        img.paste(bg_img, (0,0), bg_img)
        
        _draw_dashed_line(draw, [(left, y_70), (right, y_70)], fill=DOWN_COLOR, width=s, dash=(8*s, 4*s))
        _draw_dashed_line(draw, [(left, y_30), (right, y_30)], fill=UP_COLOR, width=s, dash=(8*s, 4*s))
        
        points = []
        for i, r in enumerate(rsi):
            if r is not None: points.append((get_x(i), val_to_y(r)))
        if len(points) > 1: draw.line(points, fill=RSI_COLOR, width=2*s, joint='curve')


_renderer_instance: Optional[PillowChartRenderer] = None

def get_pillow_renderer() -> PillowChartRenderer:
    global _renderer_instance
    if _renderer_instance is None:
        _renderer_instance = PillowChartRenderer()
    return _renderer_instance

def render_kline_chart_pillow(
    klines: List[Any],
    symbol: str,
    interval: str,
    visible_count: int = 100,
) -> str:
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
    
    renderer = get_pillow_renderer()
    return renderer.render(kline_data, symbol, interval, visible_count)
