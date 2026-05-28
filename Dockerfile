# 采用极其轻量级的 Python 3.10 环境
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装必要的系统编译库 (防止 ChromaDB 安装报错)
RUN apt-get update && apt-get install -y build-essential sqlite3 curl && rm -rf /var/lib/apt/lists/*

# 拷贝依赖文件并使用阿里云源极速安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 拷贝所有源代码
COPY . .

# 暴露 8000 端口
EXPOSE 8000

# 启动最高指挥官
CMD ["python3", "main.py"]
