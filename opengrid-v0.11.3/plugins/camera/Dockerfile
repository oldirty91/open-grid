FROM python:3.12-slim
WORKDIR /app
COPY sdk/python /sdk
RUN pip install --no-cache-dir /sdk
COPY plugins/camera/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY plugins/camera/plugin.py .
CMD ["python","plugin.py"]
