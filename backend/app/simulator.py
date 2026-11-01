"""Deterministic simulation only. Never called by the live serial path."""
import math
import random

from .models import Packet


class Simulator:
    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)
        self.tick = 0

    def next(self) -> Packet:
        phase = self.tick % 240
        mode = 'Discharging' if phase < 100 else 'Idle' if phase < 120 else 'Charging' if phase < 220 else 'Idle'
        soc = 78 - phase * .08 if phase < 100 else 70 if phase < 120 else 70 + (phase - 120) * .08 if phase < 220 else 78
        current = (.84 + math.sin(self.tick / 8) * .12) if mode == 'Discharging' else (-1.1 + math.sin(self.tick / 9) * .08) if mode == 'Charging' else 0
        temp = 30 + math.sin(self.tick / 25) * 2 + self.random.uniform(-.1, .1)
        status = 'OVERTEMPERATURE' if 85 <= phase < 95 else 'NORMAL'
        if status == 'OVERTEMPERATURE':
            temp = 46 + math.sin(self.tick)
        self.tick += 1
        return Packet(voltage=round(3.1 + soc * .0105 + self.random.uniform(-.008, .008), 3), current=round(current, 3), temperature=round(temp, 2), soc=round(soc, 2), battery_status=status, charging=mode == 'Charging', operating_mode=mode, runtime_minutes=round(soc * 2.4, 1) if mode == 'Discharging' else None)
