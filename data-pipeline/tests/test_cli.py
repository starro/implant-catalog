from drheri_pipeline.labeling import cli
from drheri_pipeline.labeling.runner import RunSummary


def test_cli_parses_and_invokes_runner(monkeypatch):
    got = {}
    def fake_run(pdf_url, brand, pages="", **kw):
        got.update(pdf=pdf_url, brand=brand, pages=pages, kw=kw)
        return RunSummary(pdf_url, brand, 1, 1, 2, 0)
    monkeypatch.setattr(cli, "label_catalog", fake_run)
    rc = cli.main(["--pdf", "/nas/BEGO/x.pdf", "--brand", "BEGO", "--pages", "12-26",
                   "--conf-min", "0.5"])
    assert rc == 0
    assert got["pdf"] == "/nas/BEGO/x.pdf" and got["brand"] == "BEGO"
    assert got["pages"] == "12-26" and got["kw"]["conf_min"] == 0.5


def test_cli_requires_pdf_and_brand():
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["--pdf", "x.pdf"])   # brand 누락
