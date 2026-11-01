"""Bounded JSONL framing; timeout fragments are retained until a newline arrives."""
import asyncio
import json
import logging

import serial

from .models import Packet

logger = logging.getLogger(__name__)


def parse_packet(line: bytes, protocol: str = 'jsonl') -> Packet:
    if protocol != 'jsonl':
        raise ValueError(f'Unsupported protocol: {protocol}')
    return Packet.model_validate(json.loads(line.decode('utf-8')))


class LineFramer:
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.buffer = bytearray()
        self.dropping = False

    def feed(self, chunk: bytes):
        for byte in chunk:
            if byte == 10:
                if not self.dropping and self.buffer:
                    yield bytes(self.buffer)
                self.buffer.clear()
                self.dropping = False
            elif not self.dropping:
                self.buffer.append(byte)
                if len(self.buffer) > self.max_bytes:
                    self.buffer.clear()
                    self.dropping = True
                    yield None  # one rejected packet per oversized line


async def read_serial(settings, on_packet, on_port, on_error, serial_factory=serial.Serial):
    while True:
        port = None
        try:
            port = serial_factory(port=settings.serial_port, baudrate=settings.baud_rate, timeout=settings.serial_timeout)
            on_port(True)
            framer = LineFramer(settings.max_packet_bytes)
            while True:
                chunk = await asyncio.to_thread(port.read, min(max(port.in_waiting, 1), settings.max_packet_bytes))
                for line in framer.feed(chunk):
                    try:
                        if line is None:
                            raise ValueError('Packet exceeds MAX_PACKET_BYTES')
                        packet = parse_packet(line, settings.protocol)
                    except (ValueError, UnicodeError) as exc:
                        on_error(f'Invalid UART packet: {type(exc).__name__}', True)
                        continue
                    await on_packet(packet)
        except (serial.SerialException, OSError) as exc:
            on_error(f'Serial unavailable: {exc}', False)
        finally:
            on_port(False)
            if port is not None:
                port.close()
        await asyncio.sleep(settings.reconnect_seconds)
