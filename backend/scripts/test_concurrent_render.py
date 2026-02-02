"""测试多线程并发渲染性能"""
import sys
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.agent.tools.chart_renderer_pillow import render_kline_chart_pillow
from modules.monitor.data.models import Kline


def generate_mock_klines(count: int = 200) -> list:
    """生成模拟K线数据"""
    base_price = 0.20
    base_time = 1700000000000
    klines = []
    
    for i in range(count):
        open_price = base_price + random.uniform(-0.01, 0.01)
        close_price = open_price + random.uniform(-0.005, 0.005)
        high_price = max(open_price, close_price) + random.uniform(0, 0.003)
        low_price = min(open_price, close_price) - random.uniform(0, 0.003)
        volume = random.uniform(1000000, 5000000)
        
        klines.append(Kline(
            timestamp=base_time + i * 3600000,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            is_closed=True,
        ))
        base_price = close_price
    
    return klines


def render_task(task_id: int, klines: list) -> dict:
    """单个渲染任务"""
    thread_name = threading.current_thread().name
    start = time.perf_counter()
    
    result = render_kline_chart_pillow(klines, f"TEST{task_id}USDT", "4h", 100)
    
    elapsed = (time.perf_counter() - start) * 1000
    return {
        'task_id': task_id,
        'thread': thread_name,
        'elapsed_ms': elapsed,
        'result_len': len(result),
    }


def test_sequential(num_tasks: int, klines: list):
    """串行测试"""
    print(f"\n{'='*60}")
    print(f"串行渲染测试 ({num_tasks} 次)")
    print('='*60)
    
    total_start = time.perf_counter()
    results = []
    
    for i in range(num_tasks):
        result = render_task(i, klines)
        results.append(result)
        print(f"  任务 {i}: {result['elapsed_ms']:.2f}ms")
    
    total_elapsed = (time.perf_counter() - total_start) * 1000
    avg_elapsed = sum(r['elapsed_ms'] for r in results) / len(results)
    
    print(f"\n串行总耗时: {total_elapsed:.2f}ms")
    print(f"平均每次: {avg_elapsed:.2f}ms")
    
    return total_elapsed, avg_elapsed


def test_concurrent(num_tasks: int, num_workers: int, klines: list):
    """并发测试"""
    print(f"\n{'='*60}")
    print(f"并发渲染测试 ({num_tasks} 次, {num_workers} 线程)")
    print('='*60)
    
    total_start = time.perf_counter()
    results = []
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(render_task, i, klines): i for i in range(num_tasks)}
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"  任务 {result['task_id']} ({result['thread']}): {result['elapsed_ms']:.2f}ms")
    
    total_elapsed = (time.perf_counter() - total_start) * 1000
    avg_elapsed = sum(r['elapsed_ms'] for r in results) / len(results)
    
    print(f"\n并发总耗时: {total_elapsed:.2f}ms")
    print(f"平均每次: {avg_elapsed:.2f}ms")
    print(f"理论最优: {avg_elapsed:.2f}ms (如果完全并行)")
    
    speedup = (avg_elapsed * num_tasks) / total_elapsed
    print(f"实际加速比: {speedup:.2f}x")
    
    return total_elapsed, avg_elapsed


def main():
    print("生成模拟K线数据...")
    klines = generate_mock_klines(200)
    print(f"生成了 {len(klines)} 条K线")
    
    print("\n预热渲染器...")
    render_kline_chart_pillow(klines, "WARMUP", "4h", 100)
    print("预热完成")
    
    num_tasks = 6
    
    seq_total, seq_avg = test_sequential(num_tasks, klines)
    
    for num_workers in [2, 4, 6]:
        con_total, con_avg = test_concurrent(num_tasks, num_workers, klines)
    
    print("\n" + "="*60)
    print("结论")
    print("="*60)
    print(f"如果并发总耗时 ≈ 串行总耗时，说明存在串行化瓶颈")
    print(f"如果并发总耗时 ≈ 串行平均耗时，说明完全并行")


if __name__ == "__main__":
    main()
