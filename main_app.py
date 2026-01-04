import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from framework.chain.chat_chain import ChatChain
from utils.config_utils import SysConfig
from utils.logger_utils import LoggerFactory

import sqlite3

import faiss
from sentence_transformers import SentenceTransformer

os.environ["RUN_ENV"] = "app"
os.environ["DASHSCOPE_API_KEY"] = "sk-2442409327df44a394fd9ed8676d3503"

logger = LoggerFactory.get_logger(__name__)
configs = SysConfig.get_config()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserInput(BaseModel):
    prompt_text: str
    chat_history: list = []
    agent_scratchpad: str = ""


@app.post("/menu/")
async def menu(user_input: UserInput):
    prompt_text = user_input.prompt_text

    if not prompt_text:
        raise HTTPException(status_code=400, detail="No input provided")

    chat = ChatChain(configs)
    responses = chat.call(
        agent_scratchpad=user_input.agent_scratchpad, message=prompt_text, info=perform(prompt_text)
    )
    # chat.add_user_message(prompt_text)
    # chat.add_ai_message(responses)

    # Return the response
    return {
        "responses": responses or "出错啦，请再试一次",
        # "memory": menu_memory.to_json()
    }


def perform(search_text):
    model = SentenceTransformer(configs['m3e_small_path'])

    # 加载 Faiss 索引
    index = faiss.read_index(configs['menu_vectors_path'])

    # 连接到 SQLite 数据库
    conn = sqlite3.connect(configs['database_path'])
    cursor = conn.cursor()

    # 将搜索文本转换为向量
    search_vector = model.encode([search_text]).astype('float32')

    # 使用 Faiss 执行搜索
    k = 3  # 我们希望返回最接近的 k 个结果
    D, I = index.search(search_vector, k)  # D 是距离数组，I 是相应的索引 ID

    # 提取与搜索查询最相关的向量 ID
    vector_ids = I[0]

    # 用这些向量 ID 从 SQLite 数据库中检索相关信息
    vector_ids_str = ', '.join(str(id) for id in vector_ids)
    query = f'SELECT * FROM menu_index WHERE vector_id IN ({vector_ids_str})'
    cursor.execute(query)
    search_results = cursor.fetchall()

    # 格式化为 Markdown 表格
    headers = ["产品编号", "产品名称", "产品目录项"]
    results_list = [
        {
            headers[0]: row[1],
            headers[1]: row[2],
            headers[2]: row[3],
        }
        for row in search_results
    ]
    markdown_results = json.dumps(results_list, cls=MarkdownTableEncoder)
    cursor.close()
    conn.close()
    return markdown_results


class MarkdownTableEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, list) and len(obj) > 0:  # Check if the list is not empty
            headers = obj[0].keys()
            md_table = "| " + " | ".join(headers) + " |\n"
            md_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
            for row in obj:
                md_table += "| " + " | ".join(str(value) for value in row.values()) + " |\n"
            return md_table
        elif (
            isinstance(obj, list) and len(obj) == 0
        ):  # If the list is empty, return an empty table or a message
            return "No data available to display in the table."
        return super(MarkdownTableEncoder, self).encode(obj)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
