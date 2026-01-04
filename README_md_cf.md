# 部署说明

## 安装conda
```sh
# 从工单中获取安装介质
# 赋予执行权限
chmod +x Miniconda3-latest-Linux-x86_64.sh
# 运行安装脚本
#  - 会提示阅读许可协议，按 `Enter` 键逐页查看，输入 `yes` 表示接受许可协议。
#  - 询问安装路径时，可选择默认路径，也可以根据需求指定其他路径。
#  - 安装完成后，询问是否初始化 Miniconda，输入 `yes` 进行初始化。
./Miniconda3-latest-Linux-x86_64.sh
# 激活环境
source ~/.bashrc
# 验证安装
conda --version
```

## 安装python环境
```sh
# 从工单中获取安装介质：magic-chat-env-0313.tar.gz
# 上传conda环境到安装目录，比如/root/miniconda3/envs
# 解压环境
tar -zxvf magic-chat-env-0313.tar.gz
# 激活conda环境
conda activate magic-chat
# 验证环境
python --version
```

## 启动服务
```sh
# 激活conda环境
conda activate magic-chat

# 启动向量化服务
# 进入服务目录：m3e_service
# 设置服务端口
export PORT=30001
# 后台启动m3e向量化服务
nohup python main.py > out.log 2>&1 &

# 启动大模型服务
# 从工单中获取安装介质：magic-chat.zip，解压并上传
# 进入服务目录：magic-chat
# 服务配置：/configs/config.md_cf.yaml
#  - 修改大模型访问地址：llm_base_url
#  - 修改大模型访问名称：model_name
#  - 修改大模型的api_key：api_key
#  - 修改pg数据库配置：postgres_rag
#  - 修改向量服务地址：m3e_base_url
#  - 修改大模型服务启动端口：
# 后台启动服务
nohup python main_md_cf.py > out.log 2>&1 &
# 验证服务
# INFO:     Started server process [10553]
# INFO:     Waiting for application startup.
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://0.0.0.0:7001 (Press CTRL+C to quit)
tail -f out.log
```

### chat_ws 请求格式
```json
{
    "message": "你好",
    "chat_config": {
        "system_prompt": "请问有什么可以帮助您的吗？",  // 系统提示
        "top_k": 1,  // 选取top_k个知识
        "allows_answer": "True",  // 没有匹配到知识时，是否允许回答
        "memory_k": 3,  // 对话记录的长度
        "knowledge_sources": {  // 知识源
            "name_match": [],  // 名称匹配
            "content_match": [],  // 内容匹配
        },
    },
}
```