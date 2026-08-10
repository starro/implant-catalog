from drheri_pipeline.ui import runner_exec as R


def test_exec_cmd_shape():
    cmd = R.exec_cmd(7, "/engine/run_7/src.pdf", "BEGO", "12-26", 200, 0.6)
    assert cmd[:3] == ["docker", "exec", R.CONTAINER]
    # inner command is composed as a single "bash -lc <script>" element, not split tokens
    joined = " ".join(cmd)
    assert "-m" in joined and "drheri_pipeline.labeling.cli" in joined
    assert "--pdf" in joined and "/engine/run_7/src.pdf" in joined
    assert "--brand" in joined and "BEGO" in joined
    assert "--pages" in joined and "12-26" in joined
    # DATA_ROOT 은 런별 tmp 로
    assert "DATA_ROOT=/engine/run_7" in joined


def test_exec_cmd_omits_empty_pages():
    cmd = R.exec_cmd(7, "http://x/a.pdf", "BEGO", "", 200, 0.6)
    assert "--pages" not in " ".join(cmd)


def test_cp_and_rm_cmd(monkeypatch, tmp_path):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    cp = R.cp_cmd(7)
    assert cp[:2] == ["docker", "cp"]
    assert f"{R.CONTAINER}:/engine/run_7/." in cp
    assert str(tmp_path) in " ".join(cp)
    rm = R.rm_cmd(7)
    assert rm[:3] == ["docker", "exec", R.CONTAINER] and "rm" in rm and "/engine/run_7" in " ".join(rm)
