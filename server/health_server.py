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


# S-STRAT-7: provider opcional para snapshot do auto-tune batch.
_BATCH_TUNE_PROVIDER = None  # type: ignore[var-annotated]


def set_batch_tune_provider(provider) -> None:
    """S-STRAT-7: registra callable() -> dict para /api/batch_tune."""
    global _BATCH_TUNE_PROVIDER
    _BATCH_TUNE_PROVIDER = provider


# S-STRAT-10 MVP: provider opcional para snapshot do shadow challenger.
_SHADOW_PROVIDER = None  # type: ignore[var-annotated]


def set_shadow_provider(provider) -> None:
    """S-STRAT-10: registra callable() -> dict para /api/shadow."""
    global _SHADOW_PROVIDER
    _SHADOW_PROVIDER = provider

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
            # S-STRAT-7: métricas do auto-tune batch (4 spins por sentido).
            "batch_runs_cw": Gauge("roleta_batch_tune_runs_cw_total", "Total runs do auto-tune batch (direcao CW)"),
            "batch_runs_ccw": Gauge("roleta_batch_tune_runs_ccw_total", "Total runs do auto-tune batch (direcao CCW)"),
            "batch_pullback_cw": Gauge("roleta_batch_tune_pullback_cw_total", "Pull-backs aplicados (CW)"),
            "batch_pullback_ccw": Gauge("roleta_batch_tune_pullback_ccw_total", "Pull-backs aplicados (CCW)"),
            "batch_delta_cw": Gauge("roleta_batch_tune_last_delta_cw", "Delta acc(last4)-acc(prev4) ultimo tune CW"),
            "batch_delta_ccw": Gauge("roleta_batch_tune_last_delta_ccw", "Delta acc(last4)-acc(prev4) ultimo tune CCW"),
            "batch_pending_cw": Gauge("roleta_batch_tune_pending_cw", "Spins pendentes ate proximo tune CW"),
            "batch_pending_ccw": Gauge("roleta_batch_tune_pending_ccw", "Spins pendentes ate proximo tune CCW"),
            # S-STRAT-11: thresholds dinâmicos do KILL v4.
            "kill_thr_c4_cw": Gauge("roleta_kill_threshold_c4_cw", "Threshold c4 dinamico KILL v4 (CW)"),
            "kill_thr_c4_ccw": Gauge("roleta_kill_threshold_c4_ccw", "Threshold c4 dinamico KILL v4 (CCW)"),
            "kill_thr_sda_cw": Gauge("roleta_kill_threshold_sda_cw", "Threshold sda dinamico KILL v4 (CW)"),
            "kill_thr_sda_ccw": Gauge("roleta_kill_threshold_sda_ccw", "Threshold sda dinamico KILL v4 (CCW)"),
            # S-STRAT-13: shadow grid (4 challengers paralelos)
            "shadow_acc": Gauge("roleta_shadow_acc", "Shadow challenger accuracy (rolling 100)", ["shift", "direction"]),
            "shadow_edge_pp": Gauge("roleta_shadow_edge_pp", "Shadow edge (pp): challenger_acc - incumbent_acc", ["shift", "direction"]),
            "shadow_n": Gauge("roleta_shadow_samples_n", "Samples observados pelo challenger", ["shift", "direction"]),
            "shadow_champion_shift": Gauge("roleta_shadow_champion_shift", "Shift do challenger campeao (0 se nenhum elegivel)"),
            "shadow_alert": Gauge("roleta_shadow_alert", "1 se algum challenger bate incumbent com n>=30"),
            # S-STRAT-13.1: suggestion automatica baseada em EMA+histerese
            "shadow_suggested_shift": Gauge("roleta_shadow_suggested_shift", "Shift sugerido pelo auto-promote (0 se nenhum)"),
            "shadow_edge_ema": Gauge("roleta_shadow_edge_ema", "EMA do edge medio (alpha=0.05) por shift", ["shift"]),
            "shadow_sustained": Gauge("roleta_shadow_sustained_spins", "Contador sustained_edge por shift", ["shift"]),
            # S-STRAT-13.1 promoção automática: contador de promoções aplicadas
            "shadow_auto_promotes": Counter("roleta_shadow_auto_promotes_total", "Total de auto-promotes do shadow grid", ["shift"]),
            # S-OBS-16: receiver webhook do AlertManager
            "alerts_received": Counter("roleta_alertmanager_webhook_received_total", "Total de alertas recebidos via webhook do AlertManager", ["severity", "alertname"]),
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
            # S-STRAT-11: KILL v4 dynamic thresholds via strategy provider
            ks = sg.get("kill_stats") or {}
            kv4 = ks.get("kill_v4") or {}
            thr_c4 = kv4.get("threshold_c4") or {}
            thr_sda = kv4.get("threshold_sda") or {}
            for dk in ("cw", "ccw"):
                if dk in thr_c4:
                    _PROM_METRICS[f"kill_thr_c4_{dk}"].set(float(thr_c4[dk]))
                if dk in thr_sda:
                    _PROM_METRICS[f"kill_thr_sda_{dk}"].set(float(thr_sda[dk]))
        # S-STRAT-7: batch tune metrics.
        if _BATCH_TUNE_PROVIDER is not None:
            bt = _BATCH_TUNE_PROVIDER() or {}
            for dk in ("cw", "ccw"):
                _PROM_METRICS[f"batch_runs_{dk}"].set(float(bt.get("batch_runs_total", {}).get(dk, 0)))
                _PROM_METRICS[f"batch_pullback_{dk}"].set(float(bt.get("batch_pullback_total", {}).get(dk, 0)))
                _PROM_METRICS[f"batch_delta_{dk}"].set(float(bt.get("batch_last_delta", {}).get(dk, 0)))
                _PROM_METRICS[f"batch_pending_{dk}"].set(float(bt.get("pending_spins", {}).get(dk, 0)))
        # S-STRAT-13: shadow grid metrics (labelled por shift+direction).
        if _SHADOW_PROVIDER is not None:
            sh = _SHADOW_PROVIDER() or {}
            challengers = sh.get("challengers") or []
            for c in challengers:
                shift = str(c.get("shift"))
                for dk in ("cw", "ccw"):
                    side = c.get(dk) or {}
                    _PROM_METRICS["shadow_acc"].labels(shift=shift, direction=dk).set(float(side.get("acc", 0.0)))
                    _PROM_METRICS["shadow_n"].labels(shift=shift, direction=dk).set(float(side.get("n", 0)))
                _PROM_METRICS["shadow_edge_pp"].labels(shift=shift, direction="cw").set(float(c.get("edge_pp_cw", 0.0)))
                _PROM_METRICS["shadow_edge_pp"].labels(shift=shift, direction="ccw").set(float(c.get("edge_pp_ccw", 0.0)))
            champ = sh.get("champion") or {}
            _PROM_METRICS["shadow_champion_shift"].set(float(champ.get("shift") or 0))
            _PROM_METRICS["shadow_alert"].set(1.0 if sh.get("alert") == "shadow_beating_incumbent" else 0.0)
            # S-STRAT-13.1: expor EMA + sustained + suggestion
            for c in challengers:
                shift = str(c.get("shift"))
                _PROM_METRICS["shadow_edge_ema"].labels(shift=shift).set(float(c.get("edge_ema", 0.0)))
                _PROM_METRICS["shadow_sustained"].labels(shift=shift).set(float(c.get("sustained_spins", 0)))
            sug = sh.get("suggestion") or {}
            _PROM_METRICS["shadow_suggested_shift"].set(float(sug.get("shift") or 0))
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
        if self.path == "/api/batch_tune":
            # S-STRAT-7: snapshot do auto-tune em lote (4 spins por sentido).
            if _BATCH_TUNE_PROVIDER is None:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"batch_tune provider not registered"}')
                return
            try:
                payload = _BATCH_TUNE_PROVIDER()
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
        if self.path == "/api/shadow":
            # S-STRAT-10 MVP: snapshot do shadow challenger (random baseline).
            if _SHADOW_PROVIDER is None:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"shadow provider not registered"}')
                return
            try:
                payload = _SHADOW_PROVIDER()
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

    def do_POST(self) -> None:  # noqa: N802
        # S-OBS-16: receiver webhook do AlertManager. Apenas loga + conta.
        if self.path == "/api/alerts/sink":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw or b"{}")
                alerts = payload.get("alerts", []) or []
                for a in alerts:
                    labels = a.get("labels", {}) or {}
                    severity = labels.get("severity", "unknown")
                    alertname = labels.get("alertname", "unknown")
                    status = a.get("status", "?")
                    summary = (a.get("annotations") or {}).get("summary", "")
                    logger.warning(
                        "alertmanager_webhook status=%s sev=%s name=%s summary=%s",
                        status, severity, alertname, summary,
                    )
                    if _PROM_METRICS and "alerts_received" in _PROM_METRICS:
                        try:
                            _PROM_METRICS["alerts_received"].labels(
                                severity=severity, alertname=alertname
                            ).inc()
                        except Exception:  # noqa: BLE001
                            pass
                body = json.dumps({"received": len(alerts)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                logger.warning("alertmanager_webhook_error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
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
