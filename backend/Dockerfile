FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# 以非 root 用户运行：容器内只留下业务所需权限，避免依赖或图片处理被利用后
# 直接拿到整个持久化目录（数据库、备份、上传文件）的 root 权限。
# /data 是宿主机 bind mount，首次部署需在宿主机执行一次：
#   chown -R 10001:10001 backend/data
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

