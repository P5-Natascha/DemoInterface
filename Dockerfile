FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=8080 ADMIN_PORT=8081 DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py index.html admin.html ./
RUN useradd --system app && mkdir /data && chown app /data
USER app
EXPOSE 8080 8081
CMD ["python", "server.py"]
