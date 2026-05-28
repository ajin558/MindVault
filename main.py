import os
import sys
import io
import csv
import hashlib
import uuid

# 🔥 强力防爆锁：强制所有日志和控制台输出为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import logging
import warnings
import traceback
import gc
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
# 确保 Nvidia API 不走本地代理
os.environ[
    "NO_PROXY"] = "api.deepseek.com,hf-mirror.com,localhost,127.0.0.1,poloai.top,api.moonshot.cn,integrate.api.nvidia.com"

import re
import json
import sqlite3
import time
import shutil
import asyncio
import httpx
import base64
import random
# 🌟 引入 Redis 异步驱动
import redis.asyncio as redis
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from datetime import datetime
from typing import List, Dict, Annotated, Sequence, TypedDict, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from contextlib import asynccontextmanager

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from neo4j import AsyncGraphDatabase
from duckduckgo_search import DDGS

# 云端沙盒执行：优先通过阿里云函数计算(FC)，未配置则本地subprocess兜底
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.warning("未安装 aiohttp，函数计算调用不可用，将使用本地沙盒。")

try:
    from tavily import TavilyClient

    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None
except ImportError:
    tavily_client = None

GLOBAL_Q = {}
GLOBAL_TASK_LOCK = asyncio.Lock()
BROWSER_LOCK = asyncio.Lock()


# =========================================================================
# 🛡️ DeepSeek thinking mode 全面修复装甲
# 作用：确保所有 AI 消息都携带 reasoning_content，防止 API 报错
# =========================================================================
def patch_reasoning_content(msg):
    """给单个消息加上 reasoning_content（如果缺失）"""
    if isinstance(msg, AIMessage):
        if 'reasoning_content' not in msg.additional_kwargs:
            msg.additional_kwargs['reasoning_content'] = None
    return msg


def patch_messages_reasoning(messages):
    """批量修复消息列表"""
    return [patch_reasoning_content(m) if isinstance(m, AIMessage) else m for m in messages]


async def safe_model_call(llm_instance, messages, **kwargs):
    """
    安全的模型调用包装器：
    1. 调用前确保所有历史 AI 消息有 reasoning_content
    2. 调用后确保返回的 AI 消息也有 reasoning_content
    """
    patched_msgs = patch_messages_reasoning(messages)
    result = await llm_instance.ainvoke(patched_msgs, **kwargs)
    return patch_reasoning_content(result)

# =========================================================================
# 🚀 2026 NVIDIA NIM 尖端引擎挂载点
# =========================================================================
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
# 阿里云函数计算 (FC) 可选配置 — 设置后优先远程执行，否则本地沙盒兜底
FC_ENDPOINT = os.getenv("FC_ENDPOINT", "")
FC_API_KEY = os.getenv("FC_API_KEY", "")
ADMIN_ACTIVATION_CODE = os.getenv("ADMIN_ACTIVATION_CODE", "").strip().upper()
# 👇 必须加上这三行！把官方和代理的 Key 重新读进来 👇
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
POLO_API_KEY = os.getenv("POLO_API_KEY")
POLO_API_BASE = os.getenv("POLO_API_BASE", "https://poloai.top/v1")

if not NVIDIA_API_KEY:
    raise ValueError("🚨 致命错误：未配置 NVIDIA_API_KEY！请在 .env 中填入英伟达密钥！")

# 兼容旧代码，Kimi 做长文本兜底（如果有的话）
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY")

try:
    MAX_UPLOAD_MB = max(1, int(os.getenv("MAX_UPLOAD_MB", "5")))
except ValueError:
    MAX_UPLOAD_MB = 5
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

logger.info("🧠 正在唤醒 NVIDIA NIM 超级计算引擎阵列...")
os.makedirs("mindvault_knowledge", exist_ok=True)
os.makedirs("mindvault_cache", exist_ok=True)
os.makedirs("my_vectordb", exist_ok=True)
os.makedirs("exports", exist_ok=True)
os.makedirs("uploads", exist_ok=True)


def safe_upload_filename(original_name: str) -> str:
    original_name = os.path.basename(original_name or "upload")
    stem, ext = os.path.splitext(original_name)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "upload"
    safe_ext = re.sub(r"[^A-Za-z0-9.]+", "", ext.lower())[:16]
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_stem[:80]}{safe_ext}"


def escape_sqlite_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# 🌟 初始化 Redis 客户端连接 (连接本地 6379 端口)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)


NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")
neo4j_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS)) if all(
    [NEO4J_URI, NEO4J_USER, NEO4J_PASS]) else None


async def ensure_neo4j_schema():
    if not neo4j_driver:
        return
    try:
        async with neo4j_driver.session() as session:
            result = await session.run(
                "CREATE INDEX entity_user_name IF NOT EXISTS FOR (n:Entity) ON (n.user_id, n.name)"
            )
            await result.consume()
        logger.info("✅ Neo4j 索引 entity_user_name 已就绪")
    except Exception as e:
        logger.warning(f"⚠️ Neo4j 索引初始化失败，服务继续启动: {e}")


skills_db_path = "mindvault_skills.db"
conn = sqlite3.connect(skills_db_path, check_same_thread=False, timeout=20)
conn.execute("CREATE TABLE IF NOT EXISTS cyber_skills (name TEXT PRIMARY KEY, description TEXT, code TEXT)")
conn.commit()

keys_db_path = "mindvault_keys.db"
keys_conn = sqlite3.connect(keys_db_path, check_same_thread=False, timeout=20)
keys_conn.execute(
    "CREATE TABLE IF NOT EXISTS activation_keys (key_code TEXT PRIMARY KEY, is_active BOOLEAN, created_at TEXT)")
keys_conn.commit()

clean_http_client = httpx.Client(trust_env=False, timeout=120.0)
clean_async_client = httpx.AsyncClient(trust_env=False, timeout=120.0)

# =========================================================================
# 👑 官方全功率混合阵列 (全官方 API，彻底告别 503 与掉线)
# =========================================================================

# 1. 向量引擎: 依然使用 PoloAPI 代理的 OpenAI 兼容模型 (这是必须的，DeepSeek不做这个)
embeddings_model = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=POLO_API_KEY,
    base_url=POLO_API_BASE
)
vector_db = Chroma(persist_directory="./mindvault_knowledge", embedding_function=embeddings_model)

# 2. 意图识别中枢 (CEO): 用官方 deepseek-v4-flash，极速秒回
llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,           # 🚀 走官方 Key
    base_url="https://api.deepseek.com", # 🚀 走官方域名
    model="deepseek-v4-flash",          # 🚀 使用你想用的 v4-flash
    streaming=True,
    max_retries=2, timeout=30.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)

# 3. 架构师推演模型: 走官方最强深度思考模型 R1 (Reasoner)
llm_r1 = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-reasoner",
    streaming=True,
    max_retries=2, timeout=60.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)

# 4. 后台苦力特工与图谱抽取: 走官方的 v4-flash，性价比拉满
sub_llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,           # 🚀 走官方 Key
    base_url="https://api.deepseek.com",
    model="deepseek-v4-flash"           # 🚀 使用 v4-flash
).with_config(tags=["sub_agent"])

extract_llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,           # 🚀 走官方 Key
    base_url="https://api.deepseek.com",
    model="deepseek-v4-flash",          # 🚀 使用 v4-flash
    temperature=0.1,
    max_retries=2, timeout=30.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)

# 5. 代码与沙盒控制智能体: 写代码必须严谨，使用官方 deepseek-chat 或 v4-pro
llm_coder = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-v4-pro",            # 🚀 升级 V4 Pro，代码质量更高
    temperature=0.1,
    max_retries=2, timeout=60.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)

# 7. V4 Pro 旗舰决策模型: Commander/Judge/CEO总结专用，准确度优先
llm_pro = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-v4-pro",
    streaming=True,
    max_retries=2, timeout=60.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)

# 7b. V4 Pro 无思考模式 — Commander 路由专用
# 思考模式会让 V4 Pro 在 additional_kwargs 里塞入 reasoning_content，
# 多轮 tool-call 回传时 LangChain 不会自动带上，导致 DeepSeek API 400。
# 关掉 thinking 不影响路由/摘要质量，还能省 token、省延迟。
llm_pro_no_think = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    streaming=True,
    max_retries=2, timeout=60.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)

# 6. 多模态视觉引擎: 依然交由 Polo 代理的 Gemini 负责看图
sub_llm_vision = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key=POLO_API_KEY,
    base_url=POLO_API_BASE,
    temperature=0.1,
    max_retries=2, timeout=45.0,
    http_client=clean_http_client, http_async_client=clean_async_client
)


class Triple(BaseModel):
    h: str = Field(description="源实体")
    r: str = Field(description="逻辑关系")
    t: str = Field(description="目标实体")


class KnowledgeGraph(BaseModel):
    triples: List[Triple] = Field(description="实体关系", default=[])


async def extract_and_store_graph(text_chunk: str, source_file: str, user_id: str):
    if not neo4j_driver: return
    extractor = extract_llm.with_structured_output(KnowledgeGraph, method="json_mode")
    try:
        # 🚀 强化了系统提示词，加入了绝对的“实体消歧”命令
        sys_msg = SystemMessage(
            content="你是一个顶级的学术知识图谱构建专家。提取核心概念，颗粒度极细，关系用明确动词。"
                    "【实体消歧规则】：你必须把同义词、中英文缩写合并为最标准的中文学名（例如：遇到'AI'或'Artificial Intelligence'必须统一个输出为'人工智能'）。"
                    "你必须输出合法的 JSON 格式数据，包含一个 'triples' 数组，数组对象包含 'h' (源), 'r' (关系), 't' (目标)。")
        res = await extractor.ainvoke([sys_msg, HumanMessage(content=text_chunk)])

        if isinstance(res, dict): res = KnowledgeGraph(**res)
        if not res or not hasattr(res, 'triples') or not res.triples: return

        batch_data =[{"h": t.h.strip(), "r": t.r.strip(), "t": t.t.strip()} for t in res.triples if
                      t.h and t.r and t.t]
        if not batch_data: return

        # 🚀 每次合并实体时，赋予它们初始生命值 hit_count = 1
        cypher = """
        UNWIND $batch AS record
        MERGE (a:Entity {name: record.h, user_id: $uid})
        ON CREATE SET a.hit_count = 1
        MERGE (b:Entity {name: record.t, user_id: $uid})
        ON CREATE SET b.hit_count = 1
        MERGE (a)-[rel:RELATED_TO {desc: record.r}]->(b)
        ON CREATE SET rel.source = $source
        """
        async with neo4j_driver.session() as session:
            await session.run(cypher, batch=batch_data, source=source_file, uid=user_id)
    except Exception as e:
        logger.warning(f"⚠️ 图谱提取局部跳过: {str(e)[:100]}")


async def process_raptor_summaries(chunks, filename, user_id: str):
    batch_size = 5
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        text = "\n".join([c.page_content if hasattr(c, 'page_content') else str(c) for c in batch])
        try:
            sys_msg = SystemMessage(content="你是一个宏观图书管理员。请将以下碎片文本总结成一段高阶宏观摘要。")
            summary_res = await sub_llm.ainvoke([sys_msg, HumanMessage(content=text[:3000])])

            def _add_raptor():
                vector_db.add_texts(texts=[summary_res.content], metadatas=[
                    {"source": f"{filename}_RAPTOR_Summary", "type": "raptor_node", "user_id": user_id}])

            await asyncio.to_thread(_add_raptor)
        except Exception:
            pass
        gc.collect()


# =========================================================================
# 🌟 Redis 异步任务工作流 Worker
# =========================================================================
# 🚀 新增一个全局广播助手
async def broadcast_log(user_id: str, message: str):
    """将后台处理进度推送到 Redis 频道，供前端实时监听"""
    logger.info(message)
    try:
        await redis_client.publish(f"mindvault_logs_{user_id}", message)
    except Exception:
        pass


# =========================================================================
# 🌟 Redis 异步任务工作流 Worker (全双工进度流版)
# =========================================================================
async def pdf_processing_worker():
    await asyncio.sleep(2)  # 等待 Redis 启动
    logger.info("👷‍♂️ Redis 后台打工人就绪，等待投喂文件...")
    while True:
        try:
            task = await redis_client.brpop("mindvault_pdf_queue", timeout=0)
            if task:
                _, task_data_str = task
                task_data = json.loads(task_data_str)
                user_id = task_data["user_id"]

                if "type" in task_data and task_data["type"] == "clip":
                    text = task_data["text"]
                    url = task_data["url"]
                    await broadcast_log(user_id, f"⚡ [闪电吸收] 开始解析网页碎片：{url[:30]}...")

                    def _add_vector():
                        vector_db.add_texts(texts=[text],
                                            metadatas=[{"source": url, "type": "web_clip", "user_id": user_id}])

                    await asyncio.to_thread(_add_vector)
                    await extract_and_store_graph(text, url, user_id)
                    await broadcast_log(user_id, f"✅[吸收完毕] 网页碎片已融入全息图谱！")
                    gc.collect()
                    continue

                filename = task_data["filename"]
                original_filename = task_data.get("original_filename", filename)
                file_path = os.path.join("uploads", filename)

                if not os.path.exists(file_path):
                    await broadcast_log(user_id, f"❌ [错误] 找不到文件: {original_filename}")
                    continue

                await broadcast_log(user_id, f"📥 [节点开启] 开始读取底层文件流: {original_filename}")
                chunks = []
                if filename.lower().endswith(".pdf"):
                    try:
                        if MOONSHOT_API_KEY:
                            await broadcast_log(user_id, "☁️[API触发] 正在上传至 Kimi 视觉解析矩阵...")
                            headers = {"Authorization": f"Bearer {MOONSHOT_API_KEY}"}
                            async with httpx.AsyncClient(timeout=180.0) as client:
                                with open(file_path, "rb") as f:
                                    res = await client.post("https://api.moonshot.cn/v1/files", headers=headers,
                                                            files={"file": (original_filename, f, "application/pdf")},
                                                            data={"purpose": "file-extract"})
                                    file_id = res.json().get("id")
                                await broadcast_log(user_id, "⏳ [云端提炼] 正在剥离 PDF 文本层数据...")
                                res_content = await client.get(f"https://api.moonshot.cn/v1/files/{file_id}/content",
                                                               headers=headers)
                                raw_text = res_content.json().get("content", "")
                            chunks = RecursiveCharacterTextSplitter(chunk_size=1000,
                                                                    chunk_overlap=200).create_documents([raw_text])
                        else:
                            raise Exception("未配置 MOONSHOT")
                    except Exception as e:
                        await broadcast_log(user_id, f"⚠️ [降级] 云端解析跳过，降级本地 PyMuPDF...")
                        loader = PyMuPDFLoader(file_path)
                        chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(
                            loader.load())
                else:
                    loader = TextLoader(file_path, encoding='utf-8')
                    chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(
                        loader.load())

                await broadcast_log(user_id, f"🔪 [切分完毕] 共生成 {len(chunks)} 个碎片微粒，开始双擎入库...")
                gc.collect()
                for c in chunks: c.metadata["user_id"] = user_id

                # 1. 存入 Chroma
                for i in range(0, len(chunks), 5):
                    await asyncio.to_thread(vector_db.add_documents, chunks[i:i + 5])
                    await asyncio.sleep(0.5)
                await broadcast_log(user_id, f"📄 [向量存储] {len(chunks)} 个微粒已存入 ChromaDB")

                # 2. 存入 Neo4j 图谱 (并发批处理，每批5个同时提取)
                await broadcast_log(user_id, f"🕸️ [神经接驳] 开始并发提取核心图谱，每批5块齐头并进，请稍后...")
                semaphore = asyncio.Semaphore(5)
                async def extract_with_limit(idx, chunk):
                    async with semaphore:
                        await extract_and_store_graph(chunk.page_content, original_filename, user_id)
                        await asyncio.sleep(0.3)

                total = len(chunks)
                for batch_start in range(0, total, 5):
                    batch = chunks[batch_start:batch_start + 5]
                    await asyncio.gather(*[extract_with_limit(batch_start + i, c) for i, c in enumerate(batch)])
                    await broadcast_log(user_id, f"⚙️ [图谱构建] 已扫视 {min(batch_start + 5, total)}/{total} 块...")

                # 3. 宏观摘要
                await broadcast_log(user_id, f"🔮 [宏观归纳] 正在生成树状宏观摘要 (RAPTOR)...")
                await process_raptor_summaries(chunks, original_filename, user_id)

                await broadcast_log(user_id, f"✅✅ [知识升维] 完美收官！《{original_filename}》已化作星光入库！[DONE]")
                gc.collect()

        except Exception as e:
            logger.error(f"🚨 Worker 异常: {e}")
            await asyncio.sleep(5)


# =========================================================================

@tool
async def deep_research_engine(topic: str, config: RunnableConfig) -> str:
    """
    【深度研究特工】撰写长篇综述、行业研报、复杂主题调查时必须使用！会触发高级深度搜索。
    参数：topic 必须是精简检索关键词。
    """
    thread_id = config.get("configurable", {}).get("thread_id", "")
    q = GLOBAL_Q.get(thread_id)
    try:
        if q: await q.put(f"\n\n> 📰 **[深研特工启动]** ：正在搜集关于【{topic}】的全网权威信源...\n\n")
        if tavily_client:
            def _do_search(): return tavily_client.search(query=topic, max_results=5, search_depth="advanced")

            res = await asyncio.to_thread(_do_search)
            return "\n".join([f"- 【{r.get('title', '')}】: {r.get('content', '')} (来源: {r.get('url', '')})" for r in
                              res.get('results', [])])
        return "⚠️ 未配置 TAVILY_API_KEY，深研引擎降级。"
    except Exception as e:
        return f"深研失败: {str(e)}"


@tool
async def perform_web_search(query: str) -> str:
    """
    【全球超光速雷达】获取最新数据、实时新闻、股票或事实核查必须调用。
    参数：query 简短关键词。
    """
    try:
        time_aware_query = f"{query} {datetime.now().strftime('%Y年%m月')} 最新"
        if tavily_client:
            def _do_search(): return tavily_client.search(query=time_aware_query, max_results=5)

            res = await asyncio.to_thread(_do_search)
            return "\n".join([f"- 【{r.get('title', '')}】: {r.get('content', '')} (来源: {r.get('url', '')})" for r in
                              res.get('results', [])])

        def _do_ddgs():
            with DDGS(timeout=20) as ddgs: return list(ddgs.text(time_aware_query, max_results=5, timelimit="d"))

        results = await asyncio.to_thread(_do_ddgs)
        if not results: return "雷达未扫描到有价值情报。"
        return "\n".join(
            [f"- 【{r.get('title', '无标题')}】: {r.get('body', '')} (来源: {r.get('href', '')})" for r in results])
    except Exception as e:
        return f"雷达受到干扰: {str(e)}"


@tool
def get_current_time() -> str:
    """【时间感知器】回答今天/近期问题时调用锚定现实时间。"""
    return datetime.now().strftime("当前的系统时间是：%Y年%m月%d日 %H时%M分%S秒")


@tool
async def fetch_webpage_content(url: str) -> str:
    """【网页阅读器】用户提供网址URL时调用，抓取纯净文本。"""
    try:
        response = await clean_async_client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15.0,
                                                follow_redirects=True)
        text = re.sub(r'<(script|style).*?>.*?</\1>', '', response.text, flags=re.DOTALL | re.IGNORECASE)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).strip()[:3000]
    except Exception as e:
        return f"抓取失败: {str(e)}"


@tool
async def execute_python_code(code: str, config: RunnableConfig) -> str:
    """
    【云端隔离沙盒】数学计算、数据分析、绘制图表(plt.show) 必须调用！
    优先通过阿里云函数计算(FC)远程执行，未配置则本地subprocess兜底。
    严禁执行系统破坏命令。
    """
    thread_id = config.get("configurable", {}).get("thread_id", "")
    q = GLOBAL_Q.get(thread_id)
    if q: await q.put(f"\n\n> ☁️ **[沙盒引擎就绪]**：代码注入沙盒执行...\n\n")

    match = re.search(chr(96) * 3 + r"(?:python)?\s*(.*?)" + chr(96) * 3, code, re.DOTALL | re.IGNORECASE)
    clean_code = match.group(1).strip() if match else code.strip()

    # ── 优先级1：阿里云函数计算 (FC) 远程执行 ──
    if FC_ENDPOINT and FC_API_KEY and HAS_AIOHTTP:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {"code": clean_code, "timeout": 30}
                headers = {"Authorization": f"Bearer {FC_API_KEY}", "Content-Type": "application/json"}
                async with session.post(FC_ENDPOINT, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=35)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        output_lines = []
                        if result.get("stdout"): output_lines.append("📝 **输出**:\n```text\n" + result["stdout"] + "\n```")
                        if result.get("stderr"): output_lines.append("⚠️ **错误**:\n```text\n" + result["stderr"] + "\n```")
                        if result.get("error"): output_lines.append(f"🚨 **运行异常**: {result['error']}")
                        if result.get("image_base64"):
                            output_lines.append(f"\n![可视化](data:image/png;base64,{result['image_base64']})\n")
                        return "\n".join(output_lines).strip() or "✅ 执行成功，无终端输出。"
        except Exception as e:
            if q: asyncio.create_task(q.put(f"\n\n> ⚠️ FC 远程执行降级本地沙盒！({str(e)[:60]})\n\n"))

    # ── 优先级2：本地 subprocess 沙盒（安全隔离）──
    if any(k in clean_code for k in ["os.system", "subprocess", "shutil.rmtree"]): return "⚠️ 安全锁拦截！"

    os.makedirs("./static", exist_ok=True)
    current_ts = int(time.time())
    magic_prefix = "import os\nos.environ['MPLBACKEND']='Agg'\nimport matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
    magic_prefix += "plt.rcParams['font.sans-serif'] =['SimHei', 'Arial Unicode MS', 'DejaVu Sans']\nplt.rcParams['axes.unicode_minus'] = False\n"
    magic_suffix = f"\ntry:\n    if plt.get_fignums(): plt.savefig('./static/chart_{current_ts}.png')\n    print('\\n[LOCAL_IMAGE_GEN_SUCCESS:chart_{current_ts}.png]\\n')\nexcept Exception: pass\n"

    filename = f"sandbox_{current_ts}.py"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(magic_prefix + clean_code + magic_suffix)

    try:
        process = await asyncio.create_subprocess_exec("python3", filename, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15.0)
        return (stdout.decode('utf-8') + "\n" + stderr.decode('utf-8')).strip()[:3000]
    except asyncio.TimeoutError:
        try:
            process.kill()
        except:
            pass
        return "⚠️ 超时！"
    except Exception as e:
        return f"崩溃：{str(e)}"
    finally:
        if os.path.exists(filename): os.remove(filename)


@tool
async def query_private_knowledge(query: str, config: RunnableConfig, k: int = 5) -> str:
    """【全息图谱与大脑检索】用户问“私有知识库/上传资料”时调用。query 是简短搜索词。"""
    user_id = config.get("configurable", {}).get("user_id", "guest_user")

    # === 1. 向量粗排与大模型精排 (LLM Reranking) ===
    try:
        def _do_vector_search():
            # 🚀 扩大粗搜范围到 10 个
            return vector_db.max_marginal_relevance_search(query, k=10, fetch_k=30, filter={"user_id": user_id})

        docs = await asyncio.to_thread(_do_vector_search)

        if docs:
            # 🚀 召唤 Flash 特工，对 10 个碎片进行瞬时逻辑质检与去重排
            rerank_prompt = f"针对用户问题【{query}】，从以下文本碎片中筛选出真正有价值的内容，剔除废话和不相关的内容。如果没有，就回复无：\n\n"
            for idx, d in enumerate(docs):
                rerank_prompt += f"碎片[{idx + 1}]: {d.page_content.strip()[:300]}\n"

            rerank_res = await sub_llm.ainvoke(
                [SystemMessage(content="你是数据清洗特工。"), HumanMessage(content=rerank_prompt)])
            vector_res = [f"📄 [宏观记忆与高阶摘要]:\n{rerank_res.content}"]
        else:
            vector_res = []
    except Exception as e:
        vector_res = []

    # === 2. 图谱抽取与记忆唤醒 (突触生长) ===
    graph_res = []
    try:
        sys_msg = SystemMessage(content="提取最多3个核心实体名词，逗号分隔。")
        entity_res = await sub_llm.ainvoke([sys_msg, HumanMessage(content=query)])
        entities = [e.strip() for e in entity_res.content.replace("，", ",").split(",") if e.strip()]

        if neo4j_driver:
            async with neo4j_driver.session() as session:
                for entity in entities:
                    # 🚀 当节点被查询时，让它的 hit_count 活跃度 +1，使星球在前端变大发光！
                    cypher = """
                    MATCH (n:Entity {user_id: $uid})-[r:RELATED_TO]-(m:Entity {user_id: $uid}) 
                    WHERE n.name CONTAINS $entity OR m.name CONTAINS $entity 
                    SET n.hit_count = COALESCE(n.hit_count, 1) + 1
                    SET m.hit_count = COALESCE(m.hit_count, 1) + 1
                    RETURN n.name AS source, r.desc AS relation, m.name AS target, r.source AS file LIMIT 15
                    """
                    result = await session.run(cypher, entity=entity, uid=user_id)
                    for rec in await result.data():
                        graph_res.append(
                            f"(实体: {rec['source']}) --[{rec['relation']}]--> (实体: {rec['target']})[溯源: {rec['file']}]")
    except:
        pass

    output = "【专属记忆检索】\n🕸️ [全息图谱精准链条]:\n" + (
        "\n".join(list(set(graph_res))) if graph_res else "该领域认知空白")
    output += "\n\n" + ("\n".join(vector_res) if vector_res else "无碎片记忆")
    return output


@tool
async def list_mindvault_files() -> str:
    """【物资清单】问“上传了啥”时调用。"""
    try:
        sources = set(os.path.basename(meta['source']) for meta in
                      vector_db._collection.get(include=['metadatas']).get('metadatas', []) if
                      meta and 'source' in meta)
        res = "🧠 **私有大脑**:\n" + "\n".join([f"- {s}" for s in sources]) + "\n\n" if sources else "大脑空。"
        return res
    except Exception as e:
        return f"读取失败: {str(e)}"


@tool
async def visual_analyzer(query: str, image_file_path: str, config: RunnableConfig) -> str:
    """【多模态视觉引擎 Llama-4】分析图片内容必须调用。"""
    if not os.path.exists(image_file_path): return "图片不存在。"
    thread_id = config.get("configurable", {}).get("thread_id", "")
    q = GLOBAL_Q.get(thread_id)
    if q: asyncio.create_task(q.put("\n\n> ⏳ 视觉神经挂载 Llama-4 多模态大语言模型对齐...\n\n"))
    try:
        with open(image_file_path, "rb") as image_file:
            # NVIDIA Llama-4 视觉要求兼容 OpenAI 的 image_url 格式
            base64_str = base64.b64encode(image_file.read()).decode('utf-8')
            content = [{"type": "text", "text": query},
                       {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_str}"}}]
            resp = await sub_llm_vision.ainvoke([HumanMessage(content=content)])
            return f"视觉诊断:\n{resp.content}"
    except Exception as e:
        return f"视觉失败: {str(e)}"


@tool
async def surf_and_analyze_web(url: str, target_query: str, config: RunnableConfig) -> str:
    """【云端穿透提取】借助 Jina API 穿透动态网页提炼特定信息。"""
    thread_id = config.get("configurable", {}).get("thread_id", "")
    q = GLOBAL_Q.get(thread_id)
    if q: await q.put(f"\n\n> 🕷️ **云端节点启动**：穿透目标网址提取数据...\n\n")
    try:
        response = await clean_async_client.get(f"https://r.jina.ai/{url}",
                                                headers={"Accept": "application/json", "X-Return-Format": "markdown"},
                                                timeout=20.0)
        if response.status_code == 200:
            resp = await sub_llm.ainvoke(
                [HumanMessage(content=f"网页内容如下：\n{response.text[:4000]}\n\n需求：【{target_query}】。")])
            return f"云端特工汇报:\n{resp.content}"
        return f"网页穿透失败，状态码: {response.status_code}"
    except Exception as e:
        return f"网页提炼失败: {str(e)}"


# ============================================================================================

researcher_agent = create_react_agent(sub_llm, tools=[get_current_time, perform_web_search, fetch_webpage_content])

# 🚀 替换代码特工底层大脑为专属模型 qwen3-coder-480b
operator_agent = create_react_agent(llm_coder, tools=[execute_python_code])


class ResearchTasks(BaseModel): tasks: List[str]


@tool(args_schema=ResearchTasks)
async def delegate_to_researcher(tasks: List[str], config: RunnableConfig) -> str:
    """将情报搜集委托给特工。"""

    async def _run(t):
        try:
            return (await researcher_agent.ainvoke(
                {"messages": [SystemMessage(content="情报特工"), HumanMessage(content=t)]}, config=config))["messages"][
                -1].content
        except:
            return "检索失败"

    return "\n---\n".join(await asyncio.gather(*[_run(t) for t in tasks]))


@tool
async def delegate_to_operator(task: str, config: RunnableConfig) -> str:
    """【代码特工】由 Qwen3-Coder 负责写代码及画图。"""
    operator_prompt = "你是顶级程序员 QwenCoder。用户要求画图/计算时直接写 Python 代码，画图末尾带 plt.show()。"
    return (
        await operator_agent.ainvoke({"messages": [SystemMessage(content=operator_prompt), HumanMessage(content=task)]},
                                     config=config))["messages"][-1].content


GLOBAL_SWARM_WORKFLOW = None
GLOBAL_DYNAMIC_WORKFLOW = None

# =========================================================================
# ⚔️ 学术法庭：红蓝双主脑对抗辩论流 (Debate Swarm) 修复不重复版
# =========================================================================
GLOBAL_DEBATE_WORKFLOW = None

def get_debate_workflow():
    global GLOBAL_DEBATE_WORKFLOW
    if GLOBAL_DEBATE_WORKFLOW is not None: return GLOBAL_DEBATE_WORKFLOW

    class DebateState(TypedDict):
        messages: Annotated[Sequence[BaseMessage], add_messages]
        topic: str
        turn_count: int
        max_turns: int

    async def red_team_node(state: DebateState):
        # 🚀 强制锁定立场：取辩题中的第一个概念
        sys_prompt = SystemMessage(
            content=f"你是【红方首席辩手】。当前的辩题是：{state['topic']}。"
                    f"【你的绝对立场】：你必须坚决支持该辩题中的第一种选择/正向选择！"
                    f"【你的任务】：请仔细阅读上文中蓝方的反驳，逐一击破他的漏洞！"
                    f"切忌重复上一轮的话！你要抛出全新的论点或引用新的数据案例。"
                    f"态度极度自信、语锋犀利、充满攻击性！字数控制在 150 字左右。"
        )
        # 🚀 拉高温度值 (temperature=0.8) 防止变成复读机
        temp_llm = llm_r1.with_config(tags=["red_team"])
        res = await safe_model_call(temp_llm, [sys_prompt] + list(state["messages"]))
        clean_content = re.sub(r'<think>.*?</think>', '', res.content.strip(), flags=re.DOTALL).strip()
        return {"messages":[AIMessage(content=clean_content, name="Red", additional_kwargs=res.additional_kwargs)], "turn_count": state["turn_count"] + 1}

    async def blue_team_node(state: DebateState):
        # 🚀 强制锁定立场：取辩题中的第二个概念
        sys_prompt = SystemMessage(
            content=f"你是【蓝方首席辩手】。当前的辩题是：{state['topic']}。"
                    f"【你的绝对立场】：你必须坚决支持该辩题中的第二种选择/反向选择！绝对不允许同意红方！"
                    f"【你的任务】：红方刚才发表了极其荒谬的言论，请立刻抓住他话里的逻辑漏洞，进行极其残忍的反击！"
                    f"绝对不要说车轱辘话！每一轮都要用全新的角度（比如商业价值、时间成本、底层逻辑）去反驳。"
                    f"字数控制在 150 字以内，一剑封喉。"
        )
        # 🚀 蓝方使用 Flash 模型，拉高创造力
        temp_llm = sub_llm.with_config(tags=["blue_team"]).bind(temperature=0.8)
        res = await safe_model_call(temp_llm, [sys_prompt] + list(state["messages"]))
        return {"messages": [AIMessage(content=res.content, name="Blue", additional_kwargs=res.additional_kwargs)], "turn_count": state["turn_count"] + 1}

    async def judge_node(state: DebateState):
        if state["turn_count"] == 0:
            return {"messages":[
                AIMessage(content=f"【宣判开庭】本庭将就以下议题展开辩论：**{state['topic']}**。\n\n"
                                  f"**规则**：红方将捍卫第一选项（正方立场），蓝方将捍卫第二选项（反方立场）。\n\n请红方率先陈述。",
                          name="Judge")]}
        else:
            sys_prompt = SystemMessage(
                content=f"你是【最高审判长】。关于《{state['topic']}》的辩论已结束。"
                        "请通读以上双方的辩论记录，给出一份上帝视角的、中立客观的「终局判决研报」。\n"
                        "包含：1. 双方核心交锋点总结； 2. 双方各自的致命逻辑漏洞； 3. 你给出的终极中立建议。\n"
                        "使用优雅的 Markdown 排版，要有大将之风。"
            )
            res = await safe_model_call(llm_pro.with_config(tags=["judge"]), [sys_prompt] + list(state["messages"]))
            return {"messages":[AIMessage(content=res.content, name="Judge", additional_kwargs=res.additional_kwargs)]}

    def debate_router(state: DebateState):
        if state["turn_count"] == 0: return "red_team"
        if state["turn_count"] >= state["max_turns"]: return "judge"

        last_speaker = state["messages"][-1].name
        if last_speaker == "Red":
            return "blue_team"
        else:
            return "red_team"

    workflow = StateGraph(DebateState)
    workflow.add_node("judge", judge_node)
    workflow.add_node("red_team", red_team_node)
    workflow.add_node("blue_team", blue_team_node)

    workflow.add_edge(START, "judge")
    workflow.add_conditional_edges("judge", lambda s: "red_team" if s["turn_count"] == 0 else END)
    workflow.add_conditional_edges("red_team", debate_router)
    workflow.add_conditional_edges("blue_team", debate_router)

    GLOBAL_DEBATE_WORKFLOW = workflow.compile()
    return GLOBAL_DEBATE_WORKFLOW


def get_swarm_workflow():
    global GLOBAL_SWARM_WORKFLOW
    if GLOBAL_SWARM_WORKFLOW is None:
        class SwarmState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], add_messages]
            task: str
            plan: str
            code: str
            test_results: str
            iterations: int
            next_agent: str
            history: list

        async def ceo_node(state: SwarmState):
            iterations = state.get("iterations", 0) + 1
            history = state.get("history", [])
            if iterations > 15: return {"next_agent": "finish", "iterations": iterations,
                                        "messages": [AIMessage(content="[FORCE_FINISH]", name="CEO")]}

            sys_prompt = SystemMessage(
                content=f"CEO。任务：{state['task']}\n蓝图: {state.get('plan')}\n代码: {state.get('code')}\n历史: {history}\n只回复: architect, coder, qa, finish。")
            res = await llm_pro.with_config(tags=["ceo"]).ainvoke([sys_prompt])
            decision_clean = re.sub(r'<think>.*?</think>', '', res.content.strip().lower(), flags=re.DOTALL).strip()

            route = "architect"
            for a in ["architect", "coder", "qa", "finish"]:
                if a in decision_clean: route = a; break

            history.append(route)
            return {"next_agent": route, "iterations": iterations, "history": history}

        async def architect_node(state: SwarmState):
            res = await llm_r1.with_config(tags=["architect"]).ainvoke(
                [SystemMessage(content="架构师，输出开发步骤，禁止写代码。"), HumanMessage(content=state["task"])])
            return {"plan": re.sub(r'<think>.*?</think>', '', res.content.strip(), flags=re.DOTALL).strip(),
                    "messages": [AIMessage(content="[蓝图输出]", name="Architect")]}

        async def coder_node(state: SwarmState):
            msgs = [SystemMessage(content="你是高级程序员 QwenCoder。用 <file path=\"name.py\">包裹代码"),
                    HumanMessage(content=f"任务:{state['task']}\n蓝图:{state.get('plan')}")]
            if state.get("test_results") and "FAIL" in state.get("test_results", ""): msgs.append(
                HumanMessage(content=f"修复Bug：\n{state['test_results']}"))
            # 🚀 Coder 节点专用 Qwen3-Coder
            res = await llm_coder.with_config(tags=["coder"]).ainvoke(msgs)
            code_content = res.content
            if "<file path=" not in code_content: code_content = f'<file path="main.py">\n{code_content}\n</file>'
            return {"code": code_content, "test_results": "[尚未测试]",
                    "messages": [AIMessage(content="[提交代码]", name="Coder")]}

        async def qa_node(state: SwarmState):
            files = re.findall(r'<file path="([^"]+)">\s*(.*?)\s*</file>', state.get("code", ""), re.DOTALL)
            if not files: return {"test_results": "FAIL: 未检测到代码"}
            workspace_dir = os.path.abspath(f"./workspaces/build_{int(time.time())}")
            os.makedirs(workspace_dir, exist_ok=True)
            main_file = None
            try:
                for file_path, content in files:
                    safe_path = os.path.normpath(file_path).lstrip('/')
                    full_path = os.path.join(workspace_dir, safe_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    if safe_path.endswith("main.py") or safe_path.endswith("app.py"): main_file = safe_path
                if not main_file: main_file = [f[0] for f in files if f[0].endswith(".py")][0]

                process = await asyncio.create_subprocess_exec("python3", "-m", "py_compile", main_file,
                                                               stdout=asyncio.subprocess.PIPE,
                                                               stderr=asyncio.subprocess.PIPE, cwd=workspace_dir)
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
                if process.returncode != 0: return {
                    "test_results": f"FAIL (语法错误):\n{stderr.decode('utf-8').strip()}"}
                return {"test_results": "PASS"}
            except Exception as e:
                return {"test_results": f"FAIL: {str(e)}"}

        workflow = StateGraph(SwarmState)
        workflow.add_node("ceo", ceo_node)
        workflow.add_node("architect", architect_node)
        workflow.add_node("coder", coder_node)
        workflow.add_node("qa", qa_node)
        workflow.add_edge(START, "ceo")
        workflow.add_conditional_edges("ceo", lambda s: s.get("next_agent", "finish"),
                                       {"architect": "architect", "coder": "coder", "qa": "qa", "finish": END})
        workflow.add_edge("architect", "ceo")
        workflow.add_edge("coder", "ceo")
        workflow.add_edge("qa", "ceo")
        GLOBAL_SWARM_WORKFLOW = workflow.compile()
    return GLOBAL_SWARM_WORKFLOW


async def get_dynamic_workflow():
    global GLOBAL_DYNAMIC_WORKFLOW
    if GLOBAL_DYNAMIC_WORKFLOW is not None: return GLOBAL_DYNAMIC_WORKFLOW

    base_tools = [delegate_to_researcher, delegate_to_operator, query_private_knowledge, list_mindvault_files,
                  surf_and_analyze_web, deep_research_engine, visual_analyzer]
    llm_with_tools = llm_pro_no_think.bind_tools(base_tools)

    class AgentState(TypedDict): messages: Annotated[Sequence[BaseMessage], add_messages]

    async def commander_node(state: AgentState):
        return {"messages": [await safe_model_call(llm_with_tools, state["messages"])]}

    workflow = StateGraph(AgentState)
    workflow.add_node("commander", commander_node)
    workflow.add_node("tools", ToolNode(base_tools))
    workflow.add_edge(START, "commander")
    workflow.add_conditional_edges("commander", lambda s: "tools" if s["messages"][-1].tool_calls else END)
    workflow.add_edge("tools", "commander")

    import aiosqlite
    _conn = await aiosqlite.connect("mindvault_checkpoints.db")
    memory_checkpointer = AsyncSqliteSaver(_conn)
    GLOBAL_DYNAMIC_WORKFLOW = workflow.compile(checkpointer=memory_checkpointer)
    return GLOBAL_DYNAMIC_WORKFLOW


# 🚀 修复版输出流，保证任何情况文字都不丢失
async def _internal_agent_loop(api_messages: list, thread_id: str, user_id: str):
    langchain_msgs = [HumanMessage(content=api_messages[-1]["content"])]
    app_engine = await get_dynamic_workflow()
    has_streamed = False
    try:
        async for event in app_engine.astream_events({"messages": langchain_msgs}, config={
            "configurable": {"thread_id": thread_id, "user_id": user_id}, "recursion_limit": 100}, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            tags = event.get("tags", [])

            if kind == "on_tool_start":
                if name == "delegate_to_researcher":
                    yield f"\n\n> 🌐 **超光速雷达 (Tavily)**：并发搜索网际协议...\n\n"
                elif name == "deep_research_engine":
                    yield f"\n\n> 📰 **[深研特工启动]**：全网信源聚合中...\n\n"
                elif name == "surf_and_analyze_web":
                    yield f"\n\n> 🕷️ **云端节点**：穿透目标网址提取纯净数据...\n\n"
                elif name == "query_private_knowledge":
                    yield f"\n\n> 🧠 **双擎检索**：激活租户图谱与 RAPTOR 节点...\n\n"
            elif kind == "on_tool_end":
                if name == "delegate_to_operator" or name == "execute_python_code":
                    tool_output = str(event.get("data", {}).get("output", ""))
                    remote_images = re.findall(r'(!\[.*?\]\(data:image/.*?;base64,.*?\))', tool_output)
                    if remote_images:
                        yield f"\n\n> ☁️ **云端沙盒释放**：绘图完毕！\n\n"
                        for img in remote_images: yield f"\n\n{img}\n\n"
                    else:
                        local_match = re.search(r'\[LOCAL_IMAGE_GEN_SUCCESS:(.*?)\]', tool_output)
                        if local_match:
                            yield f"\n\n> 💻 **本地降级沙盒释放**：绘图完毕！\n\n\n![渲染快照](/static/{local_match.group(1)})\n\n"
                        elif "❌" in tool_output or "⚠️" in tool_output:
                            yield f"\n\n> {tool_output[:500]}\n\n"
                elif name in ["delegate_to_vision_agent", "visual_analyzer"]:
                    yield f"\n\n> 🧬 **视觉神经 (Llama-4)**：图像信息已汇入主脑！\n\n"
            elif kind == "on_chat_model_stream":
                if "sub_agent" in tags: continue
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and isinstance(chunk.content, str):
                    clean_text = chunk.content
                    if clean_text:
                        has_streamed = True
                        yield clean_text
            elif kind == "on_chain_end" and name == "LangGraph":
                out_s = event["data"].get("output")
                if out_s and "messages" in out_s:
                    final_ai_msg = next((m.content for m in reversed(out_s["messages"]) if
                                         getattr(m, "type", "") == "ai" and not getattr(m, "tool_calls",
                                                                                        None)),
                                        "")
                    if final_ai_msg:
                        clean_missing = final_ai_msg
                        if not has_streamed and clean_missing: yield f"\n\n{clean_missing}\n\n"
    except Exception as e:
        yield f"\n\n> 🚨 **系统异常**：{str(e)}\n\n"


async def run_agent_loop(api_messages: list, thread_id: str, raw_query: str, user_id: str):
    q = asyncio.Queue()
    GLOBAL_Q[thread_id] = q

    async def run_graph():
        try:
            async for chunk in _internal_agent_loop(api_messages, thread_id, user_id): await q.put(chunk)
        except Exception as e:
            await q.put(f"\n\n> 🚨 **异常**：{str(e)}\n\n")
        finally:
            await q.put(None)

    asyncio.create_task(run_graph())
    try:
        while True:
            chunk = await q.get()
            if chunk is None: break
            yield chunk
    finally:
        if thread_id in GLOBAL_Q: del GLOBAL_Q[thread_id]


async def _internal_swarm_loop(task: str, thread_id: str):
    app_engine = get_swarm_workflow()
    yield f"\n\n> 🏢 **触发 /swarm**：启动 DeepSeek V4  研报研发流...\n\n"
    try:
        async with AsyncSqliteSaver.from_conn_string("mindvault_checkpoints.db") as memory_saver:
            app_engine_with_memory = app_engine.with_config({"checkpointer": memory_saver})
            async for event in app_engine_with_memory.astream_events(
                    {"task": task, "iterations": 0, "test_results": "[尚未测试]", "messages": [], "history": []},
                    config={"configurable": {"thread_id": thread_id}, "recursion_limit": 100}, version="v2"):
                kind = event["event"];
                name = event.get("name", "")
                if kind == "on_chain_start":
                    if name == "ceo":
                        yield f"> 🧠 **[CEO (DeepSeek V4)]**：全局推演...\n\n"
                    elif name == "architect":
                        yield f"> 📐 **[架构师]**：极限逻辑拆解中...\n\n"
                    elif name == "coder":
                        yield f"> 💻 **[开发组 (Qwen3-Coder 480B)]**：超量参数编写代码...\n\n"
                elif kind == "on_chain_end":
                    if name == "coder":
                        coder_output = event["data"].get("output", {})
                        if coder_output and "code" in coder_output:
                            files = re.findall(r'<file path="([^"]+)">\s*(.*?)\s*</file>', coder_output["code"],
                                               re.DOTALL)
                            if files:
                                yield f"\n\n### 📦 阶段性代码交付：\n\n"
                                for fp, fc in files: yield f"**📂 `{fp}`**\n```python\n{fc.strip()}\n```\n\n"
                    elif name == "ceo":
                        out_data = event["data"].get("output", {})
                        if out_data.get(
                            "next_agent") == "finish": yield f"> 🏁 **CEO 批示**：完结，准备发往沙盒！\n\n---\n\n"
                    elif name == "LangGraph":
                        final_state = event["data"].get("output", {})
                        if final_state and "code" in final_state:
                            code_content = final_state["code"]
                            files = re.findall(r'<file path="([^"]+)">\s*(.*?)\s*</file>', code_content, re.DOTALL)
                            main_code = ""
                            if files:
                                for fp, fc in files:
                                    if fp.endswith("main.py") or fp.endswith("app.py"): main_code = fc; break
                                if not main_code: main_code = files[0][1]
                            if main_code:
                                yield f"\n\n> 🚀 **[全自动执行]**：代码发往云端沙盒（FC/本地）...\n\n"
                                try:
                                    exec_result = await execute_python_code.ainvoke({"code": main_code}, config={
                                        "configurable": {"thread_id": thread_id}})
                                    local_match = re.search(r'\[LOCAL_IMAGE_GEN_SUCCESS:(.*?)\]', exec_result)
                                    if local_match:
                                        yield f"\n\n![渲染快照](/static/{local_match.group(1)})\n\n"
                                    else:
                                        yield f"\n\n{exec_result}\n\n"
                                except Exception as e:
                                    yield f"\n\n> ❌ **执行失败**：{str(e)}\n\n"
    except Exception as e:
        yield f"\n\n> 🚨 **Swarm 崩溃**：{str(e)}\n\n"


async def run_swarm_loop(task: str, thread_id: str):
    q = asyncio.Queue()
    GLOBAL_Q[thread_id] = q

    async def run_graph():
        try:
            async for chunk in _internal_swarm_loop(task, thread_id): await q.put(chunk)
        except Exception as e:
            await q.put(f"\n\n> 🚨 **异常**：{str(e)}\n\n")
        finally:
            await q.put(None)

    asyncio.create_task(run_graph())
    try:
        while True:
            chunk = await q.get()
            if chunk is None: break
            yield chunk
    finally:
        if thread_id in GLOBAL_Q: del GLOBAL_Q[thread_id]


# =========================================================================
# ⚔️ 学术法庭直播流引擎
# =========================================================================
async def _internal_debate_loop(topic: str, thread_id: str):
    app_engine = get_debate_workflow()
    yield f"\n\n> ⚖️ **触发 /debate (学术法庭)**：启动 DeepSeek 双引擎对抗推演流...\n\n"
    try:
        async for event in app_engine.astream_events(
                {"topic": topic, "turn_count": 0, "max_turns": 8, "messages": []},  # 默认对抗 4 个回合
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 50}, version="v2"):

            kind = event["event"];
            name = event.get("name", "")

            if kind == "on_chain_start":
                if name == "judge":
                    yield f"\n\n---\n\n> 👨‍⚖️ **[最高审判长]**：肃静，正在接管法庭...\n\n"
                elif name == "red_team":
                    yield f"\n\n---\n\n> 🔴 **[红方 (R1深度思考)]**：正在推演正方立论...\n\n"
                elif name == "blue_team":
                    yield f"\n\n---\n\n> 🔵 **[蓝方 (V4-Flash)]**：正在全网搜寻反击漏洞...\n\n"


            elif kind == "on_chain_end":

                if name == "red_team":

                    output = event["data"].get("output", {}).get("messages", [])

                    if output: yield f"\n\n**🔴 红方主张：**\n\n{output[-1].content}\n\n"

                elif name == "blue_team":

                    output = event["data"].get("output", {}).get("messages", [])

                    if output: yield f"\n\n**🔵 蓝方反击：**\n\n{output[-1].content}\n\n"

                elif name == "judge":

                    output = event["data"].get("output", {}).get("messages", [])

                    if output:

                        judge_text = output[-1].content

                        # 🚀 优化：通过判断文字内容，区分是“开庭”还是“终审判决”！

                        if "宣判开庭" not in judge_text:
                            yield f"\n\n**👨‍⚖️ 终局判决研报：**\n\n{judge_text}\n\n"

    except Exception as e:
        yield f"\n\n> 🚨 **法庭崩溃**：{str(e)}\n\n"


async def run_debate_loop(topic: str, thread_id: str):
    q = asyncio.Queue()
    GLOBAL_Q[thread_id] = q

    async def run_graph():
        try:
            async for chunk in _internal_debate_loop(topic, thread_id): await q.put(chunk)
        except Exception as e:
            await q.put(f"\n\n> 🚨 **异常**：{str(e)}\n\n")
        finally:
            await q.put(None)

    asyncio.create_task(run_graph())
    try:
        while True:
            chunk = await q.get()
            if chunk is None: break
            yield chunk
    finally:
        if thread_id in GLOBAL_Q: del GLOBAL_Q[thread_id]


# =========================================================================
# 🦋 混沌沙盘：蝴蝶效应推演模拟器 (Butterfly Effect Sandbox)
# =========================================================================
async def _internal_simulate_loop(decision: str, thread_id: str, user_id: str):
    yield f"\n\n> 🦋 **触发 /simulate (混沌沙盘)**：正在进行因果重组与时空坍缩...\n\n"
    await asyncio.sleep(0.5)

    # 1. 从 Neo4j 图数据库中读取宿主当前的最强能力锚点 (个性化推演)
    user_context = "未知 (空白大脑)"
    if neo4j_driver:
        try:
            cypher = """
            MATCH (n:Entity {user_id: $uid})-[r:RELATED_TO]-(m:Entity {user_id: $uid})
            WITH n, count(r) AS degree ORDER BY degree DESC LIMIT 15
            RETURN collect(n.name) AS top_skills
            """
            async with neo4j_driver.session() as session:
                record = await (await session.run(cypher, uid=user_id)).single()
                if record and record["top_skills"]:
                    user_context = "、".join(record["top_skills"])
        except Exception:
            pass

    yield f"> 🧬 **[读取宿主记忆锚点]**：{user_context}\n\n"
    yield f"> 🌀 **[量子计算中]**：注入变量「{decision}」，唤醒 DeepSeek-Reasoner 高阶逻辑链...\n\n"

    # 2. 构建沙盘推演提示词
    sys_prompt = SystemMessage(
        content="你是【混沌沙盘】多维命运推演引擎。你拥有极其冷酷、上帝视角的科幻语调。"
                "你的任务是基于宿主当前拥有的知识锚点，推演其某项「微小或重大决定」在未来 3 年内产生的多阶蝴蝶效应。\n"
                "【强制排版要求】：\n"
                "必须使用类似 ASCII 的树状字符 (如 ├── 和 └── ) 来绘制时间线分支。\n"
                "⚠️ 重要指令：你必须将整个 ASCII 树状推演图用 ```text 和 ``` 包裹起来，当做代码块输出！以确保前端等宽对齐。\n"
                "推演必须包含：\n"
                "1. ⏱️ 【一阶效应】(1-3个月)：最直接的后果（现实反馈、肉体/精神变化）。\n"
                "2. ⏱️ 【二阶效应】(1年)：外部环境的真实反弹（同行竞争、市场变化、蝴蝶效应初显）。\n"
                "3. ⏱️ 【三阶效应】(3年)：产生两条平行宇宙终局。必须分裂为：\n"
                "   ├── 🌟[破局线 (极小概率)]：理想情况下的史诗级成功。\n"
                "   └── 💀[陨落线 (大概率)]：现实且残酷的失败或平庸终局。\n"
                "切记：推演必须极度硬核、现实，不要盲目喂鸡汤！"
    )

    human_msg = HumanMessage(
        content=f"宿主当前的知识技能库：【{user_context}】\n"
                f"宿主注入的决定变量：【{decision}】\n"
                f"请立即开始推演。"
    )

    try:
        # 使用官方 R1 (Reasoner) 模型进行流式输出
        temp_llm = llm_r1.with_config(tags=["simulator"])
        async for chunk in temp_llm.astream([sys_prompt, human_msg]):
            if chunk.content:
                yield chunk.content

        yield f"\n\n> ⏳ **[推演结束]**：平行宇宙已收敛。一切皆为概率，最终坍缩权在宿主手中。\n\n"

    except Exception as e:
        yield f"\n\n> 🚨 **沙盘崩溃**：时空引力异常 - {str(e)}\n\n"


async def run_simulate_loop(decision: str, thread_id: str, user_id: str):
    q = asyncio.Queue()
    GLOBAL_Q[thread_id] = q

    async def run_graph():
        try:
            async for chunk in _internal_simulate_loop(decision, thread_id, user_id): await q.put(chunk)
        except Exception as e:
            await q.put(f"\n\n> 🚨 **异常**：{str(e)}\n\n")
        finally:
            await q.put(None)

    asyncio.create_task(run_graph())
    try:
        while True:
            chunk = await q.get()
            if chunk is None: break
            yield chunk
    finally:
        if thread_id in GLOBAL_Q: del GLOBAL_Q[thread_id]


# =========================================================================
# 👥 影子内阁：并发多角色圆桌会议 (Shadow Cabinet)
# =========================================================================
async def _internal_council_loop(topic: str, thread_id: str):
    yield f"\n\n> 🏛️ **触发 /council (影子内阁)**：正在并发唤醒三位顶层智囊...\n\n"
    yield f"> 🚀 [激进极客]、🎓 [严谨教授]、💼 [冷酷资本家] 已落座。\n\n"
    yield f"> 🧠 正在同时审视您的提案：**{topic}**，请稍候...\n\n"

    # 定义智囊呼叫特工
    async def get_advice(persona: str, prompt: str):
        try:
            sys_msg = SystemMessage(content=prompt)
            # 🚀 使用速度极快的 v4-flash 进行并发呼叫
            res = await sub_llm.ainvoke([sys_msg, HumanMessage(content=f"用户的重大抉择/提案是：{topic}")])
            # 把换行符换成 <br>，以完美适配 Markdown 表格
            return persona, res.content.replace('\n', '<br>')
        except Exception as e:
            return persona, f"⚠️ 智囊掉线：{str(e)}"

    # 🚀 并发执行 3 个不同人格的任务！(瞬间完成)
    tasks = [
        get_advice("🚀 激进极客 (创新与颠覆)",
                   "你是【激进极客】(类似埃隆·马斯克)。崇尚第一性原理，激进，鼓励打破常规、冒险和疯狂尝试前沿技术。"
                   "针对用户的重大抉择，给出你极具野心、无视世俗规则的建议。字数控制在250字以内，语气狂热。"),
        get_advice("🎓 严谨教授 (底座与风控)",
                   "你是【严谨教授】。保守、严谨，看重理论基础、体系化建设和可行性分析，善于指出计划中的薄弱点和致命风险。"
                   "针对用户的重大抉择，给出你的严厉警告和夯实基础的建议。字数控制在250字以内，语气严肃、苦口婆心。"),
        get_advice("💼 冷酷资本家 (ROI与现实)",
                   "你是【冷酷资本家】。极度现实、冷血，只看重ROI（投资回报率）、如何变现、如何搞钱、如何拿大厂实习Offer。"
                   "针对用户的重大抉择，从利益最大化角度进行无情的现实批判或功利性建议。字数控制在250字以内，语气犀利、功利。")
    ]


    results = await asyncio.gather(*tasks)

    content_a = results[0][1]
    content_b = results[1][1]
    content_c = results[2][1]

    # 构建表头
    table_header = f"""### 🏛️ 影子内阁圆桌决议\n\n**📝 审议提案**：{topic}\n\n| 🚀 激进极客 (创新与颠覆) | 🎓 严谨教授 (底座与风控) | 💼 冷酷资本家 (ROI与现实) |\n| :--- | :--- | :--- |\n| """

    # 1. 先输出表头
    yield table_header
    await asyncio.sleep(0.5)

    # 2. 模拟打字机效果输出表格内容
    # 把三段内容拼成 Markdown 表格的一行
    full_row = f"{content_a} | {content_b} | {content_c} |\n\n"

    # 将内容切成小块，每块延迟 0.04 秒输出，制造丝滑的打字效果
    chunk_size = 3
    for i in range(0, len(full_row), chunk_size):
        yield full_row[i:i + chunk_size]
        await asyncio.sleep(0.04)  # ⚡ 控制这里的数字可以调整打字速度

    yield f"> 👑 **[CEO中枢]**：正在听取汇报，生成最终决策...\n\n"
    await asyncio.sleep(2.0)  # ⚡ CEO 思考停顿 1 秒，增加真实感

    # CEO 根据三个人的意见做总结
    ceo_prompt = "你是最高决策者CEO。请根据以下三位智囊团的建议，为用户提取出一个最平衡、最具执行力的行动方案。字数300字以内，一锤定音。"
    ceo_input = f"极客意见：{content_a}\n教授意见：{content_b}\n资本家意见：{content_c}"

    # ---------------- 替换部分结束 ----------------

    ceo_res = await llm_pro.ainvoke([SystemMessage(content=ceo_prompt), HumanMessage(content=ceo_input)])

    yield f"**👑 CEO 终局决策**：\n\n{ceo_res.content.replace('<br>', '')}\n\n"


async def run_council_loop(topic: str, thread_id: str):
    q = asyncio.Queue()
    GLOBAL_Q[thread_id] = q

    async def run_graph():
        try:
            async for chunk in _internal_council_loop(topic, thread_id): await q.put(chunk)
        except Exception as e:
            await q.put(f"\n\n> 🚨 **内阁崩溃**：{str(e)}\n\n")
        finally:
            await q.put(None)

    asyncio.create_task(run_graph())
    try:
        while True:
            chunk = await q.get()
            if chunk is None: break
            yield chunk
    finally:
        if thread_id in GLOBAL_Q: del GLOBAL_Q[thread_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(pdf_processing_worker())
    await ensure_neo4j_schema()
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        if neo4j_driver: await neo4j_driver.close()
        await redis_client.close()


app = FastAPI(lifespan=lifespan)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://mindvault.ltd,https://www.mindvault.ltd").split(",")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health_check():
    checks = {"redis": "unknown", "neo4j": "disabled" if not neo4j_driver else "unknown"}
    ok = True
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=2.0); checks["redis"] = "ok"
    except Exception as e:
        ok = False; checks["redis"] = f"error: {type(e).__name__}"
    if neo4j_driver:
        try:
            await asyncio.wait_for(neo4j_driver.verify_connectivity(), timeout=3.0); checks["neo4j"] = "ok"
        except Exception as e:
            ok = False; checks["neo4j"] = f"error: {type(e).__name__}"
    return JSONResponse(status_code=200 if ok else 503,
                        content={"status": "ok" if ok else "degraded", "checks": checks})


async def check_rate_limit(request):
    """Redis 速率限制：5分钟内同一 IP 最多10次请求"""
    ip = request.client.host if hasattr(request, 'client') and request.client else "unknown"
    key = f"rate_limit:{ip}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 300)
        if count > 10:
            raise HTTPException(status_code=429, detail="请求过于频繁，请5分钟后再试")
    except HTTPException:
        raise
    except:
        pass  # Redis 不可用时放行


class VerifyRequest(BaseModel): code: str


@app.post("/verify_key")
async def verify_key(request: VerifyRequest, fastapi_request: Request):
    await check_rate_limit(fastapi_request)
    code = request.code.strip().upper()
    if ADMIN_ACTIVATION_CODE and code == ADMIN_ACTIVATION_CODE: return JSONResponse(
        content={"status": "success", "message": "管理员核准"})
    try:
        c = keys_conn.cursor()
        c.execute("SELECT is_active FROM activation_keys WHERE key_code = ?", (code,))
        row = c.fetchone()
        if row and row[0]:
            return JSONResponse(content={"status": "success", "message": "密钥有效"})
        else:
            return JSONResponse(content={"status": "error", "message": "无效或过期的密钥"}, status_code=403)
    except:
        return JSONResponse(content={"status": "error", "message": "服务器异常"}, status_code=500)


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    user_id: str = "guest_user"
    image_base64: Optional[str] = None


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        memory_thread_id = f"tenant_{request.user_id}_session_{uuid.uuid4().hex[:8]}"
        user_latest_input = request.messages[-1]["content"].strip() if request.messages else ""

        if user_latest_input.startswith("/swarm "):
            return StreamingResponse(run_swarm_loop(user_latest_input[7:].strip(), memory_thread_id),
                                     media_type="text/plain", headers={"X-Accel-Buffering": "no"})

        if user_latest_input.startswith("/debate "):
            return StreamingResponse(run_debate_loop(user_latest_input[8:].strip(), memory_thread_id),
                                     media_type="text/plain", headers={"X-Accel-Buffering": "no"})
        if user_latest_input.startswith("/council "):
            return StreamingResponse(run_council_loop(user_latest_input[9:].strip(), memory_thread_id),
                                     media_type="text/plain", headers={"X-Accel-Buffering": "no"})
        if user_latest_input.startswith("/simulate "):
            return StreamingResponse(
                run_simulate_loop(user_latest_input[10:].strip(), memory_thread_id, request.user_id),
                media_type="text/plain", headers={"X-Accel-Buffering": "no"})

        current_time_str = datetime.now().strftime('%Y年%m月%d日')
        system_prompt = f"""你是 MindVault 【NVIDIA NIM 增强版最高指挥官】。
        当前系统真实时间：{current_time_str}。
        【铁血法则】：
        1. 【深度冲浪】：调用 `surf_and_analyze_web` 穿透网页。
        2. 【数据/画图】：要求画图/数据分析时，必须使用 `delegate_to_operator` 调用 Qwen Coder！
        3. 【全球搜索】：调用 `perform_web_search` 或 `deep_research_engine`。
        4. 【查询知识】：必须使用 `query_private_knowledge` 获取 NVIDIA NV-Embed 双擎数据！"""

        api_messages = [{"role": "system", "content": system_prompt}]
        extra_vision_prompt = ""

        if request.image_base64:
            os.makedirs("uploads", exist_ok=True)
            try:
                image_bytes = base64.b64decode(request.image_base64, validate=True)
            except:
                raise HTTPException(status_code=400, detail="图片数据无效")
            if len(image_bytes) > MAX_UPLOAD_BYTES: raise HTTPException(status_code=400, detail=f"超 {MAX_UPLOAD_MB}MB")
            img_path = f"./uploads/vision_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            extra_vision_prompt = f"\n\n[指令：长官上传了一张图 `{img_path}`，立刻调用 visual_analyzer (Llama-4) 分析！]"

        for i, msg in enumerate(request.messages):
            if i == len(request.messages) - 1:
                api_messages.append({"role": "user", "content": msg['content'] + extra_vision_prompt})
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        return StreamingResponse(
            run_agent_loop(api_messages, memory_thread_id, raw_query=user_latest_input, user_id=request.user_id),
            media_type="text/plain", headers={"X-Accel-Buffering": "no"})
    except Exception as e:
        async def err():
            yield f"系统崩溃：{str(e)}"

        return StreamingResponse(err(), media_type="text/plain")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Form("guest_user")):
    try:
        file.file.seek(0, 2);
        file_size = file.file.tell();
        file.file.seek(0)
        if file_size > MAX_UPLOAD_BYTES: return JSONResponse(status_code=400, content={"status": "error",
                                                                                       "message": f"超 {MAX_UPLOAD_MB}MB！"})
        original_filename = file.filename or "upload"
        stored_filename = safe_upload_filename(original_filename)
        file_path = os.path.join("uploads", stored_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        task_data = {"filename": stored_filename, "original_filename": original_filename, "user_id": user_id,
                     "type": "upload"}
        await redis_client.lpush("mindvault_pdf_queue", json.dumps(task_data))
        return JSONResponse(
            content={"status": "success", "message": f"🧠 【{original_filename}】上传成功！进入 NV-Embed 提取流。"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph_data")
async def get_graph_data(user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse(
        content={"nodes": [{"id": "MindVault", "name": "无密码", "val": 5}], "links": []})
    try:
        async with neo4j_driver.session() as session:
            # 🚀 引入了 COALESCE(n.hit_count, 1)，读取节点的活跃度记录
            cypher = """
            MATCH (n:Entity {user_id: $uid})-[r:RELATED_TO]->(m:Entity {user_id: $uid}) 
            RETURN n.name AS source, COALESCE(n.hit_count, 1) AS s_hits, 
                   r.desc AS relation, 
                   m.name AS target, COALESCE(m.hit_count, 1) AS t_hits 
            LIMIT 1500
            """
            records = await (await session.run(cypher, uid=user_id)).data()

        nodes_dict, links = {}, []
        for rec in records:
            src, s_hits, rel, tgt, t_hits = rec['source'], rec['s_hits'], rec['relation'], rec['target'], rec['t_hits']

            # 🚀 节点的大小(val) = 基础大小(1) + 突触连接数(0.5) + 被大模型检索的活跃度(s_hits * 0.5)
            if src not in nodes_dict:
                nodes_dict[src] = {"id": src, "name": src, "val": 1 + (s_hits * 0.5)}
            else:
                nodes_dict[src]["val"] += 0.5

            if tgt not in nodes_dict:
                nodes_dict[tgt] = {"id": tgt, "name": tgt, "val": 1 + (t_hits * 0.5)}
            else:
                nodes_dict[tgt]["val"] += 0.5

            links.append({"source": src, "target": tgt, "label": rel})

        if not nodes_dict: nodes_dict["MindVault"] = {"id": "MindVault", "name": "大脑空", "val": 5}
        return JSONResponse(content={"nodes": list(nodes_dict.values()), "links": links})
    except Exception as e:
        return JSONResponse(content={"nodes": [{"id": "Error", "name": f"图谱异常:{str(e)}", "val": 5}], "links": []})

@app.post("/clear")
async def clear_memory(request: dict):
    user_id = request.get("user_id", "guest_user")
    try:
        if neo4j_driver:
            async with neo4j_driver.session() as session: await session.run(
                "MATCH (n:Entity {user_id: $uid}) DETACH DELETE n", uid=user_id)
        try:
            vector_db._collection.delete(where={"user_id": user_id})
        except:
            pass
        try:
            with sqlite3.connect("mindvault_checkpoints.db", timeout=20) as checkpoint_conn:
                checkpoint_prefix = escape_sqlite_like(f"tenant_{user_id}_") + "%"
                checkpoint_conn.cursor().execute("DELETE FROM checkpoints WHERE thread_id LIKE ? ESCAPE '\\'",
                                                 (checkpoint_prefix,))
                checkpoint_conn.cursor().execute("DELETE FROM checkpoint_writes WHERE thread_id LIKE ? ESCAPE '\\'",
                                                 (checkpoint_prefix,))
        except:
            pass
        return {"status": "success"}
    except:
        return {"status": "error"}

# ============ 粘贴在这里 ============

@app.get("/list_files")
async def list_files(user_id: str = "guest_user"):
    """【列出大脑文件】给前端 UI 用的接口"""
    try:
        sources = set(os.path.basename(meta['source']) for meta in vector_db._collection.get(include=['metadatas']).get('metadatas',[]) if meta and 'source' in meta)
        return {"status": "success", "files": list(sources)}
    except Exception as e:
        return {"status": "error", "files":[]}


class DeleteFileRequest(BaseModel):
    filename: str
    user_id: str = "guest_user"

@app.post("/delete_file")
async def delete_file(request: DeleteFileRequest):
    """【外科手术清除】精准抹除某个特定文件在图谱和向量库中的所有记忆"""
    file_target = request.filename
    uid = request.user_id
    try:
        # 1. 从 Neo4j 图数据库中抹除该文件的突触
        if neo4j_driver:
            async with neo4j_driver.session() as session:
                await session.run("MATCH ()-[r:RELATED_TO {source: $src}]->() DELETE r", src=file_target)
                await session.run("MATCH (n:Entity {user_id: $uid}) WHERE NOT (n)--() DETACH DELETE n", uid=uid)

        # 2. 从 Chroma 向量数据库中抹除
        try:
            results = vector_db._collection.get(where={"user_id": uid})
            ids_to_delete = [
                doc_id for doc_id, meta in zip(results['ids'], results['metadatas'])
                if file_target in meta.get('source', '')
            ]
            if ids_to_delete:
                vector_db._collection.delete(ids=ids_to_delete)
        except Exception as vec_e:
            logger.warning(f"Chroma 删除跳过: {vec_e}")

        return {"status": "success", "message": f"🔪 已彻底抹除《{file_target}》的所有记忆！"}
    except Exception as e:
        return {"status": "error", "message": f"清理失败: {str(e)}"}

# ====================================


@app.get("/system_logs")
async def stream_system_logs(user_id: str = "guest_user"):
    """
    【上帝视角瀑布流】
    前端可以使用 EventSource('/system_logs?user_id=xxx') 监听此接口，
    后台处理文件的所有进度都会像直播一样推给前端！
    """
    async def event_generator():
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"mindvault_logs_{user_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    log_text = message["data"]
                    # 按照 SSE 的标准格式发送
                    yield f"data: {log_text}\n\n"
                    # 当碰到 [DONE] 标记时，通知前端处理结束
                    if "[DONE]" in log_text:
                        yield f"data: [CLOSE_CONNECTION]\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/node_details")
async def get_node_details(node_name: str, user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse({"error": "Neo4j未连接"})
    try:
        async with neo4j_driver.session() as session:
            cypher = "MATCH (n:Entity {name: $node_name, user_id: $uid})-[r:RELATED_TO]-(m:Entity {user_id: $uid}) RETURN m.name AS connected_node, r.desc AS relation, r.source AS source_file LIMIT 10"
            records = await (await session.run(cypher, node_name=node_name, uid=user_id)).data()
            return JSONResponse({"details": records})
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/graph_path")
async def get_graph_path(start: str, end: str, user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse({"error": "Neo4j未连接"})
    try:
        async with neo4j_driver.session() as session:
            cypher = "MATCH p=shortestPath((n:Entity {name: $start, user_id: $uid})-[:RELATED_TO*1..6]-(m:Entity {name: $end, user_id: $uid})) RETURN nodes(p) AS path_nodes"
            result = await session.run(cypher, start=start, end=end, uid=user_id)
            record = await result.single()
            if not record: return JSONResponse({"path": []})
            return JSONResponse({"path": [node["name"] for node in record["path_nodes"]]})
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/isolated_nodes")
async def get_isolated_nodes(user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse({"error": "Neo4j未连接"})
    try:
        async with neo4j_driver.session() as session:
            cypher = "MATCH (n:Entity {user_id: $uid}) OPTIONAL MATCH (n)-[r]-() WITH n, count(r) AS degree WHERE degree <= 1 RETURN n.name AS node_name LIMIT 30"
            records = await (await session.run(cypher, uid=user_id)).data()
            return JSONResponse({"nodes": [r["node_name"] for r in records]})
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/graphrag_summary")
async def graphrag_summary(user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse({"error": "Neo4j未连接"})
    try:
        async with neo4j_driver.session() as session:
            cypher = "MATCH (n:Entity {user_id: $uid})-[r:RELATED_TO]-(m:Entity {user_id: $uid}) WITH n, count(r) AS degree, collect(m.name)[0..5] AS connections WHERE degree >= 2 RETURN n.name AS hub, connections ORDER BY degree DESC LIMIT 5"
            records = await (await session.run(cypher, uid=user_id)).data()
        if not records: return JSONResponse({"summary": "图谱太空。"})
        prompt = "基于聚落生成高阶摘要：\n\n" + "\n".join(
            [f"- 核心【{r['hub']}】，关联：{', '.join(r['connections'])}" for r in records])
        resp = await sub_llm.ainvoke([SystemMessage(content="你是知识梳理专家。"), HumanMessage(content=prompt)])
        return JSONResponse({"summary": resp.content})
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/download_report")
async def download_report(user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse({"error": "Neo4j未连接"})
    try:
        async with neo4j_driver.session() as session:
            cypher = "MATCH (n:Entity {user_id: $uid})-[r:RELATED_TO]->(m:Entity {user_id: $uid}) RETURN n.name AS source, r.desc AS relation, m.name AS target LIMIT 200"
            records = await (await session.run(cypher, uid=user_id)).data()
        if not records: return JSONResponse({"error": "图谱空旷！"})
        graph_text = "\n".join([f"[{rec['source']}] --({rec['relation']})--> [{rec['target']}]" for rec in records])
        sys_prompt = SystemMessage(content="撰写排版精美、逻辑严密的深度研报。")
        resp = await sub_llm.ainvoke([sys_prompt, HumanMessage(content=f"根据图谱链条撰写：\n{graph_text}")])
        filename = f"MindVault_Report_{int(time.time())}.md"
        filepath = os.path.join("exports", filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# MindVault 研报\n> 数据来源：3D全息大脑\n\n---\n\n{resp.content}")
        return FileResponse(filepath, media_type='text/markdown', filename="MindVault_研报.md")
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/download_excel")
async def download_excel(user_id: str = "guest_user"):
    if not neo4j_driver: return JSONResponse({"error": "Neo4j未连接"})
    try:
        async with neo4j_driver.session() as session:
            cypher = "MATCH (n:Entity {user_id: $uid})-[r:RELATED_TO]->(m:Entity {user_id: $uid}) RETURN n.name AS source, r.desc AS relation, m.name AS target LIMIT 1500"
            records = await (await session.run(cypher, uid=user_id)).data()
        if not records: return JSONResponse({"error": "没有足够数据！"})
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['起点概念', '关系', '终点概念'])
        for rec in records: writer.writerow([rec['source'], rec['relation'], rec['target']])
        return StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=MindVault.csv"})
    except Exception as e:
        return JSONResponse({"error": str(e)})


class ClipRequest(BaseModel):
    text: str;
    url: str;
    user_id: str = "guest_user"


@app.post("/clip")
async def clip_knowledge(request: ClipRequest):
    if not request.text.strip(): return JSONResponse(status_code=400, content={"status": "error", "message": "空"})
    try:
        await redis_client.lpush("mindvault_pdf_queue", json.dumps(
            {"type": "clip", "user_id": request.user_id, "text": request.text, "url": request.url}))
        return {"status": "success", "message": "🧠 碎片已被成功捕获！"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
    logger.info("🚀 MindVault (NVIDIA NIM 特别版) 准备就绪！")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")