from drheri_pipeline import sensors

CFG = {"ops": {"catalog_pdf_images": {"config": {
    "document_id": 3, "ui_run_id": 11, "pdf_url": "https://ex.com/a.pdf"}}}}


def test_hook_payload_extracts_identifiers():
    p = sensors.hook_payload(CFG, "SUCCESS", None)
    assert p == {"ui_run_id": 11, "document_id": 3, "status": "SUCCESS",
                 "extracted": 0, "error": None}


def test_hook_payload_none_when_not_from_ui():
    cfg = {"ops": {"catalog_pdf_images": {"config": {"document_id": 0, "ui_run_id": 0}}}}
    assert sensors.hook_payload(cfg, "SUCCESS", None) is None
    assert sensors.hook_payload({}, "SUCCESS", None) is None


def test_post_hook_sends_token_header(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers)
        return Resp()

    monkeypatch.setattr(sensors.httpx, "post", fake_post)
    assert sensors.post_hook({"ui_run_id": 11, "status": "SUCCESS"}) is True
    assert sent["headers"]["X-Hook-Token"] == sensors.HOOK_TOKEN
    assert sent["url"].endswith("/api/hooks/run-finished")


def test_post_hook_returns_false_on_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(sensors.httpx, "post", boom)
    assert sensors.post_hook({"ui_run_id": 1}) is False


class _FakeLog:
    def info(self, msg):
        pass


class _FakeRun:
    def __init__(self, run_config):
        self.run_config = run_config


class _FakeContext:
    """RunStatusSensorContext 를 흉내낸 최소 더미 — _notify 가 실제로 쓰는 속성만 갖는다."""

    def __init__(self, run_config, failure_event=None):
        self.dagster_run = _FakeRun(run_config)
        self.log = _FakeLog()
        self.failure_event = failure_event


def test_notify_skips_post_hook_when_not_from_ui(monkeypatch):
    """hook_payload() 가 None 을 반환하는 것만으로는 훅이 실제로 안 나가는지 보장 못 한다.

    _notify() 가 이 None 을 보고 실제로 post_hook 호출을 건너뛰는지까지 확인한다
    (센서가 UI 미경유 런(ui_run_id=0)에는 훅을 보내지 않아야 한다 — 오케스트레이터 지시 품질기준).
    """
    calls = []
    monkeypatch.setattr(sensors, "post_hook", lambda p: calls.append(p) or True)
    cfg = {"ops": {"catalog_pdf_images": {"config": {"document_id": 0, "ui_run_id": 0}}}}

    sensors._notify(_FakeContext(cfg), "SUCCESS", None)

    assert calls == []


def test_notify_calls_post_hook_when_from_ui(monkeypatch):
    """대조군: ui_run_id 가 있으면 실제로 post_hook 이 호출되는지 확인한다."""
    calls = []
    monkeypatch.setattr(sensors, "post_hook", lambda p: calls.append(p) or True)
    cfg = {"ops": {"catalog_pdf_images": {"config": {"document_id": 3, "ui_run_id": 11}}}}

    sensors._notify(_FakeContext(cfg), "SUCCESS", None)

    assert calls == [{"ui_run_id": 11, "document_id": 3, "status": "SUCCESS",
                      "extracted": 0, "error": None}]


def test_sensors_are_registered_as_running():
    """센서가 STOPPED 로 등록되면 사람이 Dagster UI 에서 켜기 전까지 완료 푸시가 죽는다.

    개발서버 배포에서 실제로 겪은 문제라, 기본 상태를 회귀 테스트로 고정한다.
    """
    from dagster import DefaultSensorStatus

    from drheri_pipeline.definitions import defs

    states = {s.name: s.default_status for s in defs.sensors}
    assert states == {"on_run_success": DefaultSensorStatus.RUNNING,
                      "on_run_failure": DefaultSensorStatus.RUNNING,
                      "on_run_canceled": DefaultSensorStatus.RUNNING}
