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

# NEW-12 (26/05): provider opcional callable() -> {"total": int, "filled": int}
# para fill-rate de calibration_error. Boot registra em websocket apontando
# para uma query SQLite cacheada (~30s).
_CALIBRATION_PROVIDER = None  # type: ignore[var-annotated]
_WHEEL_DIST_PROVIDER = None  # type: ignore[var-annotated]
_DNA_REALIZE_PROVIDER = None  # type: ignore[var-annotated]
# B5 PROFIT-LEDGER (12/06): provider de P&L por sessão.
_PNL_PROVIDER = None  # type: ignore[var-annotated]
# INCIDENT 13/06: provider do estado do ConnectionManager (master_present, connections).
_CONNMGR_PROVIDER = None  # type: ignore[var-annotated]


def set_pnl_provider(provider) -> None:
    """B5 (12/06): registra provider de P&L (session_pnl_stats do repo)."""
    global _PNL_PROVIDER
    _PNL_PROVIDER = provider


def set_dna_realize_provider(provider) -> None:
    """SP-29: registra callable() -> dict {unrealized, lag_seconds}."""
    global _DNA_REALIZE_PROVIDER
    _DNA_REALIZE_PROVIDER = provider


def set_wheel_dist_provider(provider) -> None:
    """SP-30: registra callable() -> dict {n, p50, p95, p99}."""
    global _WHEEL_DIST_PROVIDER
    _WHEEL_DIST_PROVIDER = provider


def set_calibration_provider(provider) -> None:
    """NEW-12: registra callable() -> dict com keys 'total' e 'filled'."""
    global _CALIBRATION_PROVIDER
    _CALIBRATION_PROVIDER = provider


def set_shadow_provider(provider) -> None:
    """S-STRAT-10: registra callable() -> dict para /api/shadow."""
    global _SHADOW_PROVIDER
    _SHADOW_PROVIDER = provider


def set_connmgr_provider(provider) -> None:
    """INCIDENT 13/06: registra callable() -> {master_present:int, connections:int}
    para o alerta RoletaNoMaster (sem MASTER eleito = spins descartados)."""
    global _CONNMGR_PROVIDER
    _CONNMGR_PROVIDER = provider

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
            # INCIDENT 13/06: eleição de MASTER — detectar "sem master com clientes" em ~1min.
            "master_present": Gauge("roleta_master_present", "1 se ha WS MASTER eleito, 0 caso contrario"),
            "ws_connections": Gauge("roleta_ws_connections", "Conexoes WS ativas (master + slaves)"),
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
            # S-STRAT-14: bandit ε-greedy
            "bandit_epsilon": Gauge("roleta_bandit_epsilon", "Bandit epsilon corrente"),
            "bandit_recommended_shift": Gauge("roleta_bandit_recommended_shift", "Shift recomendado pelo bandit (0 se nenhum)"),
            "bandit_n": Gauge("roleta_bandit_arm_n", "Pulls por braço", ["shift"]),
            "bandit_mean": Gauge("roleta_bandit_arm_mean", "Mean reward por braço", ["shift"]),
            "bandit_total_pulls": Gauge("roleta_bandit_total_pulls", "Total de pulls do bandit"),
            # S-OBS-16: receiver webhook do AlertManager
            "alerts_received": Counter("roleta_alertmanager_webhook_received_total", "Total de alertas recebidos via webhook do AlertManager", ["severity", "alertname"]),
            # NEW-12 (26/05): fill-rate de calibration_error — defesa contra
            # bugs silenciosos como B-09 (pending key mismatch). Mede se o
            # caminho W-01+W-02+B-08 (wheel_dist) esta realmente populando
            # a coluna apos cada resultado.
            "cal_total_1h": Gauge("roleta_decisions_with_result_1h", "Decisoes APOSTAR com result_actual NOT NULL na ultima 1h"),
            "cal_filled_1h": Gauge("roleta_decisions_calibration_filled_1h", "Decisoes APOSTAR com calibration_error NOT NULL na ultima 1h"),
            "cal_fill_rate": Gauge("roleta_calibration_fill_rate_1h", "Ratio calibration_error_filled / total_with_result (0..1) janela 1h"),
            # SP-30 (OBS-02 27/05): wheel_dist percentis 1h para alerta SP-31.
            "wd_n_1h": Gauge("roleta_wheel_dist_samples_1h", "Decisoes com calibration_error NOT NULL na ultima 1h"),
            "wd_p50_1h": Gauge("roleta_wheel_dist_p50_1h", "p50 de wheel_dist (calibration_error) janela 1h"),
            "wd_p95_1h": Gauge("roleta_wheel_dist_p95_1h", "p95 de wheel_dist (calibration_error) janela 1h"),
            "wd_p99_1h": Gauge("roleta_wheel_dist_p99_1h", "p99 de wheel_dist (calibration_error) janela 1h"),
            # SP-29 OBS-01 (27/05): DNA realize lag (alerta se >300s sustentado).
            "dna_unrealized": Gauge("roleta_dna_unrealized_count", "Features DNA sem realized_lift_pp/hit"),
            "dna_realize_lag": Gauge("roleta_dna_realize_lag_seconds", "Segundos desde a mais antiga feature DNA sem realize"),
            # B5 PROFIT-LEDGER (12/06): P&L real — KPI de decisão é EV, não hit rate.
            "session_pnl": Gauge("roleta_session_pnl_units", "P&L da sessão corrente (unidades; payout 36:1, stake distribuído por N)"),
            "all_time_pnl": Gauge("roleta_all_time_pnl_units", "P&L acumulado (soma de decisions.pnl_units)"),
            # MELHORIA-G (12/06): EMA do erro circular assinado por região.
            "region_err_ema": Gauge("roleta_region_err_ema", "EMA do erro assinado (casas) do resultado até o centro da região", ["direction", "region"]),
            "region_err_n": Gauge("roleta_region_err_n", "Amostras da EMA de erro por região (SV-03: gate do alerta de viés)", ["direction", "region"]),
            # SV-01 (12/06): shift aplicado pelo Modelo Universal M5.
            "region_shift": Gauge("roleta_region_shift", "Shift de C1 aplicado pelo M5 (casas, por sentido)", ["direction"]),
            # force17 (18/06): 1 se o modo C1=ForceLast/17# está no ar (SDA_BET_PAIR=force17).
            "force17_active": Gauge("roleta_force17_active", "1 se SDA_BET_PAIR=force17 (C1=ForceLast + 17# / 3 regiões)"),
        }
    except Exception:  # noqa: BLE001
        _PROM_METRICS = None


def _refresh_custom_metrics() -> None:
    """S-OBS-9: chamado a cada GET /metrics; tolerante a providers ausentes."""
    if not _PROM_METRICS:
        return
    try:
        # force17 (18/06): modo de cobertura no ar (auto-contido; sem provider).
        try:
            from app_config.settings import bet_pair_mode as _bpm
            _PROM_METRICS["force17_active"].set(1.0 if _bpm() == "force17" else 0.0)
        except Exception:  # noqa: BLE001
            pass
        # INCIDENT 13/06: eleição de MASTER (sob o try comum; erros contam em scrape_errors).
        if _CONNMGR_PROVIDER is not None:
            _cm = _CONNMGR_PROVIDER() or {}
            _PROM_METRICS["master_present"].set(1.0 if _cm.get("master_present") else 0.0)
            _PROM_METRICS["ws_connections"].set(float(_cm.get("connections", 0)))
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
            # MELHORIA-G (12/06): EMA de erro por região/sentido.
            ree = sg.get("region_err_ema") or {}
            ren = sg.get("region_err_n") or {}
            for dk in ("cw", "ccw"):
                for slot in ("c1", "c2", "c3"):
                    v = (ree.get(dk) or {}).get(slot)
                    if v is not None:
                        _PROM_METRICS["region_err_ema"].labels(
                            direction=dk, region=slot.upper()
                        ).set(float(v))
                    nv = (ren.get(dk) or {}).get(slot)
                    if nv is not None:
                        _PROM_METRICS["region_err_n"].labels(
                            direction=dk, region=slot.upper()
                        ).set(float(nv))
            # SV-01: shift corrente do M5.
            rs = sg.get("region_shift") or {}
            for dk in ("cw", "ccw"):
                sv = (rs.get(dk) or {}).get("shift_c1")
                if sv is not None:
                    _PROM_METRICS["region_shift"].labels(direction=dk).set(float(sv))
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
        # S-STRAT-14: bandit ε-greedy metrics
        if _STRATEGY_PROVIDER is not None:
            sg = _STRATEGY_PROVIDER() or {}
            bandit = sg.get("bandit") or {}
            if bandit:
                _PROM_METRICS["bandit_epsilon"].set(float(bandit.get("epsilon", 1.0)))
                _PROM_METRICS["bandit_recommended_shift"].set(float(bandit.get("recommended_shift") or 0))
                _PROM_METRICS["bandit_total_pulls"].set(float(bandit.get("total_pulls", 0)))
                for sk, a in (bandit.get("arms") or {}).items():
                    _PROM_METRICS["bandit_n"].labels(shift=str(sk)).set(float(a.get("n", 0)))
                    _PROM_METRICS["bandit_mean"].labels(shift=str(sk)).set(float(a.get("mean", 0.0)))
        # NEW-12: calibration_error fill-rate (defesa contra B-09-like bugs)
        if _CALIBRATION_PROVIDER is not None:
            cal = _CALIBRATION_PROVIDER() or {}
            total = float(cal.get("total", 0) or 0)
            filled = float(cal.get("filled", 0) or 0)
            _PROM_METRICS["cal_total_1h"].set(total)
            _PROM_METRICS["cal_filled_1h"].set(filled)
            _PROM_METRICS["cal_fill_rate"].set(filled / total if total > 0 else 1.0)
        # SP-30 OBS-02: wheel_dist percentis 1h.
        if _WHEEL_DIST_PROVIDER is not None:
            wd = _WHEEL_DIST_PROVIDER() or {}
            _PROM_METRICS["wd_n_1h"].set(float(wd.get("n", 0) or 0))
            _PROM_METRICS["wd_p50_1h"].set(float(wd.get("p50", 0.0) or 0.0))
            _PROM_METRICS["wd_p95_1h"].set(float(wd.get("p95", 0.0) or 0.0))
            _PROM_METRICS["wd_p99_1h"].set(float(wd.get("p99", 0.0) or 0.0))
        # SP-29 OBS-01: DNA realize lag.
        if _DNA_REALIZE_PROVIDER is not None:
            dr = _DNA_REALIZE_PROVIDER() or {}
            _PROM_METRICS["dna_unrealized"].set(float(dr.get("unrealized", 0) or 0))
            _PROM_METRICS["dna_realize_lag"].set(float(dr.get("lag_seconds", 0) or 0))
        # B5 PROFIT-LEDGER (12/06): P&L da sessão + acumulado.
        if _PNL_PROVIDER is not None:
            pnl = _PNL_PROVIDER() or {}
            _PROM_METRICS["session_pnl"].set(float(pnl.get("current_session_pnl", 0.0) or 0.0))
            _PROM_METRICS["all_time_pnl"].set(float(pnl.get("all_time_pnl", 0.0) or 0.0))
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
        if self.path == "/api/dna_summary":
            # SP-09 DNA-04: agregado por (feature_name, bucket) com n, hit_rate,
            # avg_lift_pp. Sem provider — le direto via dna_logger.
            try:
                from database import dna_logger as _dna
                payload = _dna.dna_summary()
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
        if self.path.startswith("/api/dealers"):
            # SP-14 DEAL-04 (27/05): ranking de dealers por hit_rate na janela.
            try:
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                limit = int(qs.get("limit", ["50"])[0])
                window = int(qs.get("window_minutes", ["1440"])[0])
                from database.service import db_service
                rows = db_service.repository.dealer_stats(limit=limit, window_minutes=window)
                body = json.dumps({"dealers": rows, "window_minutes": window}, default=str).encode()
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
        if self.path.startswith("/api/regime"):
            # S-STRAT-12: regime similarity via pgvector
            # /api/regime?direction=cw[&limit=20]
            # Usa últimas raw_features do schema como query_vec (proxy do regime atual)
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            direction = (qs.get("direction", ["cw"])[0] or "cw").lower()
            try:
                limit = int(qs.get("limit", ["20"])[0])
            except Exception:  # noqa: BLE001
                limit = 20
            if direction not in ("cw", "ccw"):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"direction must be cw|ccw"}')
                return
            try:
                from database.regime_similarity import RegimeSimilarityReader
                import psycopg2  # noqa: F401  (ensure dep available)
                import os as _os
                dsn = _os.environ.get("ROLETA_PG_DSN")
                if not dsn:
                    raise RuntimeError("ROLETA_PG_DSN not set")
                # Pega último raw_features do mesmo schema como query
                import psycopg2 as _pg
                _c = _pg.connect(dsn)
                _c.autocommit = True
                try:
                    with _c.cursor() as cur:
                        cur.execute(
                            f"SELECT raw_features::text FROM {direction}.spins_vectors ORDER BY id DESC LIMIT 1;"
                        )
                        row = cur.fetchone()
                finally:
                    _c.close()
                if not row or not row[0]:
                    payload = {"direction": direction, "n": 0, "reason": "no vectors yet"}
                else:
                    # raw_features::text vem como "[1,2,3,4,5,6]"
                    import json as _json
                    qvec = _json.loads(row[0])
                    reader = RegimeSimilarityReader(dsn=dsn)
                    score = reader.regime_score(direction, qvec, limit=limit)
                    sims = reader.find_similar(direction, qvec, limit=min(limit, 10))
                    reader.close()
                    payload = {**score, "top_similar": sims}
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
                self.wfile.write(json.dumps({"error": str(exc), "type": type(exc).__name__}).encode())
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
