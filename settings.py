import os
from utils.config_utils import SysConfig


CONFIG = SysConfig.get_config()

os.environ["DASHSCOPE_API_KEY"] = CONFIG.get("api_key", "")
os.environ["OPENAI_API_KEY"] = CONFIG.get("api_key", "")
