import json
import os
import sys

from helpers import supercias_detached_launch


def test_launcher_restores_the_environment_logs_and_runs_the_build(monkeypatch, tmp_path):
    env_file = tmp_path / "build.env.json"
    log_file = tmp_path / "build.log"
    env_file.write_text(json.dumps({"ECUADOR_MCP_DATA_DIR": "D:/datos"}), encoding="utf-8")
    monkeypatch.delenv("ECUADOR_MCP_DATA_DIR", raising=False)
    ran: list[tuple[str, str]] = []

    def fake_run_module(name, run_name):
        ran.append((name, run_name))
        print("Descargando bi_ranking.csv...")  # lands in the log, not the console

    monkeypatch.setattr(supercias_detached_launch.runpy, "run_module", fake_run_module)
    monkeypatch.setattr(sys, "stdout", sys.stdout)  # restored after main() swaps it
    monkeypatch.setattr(sys, "stderr", sys.stderr)

    supercias_detached_launch.main([str(env_file), str(log_file)])
    sys.stdout.flush()

    assert os.environ["ECUADOR_MCP_DATA_DIR"] == "D:/datos"
    assert not env_file.exists()  # it can hold proxy credentials
    assert ran == [("helpers.supercias_financials_build", "__main__")]
    assert "Descargando bi_ranking.csv..." in log_file.read_text(encoding="utf-8")
    monkeypatch.delenv("ECUADOR_MCP_DATA_DIR")


def test_launcher_deletes_the_env_file_even_when_it_is_unreadable_json(
    monkeypatch, tmp_path
):
    env_file = tmp_path / "build.env.json"
    env_file.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)

    try:
        supercias_detached_launch.main([str(env_file), str(tmp_path / "build.log")])
    except ValueError:
        pass

    assert not env_file.exists()
