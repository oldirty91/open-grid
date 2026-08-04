FROM python:3.12-slim
WORKDIR /app
COPY sdk/python /opt/opengrid-sdk
RUN pip install --no-cache-dir /opt/opengrid-sdk
COPY plugins/adsb/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY plugins/adsb/plugin.py .
CMD ["python", "plugin.py"]
