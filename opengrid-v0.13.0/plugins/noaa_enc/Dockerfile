FROM python:3.12-slim
WORKDIR /app
COPY plugins/noaa_enc/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY plugins/noaa_enc/plugin.py .
EXPOSE 8090
CMD ["uvicorn", "plugin:app", "--host", "0.0.0.0", "--port", "8090"]
