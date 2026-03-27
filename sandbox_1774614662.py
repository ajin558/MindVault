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
import seaborn as sns
from matplotlib import rcParams

# 设置中文字体和样式
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")
sns.set_palette("husl")

# 创建图表
fig = plt.figure(figsize=(20, 16))

# 1. 全球AI芯片市场规模柱状图（2023-2026年）
ax1 = plt.subplot(2, 2, 1)
years = ['2023', '2024', '2025', '2026']
market_size = [450, 620, 850, 1150]  # 单位：亿美元

bars = ax1.bar(years, market_size, color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'])
ax1.set_title('全球AI芯片市场规模（2023-2026年）', fontsize=16, fontweight='bold')
ax1.set_xlabel('年份', fontsize=12)
ax1.set_ylabel('市场规模（亿美元）', fontsize=12)
ax1.set_ylim(0, 1300)

# 在柱子上添加数值标签
for bar, value in zip(bars, market_size):
    height = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., height + 20,
             f'{value}亿', ha='center', va='bottom', fontsize=11)

# 2. 主要厂商市场份额饼图
ax2 = plt.subplot(2, 2, 2)
companies = ['英伟达', 'AMD', '英特尔', '谷歌TPU', '华为昇腾', '其他']
market_share = [68, 12, 8, 5, 4, 3]  # 百分比
colors = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#feca57', '#ff9ff3']

wedges, texts, autotexts = ax2.pie(market_share, labels=companies, autopct='%1.1f%%',
                                   colors=colors, startangle=90, textprops={'fontsize': 11})
ax2.set_title('2026年主要AI芯片厂商市场份额', fontsize=16, fontweight='bold')

# 3. 中国AI芯片市场规模折线图
ax3 = plt.subplot(2, 2, 3)
china_years = ['2023', '2024', '2025', '2026']
china_market = [85, 120, 180, 280]  # 单位：亿美元

ax3.plot(china_years, china_market, marker='o', linewidth=3, markersize=10,
         color='#e74c3c', markerfacecolor='white', markeredgewidth=2)
ax3.fill_between(china_years, china_market, alpha=0.2, color='#e74c3c')
ax3.set_title('中国AI芯片市场规模增长趋势（2023-2026年）', fontsize=16, fontweight='bold')
ax3.set_xlabel('年份', fontsize=12)
ax3.set_ylabel('市场规模（亿美元）', fontsize=12)
ax3.set_ylim(0, 320)
ax3.grid(True, alpha=0.3)

# 添加数据点标签
for x, y in zip(china_years, china_market):
    ax3.text(x, y + 10, f'{y}亿', ha='center', va='bottom', fontsize=11, fontweight='bold')

# 4. AI芯片应用场景分布条形图
ax4 = plt.subplot(2, 2, 4)
applications = ['数据中心', '自动驾驶', '智能手机', '工业物联网', '医疗健康', '安防监控', '其他']
application_share = [45, 18, 15, 10, 6, 4, 2]  # 百分比
colors_app = plt.cm.viridis(np.linspace(0.2, 0.9, len(applications)))

bars_app = ax4.barh(applications, application_share, color=colors_app)
ax4.set_title('AI芯片应用场景分布（2026年）', fontsize=16, fontweight='bold')
ax4.set_xlabel('市场份额（%）', fontsize=12)

# 在条形上添加百分比标签
for bar, value in zip(bars_app, application_share):
    width = bar.get_width()
    ax4.text(width + 0.5, bar.get_y() + bar.get_height()/2,
             f'{value}%', ha='left', va='center', fontsize=11)

plt.tight_layout()
plt.savefig('ai_chip_market_analysis.png', dpi=300, bbox_inches='tight')
plt.show()

print("图表已生成并保存为 'ai_chip_market_analysis.png'")
print("\n数据说明：")
print("1. 全球AI芯片市场规模：基于行业预测数据")
print("2. 市场份额：基于2026年预测数据")
print("3. 中国市场规模：反映中国市场的快速增长")
print("4. 应用场景：展示AI芯片的主要应用领域")
# 系统底层保底扫描机制
try:
    if plt.get_fignums():
        plt.savefig('./static/chart_1774614662.png')
        print('\n![数据图表](http://47.93.151.189:8000/static/chart_1774614662.png)')
        print('\n[👉 若上方图片没显示，请点击这里查看高清大图](http://47.93.151.189:8000/static/chart_1774614662.png)')
except Exception:
    pass
