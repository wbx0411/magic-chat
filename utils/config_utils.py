import os

import yaml


class SysConfig:
    _config = None

    @staticmethod
    def get_config(key=None, env='dev'):
        if not SysConfig._config:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(current_dir, '..', "configs")
            base_config_file = os.path.join(config_dir, 'config.base.yaml')
            env = os.getenv('RUN_ENV', env)  # default dev
            print(f"Loading config for {env}")
            config_file = os.path.join(config_dir, f'config.{env}.yaml')

            # load yaml
            try:
                with open(base_config_file, 'r', encoding="utf-8") as file:
                    base_config = yaml.safe_load(file)
            except FileNotFoundError:
                raise Exception(f"Configuration file {base_config_file} not found.")

            try:
                with open(config_file, 'r', encoding="utf-8") as f:
                    config = yaml.safe_load(f)
            except FileNotFoundError:
                raise Exception(f"Configuration file {config_file} not found.")

            SysConfig._config = {**base_config, **config}
        return SysConfig._config if key is None else SysConfig._config.get(key, {})

    @staticmethod
    def get_yaml_config(file_path: str):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(current_dir, '..', "configs")
        config_file = os.path.join(config_dir, f'{file_path}.yaml')
        with open(config_file, 'r', encoding="utf-8") as f:
            return yaml.safe_load(f)


if __name__ == '__main__':
    print(SysConfig.get_config("api_code_key"))
