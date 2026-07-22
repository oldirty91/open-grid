from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://opengrid:opengrid@localhost:5432/opengrid"
    nats_url: str = "nats://localhost:4222"
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    fusion_gate_m: float = 250.0
    fusion_max_age_s: int = 30
    minio_endpoint: str = "localhost:9002"
    minio_access_key: str = "opengrid"
    minio_secret_key: str = "opengrid-dev-password"
    minio_secure: bool = False
    artifact_bucket: str = "opengrid-artifacts"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

settings = Settings()
