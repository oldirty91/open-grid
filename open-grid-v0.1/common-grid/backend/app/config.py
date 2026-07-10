from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    database_url:str='postgresql+asyncpg://commongrid:commongrid@localhost:5432/commongrid'
    nats_url:str='nats://localhost:4222'
    cors_origins:str='http://localhost:8080,http://localhost:5173'
    fusion_gate_m:float=250.0
    fusion_max_age_s:int=30
    model_config=SettingsConfigDict(env_file='.env',extra='ignore')
    @property
    def cors_origin_list(self): return [x.strip() for x in self.cors_origins.split(',') if x.strip()]
settings=Settings()
