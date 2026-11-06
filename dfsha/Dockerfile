FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto proto
COPY dfsha dfsha
RUN python -m grpc_tools.protoc -Iproto --python_out=dfsha --grpc_python_out=dfsha proto/dfsha.proto \
 && sed -i 's/^import dfsha_pb2/from . import dfsha_pb2/' dfsha/dfsha_pb2_grpc.py
ENV PYTHONUNBUFFERED=1
