import os

from framework.rag import rmWWW
from utils import get_uuid

os.environ["RUN_ENV"] = "md_cf"

import asyncio
import json
import time
import traceback

from settings import CONFIG

from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from starlette.websockets import WebSocketDisconnect
from websockets import ConnectionClosedOK

from biz.tools import RTN_TYPE, tool_manager
from biz.chat_record_manager import ChatRecordManager
from framework.chain.streaming_chat_chain import StreamingChatChain
from transport.web_container.fastapi_base import create_base_fastapi
from transport.websocket.websocket_sender import send_msg
from utils.logger_utils import LoggerFactory

logger = LoggerFactory.get_logger(__name__)
chat_record = ChatRecordManager()
app = create_base_fastapi()


@app.websocket("/chat_ws")
async def chat_ws(websocket: WebSocket):
    connection_id = get_uuid()
    await websocket.accept()

    logger.info(f"[{connection_id}]connection established")
    streaming_chat_chain = None
    while True:
        try:
            if websocket.application_state == WebSocketState.DISCONNECTED:
                logger.info(f"[{connection_id}]connection was disconnected")
                break

            user_msg = await websocket.receive_text()
            logger.info(f"[{connection_id}]client message: %s", user_msg)

            if not streaming_chat_chain:
                msg_dict = json.loads(user_msg)
                chat_config = msg_dict.get("chat_config", {})
                # 创建StreamingChatChain实例，加载配置
                streaming_chat_chain = await StreamingChatChain.create(
                    websocket,
                    {
                        **CONFIG,
                        **chat_config,
                        'user_id': msg_dict.get("user_id", ""),
                        'org_no': msg_dict.get("org_no", ""),
                        'connection_id': connection_id,
                    },
                )
                # 设置tool
                logger.info(f"StreamingChatChain created: {streaming_chat_chain.configs}")

            await asyncio.wait_for(
                handle_chat_interaction(websocket, user_msg, streaming_chat_chain),
                timeout=streaming_chat_chain.configs['websocket_timeout'],
            )

        except TimeoutError:
            logger.warning(f"[{connection_id}]Interaction timeout")
            await send_msg(websocket, "bot", "请求超时，请稍后再试。", "error")
            continue  # 继续监听下一个消息
        except WebSocketDisconnect:
            logger.info(f"[{connection_id}]connection was disconnected")
            break
        except ConnectionClosedOK:
            logger.info(f"[{connection_id}]connection was closed properly")
            break
        except Exception as e:
            logger.error(f"[{connection_id}]An error occurred: %s", e, exc_info=True)
            await send_msg(websocket, "bot", "对不起, 出错了，请再试一次。", "error")
            await send_msg(websocket, "bot", traceback.format_exc(), "error_trace")
    streaming_chat_chain = None


user_msg_temp = {
    "message": "你好",
    "chat_config": {
        "system_prompt": "请问有什么可以帮助您的吗？",  # 系统提示
        "top_k": 1,  # 选取top_k个知识
        "allows_answer": True,  # 没有匹配到知识时，是否允许回答
        "memory_k": 3,  # 对话记录的长度
        "knowledge_sources": {  # 知识源
            "name_match": [],  # 名称匹配
            "content_match": [],  # 内容匹配
        },
    },
}


async def handle_chat_interaction(
    websocket: WebSocket, user_msg: str, chat_chain: StreamingChatChain
):
    connection_id = chat_chain.configs.get("connection_id", "")
    msg_dict = json.loads(user_msg)
    assert "message" in msg_dict, "Message content is required in user message"
    message_content = msg_dict.get("message", "")

    await send_msg(websocket, "human", message_content, "stream")
    # bot resp start
    await send_msg(websocket, "bot", '', "start")

    # 去除问句中的无效词
    message_content = rmWWW(message_content)
    logger.info(f"[{connection_id}]rmWWW: {message_content}")

    # 通过tool调用获取知识
    time_begin = time.time()
    # 名称匹配
    knowledges = await tool_manager.name_match(message_content, chat_chain)
    if not knowledges:
        # 内容匹配
        knowledges = await tool_manager.content_match(message_content, chat_chain)
    vector_duration = time.time() - time_begin

    # 通过llm获取回答
    time_begin = time.time()
    if knowledges:
        for kv, kt in [(k.value, k.type) for k in knowledges if k.type != RTN_TYPE.KNOWLEDGE]:
            await send_msg(websocket, "bot", "", kt, kv)
            logger.info(f"[{connection_id}]send message, {kt}: {kv}")
        answer = ""
        prompts = [k.value for k in knowledges if k.type == RTN_TYPE.KNOWLEDGE]
        if prompts:
            answer, prompt = await chat_chain.call(',\n'.join(prompts), message_content)
        else:
            chat_chain.add_message(message_content)
    else:
        if chat_chain.configs.get("allows_answer", False):
            answer, prompt = await chat_chain.call_simple(message_content)
            await send_msg(websocket, "bot", prompt, "prompt")
        else:
            answer = "抱歉，您输入的内容在我的知识体系与检索范围内未找到匹配项，无法解答。"
            await send_msg(websocket, "bot", answer, "stream")
            chat_chain.add_message(message_content)
    llm_duration = time.time() - time_begin

    # Send the end-response back to the client
    await send_msg(websocket, "bot", answer, "end")
    logger.info(f"[{connection_id}]Bot response: {answer}")

    # 写入聊天记录
    chat_record.add_chat_record(
        session_code=chat_chain.configs.get("user_id", ''),
        question=message_content,
        api_code=connection_id,
        answer=answer,
        org_no=chat_chain.configs.get("org_no", ''),
        vector_duration=vector_duration,
        llm_duration=llm_duration,
        rating=1,
    )


@app.post("/tool/register")
def register(tool_config: dict):
    try:
        logger.info(f"Register tool: {tool_config}")
        tool_manager.unregister(tool_config)
        tool_manager.register(tool_config)
        return {"code": "200", "message": "success"}
    except Exception as e:
        logger.error("Failed to register tool: %s", e, exc_info=True)
        return {"code": "500", "message": str(e)}


@app.post("/tool/unregister")
def register(tool_config: dict):
    try:
        logger.info(f"Unregister tool: {tool_config}")
        tool_manager.unregister(tool_config)
        return {"code": "200", "message": "success"}
    except Exception as e:
        logger.error("Failed to register tool: %s", e, exc_info=True)
        return {"code": "500", "message": str(e)}


@app.post("/tool/action")
async def execute_tool_action(tool_config: dict):
    try:
        assert "action" in tool_config, "Action is required in request body"
        tool = tool_manager.get_tool(tool_config)
        assert hasattr(tool, action := tool_config["action"]), f"Action {action} not found"
        await getattr(tool, action)(**tool_config.get("params", {}))
        return {"code": "200", "message": "success"}
    except Exception as e:
        logger.error("Failed to execute tool: %s", e, exc_info=True)
        return {"code": "500", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=CONFIG.get("app_port", 7002))
