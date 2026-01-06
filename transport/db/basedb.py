from abc import ABC, abstractmethod
from typing import Union

from utils.config_utils import SysConfig
from utils.encryptor_utils import SimpleEncryptor


class BaseDB(ABC):
    def __init__(self, config: str = None):
        if not config:
            raise ValueError("DB config is required")

        self.config_name = config
        self.config = SysConfig.get_config(config)
        simple_encryptor = SimpleEncryptor()
        self.config['password'] = simple_encryptor.decrypt(self.config['password']) if self.config[
            'password'].endswith('=') else self.config['password']

    @abstractmethod
    def query(self, statement: str, parameters: Union[list, tuple, dict] = None, **keyword_parameters: dict):
        pass

    @abstractmethod
    def execute(self, statement: str, parameters: Union[list, tuple, dict] = None, **keyword_parameters: dict):
        pass

    @abstractmethod
    def execute_batch(self, commands: list[(str, Union[list, tuple, dict])]):
        pass
