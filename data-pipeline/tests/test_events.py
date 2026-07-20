import asyncio
import json

import pytest

from drheri_pipeline.ui.events import Broadcaster


@pytest.mark.asyncio
async def test_publish_reaches_all_subscribers():
    b = Broadcaster()
    q1, q2 = b.subscribe(), b.subscribe()
    b.publish("run.finished", {"run_id": 7})
    for q in (q1, q2):
        evt = await asyncio.wait_for(q.get(), timeout=1)
        assert evt["event"] == "run.finished"
        assert evt["payload"] == {"run_id": 7}


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    b = Broadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    b.publish("run.finished", {})
    assert q.empty()


@pytest.mark.asyncio
async def test_sse_stream_formats_frames():
    b = Broadcaster()
    q = b.subscribe()
    b.publish("sync.finished", {"kept": 2})
    stream = b.sse_stream(q)
    frame = await asyncio.wait_for(stream.__anext__(), timeout=1)
    assert frame.startswith("event: sync.finished\ndata: ")
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {"kept": 2}
    assert frame.endswith("\n\n")


@pytest.mark.asyncio
async def test_full_subscriber_queue_does_not_block_others():
    """브리프의 publish() 는 큐가 가득 찬 느린 구독자를 QueueFull 로 건너뛴다.
    이 동작(다른 구독자가 막히지 않음, 예외가 새지 않음)을 실제로 검증한다."""
    from drheri_pipeline.ui.events import MAX_QUEUE

    b = Broadcaster()
    slow, fast = b.subscribe(), b.subscribe()
    for _ in range(MAX_QUEUE):
        slow.put_nowait({"event": "filler", "payload": {}})
    assert slow.full()

    b.publish("run.finished", {"run_id": 1})  # slow 큐는 가득 찼어도 예외 없이 넘어가야 한다

    assert slow.full()  # 느린 구독자의 큐는 그대로 가득 찬 상태(새 이벤트는 드롭됨)
    evt = await asyncio.wait_for(fast.get(), timeout=1)  # 빠른 구독자는 정상 수신(막히지 않음)
    assert evt["event"] == "run.finished"
    assert evt["payload"] == {"run_id": 1}
