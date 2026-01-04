import asyncio
import os

import httpx

from framework.llm.llm_manager import achat, chat
from utils.logger_utils import LoggerFactory

logger = LoggerFactory.get_logger(__name__)


def local_test():
    os.environ['OPENAI_API_KEY'] = 'IY4Afv+cRogFUTWG5KeicoLYbsqWmq6rcRq8kv6y2LI='
    CONFIG = {
        'model_type': 'openai',
        'llm_base_url': 'http://10.4.57.222:21434/v1',
        'model_name': 'deepseek-r1:32b',
    }
    print(chat(CONFIG, "你好"))


def gm_connect_test():
    CONFIG = {
        'llm_base_url': 'http://25.75.64.157/lmp-cloud-ias-server/api/llm/chat/completions',
        'model_name': 'DeepSeek-R1-Distill-Qwen-32B',
        'openai_api_key': 'lY4Afv+cRogFUTWG5KeicoLYbsqWmq6rcRq8kv6y2LI=',
        'streaming': False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": CONFIG['openai_api_key'],
    }
    data = {
        "model": CONFIG['model_name'],
        "messages": [{"role": "user", "content": "你好"}],
        "stream": CONFIG['streaming'],
    }
    client = httpx.Client()
    response = client.post(CONFIG['llm_base_url'], headers=headers, json=data)
    response.raise_for_status()
    logger.info(f"llm response: {response.json()}")


async def main_test():

    CONFIG = {
        'model_type': 'guangming',
        'llm_base_url': 'http://25.75.64.157/lmp-cloud-ias-server/api/llm',
        'model_name': 'DeepSeek-R1-Distill-Qwen-32B',
        'api_key': 'lY4Afv+cRogFUTWG5KeicoLYbsqWmq6rcRq8kv6y2LI=',
    }
    TEST_CONFIG = {
        'model_type': 'openai',
        'llm_base_url': 'http://10.4.57.222:28000/guangming',
        # 'llm_base_url': 'http://10.4.57.222:21434/v1',
        'model_name': 'deepseek-r1:32b',
        'api_key': 'sk-neusoft',
    }
    CONFIG = TEST_CONFIG
    # local_test()
    try:
        logger.info("================chat====================")
        print(chat(CONFIG, "你好"))
    except Exception as e:
        logger.error("Error in gm_test: %s", e, exc_info=True)
    try:
        logger.info("================chat_stream====================")
        print(chat(CONFIG, "你好", streaming=True))
    except Exception as e:
        logger.error("Error in gm_stream_test: %s", e, exc_info=True)
    try:
        logger.info("================achat====================")
        print(await achat(CONFIG, "你好"))
    except Exception as e:
        logger.error("Error in gm_test: %s", e, exc_info=True)
    try:
        logger.info("================achat_stream====================")
        print(await achat(CONFIG, "你好", streaming=True))
    except Exception as e:
        logger.error("Error in gm_stream_test: %s", e, exc_info=True)


asyncio.run(main_test())
