FROM python:3.12-slim
WORKDIR /app
COPY plugins/map_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY plugins/map_engine/plugin.py .
EXPOSE 8091
CMD ["uvicorn", "plugin:app", "--host", "0.0.0.0", "--port", "8091"]
