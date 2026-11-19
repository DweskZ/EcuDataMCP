"""Windows build launch through WMI (helpers/supercias_financials._spawn_via_wmi).

A build started the plain detached way stays inside the job its parent runs
in, and dies when a client tears that job down; a process WMI creates does
not. The real-process test at the bottom reproduces that in a job of its own.
"""

import json
import subprocess
import sys
import time

import pytest

from helpers import supercias_financials


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        supercias_financials, "DB_PATH", tmp_path / "data" / "financials.sqlite3"
    )
    monkeypatch.setattr(supercias_financials, "_build_process", None)
    monkeypatch.setattr(supercias_financials, "_build_started_at", None)


def _wmi_result(returncode=0, stdout="4321\n", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _stub_wmi(monkeypatch, tmp_path, result):
    """Pretend PowerShell exists and answers `result`; return the run() calls."""
    calls: list[dict] = []

    def fake_run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(supercias_financials.shutil, "which", lambda name: "powershell.exe")
    monkeypatch.setattr(supercias_financials.subprocess, "run", fake_run)
    monkeypatch.setattr(supercias_financials, "_process_creation_time", lambda pid: 111)
    return calls, tmp_path / "supercias_build.log"


def test_wmi_launch_returns_the_pid_and_hands_over_only_the_build_environment(
    monkeypatch, tmp_path
):
    calls, log_path = _stub_wmi(monkeypatch, tmp_path, _wmi_result())
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", "D:/datos")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    monkeypatch.setenv("UNRELATED_SECRET", "no")

    build = supercias_financials._spawn_via_wmi(log_path)

    assert isinstance(build, supercias_financials._WmiBuild) and build.pid == 4321
    env = json.loads((tmp_path / "supercias_build.env.json").read_text(encoding="utf-8"))
    assert env["ECUADOR_MCP_DATA_DIR"] == "D:/datos"
    assert env["HTTPS_PROXY"] == "http://proxy:3128"
    assert "UNRELATED_SECRET" not in env
    command = calls[0]["env"]["ECUADOR_MCP_WMI_COMMAND"]
    assert "-m helpers.supercias_detached_launch" in command
    assert str(log_path) in command
    assert calls[0]["env"]["ECUADOR_MCP_WMI_CWD"] == str(supercias_financials._PACKAGE_ROOT)


@pytest.mark.parametrize(
    "result",
    [
        _wmi_result(returncode=1, stdout="", stderr="Access denied"),
        _wmi_result(stdout="not a pid"),
        subprocess.TimeoutExpired("powershell", 30),
        OSError("powershell vanished"),
    ],
)
def test_wmi_launch_failure_returns_none_and_leaves_no_env_file(
    monkeypatch, tmp_path, result
):
    _, log_path = _stub_wmi(monkeypatch, tmp_path, result)

    assert supercias_financials._spawn_via_wmi(log_path) is None
    assert not (tmp_path / "supercias_build.env.json").exists()


def test_wmi_launch_without_powershell_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(supercias_financials.shutil, "which", lambda name: None)

    assert supercias_financials._spawn_via_wmi(tmp_path / "supercias_build.log") is None


def test_windows_build_launch_prefers_wmi_and_skips_popen(monkeypatch):
    popen_calls: list = []
    wmi = supercias_financials._WmiBuild.__new__(supercias_financials._WmiBuild)
    wmi.pid, wmi.returncode, wmi._created = 777, None, 1
    monkeypatch.setattr(supercias_financials, "_spawn_via_wmi", lambda log_path: wmi)
    monkeypatch.setattr(
        supercias_financials.subprocess, "Popen", lambda *a, **k: popen_calls.append(a)
    )
    monkeypatch.setattr(supercias_financials.sys, "platform", "win32")

    supercias_financials._trigger_background_build()

    assert popen_calls == []
    assert supercias_financials._build_process is wmi


def test_wmi_build_tracks_its_process_by_pid_and_creation_time(monkeypatch):
    alive = {"yes": True}
    created = {"time": 111}
    monkeypatch.setattr(supercias_financials, "_pid_alive", lambda pid: alive["yes"])
    monkeypatch.setattr(
        supercias_financials, "_process_creation_time", lambda pid: created["time"]
    )
    build = supercias_financials._WmiBuild(900)

    assert build.poll() is None
    created["time"] = 222  # the PID now belongs to a different process
    assert build.poll() == -1
    created["time"] = 111
    assert build.poll() == -1  # and an ended build stays ended


def test_wmi_build_wait_times_out_while_alive_and_returns_once_gone(monkeypatch):
    alive = {"yes": True}
    monkeypatch.setattr(supercias_financials, "_pid_alive", lambda pid: alive["yes"])
    monkeypatch.setattr(supercias_financials, "_process_creation_time", lambda pid: 5)
    build = supercias_financials._WmiBuild(901)

    with pytest.raises(subprocess.TimeoutExpired):
        build.wait(timeout=0.3)
    alive["yes"] = False
    assert build.wait(timeout=1) == -1


def test_wmi_build_kill_never_touches_a_reused_pid(monkeypatch):
    runs: list[list[str]] = []
    created = {"time": 1}
    monkeypatch.setattr(supercias_financials, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        supercias_financials, "_process_creation_time", lambda pid: created["time"]
    )
    monkeypatch.setattr(
        supercias_financials.subprocess, "run", lambda args, **kw: runs.append(args)
    )
    build = supercias_financials._WmiBuild(902)

    created["time"] = 2  # another process took the PID
    build.kill()
    assert runs == []

    other = supercias_financials._WmiBuild(903)
    other.kill()  # still the same process: taskkill runs
    assert runs == [["taskkill", "/PID", "903", "/F"]]


_HELPER_CODE = """
import json, pathlib, subprocess, sys, time
from helpers import supercias_financials as sf

here = pathlib.Path(sys.argv[1])
while not (here / "go").exists():
    time.sleep(0.1)
py = getattr(sys, "_base_executable", sys.executable)
plain = subprocess.Popen(
    [py, str(here / "sleeper.py"), "unused"],
    creationflags=0x8 | 0x200, stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
sf._DETACHED_LAUNCH_MODULE = "tests.wmi_launch_stub"
wmi = sf._spawn_via_wmi(here / "supercias_build.log")
(here / "pids.json").write_text(json.dumps({"plain": plain.pid, "wmi": wmi.pid}))
time.sleep(120)
"""


@pytest.mark.skipif(sys.platform != "win32", reason="job objects and WMI are Windows-only")
def test_wmi_started_build_survives_its_parents_job_and_a_plain_detached_one_does_not(
    tmp_path,
):
    """The failure this launch path exists for, reproduced in a job of our own.

    The helper process runs inside a job that forbids breakaway, like the
    shell of a client that tears its session down. It starts one sleeper the
    old way (detached) and one through `_spawn_via_wmi` pointed at a sleeper
    module; terminating the job must take the first and spare the second.
    """
    import ctypes
    from ctypes import wintypes

    (tmp_path / "sleeper.py").write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    job = k32.CreateJobObjectW(None, None)  # no limits: breakaway is not permitted
    helper = subprocess.Popen(
        [sys.executable, "-c", _HELPER_CODE, str(tmp_path)],
        cwd=supercias_financials._PACKAGE_ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pids: dict[str, int] = {}
    try:
        assert k32.AssignProcessToJobObject(job, ctypes.c_void_p(int(helper._handle)))
        (tmp_path / "go").write_text("")
        deadline = time.time() + 60
        while not (tmp_path / "pids.json").exists() and time.time() < deadline:
            time.sleep(0.3)
        pids = json.loads((tmp_path / "pids.json").read_text())
        assert supercias_financials._pid_alive(pids["plain"])
        assert supercias_financials._pid_alive(pids["wmi"])

        k32.TerminateJobObject(job, 1)
        time.sleep(3)

        assert not supercias_financials._pid_alive(pids["plain"])
        assert supercias_financials._pid_alive(pids["wmi"])
    finally:
        helper.kill()
        for pid in pids.values():
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, check=False,
            )
