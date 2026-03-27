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
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 创建参数网格
u = np.linspace(0, 4 * np.pi, 200)
v = np.linspace(0, 2 * np.pi, 100)
U, V = np.meshgrid(u, v)

# 计算参数方程
x = (1 + 0.5 * np.cos(V)) * np.cos(U)
y = (1 + 0.5 * np.cos(V)) * np.sin(U)
z = np.sin(V) + 0.5 * U

# 创建图形
fig = plt.figure(figsize=(12, 10))
ax = fig.add_subplot(111, projection='3d')

# 绘制3D曲面，使用plasma色彩映射以获得炫酷效果
surf = ax.plot_surface(x, y, z, 
                      cmap='plasma',  # 使用plasma色彩映射
                      edgecolor='none',  # 无边缘线
                      alpha=0.9,  # 透明度
                      linewidth=0.5,  # 线宽
                      antialiased=True,  # 抗锯齿
                      shade=True,  # 启用阴影
                      rstride=2,  # 减少行步长以提高性能
                      cstride=2)  # 减少列步长以提高性能

# 设置视角
ax.view_init(elev=30, azim=45)

# 添加颜色条
cbar = fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10)
cbar.set_label('Z值', rotation=270, labelpad=15)

# 设置标题和标签
ax.set_title('炫酷3D螺旋曲面图', fontsize=18, fontweight='bold', pad=20)
ax.set_xlabel('X轴', fontsize=12, labelpad=10)
ax.set_ylabel('Y轴', fontsize=12, labelpad=10)
ax.set_zlabel('Z轴', fontsize=12, labelpad=10)

# 设置网格线
ax.grid(True, linestyle='--', alpha=0.5)

# 设置坐标轴范围
ax.set_xlim([-2, 2])
ax.set_ylim([-2, 2])
ax.set_zlim([-2, 8])

# 添加一些炫酷效果
# 设置背景色
ax.xaxis.pane.fill = False
ax.yaxis.pane.fill = False
ax.zaxis.pane.fill = False

# 设置坐标轴颜色
ax.xaxis._axinfo["grid"]['color'] = (0.5, 0.5, 0.5, 0.3)
ax.yaxis._axinfo["grid"]['color'] = (0.5, 0.5, 0.5, 0.3)
ax.zaxis._axinfo["grid"]['color'] = (0.5, 0.5, 0.5, 0.3)

# 调整布局
plt.tight_layout()

# 保存图像
save_path = '/tmp/cool_3d_spiral_surface.png'
plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='black')
print(f"图像已保存到: {save_path}")

# 显示图像
plt.show()

# 返回图像路径
print("\n图像保存路径:", save_path)
# 系统底层保底扫描机制
try:
    if plt.get_fignums():
        plt.savefig('./static/chart_1774528217.png')
        print('\n![数据图表](http://47.93.151.189:8000/static/chart_1774528217.png)')
        print('\n[👉 若上方图片没显示，请点击这里查看高清大图](http://47.93.151.189:8000/static/chart_1774528217.png)')
except Exception:
    pass
