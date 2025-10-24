FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 50051 9000
CMD bash -lc "python tools/mlx_runtime.py & python core/server.py"
