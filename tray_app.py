#!/usr/bin/env python3
"""
MailMindHub Tray App (Plan A).
Starts/controls email daemon + Web UI, with a system tray menu.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DAEMON_LOG = ROOT / "daemon.log"
WEBUI_LOG = ROOT / "webui.log"
DAEMON_PID = ROOT / "daemon.pid"
WEBUI_PID = ROOT / "webui.pid"
WEBUI_PID_META = ROOT / "webui.pid.meta"


def read_env_file() -> dict[str, str]:
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    with ENV_FILE.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if value and value[0] in ('"', "'"):
                q = value[0]
                end = value.find(q, 1)
                value = value[1:end] if end != -1 else value[1:]
            else:
                value = value.split("#")[0].strip()
            result[key] = value
    return result


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _safe_kill(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        pass


class ManagedProcess:
    def __init__(
        self,
        name: str,
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        log_path: Path,
        pid_file: Path,
        meta_file: Path | None = None,
    ) -> None:
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.log_path = log_path
        self.pid_file = pid_file
        self.meta_file = meta_file
        self.proc: subprocess.Popen | None = None
        self.external_pid: int | None = None
        self._log_handle = None

    def _read_pid_file(self) -> int | None:
        if not self.pid_file.exists():
            return None
        try:
            text = self.pid_file.read_text().strip()
            return int(text) if text else None
        except Exception:
            return None

    def _write_pid_file(self, pid: int) -> None:
        try:
            self.pid_file.write_text(str(pid))
        except Exception:
            pass

    def _clear_pid_file(self) -> None:
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass
        if self.meta_file:
            try:
                if self.meta_file.exists():
                    self.meta_file.unlink()
            except Exception:
                pass

    def running(self) -> bool:
        if self.proc and self.proc.poll() is None:
            return True
        if self.external_pid and is_pid_running(self.external_pid):
            return True
        pid = self._read_pid_file()
        if pid and is_pid_running(pid):
            self.external_pid = pid
            return True
        # Stale external pid or stale pid file
        self.external_pid = None
        return False

    def start(self) -> bool:
        if self.running():
            return False
        existing_pid = self._read_pid_file()
        if existing_pid and is_pid_running(existing_pid):
            self.external_pid = existing_pid
            return False

        self._log_handle = self.log_path.open("a", encoding="utf-8")
        try:
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=str(self.cwd),
                env=self.env,
                stdout=self._log_handle,
                stderr=self._log_handle,
            )
        except Exception:
            if self._log_handle:
                self._log_handle.close()
                self._log_handle = None
            raise

        self._write_pid_file(self.proc.pid)
        return True

    def stop(self, timeout: float = 8.0) -> bool:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if hasattr(signal, "SIGKILL"):
                    self.proc.kill()
            self.proc = None
        elif self.external_pid:
            _safe_kill(self.external_pid, signal.SIGTERM)
            # Give it a moment, then force kill if still running
            time.sleep(0.5)
            if is_pid_running(self.external_pid) and hasattr(signal, "SIGKILL"):
                _safe_kill(self.external_pid, signal.SIGKILL)
            self.external_pid = None

        self._clear_pid_file()
        if self._log_handle:
            try:
                self._log_handle.close()
            finally:
                self._log_handle = None
        return True

    def restart(self) -> None:
        self.stop()
        time.sleep(0.5)
        self.start()


class ServiceManager:
    def __init__(self) -> None:
        env_file = read_env_file()
        os.environ.update(env_file)

        mailbox = os.environ.get("MAILBOX", "").strip()
        ai = os.environ.get("AI", "").strip()
        mode = os.environ.get("MODE", "idle").strip().lower()

        webui_host = os.environ.get("WEBUI_HOST", "0.0.0.0").strip() or "0.0.0.0"
        webui_port = int(os.environ.get("WEBUI_PORT", "8000"))

        self.webui_url = self._make_webui_url(webui_host, webui_port)

        daemon_cmd = [sys.executable, str(ROOT / "email_daemon.py")]
        if mailbox:
            daemon_cmd += ["--mailbox", mailbox]
        if ai:
            daemon_cmd += ["--ai", ai]
        if mode == "poll":
            daemon_cmd += ["--poll"]

        webui_cmd = [
            sys.executable, "-m", "webui.server",
            "--host", webui_host,
            "--port", str(webui_port),
        ]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        self.daemon = ManagedProcess(
            "daemon",
            daemon_cmd,
            cwd=ROOT,
            env=env,
            log_path=DAEMON_LOG,
            pid_file=DAEMON_PID,
        )
        self.webui = ManagedProcess(
            "webui",
            webui_cmd,
            cwd=ROOT,
            env=env,
            log_path=WEBUI_LOG,
            pid_file=WEBUI_PID,
            meta_file=WEBUI_PID_META,
        )
        self.webui_meta = f"WEBUI_HOST={webui_host} WEBUI_PORT={webui_port}"

    def _make_webui_url(self, host: str, port: int) -> str:
        if host in ("0.0.0.0", "127.0.0.1", "localhost", ""):
            host = "localhost"
        return f"http://{host}:{port}"

    def start_all(self) -> None:
        self.daemon.start()
        if self.webui.start():
            try:
                WEBUI_PID_META.write_text(self.webui_meta)
            except Exception:
                pass

    def stop_all(self) -> None:
        self.webui.stop()
        self.daemon.stop()

    def restart_all(self) -> None:
        self.stop_all()
        time.sleep(0.8)
        self.start_all()

    def running_any(self) -> bool:
        return self.daemon.running() or self.webui.running()


def build_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (20, 43, 72, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((6, 6, size - 6, size - 6), radius=12, fill=(29, 124, 111, 255))
    font = ImageFont.load_default()
    text = "M"
    tw, th = draw.textsize(text, font=font)
    draw.text(((size - tw) / 2, (size - th) / 2 - 2), text, fill=(255, 255, 255, 255), font=font)
    return img


def main() -> None:
    manager = ServiceManager()
    manager.start_all()

    def on_start(_icon, _item):
        manager.start_all()

    def on_restart(_icon, _item):
        manager.restart_all()

    def on_stop(_icon, _item):
        manager.stop_all()

    def on_open(_icon, _item):
        webbrowser.open(manager.webui_url, new=2)

    def on_quit(icon, _item):
        manager.stop_all()
        icon.stop()

    icon = pystray.Icon(
        "MailMindHub",
        build_icon(),
        "MailMindHub",
        menu=pystray.Menu(
            pystray.MenuItem("Start Service", on_start, enabled=lambda _i: not manager.running_any()),
            pystray.MenuItem("Restart", on_restart, enabled=lambda _i: manager.running_any()),
            pystray.MenuItem("Stop", on_stop, enabled=lambda _i: manager.running_any()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Console", on_open),
            pystray.MenuItem("Quit", on_quit),
        ),
    )

    # Background watcher to clear stale pid files if children die.
    stop_evt = threading.Event()

    def watcher():
        while not stop_evt.is_set():
            if not manager.daemon.running():
                manager.daemon._clear_pid_file()
            if not manager.webui.running():
                manager.webui._clear_pid_file()
            time.sleep(2.0)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()

    try:
        icon.run()
    finally:
        stop_evt.set()
        manager.stop_all()


if __name__ == "__main__":
    main()
