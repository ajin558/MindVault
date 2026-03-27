import os
from dotenv import load_dotenv

# ==========================================
# 1. 挂载保险箱：加载 .env 里的私有环境变量
# ==========================================
load_dotenv()

# ==========================================
# 🛑 绝对物理断网阀门 (必须放在大模型 import 之前)
# ==========================================
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

proxy_keys = [k for k in os.environ.keys() if 'proxy' in k.lower()]
for k in proxy_keys:
    del os.environ[k]
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import re
import sqlite3
import time
import json
import logging
import traceback
import shutil
import asyncio
import httpx
import subprocess
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import List, Dict, Annotated, Sequence, TypedDict
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from contextlib import asynccontextmanager

from search_engine import search_web

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# ==========================================
# ⚙️ 全局配置中枢 (彻底告别明文泄漏)
# ==========================================
SERVER_BASE_URL = "http://47.93.151.189:8000"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not DEEPSEEK_API_KEY:
    raise ValueError("🚨 致命错误：未在 .env 文件中找到 DEEPSEEK_API_KEY！请配置后重试。")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==========================================
# 🗡️ 完美替身知识库（绝对闭嘴，绝不干扰大模型决策！）
# ==========================================
class DummyKB:
    def query(self, q):
        return ""


kb = DummyKB()

# ==========================================
# 🗄️ 数据库解耦隔离 (核心修复区)
# ==========================================
logger.info("🧠 正在挂载 赛博铁匠铺 技能库...")
# 技能库独立使用 mindvault_skills.db，绝对不和 LangGraph 抢文件！
skills_db_path = "mindvault_skills.db"
conn = sqlite3.connect(skills_db_path, check_same_thread=False, timeout=20)
conn.execute("CREATE TABLE IF NOT EXISTS cyber_skills (name TEXT PRIMARY KEY, description TEXT, code TEXT)")
conn.commit()

clean_http_client = httpx.Client(trust_env=False, timeout=120.0)
clean_async_client = httpx.AsyncClient(trust_env=False, timeout=120.0)

llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
    streaming=True,
    max_retries=5,
    http_client=clean_http_client,
    http_async_client=clean_async_client
)


# ==========================================
# 🛠️ 零区：基础物理工具包
# ==========================================
@tool
def get_current_time() -> str:
    """获取当前真实的系统时间。"""
    now = datetime.now()
    time_str = now.strftime("当前的系统时间是：%Y年%m月%d日 %H时%M分%S秒，星期%w")
    return time_str.replace("星期0", "星期日").replace("星期1", "星期一").replace("星期2", "星期二").replace("星期3",
                                                                                                             "星期三").replace(
        "星期4", "星期四").replace("星期5", "星期五").replace("星期6", "星期六")


@tool
async def perform_web_search(query: str) -> str:
    """全球搜索雷达，返回网页摘要和URL链接。"""
    return await asyncio.to_thread(search_web, query)


@tool
async def fetch_webpage_content(url: str) -> str:
    """【深度阅读器】：抓取网页完整内容。"""
    try:
        logger.info(f"🕸️ 深度研究员正在潜入并阅读网页: {url}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = await clean_async_client.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        html_content = response.text

        text = re.sub(r'<(script|style|nav|footer|header|aside|noscript).*?>.*?</\1>', '', html_content,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > 3000:
            return text[:3000] + "\n\n...[网页尾部已截断，请基于核心内容分析。]"
        return text
    except Exception as e:
        return f"网页抓取失败: {str(e)}。请尝试其他搜索结果。"


@tool
async def save_report_to_disk(filename: str, content: str) -> str:
    """将深度研究报告保存为本地的 Markdown 文件。"""

    def write_file():
        save_dir = "./reports"
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        file_url = f"{SERVER_BASE_URL}/static/reports/{filename}"
        static_reports_dir = "./static/reports"
        os.makedirs(static_reports_dir, exist_ok=True)
        shutil.copy(file_path, os.path.join(static_reports_dir, filename))
        return file_url

    try:
        file_url = await asyncio.to_thread(write_file)
        return f"系统执行成功：报告已排版并生成！请务必在回答中带上这个下载链接：{file_url}"
    except Exception as e:
        return f"保存失败: {str(e)}"


@tool
async def send_wechat_push(title: str, content: str) -> str:
    """向管理员微信发送推送。"""
    PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN")
    if not PUSHPLUS_TOKEN:
        return "执行失败：系统未在 .env 文件中配置 PUSHPLUS_TOKEN！"

    url = "http://www.pushplus.plus/send"
    payload = {"token": PUSHPLUS_TOKEN, "title": title, "content": content, "template": "markdown"}
    try:
        response = await clean_async_client.post(url, json=payload, timeout=10.0)
        return "消息推送成功！" if response.status_code == 200 else f"推送失败: {response.status_code}"
    except Exception as e:
        return f"微信推送失败: {str(e)}"


@tool
def query_business_data(metric: str) -> str:
    """查询内部机密业务数据。"""
    if "活跃" in metric or "访问" in metric:
        return "机密：月均活跃用户突破 150 万，环比增长 35%。"
    elif "收入" in metric or "营收" in metric:
        return "机密：总营收达到 500 万人民币。"
    return f"数据库中未找到关于 '{metric}' 的精确数据。"


@tool
async def execute_shell_command(command: str) -> str:
    """在Linux底层执行Shell命令。"""
    forbidden_keywords = ["rm", "kill", "reboot", "shutdown", "mkfs", "chmod", "chown", ">"]
    for keyword in forbidden_keywords:
        if re.search(rf"\b{keyword}\b", command):
            return f"执行失败：安全拦截！"
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20.0)
            output = ""
            if stdout: output += f"[标准输出]:\n{stdout.decode('utf-8', errors='replace')}\n"
            if stderr: output += f"[标准错误]:\n{stderr.decode('utf-8', errors='replace')}\n"
            if not output: output = "指令执行成功，无输出。"
            return output[:2000] + "\n...(输出过长，已截断)。" if len(output) > 2000 else output
        except asyncio.TimeoutError:
            process.kill()
            return "执行失败：命令运行超时！"
    except Exception as e:
        return f"执行失败：底层报错 {str(e)}"


@tool
async def execute_python_code(code: str) -> str:
    """【极客技术局 - Python沙盒】执行任何数学计算、逻辑处理或生成图表。"""
    logger.info("⚙️ 沙盒引擎已启动，正在编译执行代码...")

    block_char = chr(96)
    pattern = f"{block_char}{{3}}(?:python)?\s*(.*?){block_char}{{3}}"
    match = re.search(pattern, code, re.DOTALL | re.IGNORECASE)
    if match:
        code = match.group(1)
    code = code.strip()

    forbidden_libs = ["os.system", "subprocess", "shutil.rmtree"]
    for f in forbidden_libs:
        if f in code: return f"执行失败：安全拦截！"

    os.makedirs("./static", exist_ok=True)
    current_ts = int(time.time())

    magic_prefix = (
        "import os\n"
        "os.environ['MPLBACKEND'] = 'Agg'\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "import builtins\n"
        "builtins.input = lambda *args, **kwargs: '0'\n"
        "plt.show = lambda *args, **kwargs: None\n"
    )

    magic_suffix = (
        "\n# 系统底层保底扫描机制\n"
        "try:\n"
        "    if plt.get_fignums():\n"
        f"        plt.savefig('./static/chart_{current_ts}.png')\n"
        f"        print('\\n![数据图表]({SERVER_BASE_URL}/static/chart_{current_ts}.png)')\n"
        "except Exception:\n"
        "    pass\n"
    )

    final_code = magic_prefix + code + magic_suffix
    filename = f"sandbox_{current_ts}.py"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_code)

        process = await asyncio.create_subprocess_exec(
            "python3", filename,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20.0)
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')

            logger.info("✅ 沙盒代码执行完毕，正在交还指挥官...")
            output = ""
            if stdout_text: output += f"[计算结果]:\n{stdout_text}\n"
            if stderr_text or process.returncode != 0:
                output += f"[执行报错]:\n{stderr_text}\n"
                output += "\n⚠️ 请自我反思 Bug，修改代码并**再次调用本工具**！"
            elif not output:
                output = "计算完成，无文字输出。"

            return output[:2000]
        except asyncio.TimeoutError:
            process.kill()
            return "执行失败：代码运行超时死循环！请优化逻辑重新测试！"
    except Exception as e:
        return f"执行失败：沙盒故障 {str(e)}"
    finally:
        if os.path.exists(filename):
            os.remove(filename)


@tool
async def forge_cyber_skill(skill_name: str, description: str, code: str) -> str:
    """【赛博铁匠铺】将一段跑通的代码永久刻录为系统的新能力！"""
    if not re.match(r"^[a-zA-Z_]+$", skill_name):
        return "执行失败：skill_name 只能包含英文字母和下划线！"
    try:
        def write_db():
            c = conn.cursor()
            c.execute("REPLACE INTO cyber_skills (name, description, code) VALUES (?, ?, ?)",
                      (skill_name, description, code))
            conn.commit()

        await asyncio.to_thread(write_db)
        return f"✨ 伟大时刻！技能 [{skill_name}] 刻录成功！"
    except Exception as e:
        return f"刻录失败：底层数据库存储异常 {str(e)}"


# ==========================================
# 👑 第一区：【多智能体兵团】孵化中心
# ==========================================
researcher_agent = create_react_agent(llm, tools=[get_current_time, perform_web_search, fetch_webpage_content,
                                                  save_report_to_disk])
operator_agent = create_react_agent(llm, tools=[execute_shell_command, query_business_data, execute_python_code])
communicator_agent = create_react_agent(llm, tools=[send_wechat_push, save_report_to_disk])


# ==========================================
# 👔 第二区：最高指挥官的“委派权杖” (描述极其严谨化)
# ==========================================
@tool
async def delegate_to_researcher(task: str) -> str:
    """【仅用于：查资料、行业调研、时事新闻】如果需要搜索互联网资料，必须调用此工具。"""
    logger.info(f"👔 指挥官委派 -> 🌐深度研究局: {task}")
    sys_msg = SystemMessage(content="""你是【深度研究局长】。需执行以下工作流：
    1. 调用 perform_web_search 检索。2. 调用 fetch_webpage_content 阅读。3. 给出详细报告。""")
    try:
        res = await researcher_agent.ainvoke({"messages": [sys_msg, HumanMessage(content=task)]},
                                             config={"recursion_limit": 30})
        return res["messages"][-1].content
    except Exception as e:
        return f"研究失败：{str(e)}"


@tool
async def delegate_to_operator(task: str) -> str:
    """【仅用于：数学计算、算复利、数据处理、画图表】严禁自己瞎算！必须调用此工具，让沙盒写Python代码算出绝对精确的结果！"""
    logger.info(f"👔 指挥官委派 -> 💻极客运维局: {task}")
    sys_msg = SystemMessage(content="你是极客运维局长。必须写 Python 代码调用沙盒计算出精确答案并汇报！")
    try:
        res = await operator_agent.ainvoke({"messages": [sys_msg, HumanMessage(content=task)]},
                                           config={"recursion_limit": 15})
        return res["messages"][-1].content
    except Exception:
        return "运维局汇报：代码死锁或执行超时。"


@tool
async def delegate_to_communicator(task: str) -> str:
    """推送到微信时调用。"""
    sys_msg = SystemMessage(content="你是公关部长。负责微信推送。")
    try:
        res = await communicator_agent.ainvoke({"messages": [sys_msg, HumanMessage(content=task)]},
                                               config={"recursion_limit": 15})
        return res["messages"][-1].content
    except Exception:
        return "推送失败。"


def create_dynamic_workflow():
    base_tools = [delegate_to_researcher, delegate_to_operator, delegate_to_communicator, forge_cyber_skill]
    c = conn.cursor()
    c.execute("SELECT name, description, code FROM cyber_skills")
    skills = c.fetchall()

    dynamic_tools = []
    for skill_name, skill_desc, skill_code in skills:
        def make_tool(name, desc, code):
            @tool
            async def dynamic_generated_tool(instruction: str) -> str:
                injected_code = f"USER_INPUT = {repr(instruction)}\n" + code
                return await execute_python_code.ainvoke({"code": injected_code})

            dynamic_generated_tool.name = name
            dynamic_generated_tool.description = desc
            return dynamic_generated_tool

        dynamic_tools.append(make_tool(skill_name, skill_desc, skill_code))

    all_commander_tools = base_tools + dynamic_tools
    llm_with_commander_tools = llm.bind_tools(all_commander_tools)

    class AgentState(TypedDict):
        messages: Annotated[Sequence[BaseMessage], add_messages]

    async def commander_node(state: AgentState):
        response = await llm_with_commander_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("commander", commander_node)
    workflow.add_node("tools", ToolNode(all_commander_tools))
    workflow.add_edge(START, "commander")
    workflow.add_conditional_edges("commander", should_continue, ["tools", END])
    workflow.add_edge("tools", "commander")

    return workflow.compile, all_commander_tools


# ==========================================
# ⚡ 第四区：底层流式计算 (内部引擎)
# ==========================================
async def _internal_agent_loop(api_messages: list, thread_id: str):
    langchain_msgs = []
    for msg in api_messages:
        if msg["role"] == "system":
            langchain_msgs.append(SystemMessage(content=msg["content"]))
        elif msg["role"] == "user":
            langchain_msgs.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_msgs.append(AIMessage(content=msg["content"]))

    logger.info(f"🚀 兵团开始协同作战 (记忆线程: {thread_id})...")

    compile_workflow, current_tools = create_dynamic_workflow()
    system_tool_names = [t.name for t in current_tools]

    try:
        # 🗄️ 独立使用 mindvault_checkpoints.db 进行 LangGraph 状态保存
        async with AsyncSqliteSaver.from_conn_string("mindvault_checkpoints.db") as memory_saver:
            await memory_saver.setup()
            company_engine = compile_workflow(checkpointer=memory_saver)

            streamed_text_buffer = ""
            final_ai_message = ""
            config = {"configurable": {"thread_id": thread_id}}

            async for event in company_engine.astream_events({"messages": langchain_msgs}, config=config, version="v2"):
                kind = event["event"]
                if kind == "on_chat_model_start":
                    streamed_text_buffer = ""
                elif kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and isinstance(chunk.content, str):
                        yield chunk.content
                        streamed_text_buffer += chunk.content
                    elif hasattr(chunk, "content") and isinstance(chunk.content, list):
                        for c in chunk.content:
                            if isinstance(c, dict) and "text" in c and c["text"]:
                                yield c["text"]
                                streamed_text_buffer += c["text"]
                elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                    output_state = event["data"].get("output")
                    if output_state and isinstance(output_state, dict) and "messages" in output_state:
                        last_msg = output_state["messages"][-1]
                        if getattr(last_msg, "type", "") == "ai" and not getattr(last_msg, "tool_calls", None):
                            if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                                final_ai_message = last_msg.content

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    if tool_name == "delegate_to_researcher":
                        yield f"\n\n> 🌐 **战略指派**：唤醒【深度研究局长】！正在全网收集资料，请稍候...\n\n"
                    elif tool_name == "perform_web_search":
                        query = event['data'].get('input', {}).get('query', '未知')
                        yield f"\n> 📡 **广度雷达**：正在检索关键词：`{query}` ...\n"
                    elif tool_name == "fetch_webpage_content":
                        url = event['data'].get('input', {}).get('url', '未知')
                        yield f"\n> 🕸️ **深度潜入**：正在读取外部长文：`{url}` ...\n"
                    elif tool_name == "delegate_to_operator":
                        yield f"\n\n> 💻 **战略指派**：唤醒【极客技术局】，启动 Python 沙盒进行绝对精确的计算...\n\n"
                    elif tool_name == "execute_python_code":
                        yield f"\n> ⚙️ **执行中**：沙盒代码疯狂运转中...\n"
                    elif tool_name == "save_report_to_disk":
                        filename = event['data'].get('input', {}).get('filename', '报告.md')
                        yield f"\n> 🖨️ **排版装订**：研究完毕，正在生成实体报告文件 `{filename}` ...\n"
                    elif tool_name == "forge_cyber_skill":
                        yield f"\n\n> 🔨 **系统进化**：最高指挥官触发 [赛博铁匠铺]！正在刻录永久能力...\n\n"
                    elif tool_name in system_tool_names:
                        yield f"\n\n> ⚡ **觉醒技触发**：调动自定义进化技能 [{tool_name}] 进行运算...\n\n"

            if final_ai_message and len(final_ai_message) > len(streamed_text_buffer):
                missing_text = final_ai_message[len(streamed_text_buffer):]
                if missing_text.strip():
                    yield f"\n\n{missing_text}"

            logger.info("✨ 作战圆满结束！")

    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"❌ 系统核爆级故障: {error_msg}")
        yield f"\n\n> 🚨 **系统红色警报**：底座运算引擎崩溃！报错信息：{str(e)}\n\n(请将此日志发给架构师排查)"


# ==========================================
# ⚡ 第五区：外壳流式引擎 (核心优化三：强行心跳保活)
# ==========================================
async def run_agent_loop(api_messages: list, thread_id: str):
    """【心脏起搏器】让后端持续呼吸，防止 Vercel 强制挂断"""
    q = asyncio.Queue()

    async def run_graph():
        try:
            async for chunk in _internal_agent_loop(api_messages, thread_id):
                await q.put(chunk)
        except Exception as e:
            await q.put(f"\n\n> 🚨 **系统异常**：{str(e)}\n\n")
        finally:
            await q.put(None)

    task = asyncio.create_task(run_graph())

    while True:
        try:
            chunk = await asyncio.wait_for(q.get(), timeout=2.5)
            if chunk is None:
                break
            yield chunk
        except asyncio.TimeoutError:
            # 使用标准的普通空格，确保 Vercel 绝对能收到字节并重置倒计时
            yield " "


# ==========================================
# 🌐 第六区：FastAPI 服务接口
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    user_id: str = "guest_user"
    session_id: str = "default_chat"
    mode: str = "researcher"
    use_web_search: bool = False


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        latest_question = request.messages[-1]["content"]

        current_date = datetime.now().strftime("%Y年%m月%d日")
        import uuid
        memory_thread_id = f"tenant_{request.user_id}_session_{uuid.uuid4().hex[:8]}"

        # 🔥 铁血军令状提示词
        system_prompt = f"""你是 MindVault 平台的【最高指挥官】。当前时间：{current_date}。
        【🔥 铁血调度法则 - 违令者死】：
        1. 【计算/画图】：当用户让你“计算”、“算算复利”、“画图”时，必须立刻调用 `delegate_to_operator` 工具！绝不能调用研究局长！
        2. 【查资料】：只有当用户询问“市场趋势”、“新闻”、“帮我查一下资料”时，才能调用 `delegate_to_researcher`。
        3. 收到指令后，闭嘴直接调用工具！禁止回复“收到”、“我已就位”、“请指示”等废话！"""

        api_messages = [{"role": "system", "content": system_prompt}]
        for i, msg in enumerate(request.messages):
            if i == len(request.messages) - 1:
                api_messages.append({"role": "user", "content": msg['content']})
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        # 📜 强行收缴 Vercel 和 Nginx 的“大水桶”
        no_bucket_headers = {
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }

        return StreamingResponse(
            run_agent_loop(api_messages, thread_id=memory_thread_id),
            media_type="text/plain",
            headers=no_bucket_headers
        )

    except Exception as e:
        async def error_stream():
            yield f"系统故障：{str(e)}"

        return StreamingResponse(error_stream(), media_type="text/plain")


class ClearRequest(BaseModel):
    user_id: str
    session_id: str


@app.post("/clear")
async def clear_memory(request: ClearRequest):
    try:
        # 修改清除逻辑，指向新的检查点数据库
        conn = sqlite3.connect("mindvault_checkpoints.db", timeout=20)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM checkpoints")
        cursor.execute("DELETE FROM checkpoint_writes")
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"全局记忆已彻底核弹销毁！"}
    except Exception as e:
        return {"status": "error", "message": f"销毁失败: {str(e)}"}


if __name__ == "__main__":
    logger.info("🚀 MindVault (解耦隔离版 V8.9) 准备就绪！")
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())