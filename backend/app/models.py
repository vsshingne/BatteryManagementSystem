from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

BatteryStatus = Literal['NORMAL', 'WARNING', 'OVERVOLTAGE', 'UNDERVOLTAGE', 'OVERCURRENT', 'OVERTEMPERATURE', 'SENSOR_ERROR', 'COMMUNICATION_FAILURE']


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class Packet(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    voltage: float = Field(ge=0, le=1000)
    current: float = Field(ge=-10000, le=10000)
    temperature: float = Field(ge=-100, le=250)
    soc: float = Field(ge=0, le=100)
    battery_status: BatteryStatus
    charging: StrictBool
    operating_mode: Literal['Charging', 'Discharging', 'Idle'] | None = None
    runtime_minutes: float | None = Field(default=None, ge=0, le=1000000)

    @model_validator(mode='after')
    def coherent_mode(self):
        if self.operating_mode is not None and self.charging != (self.operating_mode == 'Charging'):
            raise ValueError('charging and operating_mode disagree')
        return self


class Measurement(Packet):
    timestamp: str
    source: Literal['demo', 'live']
    id: int | None = None


class Alert(BaseModel):
    id: int
    code: str
    severity: Literal['normal', 'warning', 'critical']
    description: str
    timestamp: str
    resolved_at: str | None
    acknowledged: bool
    source: Literal['demo', 'live']
