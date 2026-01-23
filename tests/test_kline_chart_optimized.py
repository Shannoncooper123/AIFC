"""
测试K线图工具（优化版）- 查看绘制效果
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from agent.tools.get_kline_image_tool import get_kline_image_tool

print("=" * 80)
print("测试K线图工具（优化版 - 单周期 + 高图像）")
print("=" * 80)

# 测试1：单周期
print("\n[测试] 生成单周期K线图（1小时，100根）")
print("-" * 80)

result_str = get_kline_image_tool.invoke({
    "symbol": "BTCUSDT",
    "interval": "1h",  # 注意参数名变成了 interval
    "feedback": "测试优化后的图表",
    "limit": 100
})

result = json.loads(result_str)

if "error" in result_str:
    print(f"❌ 失败: {result_str}")
    sys.exit(1)

print(f"✅ 生成成功")
print(f"  - 交易对: {result['symbol']}")
print(f"  - 时间周期: {result['intervals']}")
print(f"  - K线数量: {result['kline_count']}")
print(f"  - 图像大小: {len(result['image_data'])} 字符")

# 保存图片
import base64
image_data = result['image_data']
output_file = ROOT / 'test_chart_optimized.png'
with open(output_file, 'wb') as f:
    f.write(base64.b64decode(image_data))
print(f"\n📁 图片已保存: {output_file}")

print("\n" + "=" * 80)
print("测试完成！")
print("=" * 80)
print(f"""
✅ 优化版K线图生成成功！

改进点：
1. 图像高度增加（16x12英寸），解决扁平问题
2. 指标分离更清晰（hspace=0.15）
3. 主图占比更大（height_ratios=[3, 1, 1]）
4. 仅支持单周期，专注细节分析

生成的图片：
{output_file}

请打开图片查看效果！
""")
