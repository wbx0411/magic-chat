import asyncio
import datetime
import json
import time
import traceback
import uuid

from fastapi import FastAPI, WebSocket, Request
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
from websockets import ConnectionClosedOK

from biz import data_filter
from biz.miop.auth_client import AuthClient
from biz.chat_record_manager import ChatRecordManager
from biz.index.dqs_client import DQSClient
from biz.index.get_knowledge import get_org, get_index
from biz.miop import chat_request_filter
from biz.index.recommend import recommend_index
from framework.algorithm.jionlp_data_collect import jio_parse_time_point, time_wash_text
from framework.algorithm.simple_bm25 import SimpleBM25
from framework.chain.streaming_chat_chain import StreamingChatChain
from framework.embedding.m3e_client import m3e_client
from transport.db.neo4jdb import Neo4jDB
from transport.websocket import websocket_sender
from utils.config_utils import SysConfig
from utils.date_utils import cmp_current_date, parse_season
from utils.logger_utils import LoggerFactory
from utils.str_utils import text_wash

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

auth_client = AuthClient(configs['auth_base_url'], configs['http_timeout'])
dqs_client = DQSClient(configs['dqs_base_url'], configs['dqs_token'], configs['http_timeout'])

neo4j = Neo4jDB()
bm25 = SimpleBM25()
chat_record = ChatRecordManager()
db_namespace = configs['neo4j_config']['namespace']


@app.websocket("/chat_ws")
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

    msg_dict = json.loads(user_msg)
    message_content = msg_dict.get("message", "")

    await websocket_sender.send_msg(websocket, "human", message_content, "stream")

    # bot resp start
    await websocket_sender.send_msg(websocket, "bot", '', "start")

    # auth
    if configs['auth_mock']:
        org_no = configs['auth_mock_org']
        user_id = configs['auth_mock_user']

    else:
        auth_code = msg_dict.get("token", "")
        auth_result = auth(auth_code)
        if auth_result:
            org_no = auth_result['orgNo']
            user_id = auth_result['userId']
        else:
            await websocket_sender.send_msg(websocket, "bot", "对不起, 没有权限。", "error")
            return

    # 文本清洗
    message_content = text_wash(message_content)
    logger.info(f"Text wash: {message_content}")

    vector_duration = 0

    # 使用聊天请求过滤器对消息内容进行关键词过滤，并获取过滤结果
    filter_start_time = time.time()
    filtration = await chat_request_filter.filter_request_message(message_content, org_no)
    filter_duration = time.time() - filter_start_time
    logger.info(f"request filter time duration: {filter_duration}")

    api_code = None
    connected_sentences = []
    recommend_data = []
    if filtration:
        connected_sentences = [filtration.info]
        api_code = filtration.api
    elif not filtration or filtration.mode == chat_request_filter.Modes.APPEND.value:
        logger.info("No customer 360 information found.")
        # 需要根据问题的原意解析变动的时间格式
        data_time = parse_data_date(message_content)

        # card start
        if configs['card_enable']:
            if cmp_current_date(data_time):
                logger.info("Card search start...")
                api_code, connected_sentences = retrieve_card(message_content, data_time, org_no)

            if api_code:
                logger.info(f"Card api code: {api_code}")
                await websocket_sender.send_msg(websocket, "bot", api_code, "api_code")

        # graph start
        if not api_code:
            logger.info("Card not found, start graph search...")
            time_wash_text_message = time_wash_text(message_content)
            retrieve_start_time = time.time()
            connected_sentences, vector_duration, dqs_url_params, recommend_data_tuple = (
                retrieve_index(time_wash_text_message, data_time, org_no, user_id)
            )
            retrieve_duration = time.time() - retrieve_start_time
            logger.info(f"Retrieve sentences duration: {retrieve_duration}")
            if dqs_url_params:
                await websocket_sender.send_msg(
                    websocket, "bot", str(dqs_url_params), "chart", dqs_url_params
                )

    llm_start_time = time.time()
    if connected_sentences != '[]':
        answer, prompt = await streaming_chat_chain.call(connected_sentences, message_content)
    else:
        answer, prompt = await streaming_chat_chain.call_simple(message_content)
    llm_duration = time.time() - llm_start_time
    logger.info(f"LLM chat duration: {llm_duration}")
    await websocket_sender.send_msg(websocket, "bot", prompt, "prompt")

    # Send the end-response back to the client
    await websocket_sender.send_msg(websocket, "bot", answer, "end")

    recommend_data = recommend(message_content, data_time, org_no, user_id, recommend_data_tuple)
    if recommend_data:
        await websocket_sender.send_msg(websocket, "bot", str(recommend_data), "recommend")

    # 写入聊天记录
    chat_record.add_chat_record(
        session_code=user_id,
        question=message_content,
        api_code=api_code,
        answer=answer,
        org_no=org_no,
        vector_duration=vector_duration,
        llm_duration=llm_duration,
        rating=1,
    )


def auth(auth_code):
    result = auth_client.check_auth(auth_code)
    if result['success'] and result['data']:
        return result['data']
    else:
        return None


def parse_data_date(message_content):
    # 需要根据问题的原意解析变动的时间格式
    parse_data_time = jio_parse_time_point(message_content)
    data_time = parse_data_time[0] if parse_data_time else None
    logger.info(f"Jio date: {data_time}")

    # 分析问话中的季度
    data_time = parse_season(
        message_content, data_time, float(configs.get('min_score_index_time', 0.8))
    )
    logger.info(f"Parse season: {data_time}")

    # 获取当前日期yyyymmdd
    # data_time = time.strftime("%Y%m%d", time.localtime()) if not data_time else data_time
    # logger.info(f"Final data date: {data_time}")
    return data_time or ''


def retrieve_card(message_content, data_time, org_no):
    from biz.card.card_manager import get_api_code, EmbeddingService

    embedding_service = EmbeddingService()

    vec_search_start = time.time()
    vector_result = embedding_service.vector_search(message_content, org_no)
    vec_search_duration = time.time() - vec_search_start
    logger.info(f"Card vector search duration: {vec_search_duration}")

    # card key resp
    api_code, api_desc = get_api_code(vector_result)
    connected_sentences = []
    parse_time = jio_parse_time_point(api_desc)
    api_date_time = (
        parse_time[0]
        if parse_time and parse_time[0]
        else datetime.datetime.now().strftime("%Y%m%d")
    )
    logger.info(f"Card api date time: {api_date_time}, date time: {data_time}")

    if api_code and (
        data_time is None or api_date_time == data_time or str(int(api_date_time) + 1) == data_time
    ):
        # vector search resp
        logger.info(f"api date time = data time, api code: {api_code}")
        for item in vector_result:
            connected_sentences.append(data_filter.filter_cities(message_content, item[0]))
    else:
        api_code = ''

    return api_code, connected_sentences


# 根据对话内容，分析时间，并在知识库中分别检索供电单位、指标及其维度和纬度值，并构建DQS请求参数，获取数据并格式化返回文本
def retrieve_index(message_content, data_time, org_no, user_id):
    _start = time.time()
    db_top = configs['top_k']

    # 请求嵌入文本
    embedding_response = m3e_client.get_embeddings(message_content, configs['m3e_model_name'])
    if embedding_response is None:
        return "空", 0, []

    embedding = embedding_response['data'][0]['embedding']

    _time_search = time.time()
    embedding_duration = _time_search - _start
    logger.info(f"Embedding duration: {embedding_duration}")

    # 原子指标检索
    nodes_ind, scene_flag = get_index(neo4j, db_namespace, message_content, embedding, db_top)

    # 检索供电单位
    _time_org = time.time()
    org_no_query, org_name_query = get_org(neo4j, db_namespace, message_content, embedding, org_no)
    logger.info(f"Org result: {org_no_query} - {org_name_query}")

    _time_dqs = time.time()
    logger.info(f"Search org result: {org_no} -> {org_no_query}")
    logger.info(f"Search org duration: {_time_dqs - _time_org}")
    # DQS请求数据
    # if scene_flag:

    dqs_data, dqs_url_params = dqs_client.get_data_by_kg(
        db_namespace,
        neo4j,
        nodes_ind[: 1 if not scene_flag else len(nodes_ind)],
        message_content,
        embedding,
        org_no_query,
        user_id,
        data_time,
        org_name_query,
    )

    # recommend_data = recommend_index(db_namespace, neo4j, nodes_ind[1:], message_content, embedding,
    #                                  org_name_query, org_no, user_id, data_time) if not scene_flag else None

    _time_graph = time.time()
    logger.info(f"Dimension result: {nodes_ind[:3]}")
    logger.info(f"DQS result: {dqs_data}")
    logger.info(f"DQS duration: {_time_graph - _time_dqs}")

    if len(dqs_data) > 0:
        dqs_data[0]['供电单位'] = org_name_query

    connected_sentences = json.dumps(dqs_data, ensure_ascii=False, indent=2)
    recommend_data_tuple = (nodes_ind, embedding, org_name_query, scene_flag)

    return connected_sentences, embedding_duration, dqs_url_params, recommend_data_tuple


def recommend(message_content, data_time, org_no, user_id, recommend_data_tuple):
    nodes_ind = recommend_data_tuple[0]
    embedding = recommend_data_tuple[1]
    org_name_query = recommend_data_tuple[2]
    scene_flag = recommend_data_tuple[3]
    recommend_data = (
        recommend_index(
            db_namespace,
            neo4j,
            nodes_ind[1:],
            message_content,
            embedding,
            org_name_query,
            org_no,
            user_id,
            data_time,
        )
        if not scene_flag
        else None
    )
    return recommend_data


templates = Jinja2Templates(directory="static")
app.mount("/static", StaticFiles(directory="static"))


@app.get("/test/chat")
async def test_chat(request: Request):
    token = request.query_params['token'] if 'token' in request.query_params else ''
    return templates.TemplateResponse(
        "chat_test.html",
        {
            "request": request,
            "endpoint": configs['test_ws_url'],
            "org_no": configs['test_org_no'],
            "token": token,
        },
    )


@app.post("/test/data")
async def test_data(data: dict):
    message_content = data['message']
    token = data['token'] if 'token' in data else None
    mock = data['mock'] if 'mock' in data else None

    if mock or configs['auth_mock']:
        org_no = configs['auth_mock_org']
        user_id = configs['auth_mock_user']
    else:
        auth_start_time = time.time()
        auth_result = auth(token)
        auth_duration = time.time() - auth_start_time
        logger.info(f"auth duration: {auth_duration}")
        if auth_result:
            org_no = auth_result['orgNo']
            user_id = auth_result['userId']
        else:
            return {"code": "200", "message": "FAIL", "data": "对不起, 没有权限。"}

    ret_data = {}

    vector_duration = 0

    # 使用聊天请求过滤器对消息内容进行关键词过滤，并获取过滤结果
    filter_start_time = time.time()
    filtration = await chat_request_filter.filter_request_message(message_content, org_no)
    filter_duration = time.time() - filter_start_time
    logger.info(f"request filter time duration: {filter_duration}")

    api_code = None
    connected_sentences = []
    if filtration:
        connected_sentences = [filtration.info]
        api_code = filtration.api
    elif not filtration or filtration.mode == chat_request_filter.Modes.APPEND.value:
        logger.info("No customer 360 information found.")
        # 需要根据问题的原意解析变动的时间格式
        data_time = parse_data_date(message_content)
        ret_data['data_time'] = data_time

        # card start
        if configs['card_enable']:
            if cmp_current_date(data_time):
                logger.info("Card search start...")
                api_code, connected_sentences = retrieve_card(message_content, data_time, org_no)

            if api_code:
                logger.info(f"Card api code: {api_code}")
                ret_data['api_code'] = api_code

        # graph start
        if not api_code:
            logger.info("Card not found, start graph search...")
            retrieve_start_time = time.time()
            connected_sentences, vector_duration, dqs_url_params, recommend_data = retrieve_index(
                message_content, data_time, org_no, user_id
            )
            retrieve_duration = time.time() - retrieve_start_time
            logger.info(f"Retrieve sentences duration: {retrieve_duration}")
            if dqs_url_params:
                ret_data['dqs_url_params'] = dqs_url_params
            if recommend_data:
                ret_data['recommend_data'] = recommend_data

    if connected_sentences != '[]':
        llm_start_time = time.time()
        from framework.chain.chat_chain import ChatChain

        chain = ChatChain(configs)
        answer = chain.call(connected_sentences, message_content)
        llm_duration = time.time() - llm_start_time
    else:
        answer = ""
        llm_duration = 0

    ret_data['dqs_data'] = json.loads(connected_sentences)
    ret_data['answer'] = answer

    # 异步插入对话记录
    chat_record.add_chat_record(
        session_code=user_id,
        question=message_content,
        api_code=api_code,
        answer=answer,
        org_no=org_no,
        vector_duration=vector_duration,
        llm_duration=llm_duration,
        rating=1,
    )

    return {"code": "200", "message": "SUCCESS", "data": ret_data}


@app.post("/graph/import/pg")
async def graph_import_pg(data: dict):
    password = data['password']
    if password != configs['neo4j_config']["password"]:
        return {"code": "200", "message": "password error", "data": ""}
    scope = data['scope'] if 'scope' in data else None
    from biz.index.datas import graph_import_pg

    result = graph_import_pg.import_graph(db_namespace, scope)
    return {"code": "200", "message": "SUCCESS", "data": result}


@app.post("/graph/import/ora")
async def graph_import_ora(data: dict):
    password = data['password']
    if password != configs['neo4j_config']["password"]:
        return {"code": "200", "message": "password error", "data": ""}
    scope = data['scope'] if 'scope' in data else None
    from biz.index.datas import graph_import_ora

    result = graph_import_ora.import_graph(db_namespace, scope)
    return {"code": "200", "message": "SUCCESS", "data": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7002)
