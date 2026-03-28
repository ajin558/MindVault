<img width="1919" height="1079" alt="屏幕截图 2026-03-27 223019" src="https://github.com/user-attachments/assets/6a296636-b94e-4118-8938-80e9407469e3" />
<img width="1919" height="1079" alt="屏幕截图 2026-03-27 222407" src="https://github.com/user-attachments/assets/fd30e585-265a-4deb-a91f-b475dff04135" />

\# 🧠 MindVault: 工业级全异步多智能体架构 (Deep Research Agent)



\[!\[Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

\[!\[FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)

\[!\[LangGraph](https://img.shields.io/badge/LangGraph-Async-orange.svg)](https://github.com/langchain-ai/langgraph)

\[!\[License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)



> \*\*这不是又一个简单的“套壳大模型对话框”。\*\* > MindVault 是一个专为严苛的 Serverless 部署环境（如 Vercel）和大陆复杂网络环境设计的\*\*工业级多智能体底座\*\*。



它从底层重写了多智能体的异步流式通信逻辑，彻底解决了 AI 开发者部署项目时面临的“超时断连”、“数据库锁死”、“本地模型卡死”等三大世界级难题。



\---



\## 🔥 核心黑科技 (Core Features)



如果你曾被 Vercel 的 10 秒/15 秒执行超时折磨过，或者被 LangGraph 的同步逻辑卡死过，MindVault 将是你的终极解药：



\* 💓 \*\*Vercel Heartbeat 引擎 (防斩首机制)\*\*

&#x20; 首创“零宽字符心跳包”流式输出。即使大模型在后台进行长达 60 秒的深度思考或沙盒计算，引擎也会通过 `asyncio.Queue` 持续向前端发送不可见心跳，强行穿透 Vercel Serverless Function 的 15 秒超时强制挂断限制。

\* 🧱 \*\*双轨 SQLite 数据库隔离架构\*\*

&#x20; 彻底解决 `aiosqlite` (异步) 与传统 `sqlite3` (同步) 争抢同一文件句柄导致的 `Disk I/O Error`。MindVault 将 LangGraph 的状态记忆库与动态技能库进行物理隔离，支持高并发读写而不崩溃。

\* 🛡️ \*\*Air-gapped 纯净离线护城河\*\*

&#x20; 针对大陆服务器连通率极差的 HuggingFace 节点，在引擎点火第一行强行注入“绝对离线圣旨” (`HF\_HUB\_OFFLINE=1`)，彻底斩断本地向量模型（SentenceTransformers）的联网检测盲肠，实现秒级点火启动。

\* 📜 \*\*反中间人“大水桶”流式协议\*\*

&#x20; 强行覆盖 Nginx (`X-Accel-Buffering: no`) 和 CDN (`Cache-Control: no-cache`) 的打包缓冲机制，还原最纯粹、最丝滑的毫秒级“打字机”流式响应。

\* 💻 \*\*全自动 Python 自愈沙盒\*\*

&#x20; 内置极客技术局 Agent，面对复杂的数学计算和数据分析，它会自动编写代码、在安全沙盒中执行、生成可视化图表，并自带 Error 反思自愈重试能力。



\---



\## 🏗️ 架构概览



MindVault 采用 `Supervisor (指挥官) - Worker (局长)` 的多智能体编排模式：



1\. \*\*最高指挥官 (Commander)\*\*: 负责意图识别与任务拆解。

2\. \*\*深度研究局 (Researcher)\*\*: 专精于全网资料检索、深度网页抓取与超长文本清洗提炼。

3\. \*\*极客技术局 (Operator)\*\*: 专精于调用底层 Python 沙盒，生成精准的计算结果与数据可视化图表。

4\. \*\*赛博铁匠铺 (Cyber Forge)\*\*: 动态能力扩充引擎，可将跑通的代码作为新技能永久刻录入数据库。



\---



\## 🚀 极速部署指北 (Quick Start)



\### 1. 环境准备

```bash

git clone \[https://github.com/yourusername/MindVault.git](https://github.com/yourusername/MindVault.git)

cd MindVault

python3 -m venv venv

source venv/bin/activate

pip install -r requirements.txt

