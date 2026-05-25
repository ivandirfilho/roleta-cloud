"""HTTP server minimal: /health + /metrics (VF-3/VF-4).

Sobe em thread daemon na porta 8766 (não conflita com WS 8765).
NUNCA bloqueia ou quebra o app principal.

Endpoints:
- GET /health  -> 200 OK {"status":"ok","ts":...,"version":...} se app vivo
- GET /metrics -> prometheus exposition (se prometheus_client instalado)
- GET /        -> 200 OK ping simples

Uso (em main.py ANTES de asyncio.run):
    from server.health_server import start_health_server
    start_health_server()
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

_STARTED_AT = time.time()
_VERSION: str = "unknown"

# S-OBS-3: provider opcional para introspecção viva da estratégia.
# Setado por server.websocket no boot; se ausente, /api/strategy retorna 503.
_STRATEGY_PROVIDER = None  # type: ignore[var-annotated]

# S-OBS-8: provider opcional para saúde do estado adaptativo persistido.
# Setado por server.websocket no boot; se ausente, /api/state retorna 503.
_STATE_PROVIDER = None  # type: ignore[var-annotated]


def set_strategy_provider(provider) -> None:
    """Registra callable() -> dict para /api/strategy. Idempotente."""
    global _STRATEGY_PROVIDER
    _STRATEGY_PROVIDER = provider


def set_state_provider(provider) -> None:
    """S-OBS-8: registra callable() -> dict para /api/state. Idempotente."""
    global _STATE_PROVIDER
    _STATE_PROVIDER = provider

try:
    from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST  # type: ignore
    _METRICS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _METRICS_AVAILABLE = False


def _read_version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # silencia access log
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz"):
            payload = {
                "status": "ok",
                "uptime_sec": int(time.time() - _STARTED_AT),
                "version": _VERSION,
                "ts": int(time.time()),
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/metrics":
            if not _METRICS_AVAILABLE:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"prometheus_client not installed")
                return
            data = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/api/strategy":
            if _STRATEGY_PROVIDER is None:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"strategy provider not registered"}')
                return
            try:
                payload = _STRATEGY_PROVIDER()
                body = json.dumps(payload, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return
        if self.path == "/api/state":
            # S-OBS-8: saúde do estado adaptativo persistido (para monitor externo)
            if _STATE_PROVIDER is None:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"state provider not registered"}')
                return
            try:
                payload = _STATE_PROVIDER()
                body = json.dumps(payload, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"roleta-cloud health server")
            return
        self.send_response(404)
        self.end_headers()


def start_health_server(host: str = "0.0.0.0", port: int = 8766) -> None:
    """Inicia thread daemon servindo /health e /metrics. Idempotente."""
    global _VERSION
    _VERSION = _read_version()

    # Pre-importa outbox_integration para registrar métricas no REGISTRY default
    try:
        import database.outbox_integration  # noqa: F401
    except Exception:  # noqa: BLE001
        pass

    def _serve() -> None:
        try:
            httpd = ThreadingHTTPServer((host, port), _Handler)
            logger.warning("health_server_started host=%s port=%d metrics=%s", host, port, _METRICS_AVAILABLE)
            httpd.serve_forever()
        except Exception as exc:  # noqa: BLE001
            logger.warning("health_server_failed: %s", exc)

    t = threading.Thread(target=_serve, daemon=True, name="health-server")
    t.start()
