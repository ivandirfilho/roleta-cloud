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
    from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST, Gauge, Counter  # type: ignore
    _METRICS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _METRICS_AVAILABLE = False


# S-OBS-9: métricas Prometheus alimentadas pelos providers de /api/state e /api/strategy.
# Atualizadas on-demand a cada scrape /metrics (não loop dedicado).
_PROM_METRICS = None
if _METRICS_AVAILABLE:
    try:
        _PROM_METRICS = {
            "kill_pulls": Gauge("roleta_kill_pulls_total", "Total Kill Switch v3 pulls in process (persistido em state.json)"),
            "adp_keys": Gauge("roleta_adaptive_state_keys_count", "Numero de chaves no _adaptive_state (alarmar se < 5)"),
            "sigmoid_ok": Gauge("roleta_sigmoid_off_populated", "1 se sigmoid_off tem chaves, 0 vazio"),
            "state_age": Gauge("roleta_state_file_age_seconds", "Segundos desde ultima escrita de state.json"),
            "state_size": Gauge("roleta_state_file_size_bytes", "Tamanho do state.json em disco"),
            "recent_acc_cw": Gauge("roleta_recent_acc_cw", "Accuracy rolling 100 spins direcao CW"),
            "recent_acc_ccw": Gauge("roleta_recent_acc_ccw", "Accuracy rolling 100 spins direcao CCW"),
            "seconds_since_spin": Gauge("roleta_seconds_since_last_spin", "Segundos desde ultimo spin processado"),
            "scrape_errors": Counter("roleta_metrics_scrape_errors_total", "Falhas ao atualizar metricas durante scrape"),
        }
    except Exception:  # noqa: BLE001
        _PROM_METRICS = None


def _refresh_custom_metrics() -> None:
    """S-OBS-9: chamado a cada GET /metrics; tolerante a providers ausentes."""
    if not _PROM_METRICS:
        return
    try:
        if _STATE_PROVIDER is not None:
            st = _STATE_PROVIDER() or {}
            bs = st.get("bet_advisor_state") or {}
            _PROM_METRICS["kill_pulls"].set(float(bs.get("kill_pulls_total", 0)))
            _PROM_METRICS["adp_keys"].set(float(st.get("adaptive_state_keys_count", 0)))
            _PROM_METRICS["sigmoid_ok"].set(1.0 if st.get("sigmoid_off_populated") else 0.0)
            age = st.get("state_file_age_seconds")
            if age is not None:
                _PROM_METRICS["state_age"].set(float(age))
            size = st.get("state_file_size_bytes")
            if size is not None:
                _PROM_METRICS["state_size"].set(float(size))
        if _STRATEGY_PROVIDER is not None:
            sg = _STRATEGY_PROVIDER() or {}
            ra = sg.get("recent_acc") or {}
            cw = ra.get("cw_last_100")
            ccw = ra.get("ccw_last_100")
            if cw is not None:
                _PROM_METRICS["recent_acc_cw"].set(float(cw))
            if ccw is not None:
                _PROM_METRICS["recent_acc_ccw"].set(float(ccw))
            sec = sg.get("seconds_since_last_spin")
            if sec is not None:
                _PROM_METRICS["seconds_since_spin"].set(float(sec))
    except Exception:  # noqa: BLE001
        try:
            _PROM_METRICS["scrape_errors"].inc()
        except Exception:  # noqa: BLE001
            pass


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
            _refresh_custom_metrics()  # S-OBS-9: atualiza gauges custom antes do scrape
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
