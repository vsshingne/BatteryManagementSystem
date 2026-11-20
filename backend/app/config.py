from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT=Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=ROOT/'.env',extra='ignore')
    mode: Literal['demo','live']='demo'
    stale_after_seconds: float=Field(default=10,gt=0)
    database_path: str=str(ROOT/'backend'/'data'/'esu.sqlite3')
    frontend_dist: str=str(ROOT/'frontend'/'dist')
    persist_demo: bool=False
    demo_interval_seconds: float=Field(default=1,ge=.05)
    demo_seed: int=42
    ingest_token: str|None=None
