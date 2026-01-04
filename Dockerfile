FROM 10.0.87.150:15001/python:3.10.17-slim-bullseye
ENV TZ=Asia/Shanghai
RUN mkdir -p /app
WORKDIR /app
COPY requirements.txt requirements.txt

# RUN pip config set global.index-url https://pypi.org/simple
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# RUN pip install -r requirements.txt
RUN pip install --proxy="dl-proxy.neusoft.com:8080" -r requirements.txt

#
## for oracledb
#RUN apt-get update && apt-get install -y libaio-dev
#COPY ./instantclient_11_2 /app/instantclient_11_2
#COPY ./instantclient_11_2/libclntsh.so.11.1 /app/instantclient_11_2/libclntsh.so
#COPY ./instantclient_11_2/libnnz11.so /usr/lib/libnnz11.so
#ENV ORACLE_HOME=/app/instantclient_11_2
#ENV PATH=$ORACLE_HOME:$PATH


# FROM rebuilt/base-kg-rag:latest
# RUN mkdir -p /app/src
# WORKDIR /app/src
# COPY . .
# ENTRYPOINT ["python", "main.py"]
