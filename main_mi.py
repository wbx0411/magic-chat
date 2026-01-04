import asyncio
import json
import os
import traceback
import uuid

from fastapi import FastAPI, WebSocket, Request
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
from websockets import ConnectionClosedOK

from biz.fk_assistant.tools.cost_control_calculation import CostControlCalculation
from biz.fk_assistant.tools.outage_execution_manager import OutExecutionManager
from biz.fk_assistant.tools.outage_order_approval import OutageOrderApproval
from biz.fk_assistant.tools.payment_based_reconnection import PaymentBasedReconnection
from biz.fk_assistant.tools.reconnection_process_controller import ReconnectionProcessController
from biz.fk_assistant.tools.sms_delivery import SmsDelivery
from framework.algorithm.simple_bm25 import SimpleBM25
from framework.chain.streaming_chat_chain import StreamingChatChain
from transport.websocket import websocket_sender
from utils.config_utils import SysConfig
from utils.logger_utils import LoggerFactory

os.environ["RUN_ENV"] = "mi"
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
bm25 = SimpleBM25()

tools = [
    CostControlCalculation(),
    OutExecutionManager(),
    OutageOrderApproval(),
    PaymentBasedReconnection(),
    ReconnectionProcessController(),
    SmsDelivery(),
]

tool_docs = [(tool.name, tool) for tool in tools]


@app.websocket("/mi_chat_ws")
async def chat_ws(websocket: WebSocket):
    connection_id = str(uuid.uuid4())
    await websocket.accept()
    logger.info(f"WebSocket connection established with ID: {connection_id}")

    streaming_chat_chain = await StreamingChatChain.create(websocket, configs)

    while True:
        try:
            user_msg = await websocket.receive_text()
            logger.debug("Received message from client: %s", user_msg)

            await asyncio.wait_for(
                handle_chat_interaction(websocket, user_msg, streaming_chat_chain),
                timeout=configs['websocket_timeout'],
            )

        except TimeoutError:
            logger.warning("Interaction timeout")
            await websocket_sender.send_msg(websocket, "bot", "请求超时，请稍后再试。", "error")
            continue  # 继续监听下一个消息
        except WebSocketDisconnect:
            logger.info("WebSocket connection was disconnected")
            break
        except ConnectionClosedOK:
            logger.info("WebSocket connection was closed properly")
            break
        except Exception as e:
            logger.error("An error occurred: %s", e, exc_info=True)
            await websocket_sender.send_msg(
                websocket, "bot", "对不起, 出错了，请再试一次。", "error"
            )
            await websocket_sender.send_msg(websocket, "bot", traceback.format_exc(), "error_trace")


async def handle_chat_interaction(websocket, user_msg, streaming_chat_chain):
    logger.debug("Received message from client: %s", user_msg)

    await websocket_sender.send_msg(websocket, "human", user_msg, "stream")

    # bot resp start
    await websocket_sender.send_msg(websocket, "bot", '', "start")

    docs = bm25.query(tool_docs, user_msg, num_best=1, field=0)
    if docs:
        tool_doc = json.loads(await docs[0][1]._arun("cons_no"))
        await websocket_sender.send_msg(websocket, "bot", f'${tool_doc["key"]}$', "stream")
        answer = await streaming_chat_chain.call(tool_doc['result'], user_msg)
    else:
        answer = await streaming_chat_chain.call_simple(user_msg)

    # Send the end-response back to the client
    await websocket_sender.send_msg(websocket, "bot", answer[0], "end")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
