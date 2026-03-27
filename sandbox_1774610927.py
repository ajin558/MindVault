import os
os.environ['MPLBACKEND'] = 'Agg'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import builtins
builtins.input = lambda *args, **kwargs: '0'
plt.show = lambda *args, **kwargs: None
import matplotlib.pyplot as plt
import numpy as np

# 复利计算参数
principal = 10000  # 本金1万元
annual_rate = 0.10  # 年化利率10%
years = 3  # 存3年

# 计算复利终值
final_value = principal * (1 + annual_rate) ** years

# 计算每年的终值
yearly_values = []
for year in range(1, years + 1):
    yearly_value = principal * (1 + annual_rate) ** year
    yearly_values.append(yearly_value)

# 计算每年的利息
yearly_interests = []
cumulative_interest = 0
for i, value in enumerate(yearly_values):
    if i == 0:
        interest = value - principal
    else:
        interest = value - yearly_values[i-1]
    cumulative_interest += interest
    yearly_interests.append(interest)

print("复利计算详细过程：")
print("=" * 50)
print(f"本金：{principal:.2f}元")
print(f"年化利率：{annual_rate*100:.1f}%")
print(f"存款年限：{years}年")
print("=" * 50)

print("\n逐年计算过程：")
for i in range(years):
    year = i + 1
    print(f"\n第{year}年：")
    if i == 0:
        print(f"  期初本金：{principal:.2f}元")
    else:
        print(f"  期初本金：{yearly_values[i-1]:.2f}元")
    print(f"  当年利息：{yearly_interests[i]:.2f}元")
    print(f"  期末本息和：{yearly_values[i]:.2f}元")

print("\n" + "=" * 50)
print(f"最终结果：")
print(f"复利终值：{final_value:.2f}元")
print(f"总利息：{cumulative_interest:.2f}元")
print(f"本息合计：{final_value:.2f}元")

# 创建可视化图表
plt.figure(figsize=(10, 8))

# 子图1：逐年本息和增长
plt.subplot(2, 2, 1)
years_list = list(range(1, years + 1))
plt.plot(years_list, yearly_values, 'bo-', linewidth=2, markersize=8)
plt.title('逐年本息和增长', fontsize=12, fontweight='bold')
plt.xlabel('年份')
plt.ylabel('本息和（元）')
plt.grid(True, alpha=0.3)
for x, y in zip(years_list, yearly_values):
    plt.text(x, y, f'{y:.0f}', ha='center', va='bottom', fontsize=9)

# 子图2：逐年利息
plt.subplot(2, 2, 2)
plt.bar(years_list, yearly_interests, color='orange', alpha=0.7)
plt.title('逐年利息收入', fontsize=12, fontweight='bold')
plt.xlabel('年份')
plt.ylabel('利息（元）')
plt.grid(True, alpha=0.3, axis='y')
for x, y in zip(years_list, yearly_interests):
    plt.text(x, y, f'{y:.0f}', ha='center', va='bottom', fontsize=9)

# 子图3：本金与利息占比
plt.subplot(2, 2, 3)
labels = ['本金', '总利息']
sizes = [principal, cumulative_interest]
colors = ['lightblue', 'lightcoral']
plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
plt.title('本金与利息占比', fontsize=12, fontweight='bold')

# 子图4：复利增长曲线（简化）
plt.subplot(2, 2, 4)
x_points = np.arange(0, years + 0.1, 0.5)
y_points = principal * (1 + annual_rate) ** x_points
plt.plot(x_points, y_points, 'g-', linewidth=2)
plt.scatter(years_list, yearly_values, color='red', s=50, zorder=5)
plt.title('复利增长曲线', fontsize=12, fontweight='bold')
plt.xlabel('年份')
plt.ylabel('本息和（元）')
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('/tmp/compound_interest_calculation.png', dpi=100, bbox_inches='tight')
print("\n图表已保存为：/tmp/compound_interest_calculation.png")

# 显示图表
plt.show()
# 系统底层保底扫描机制
try:
    if plt.get_fignums():
        plt.savefig('./static/chart_1774610927.png')
        print('\n![数据图表](http://47.93.151.189:8000/static/chart_1774610927.png)')
        print('\n[👉 若上方图片没显示，请点击这里查看高清大图](http://47.93.151.189:8000/static/chart_1774610927.png)')
except Exception:
    pass
