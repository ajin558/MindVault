import matplotlib.pyplot as plt
import numpy as np
import os

# 创建static目录用于保存图表
os.makedirs('./static', exist_ok=True)

# 初始参数
initial_profit = 10000  # 第一个月利润：10,000元
monthly_growth_rate = 0.15  # 每月15%的复利增长
months = 12  # 计算12个月

# 计算每个月的利润
profits = []
for month in range(1, months + 1):
    profit = initial_profit * ((1 + monthly_growth_rate) ** (month - 1))
    profits.append(profit)

# 输出结果
print("咖啡店利润增长计算：")
print(f"第一个月利润：{initial_profit:,.2f}元")
print(f"每月增长率：{monthly_growth_rate*100:.1f}%")
print("\n各月利润明细：")
for month, profit in enumerate(profits, 1):
    print(f"第{month:2d}个月：{profit:,.2f}元")

print(f"\n第12个月的当月利润：{profits[-1]:,.2f}元")
print(f"总利润增长倍数：{profits[-1]/initial_profit:.2f}倍")

# 创建图表
plt.figure(figsize=(12, 8))

# 绘制折线图
months_list = list(range(1, months + 1))
plt.plot(months_list, profits, 'b-o', linewidth=2, markersize=8, label='月利润')

# 添加数据标签
for i, (month, profit) in enumerate(zip(months_list, profits)):
    if i % 2 == 0:  # 每隔一个月显示标签，避免重叠
        plt.annotate(f'{profit:,.0f}', 
                    xy=(month, profit), 
                    xytext=(0, 10),
                    textcoords='offset points',
                    ha='center',
                    fontsize=9,
                    color='blue')

# 设置图表属性
plt.title('咖啡店12个月利润增长趋势（每月15%复利增长）', fontsize=16, fontweight='bold')
plt.xlabel('月份', fontsize=12)
plt.ylabel('利润（元）', fontsize=12)
plt.grid(True, alpha=0.3)
plt.legend(fontsize=12)

# 设置Y轴格式
plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))

# 添加背景色
plt.gca().set_facecolor('#f8f9fa')

# 保存图表
chart_path = './static/coffee_profit_growth.png'
plt.tight_layout()
plt.savefig(chart_path, dpi=300, bbox_inches='tight')
plt.close()

print(f"\n图表已保存到：{chart_path}")
print("![数据图表](http://47.93.151.189:8000/static/coffee_profit_growth.png)")