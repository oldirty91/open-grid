import hashlib, io
from minio import Minio
from app.config import settings
client=Minio(settings.minio_endpoint,access_key=settings.minio_access_key,secret_key=settings.minio_secret_key,secure=settings.minio_secure)
def ensure_bucket():
    if not client.bucket_exists(settings.artifact_bucket): client.make_bucket(settings.artifact_bucket)
def put_bytes(name,data,content_type):
    digest=hashlib.sha256(data).hexdigest();client.put_object(settings.artifact_bucket,name,io.BytesIO(data),len(data),content_type=content_type);return len(data),digest
def get_object(name): return client.get_object(settings.artifact_bucket,name)
