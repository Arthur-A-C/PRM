"""Serve a short-lived, password-gated PRM preview through a Cloudflare Quick Tunnel.

Run in a terminal and keep the process alive. No router/firewall inbound rule is needed.
The generated Basic password is printed once; PRM login is still required.
"""

import argparse
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
CLOUDFLARED = ROOT / "data" / "tools" / "cloudflared.exe"
STATUS = ROOT / "data" / "exports" / "public_preview_status.json"
STOP = ROOT / "data" / "exports" / "public_preview.stop"
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _consume_lines(pipe, messages: queue.Queue[str]) -> None:
    for line in iter(pipe.readline, ""):
        messages.put(line)


def _terminate(process: subprocess.Popen | None) -> bool:
    if process is None or process.poll() is not None:
        return True
    if os.name == "nt":
        # Windows venv python.exe starts a child interpreter; stop the exact
        # process tree owned by this supervisor so port 8002 is not orphaned.
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print(f"Falha ao encerrar árvore PID {process.pid}: {result.stderr.strip() or result.stdout.strip()}", flush=True)
            try:
                process.terminate()
            except OSError:
                return False
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return False
        return result.returncode == 0
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    return process.poll() is not None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--duration-minutes", type=int, default=120)
    args = parser.parse_args()
    if not 15 <= args.duration_minutes <= 240:
        raise SystemExit("A duração deve ser de 15 a 240 minutos.")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Porta inválida.")
    if not CLOUDFLARED.is_file():
        raise SystemExit(f"cloudflared não encontrado em {CLOUDFLARED}")

    password = secrets.token_urlsafe(32)
    server = tunnel = None
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STOP.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update({
        "PRM_PREVIEW_BASIC_PASSWORD": password,
        "PRM_SESSION_COOKIE_SECURE": "true",
        "PRM_SESSION_TTL_HOURS": "2",
        "PRM_ENVIRONMENT": "remote_preview",
    })
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.remote_preview:app", "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        local_url = f"http://127.0.0.1:{args.port}/api/v1/health/live"
        with httpx.Client(timeout=3) as client:
            for _ in range(30):
                if server.poll() is not None:
                    raise RuntimeError("O servidor da prévia não iniciou; confira porta e ambiente.")
                try:
                    response = client.get(local_url, auth=("prm-preview", password))
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("O servidor da prévia não respondeu em 15 segundos.")

        tunnel = subprocess.Popen(
            [str(CLOUDFLARED), "tunnel", "--url", f"http://127.0.0.1:{args.port}"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=creationflags,
        )
        messages: queue.Queue[str] = queue.Queue()
        threading.Thread(target=_consume_lines, args=(tunnel.stdout, messages), daemon=True).start()
        public_url = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError("O túnel encerrou antes de fornecer uma URL; verifique a conexão externa.")
            try:
                line = messages.get(timeout=1)
            except queue.Empty:
                continue
            match = URL_PATTERN.search(line)
            if match:
                public_url = match.group(0)
                break
        if not public_url:
            raise RuntimeError("O túnel não forneceu URL pública em 60 segundos.")

        started = datetime.now(timezone.utc)
        expires = started + timedelta(minutes=args.duration_minutes)
        STATUS.write_text(json.dumps({
            "url": public_url,
            "started_at": started.isoformat(),
            "expires_at": expires.isoformat(),
            "supervisor_pid": os.getpid(),
            "server_pid": server.pid,
            "tunnel_pid": tunnel.pid,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"URL: {public_url}", flush=True)
        print("USUÁRIO DA PRÉVIA: prm-preview", flush=True)
        print(f"SENHA DA PRÉVIA (mostrada uma vez): {password}", flush=True)
        print(f"EXPIRA: {expires.isoformat()} | Para encerrar: python -m scripts.stop_public_preview", flush=True)
        while datetime.now(timezone.utc) < expires:
            if STOP.is_file():
                print("Prévia encerrada por solicitação local.", flush=True)
                break
            if server.poll() is not None or tunnel.poll() is not None:
                print("Prévia encerrada porque o servidor ou túnel parou.", flush=True)
                break
            time.sleep(2)
    finally:
        tunnel_stopped = _terminate(tunnel)
        server_stopped = _terminate(server)
        if tunnel_stopped and server_stopped:
            STATUS.unlink(missing_ok=True)
            STOP.unlink(missing_ok=True)
        else:
            print("ATENÇÃO: um processo pode ter permanecido ativo; confira os PIDs no arquivo de status.", flush=True)


if __name__ == "__main__":
    main()
