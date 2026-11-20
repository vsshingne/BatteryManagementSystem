from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

BatteryStatus = Literal['NORMAL', 'WARNING', 'OVERVOLTAGE', 'UNDERVOLTAGE', 'OVERCURRENT', 'OVERTEMPERATURE', 'SENSOR_ERROR', 'COMMUNICATION_FAILURE']
BatteryId = Literal['BATTERY_1', 'BATTERY_2']

class Packet(BaseModel):
    """Internal demo measurement shape; never used by the live ingest API."""
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    voltage: float
    current: float
    temperature: float
    soc: float
    battery_status: BatteryStatus
    charging: bool
    operating_mode: Literal['Charging','Discharging','Idle'] | None = None
    runtime_minutes: float | None = None

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

class BatteryPacket(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    battery_id: BatteryId
    voltage: float = Field(ge=0, le=1000)
    current: float = Field(ge=-10000, le=10000)
    temperature: float = Field(ge=-100, le=250)
    soc: float = Field(ge=0, le=100)
    battery_status: BatteryStatus = 'NORMAL'
    charging: StrictBool | None = None
    operating_mode: Literal['Charging', 'Discharging', 'Idle'] | None = None
    runtime_minutes: float | None = Field(default=None, ge=0, le=1000000)

    @model_validator(mode='before')
    @classmethod
    def normalize_example_status(cls, value):
        # Support the documented compact wire example: status is the operating mode.
        if isinstance(value, dict) and 'status' in value:
            value=dict(value)
            status=value.pop('status')
            if 'operating_mode' not in value:
                modes={'charging':'Charging','discharging':'Discharging','idle':'Idle'}
                if status not in modes: raise ValueError('status must be charging, discharging, or idle')
                value['operating_mode']=modes[status]
        return value

    @model_validator(mode='after')
    def coherent_mode(self):
        if self.operating_mode and self.charging is not None and self.charging != (self.operating_mode == 'Charging'):
            raise ValueError('charging and operating_mode disagree')
        return self

class IngestPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    device_id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$')
    timestamp: datetime | None = Field(default=None, strict=False)
    batteries: list[BatteryPacket] = Field(min_length=1, max_length=2)

    @field_validator('timestamp')
    @classmethod
    def timestamp_has_timezone(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('timestamp must include a timezone')
        return value

    @model_validator(mode='after')
    def unique_batteries(self):
        ids = [battery.battery_id for battery in self.batteries]
        if len(ids) != len(set(ids)):
            raise ValueError('battery_id values must be unique within a payload')
        return self

class Measurement(BatteryPacket):
    battery_status: BatteryStatus
    charging: bool
    operating_mode: str
    timestamp: str
    source: Literal['demo', 'live']
    device_id: str | None = None
    id: int | None = None

class Alert(BaseModel):
    id: int
    battery_id: BatteryId | None
    code: str
    severity: Literal['normal', 'warning', 'critical']
    description: str
    timestamp: str
    resolved_at: str | None
    acknowledged: bool
    source: Literal['demo', 'live']
