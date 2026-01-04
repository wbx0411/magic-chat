
## 开发资料
### DQS-API手册
https://neusoft.feishu.cn/docx/RSd2dHX19oTDJ3xGcNScZmsanbe

### DQS测试数据库地址
```
url: 10.4.59.174
port: 31027
db: miop_dev
user: dws_miop_sxdp
password: Neu@1234
```

## 服务API
### Websocket对话服务
```
ws://server_ip:27002/chat_ws
{
    "message": "2024年9月的售电量是多少",
    "token": ""
}
```

### 数据服务测试，包括：身份验证+知识检索+指标查询+智能回复+对话记录，应返回解析时间、卡片编码、DQS请求参数、推荐指标、指标JSON数据、回答文本等。
```
curl --request POST \
  --url http://server_ip:27001/test/data \
  --header 'content-type: application/json' \
  --data '{
    "message": "2024年9月的售电量是多少",
    "token": ""
}'
```
- 参数message为对话内容
- 参数token为身份认证token，此token由调用对话服务的应用功能提供（在对话页面的HTML源码中有）

### 对话测试
- 启用Mock（不需身份鉴权），则访问 http://localhost:7001/test/chat
- 测试环境增加token参数，访问 http://localhost:7001/test/chat?token=3732353033030303430


## 部署

### 1.部署大语言模型对话服务（之前已部署可跳过）

### 2.部署文本嵌入服务（之前已部署可跳过）

### 3.部署Neo4j数据库（社区版只支持单机部署）
```
docker run -d --name neo4j \
-p 7474:7474 \                              -- 管理页面端口
-p 7687:7687 \                              -- 数据访问端口
-e TZ=Asia/Shanghai \
-e NEO4J_ACCEPT_LICENSE_AGREEMENT=yes \
-e NEO4J_AUTH=neo4j/password \              -- 设定用户密码，需要修改为符合安全要求的密码，最小8位连续字符
-v /app/neo4j/data:/data \                  -- 数据目录
-v /app/neo4j/logs:/logs \                  -- 日志目录
neo4j:5.21.2
```
#### 3.1.修改配置（此步骤可选）
- 配置文件目录为 /var/lib/neo4j/conf
- 可修改neo4j.conf中的缓存大小参数配置，如：server.memory.pagecache.size=2048M
- 修改后将整个conf目录进行容器映射

### 4.准备config文件
- 配置文件为环境变量RUN_ENV，默认为dev，所对应的configs/config.{RUN_ENV}.yaml
  - 比如：复制configs/config.test.yaml到configs/config.prod.yaml
- llm_base_url为大语言模型的服务地址
- dqs_base_url为DQS指标数据请求服务的根地址
  - 比如：大连测试环境为 http://10.4.59.50/miop/tools/dbService，则此处配置为http://10.4.59.50/miop/tools
- neo4j_config为neo4j数据库配置信息，namespace为本服务的命名空间
- m3e_base_url为m3e嵌入服务地址
- auth_base_url为身份认证服务地址
- ws_url是网页对话测试地址，配置为: ws://server_ip:port/chat_ws，此port为映射的主机port
- auth_mock是否本地模拟认证。开发环境为True，测试和生产环境为False
- chat_record_dbs将对话记录写入数据库配置名称的集合（多个数据库以半角逗号分隔）
- postgres_qin为对话管理配置的数据库，也用于保存对话记录
- oracle_emss为emss数据库配置信息，目前是对话记录表所对应的数据库
- postgres_dqs为DQS指标配置管理数据库，目的是将此数据库中的配置信息同步到知识库中
- config.base.yaml中的模型名称model_name: "Qwen-7B-Chat"，如果需要修改，同样要挂载此文件

### 5.在数据库中创建对话记录表（需要统计查询对话信息的数据库中），可选择oracle或postgres。如果此表已存在则忽略此步骤
```oracle
CREATE SEQUENCE SEQ_AI_CHAT_RECORDS
INCREMENT BY 1
START WITH 1
MAXVALUE 999999999999999
CACHE 20;

CREATE TABLE AI_CHAT_RECORDS (
ID NUMBER PRIMARY KEY,
SESSION_CODE VARCHAR2(255) NULL,
QUESTION VARCHAR2(4000) NOT NULL,
API_CODE VARCHAR2(255) NULL,
ANSWER VARCHAR2(4000) NULL,
ORG_NO VARCHAR2(16) NOT NULL,
RATING NUMBER NULL,
TIMESTAMP TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
VECTOR_DURATION FLOAT NULL,
LLM_DURATION FLOAT NULL
);
```

```postgres
CREATE TABLE "ai_chat_records" ( 
  "id" SERIAL,
  "session_code" VARCHAR(255) NULL,
  "question" TEXT NOT NULL,
  "api_code" VARCHAR(255) NULL,
  "answer" TEXT NULL,
  "org_no" VARCHAR(16) NOT NULL,
  "rating" INTEGER NULL,
  "timestamp" TIMESTAMP WITH TIME ZONE NULL DEFAULT now() ,
  "vector_duration" DOUBLE PRECISION NULL,
  "llm_duration" DOUBLE PRECISION NULL,
  CONSTRAINT "ai_chat_records2_pkey" PRIMARY KEY ("id")
);
```

### 6.运行服务容器
```
docker run -d --name magic-chat \
-p 27002:7002 \
-e RUN_ENV=prod \
-v /app/docker/magic-chat/configs:/app/src/configs \
-v /app/docker/magic-chat/datas/graph/entity_scene_test.csv:app/src/datas/graph/entity_scene_test.csv \
-v /app/docker/magic-chat/datas/graph/rela_scene-yz_test.csv:app/src/datas/graph/rela_scene-yz_test.csv \
neusoft/magic-chat:latest
```

### 7.配置场景及原子指标对应关系
#### 7.1 配置场景信息
配置文件为entity_scene_test.csv，文件格式如下所示

```
# scene_code场景编码, scene_name场景名字, scene_desc场景描述
powerOutage,停电情况,描述了停电情况的场景
```
#### 7.2 配置场景和原子指标对饮关系

配置文件为rela_scene-yz_test.csv，文件格式如下所示

```
# scene_code场景编码, yz_code原子指标编码
powerOutage,avg_poweroff_len_tg
powerOutage,avg_poweroff_len_cons
powerOutage,avg_poweroff_times
```

### 8.初始化
#### 8.1 同步知识库信息
- 通过下面请求，从指标管理数据库中同步指标配置数据，时间较长需要耐心等待
- 参数password为Neo4j的密码
- 初次运行时，需要参数scope=all，只同步指标配置数据时可去掉此参数
```
curl --request POST \
  --url http://server_ip:27001/graph/import \
  --header 'content-type: application/json' \
  --data '{
	"password": "password",
	"scope": "all"
}'
```

# V1.0.0
- main.py: AI对话服务主程序入口
  - 陕西辽宁封版
- main_mc_task.py: 【服务工单场景化】主程序入口
  - 陕西初版
  - 部署说明
```shell
docker run -d --name magic-chat-95598 \
  -p 27005:7003 \
  -e RUN_ENV=95598 \
  -v /app/docker/volume/magic-chat:/app/src \
  -v /app/docker/volume/magic-chat/main_mc_task.py:/app/src/main.py \
  neusoft/magic-chat:latest

```
  - 服务测试
```shell
curl --request POST \
  --url http://server_ip:27005/mc_task/create \
  --header 'content-type: application/json' \
  --data '{
      "task_type": "95598",
      "task_desc": "95598任务",
      "creator": "test",
      "task_ext": {
        "org_no": "61102",
        "handle_day": "2024-12-12"
      }
    }'
```

## 文件目录说明
```
├── README.MD                  # 项目说明文件
├── main.py                    # 小秦AI对话服务主程序入口
├── main_mc_task.py            # 陕西工单服务工单场景化主程序入口
├── configs/                   # 配置文件目录
│   ├── config.dev.yaml        # 开发环境配置文件
│   ├── config.test.yaml       # 测试环境配置文件
│   └── config.prod.yaml       # 生产环境配置文件
├── framework/                 # 系统框架
│   ├── algorithm/             # 算法相关
│   ├── chain/                 # 调用链相关
│   ├── embedding/             # 向量化相关
│   └── llm/                   # 大模型相关
├── transport/                 # 数据传输：数据库、websocket等
├── biz/                       # 业务模块
├── utils/                     # 工具方法
├── resources/                 # 项目资源
│   ├── models/                # 模型
│   ├── datas/                 # 数据存储
│   └── static/                # 静态网页资源
├── logs/                      # 运行日志
└── test                       # 测试代码
```

## 服务列表
- main.py           陕西小秦
- main_mc_task.py   陕西客服工单
- main_mi.py        在线demo - 费控助手 - 8002
- main_app.py       在线demo - 应用助手 - 8000
- main_md_cf.py     蒙东赤峰数字人
- main_doc_emb.py   问政策