from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    mode: Literal['demo', 'live'] = 'demo'
    serial_port: str = '/dev/ttyUSB0'
    baud_rate: int = Field(default=115200, gt=0)
    protocol: Literal['jsonl'] = 'jsonl'
    serial_timeout: float = Field(default=0.5, gt=0, le=5)
    reconnect_seconds: float = Field(default=2, gt=0, le=60)
    stale_after_seconds: float = Field(default=5, gt=0)
    max_packet_bytes: int = Field(default=4096, ge=256, le=65536)
    database_path: str = str(ROOT / 'backend' / 'data' / 'esu.sqlite3')
    frontend_dist: str = str(ROOT / 'frontend' / 'dist')
    persist_demo: bool = False
    demo_interval_seconds: float = Field(default=1, ge=0.05)
    demo_seed: int = 42
    # Optional gateway-only notifications; never protection controls.
    voltage_high: float | None = None
    voltage_low: float | None = None
    current_high: float | None = Field(default=None, gt=0)
    temperature_high: float | None = None

    @model_validator(mode='after')
    def thresholds_ordered(self):
        if self.voltage_low is not None and self.voltage_high is not None and self.voltage_low >= self.voltage_high:
            raise ValueError('VOLTAGE_LOW must be less than VOLTAGE_HIGH')
        return self
