"""SSE 브로드캐스터 — 서버에서 브라우저로 이벤트를 민다(폴링 대체).

이벤트: run.finished, sync.finished, export.finished
"""
from __future__ import annotations

import asyncio
import json

MAX_QUEUE = 100


class Broadcaster:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: str, payload: dict) -> None:
        """느린 구독자 때문에 서버가 막히지 않도록 큐가 차면 그 구독자는 건너뛴다."""
        for q in list(self._subs):
            try:
                q.put_nowait({"event": event, "payload": payload})
            except asyncio.QueueFull:
                continue

    async def sse_stream(self, q: asyncio.Queue):
        """SSE 프레임 생성기. 25초마다 주석 프레임으로 연결을 살려둔다."""
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield (f"event: {evt['event']}\n"
                       f"data: {json.dumps(evt['payload'], ensure_ascii=False)}\n\n")
        finally:
            self.unsubscribe(q)


broadcaster = Broadcaster()
