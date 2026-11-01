import asyncio

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, payload: dict):
        async def send(client):
            try:
                await asyncio.wait_for(client.send_json(payload), timeout=1)
            except Exception:
                self.clients.discard(client)
                try:
                    await asyncio.wait_for(client.close(code=1011), timeout=.2)
                except Exception:
                    pass
        await asyncio.gather(*(send(c) for c in tuple(self.clients)))
