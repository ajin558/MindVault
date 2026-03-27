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
import pandas as pd
from datetime import datetime, timedelta
import seaborn as sns
import matplotlib.cm as cm

# 设置中文字体和样式
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('seaborn-v0_8-darkgrid')

# 创建图表
fig = plt.figure(figsize=(20, 15))

# 1. 全球科技发展趋势时间线图（2025-2026年关键节点）
ax1 = plt.subplot(3, 2, 1)

# 模拟时间线数据 - 使用字符串日期避免转换问题
timeline_data = [
    ("2025-Q1", "量子计算突破\n(1000量子比特)", "美国", "技术突破"),
    ("2025-Q2", "AI通用模型\n(AGI原型)", "中国", "技术突破"),
    ("2025-Q3", "全球6G标准\n制定完成", "国际组织", "标准制定"),
    ("2025-Q4", "脑机接口\n临床应用", "欧盟", "医疗应用"),
    ("2026-Q1", "可控核聚变\n首次净能量增益", "美国", "能源革命"),
    ("2026-Q2", "太空采矿\n技术验证", "中国", "太空经济"),
    ("2026-Q3", "全球数字\n货币体系", "国际组织", "金融科技"),
    ("2026-Q4", "生物合成\n粮食量产", "欧盟", "农业革命")
]

# 创建x轴位置（使用数值而不是日期）
x_positions = list(range(len(timeline_data)))
events = [event for _, event, _, _ in timeline_data]
countries = [country for _, _, country, _ in timeline_data]
categories = [category for _, _, _, category in timeline_data]

# 颜色映射
category_colors = {
    "技术突破": "#FF6B6B",
    "标准制定": "#4ECDC4",
    "医疗应用": "#45B7D1",
    "能源革命": "#96CEB4",
    "太空经济": "#FECA57",
    "金融科技": "#FF9FF3",
    "农业革命": "#54A0FF"
}

# 绘制时间线
for i, (date_str, event, country, category) in enumerate(timeline_data):
    y_pos = len(timeline_data) - i - 1
    color = category_colors[category]
    
    # 时间点
    ax1.plot(i, y_pos, 'o', markersize=15, color=color, markeredgecolor='white', markeredgewidth=2)
    
    # 事件标签
    ax1.text(i, y_pos + 0.3, event, ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax1.text(i, y_pos - 0.3, f"{country} | {category}", ha='center', va='top', fontsize=8, alpha=0.8)

# 时间线连接
for i in range(len(timeline_data)-1):
    y_pos1 = len(timeline_data) - i - 1
    y_pos2 = len(timeline_data) - i - 2
    ax1.plot([i, i+1], [y_pos1, y_pos2], 'k-', alpha=0.3, linewidth=1)

ax1.set_xticks(range(len(timeline_data)))
ax1.set_xticklabels([date for date, _, _, _ in timeline_data], rotation=45, ha='right')
ax1.set_yticks(range(len(timeline_data)))
ax1.set_yticklabels([f"事件 {i+1}" for i in range(len(timeline_data))])
ax1.set_xlabel('时间节点', fontsize=12, fontweight='bold')
ax1.set_ylabel('事件序列', fontsize=12, fontweight='bold')
ax1.set_title('全球科技发展趋势时间线图 (2025-2026)', fontsize=14, fontweight='bold', pad=20)
ax1.grid(True, alpha=0.3)

# 添加图例
legend_elements = [plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=color, 
                             markersize=10, label=category, markeredgecolor='white', markeredgewidth=2)
                  for category, color in category_colors.items()]
ax1.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=8)

# 2. 主要国家科技战略布局对比雷达图
ax2 = plt.subplot(3, 2, 2, projection='polar')

# 科技战略维度
categories = ['人工智能', '量子技术', '生物科技', '新能源', '太空探索', '半导体', '6G通信', '网络安全']
N = len(categories)
theta = np.linspace(0, 2*np.pi, N, endpoint=False)

# 各国数据
countries_data = {
    '美国': [9.5, 8.8, 8.2, 7.5, 9.0, 8.5, 7.8, 9.2],
    '中国': [9.2, 7.5, 7.8, 8.5, 8.0, 8.8, 9.0, 8.0],
    '欧盟': [7.8, 7.0, 8.5, 8.8, 7.2, 7.0, 7.5, 8.5],
    '日本': [7.0, 7.8, 8.0, 7.2, 6.5, 8.2, 7.0, 7.8],
    '俄罗斯': [6.5, 6.8, 6.2, 7.0, 8.5, 5.5, 6.0, 8.2]
}

colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FECA57', '#FF9FF3']

# 绘制雷达图
for idx, (country, values) in enumerate(countries_data.items()):
    values = np.concatenate((values, [values[0]]))
    theta_closed = np.concatenate((theta, [theta[0]]))
    ax2.plot(theta_closed, values, color=colors[idx], linewidth=2, label=country)
    ax2.fill(theta_closed, values, color=colors[idx], alpha=0.25)

ax2.set_xticks(theta)
ax2.set_xticklabels(categories)
ax2.set_ylim(0, 10)
ax2.set_yticks([2, 4, 6, 8, 10])
ax2.set_yticklabels(['2', '4', '6', '8', '10'], fontsize=8)
ax2.set_title('主要国家科技战略布局对比雷达图', fontsize=14, fontweight='bold', pad=20)
ax2.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=9)

# 3. 地缘政治风险热力图
ax3 = plt.subplot(3, 2, 3)

# 模拟地缘政治风险数据
regions = ['北美', '欧洲', '东亚', '东南亚', '南亚', '中东', '非洲', '拉美']
risk_factors = ['军事冲突', '经济制裁', '技术封锁', '资源争夺', '意识形态']
risk_data = np.array([
    [0.2, 0.3, 0.4, 0.1, 0.2],  # 北美
    [0.4, 0.5, 0.3, 0.2, 0.3],  # 欧洲
    [0.6, 0.7, 0.8, 0.5, 0.6],  # 东亚
    [0.5, 0.4, 0.3, 0.6, 0.4],  # 东南亚
    [0.7, 0.6, 0.4, 0.7, 0.8],  # 南亚
    [0.9, 0.8, 0.5, 0.9, 0.7],  # 中东
    [0.8, 0.7, 0.3, 0.8, 0.5],  # 非洲
    [0.3, 0.4, 0.2, 0.3, 0.4]   # 拉美
])

# 创建热力图
im = ax3.imshow(risk_data, cmap='YlOrRd', aspect='auto', vmin=0, vmax=1)

# 添加文本
for i in range(len(regions)):
    for j in range(len(risk_factors)):
        text = ax3.text(j, i, f'{risk_data[i, j]:.1f}',
                       ha="center", va="center", color="black" if risk_data[i, j] < 0.6 else "white",
                       fontsize=9, fontweight='bold')

ax3.set_xticks(np.arange(len(risk_factors)))
ax3.set_yticks(np.arange(len(regions)))
ax3.set_xticklabels(risk_factors, rotation=45, ha='right')
ax3.set_yticklabels(regions)
ax3.set_title('地缘政治风险热力图 (风险指数 0-1)', fontsize=14, fontweight='bold', pad=20)

# 添加颜色条
cbar = plt.colorbar(im, ax=ax3, fraction=0.046, pad=0.04)
cbar.set_label('风险指数', rotation=270, labelpad=15)

# 4. 经济市场变化趋势折线图
ax4 = plt.subplot(3, 2, 4)

# 模拟经济数据
months = pd.date_range('2024-01', '2026-12', freq='M')
n_months = len(months)

# 生成趋势数据
np.random.seed(42)
base_gdp = 100
gdp_growth = np.cumsum(np.random.normal(0.005, 0.01, n_months)) + 1
gdp_data = base_gdp * gdp_growth

# 添加周期性波动
for i in range(0, n_months, 12):
    if i+4 < n_months:
        gdp_data[i:i+4] *= 1.02  # Q1增长
    if i+8 < n_months:
        gdp_data[i+4:i+8] *= 0.99  # Q2调整
    if i+12 < n_months:
        gdp_data[i+8:i+12] *= 1.03  # Q3-Q4复苏

# 添加趋势线
x_numeric = np.arange(n_months)
trend_line = np.poly1d(np.polyfit(x_numeric, gdp_data, 2))(x_numeric)

# 绘制折线图
ax4.plot(months, gdp_data, 'b-', linewidth=2, alpha=0.7, label='GDP指数')
ax4.plot(months, trend_line, 'r--', linewidth=2, label='趋势线')

# 标记关键事件
key_events = [
    ('2025-03', 'AI投资热潮', 1.05),
    ('2025-09', '贸易政策调整', 0.98),
    ('2026-03', '新能源突破', 1.08),
    ('2026-09', '全球复苏', 1.12)
]

for date, event, factor in key_events:
    event_date = pd.Timestamp(date)
    idx = np.argmin(np.abs(months - event_date))
    if idx < len(gdp_data):
        ax4.plot(event_date, gdp_data[idx], 'ro', markersize=8)
        ax4.annotate(event, xy=(event_date, gdp_data[idx]),
                    xytext=(10, 20), textcoords='offset points',
                    arrowprops=dict(arrowstyle='->', color='red'),
                    fontsize=8, fontweight='bold')

ax4.set_xlabel('时间', fontsize=12, fontweight='bold')
ax4.set_ylabel('GDP指数 (基准=100)', fontsize=12, fontweight='bold')
ax4.set_title('经济市场变化趋势折线图', fontsize=14, fontweight='bold', pad=20)
ax4.legend(loc='best')
ax4.grid(True, alpha=0.3)

# 5. 社会文化演变指标柱状图
ax5 = plt.subplot(3, 2, (5, 6))

# 社会文化指标
indicators = ['数字素养', '环保意识', '多元包容', '远程工作', '健康关注', '教育投入', '社会信任']
years = ['2024', '2025', '2026']

# 模拟数据
np.random.seed(42)
data = np.array([
    [65, 72, 78],  # 数字素养
    [70, 75, 82],  # 环保意识
    [60, 68, 75],  # 多元包容
    [45, 55, 65],  # 远程工作
    [75, 78, 85],  # 健康关注
    [68, 72, 77],  # 教育投入
    [58, 63, 70]   # 社会信任
])

x = np.arange(len(indicators))
width = 0.25

# 绘制分组柱状图
bars1 = ax5.bar(x - width, data[:, 0], width, label='2024', color='#4ECDC4', edgecolor='black')
bars2 = ax5.bar(x, data[:, 1], width, label='2025', color='#45B7D1', edgecolor='black')
bars3 = ax5.bar(x + width, data[:, 2], width, label='2026', color='#FF6B6B', edgecolor='black')

# 添加数值标签
def autolabel(bars):
    for bar in bars:
        height = bar.get_height()
        ax5.annotate(f'{height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=8)

autolabel(bars1)
autolabel(bars2)
autolabel(bars3)

ax5.set_xlabel('社会文化指标', fontsize=12, fontweight='bold')
ax5.set_ylabel('指数 (0-100)', fontsize=12, fontweight='bold')
ax5.set_title('社会文化演变指标柱状图', fontsize=14, fontweight='bold', pad=20)
ax5.set_xticks(x)
ax5.set_xticklabels(indicators, rotation=45, ha='right')
ax5.legend(loc='upper left')
ax5.grid(True, alpha=0.3, axis='y')

# 调整布局
plt.tight_layout()

# 保存图表
plt.savefig('/tmp/global_analysis_charts.png', dpi=300, bbox_inches='tight')
plt.show()

print("图表已成功生成并保存为 /tmp/global_analysis_charts.png")
print("\n=== 图表分析报告 ===")
print("1. 全球科技发展趋势时间线图：展示了2025-2026年关键科技突破节点")
print("2. 主要国家科技战略布局雷达图：对比了美、中、欧、日、俄在8个关键领域的战略投入")
print("3. 地缘政治风险热力图：分析了全球各区域在5个风险维度的威胁程度")
print("4. 经济市场变化趋势折线图：预测了未来3年GDP指数的波动趋势")
print("5. 社会文化演变指标柱状图：追踪了7个社会文化指标的年度变化")
# 系统底层保底扫描机制
try:
    if plt.get_fignums():
        plt.savefig('./static/chart_1774621117.png')
        print('\n![数据图表](http://47.93.151.189:8000/static/chart_1774621117.png)')
        print('\n[👉 若上方图片没显示，请点击这里查看高清大图](http://47.93.151.189:8000/static/chart_1774621117.png)')
except Exception:
    pass
