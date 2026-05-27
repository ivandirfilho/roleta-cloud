# Roleta Cloud - WebSocket Server

import asyncio
import json
import logging
import ssl
import os
from pathlib import Path
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from app_config.settings import settings
from auth.middleware import verify_auth
from database.service import db_service
from models.trace import now_ms
from server.connection_manager import connection_manager
from server.message_handler import MessageHandler
from state.game import GameState
from strategies.sda17 import SDA17Strategy

# Logging
logger = logging.getLogger(__name__)

# Estado global
state_lock = asyncio.Lock()
game_state: GameState = GameState.load()
strategy = SDA17Strategy()  # M15-ADA Adaptive Triple Focus

# M15-ADA: Restaurar estado adaptativo da sessão anterior
if game_state._adaptive_state:
    try:
        strategy.load_adaptive_state(game_state._adaptive_state)
        logger.info("Estado adaptativo restaurado com sucesso")
    except Exception as e:
        logger.warning(f"Falha ao restaurar estado adaptativo: {e}, usando defaults")

configs_path = os.path.join(os.path.dirname(__file__), "configs")
message_handler = MessageHandler(game_state, strategy, state_lock, configs_path)

# S-OBS-3: registra provider de introspecção da estratégia no health_server.
try:
    from server.health_server import set_strategy_provider as _set_sp

    def _strategy_snapshot():
        import time as _time
        adp = strategy.get_adaptive_state() if hasattr(strategy, "get_adaptive_state") else {}
        mg_cw = game_state.martingale_cw
        mg_ccw = game_state.martingale_ccw
        recent_hits = adp.get("recent_hits", {})
        def _acc(buf):
            return round(sum(buf) / len(buf), 3) if buf else None
        # S-OBS-6: kill switch counter + last spin ts
        kill_stats = {"pulls_total": 0, "last_pull_ts": None}
        try:
            if hasattr(game_state, "bet_advisor") and hasattr(game_state.bet_advisor, "get_kill_stats"):
                kill_stats = game_state.bet_advisor.get_kill_stats()
        except Exception:  # noqa: BLE001
            pass
        last_spin_ts = getattr(message_handler, "last_spin_ts", None)
        now = _time.time()
        sec_since = round(now - last_spin_ts, 1) if last_spin_ts else None
        # S-STRAT-14: bandit snapshot
        bandit_stats = {}
        try:
            if hasattr(game_state, "get_bandit_stats"):
                bandit_stats = game_state.get_bandit_stats()
        except Exception:  # noqa: BLE001
            pass
        return {
            "session_id": getattr(message_handler, "current_session_id", None),
            "last_number": game_state.last_number,
            "last_direction": game_state.last_direction,
            "last_spin_ts": last_spin_ts,
            "seconds_since_last_spin": sec_since,
            "timeline": {
                "cw_size": game_state.timeline_cw.size,
                "ccw_size": game_state.timeline_ccw.size,
            },
            "sigmoid_off": adp.get("sigmoid_off", {}),
            "recent_acc": {
                "cw_last_100": _acc(recent_hits.get("cw", [])),
                "ccw_last_100": _acc(recent_hits.get("ccw", [])),
            },
            "cooldown": adp.get("cooldown", {}),
            "drift_freeze": adp.get("drift_freeze", {}),
            "martingale": {
                "cw": {
                    "level": mg_cw.level,
                    "consecutive_hits": mg_cw.consecutive_hits,
                    "global_streak": mg_cw.global_consecutive_hits,
                },
                "ccw": {
                    "level": mg_ccw.level,
                    "consecutive_hits": mg_ccw.consecutive_hits,
                    "global_streak": mg_ccw.global_consecutive_hits,
                },
            },
            "kill_switch": kill_stats,  # S-OBS-6
            "kill_stats": kill_stats,   # S-STRAT-11: alias para health_server consumir thresholds
            "bandit": bandit_stats,     # S-STRAT-14
            "ts": int(now),
        }

    _set_sp(_strategy_snapshot)
    logger.info("strategy_provider_registered for /api/strategy")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"strategy_provider_register_failed: {_e}")


# S-STRAT-7: provider de snapshot do auto-tune batch para /api/batch_tune
try:
    from server.health_server import set_batch_tune_provider as _set_bt_p

    def _batch_tune_snapshot():
        try:
            if hasattr(strategy, "get_batch_tune_snapshot"):
                return strategy.get_batch_tune_snapshot()
        except Exception:  # noqa: BLE001
            pass
        return {}

    _set_bt_p(_batch_tune_snapshot)
    logger.info("batch_tune_provider_registered for /api/batch_tune")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"batch_tune_provider_register_failed: {_e}")


# S-STRAT-10 MVP: provider de snapshot shadow challenger para /api/shadow
try:
    from server.health_server import set_shadow_provider as _set_shd_p

    def _shadow_snapshot():
        try:
            if hasattr(game_state, "get_shadow_stats"):
                return game_state.get_shadow_stats()
        except Exception:  # noqa: BLE001
            pass
        return {}

    _set_shd_p(_shadow_snapshot)
    logger.info("shadow_provider_registered for /api/shadow")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"shadow_provider_register_failed: {_e}")


# NEW-12 (26/05): calibration_error fill-rate provider para Prometheus.
# Defesa contra bugs silenciosos pos-deploy (vide B-09 — pending key
# mismatch que fez fill rate cair a 0 sem alarme algum).
try:
    from server.health_server import set_calibration_provider as _set_cal_p
    import time as _time_cal

    _cal_cache = {"ts": 0.0, "val": {"total": 0, "filled": 0}}

    def _calibration_snapshot():
        """Cache de 30s — evita query a cada scrape /metrics (~5s)."""
        now = _time_cal.time()
        if now - _cal_cache["ts"] < 30.0:
            return _cal_cache["val"]
        try:
            repo = db_service.repository
            if hasattr(repo, "calibration_fill_stats"):
                val = repo.calibration_fill_stats(window_minutes=60)
            else:
                val = {"total": 0, "filled": 0}
            _cal_cache["val"] = val
            _cal_cache["ts"] = now
            return val
        except Exception:
            return _cal_cache["val"]

    _set_cal_p(_calibration_snapshot)
    logger.info("calibration_provider_registered for NEW-12 fill-rate alert")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"calibration_provider_register_failed: {_e}")


# SP-30 OBS-02 (27/05): wheel_dist percentis provider para Prometheus.
try:
    from server.health_server import set_wheel_dist_provider as _set_wd_p
    import time as _time_wd

    _wd_cache = {"ts": 0.0, "val": {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0}}

    def _wheel_dist_snapshot():
        now = _time_wd.time()
        if now - _wd_cache["ts"] < 30.0:
            return _wd_cache["val"]
        try:
            repo = db_service.repository
            if hasattr(repo, "wheel_dist_stats"):
                val = repo.wheel_dist_stats(window_minutes=60)
            else:
                val = {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
            _wd_cache["val"] = val
            _wd_cache["ts"] = now
            return val
        except Exception:
            return _wd_cache["val"]

    _set_wd_p(_wheel_dist_snapshot)
    logger.info("wheel_dist_provider_registered for SP-30 OBS-02")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"wheel_dist_provider_register_failed: {_e}")


# SP-29 OBS-01 (27/05): DNA realize lag provider.
try:
    from server.health_server import set_dna_realize_provider as _set_dna_p
    from database.dna_logger import dna_realize_stats as _dna_realize_stats
    import time as _time_dna

    _dna_cache = {"ts": 0.0, "val": {"unrealized": 0, "lag_seconds": 0}}

    def _dna_realize_snapshot():
        now = _time_dna.time()
        if now - _dna_cache["ts"] < 30.0:
            return _dna_cache["val"]
        try:
            val = _dna_realize_stats()
            _dna_cache["val"] = val
            _dna_cache["ts"] = now
            return val
        except Exception:
            return _dna_cache["val"]

    _set_dna_p(_dna_realize_snapshot)
    logger.info("dna_realize_provider_registered for SP-29 OBS-01")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"dna_realize_provider_register_failed: {_e}")


# S-OBS-8: provider de saúde do estado adaptativo persistido em /api/state
try:
    from server.health_server import set_state_provider as _set_state_p
    from app_config.settings import settings as _settings
    import os as _os

    def _state_snapshot():
        import time as _time
        adp = strategy.get_adaptive_state() if hasattr(strategy, "get_adaptive_state") else {}
        bet_state = {}
        try:
            if hasattr(game_state, "bet_advisor") and hasattr(game_state.bet_advisor, "state_dict"):
                bet_state = game_state.bet_advisor.state_dict()
        except Exception:  # noqa: BLE001
            pass
        sf = str(_settings.state_file)
        sf_size = None
        sf_age = None
        try:
            st = _os.stat(sf)
            sf_size = st.st_size
            sf_age = round(_time.time() - st.st_mtime, 1)
        except Exception:  # noqa: BLE001
            pass
        adp_keys = sorted(list(adp.keys())) if isinstance(adp, dict) else []
        sigmoid_off = adp.get("sigmoid_off", {}) if isinstance(adp, dict) else {}
        recent_hits = adp.get("recent_hits", {}) if isinstance(adp, dict) else {}
        recent_hits_lens = {k: len(v) if hasattr(v, "__len__") else 0 for k, v in recent_hits.items()}
        return {
            "adaptive_state_keys_count": len(adp_keys),
            "adaptive_state_keys": adp_keys,
            "sigmoid_off_populated": bool(sigmoid_off),
            "recent_hits_lens": recent_hits_lens,
            "bet_advisor_state": bet_state,
            "state_file_path": sf,
            "state_file_size_bytes": sf_size,
            "state_file_age_seconds": sf_age,
            "ts": int(_time.time()),
        }

    _set_state_p(_state_snapshot)
    logger.info("state_provider_registered for /api/state")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"state_provider_register_failed: {_e}")


async def broadcast_heartbeat():
    """Envia estado atual para todos os clientes a cada 1 segundo."""
    while True:
        await asyncio.sleep(1)
        
        if not connection_manager.active_connections_set:
            continue
        
        try:
            # Obter histórico de janelas FORA do lock (I/O não deve bloquear)
            window_history = await asyncio.to_thread(db_service.get_window_history)
            
            # Snapshot do estado com lock para evitar race condition
            async with state_lock:
                # Martingale da direção ALVO (próxima aposta)
                mg = game_state.target_martingale
                
                # Verificar se a última predição foi uma aposta real
                last_bet_placed = game_state.pending_prediction.get("bet_placed", False)
                
                state_sync = {
                    "type": "state_sync",
                    "data": {
                        "gale_level": mg.level,
                        "gale_display": mg.gale_display,
                        "martingale": mg.multiplier,
                        "aposta": mg.current_bet,
                        "last_number": game_state.last_number,
                        "target_direction": game_state.target_direction,
                        "performance": game_state.get_performance_stats(),
                        # Ambos Martingales para dashboard
                        "martingale_cw": game_state.martingale_cw.to_dict(),
                        "martingale_ccw": game_state.martingale_ccw.to_dict(),
                        "pending_prediction": game_state.pending_prediction,
                        # Histórico de janelas para visualização
                        "window_history": window_history,
                        # Flag para overlay saber se deve sincronizar Gale
                        "bet_placed": last_bet_placed,
                        "timestamp": now_ms()
                    }
                }
            
            message = json.dumps(state_sync)
            
            # Broadcast para todas as conexões
            await connection_manager.broadcast(message)
                
        except Exception as e:
            logger.error(f"Erro no heartbeat: {e}")


async def handler(websocket: WebSocketServerProtocol, path: str = "") -> None:
    """
    Handler principal de conexões WebSocket.
    
    Sistema MASTER/SLAVE:
    - Nova conexão SEMPRE vira MASTER
    - MASTER anterior vira SLAVE
    - Se MASTER desconectar, último SLAVE é promovido após grace period
    """
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    
    # Verificar auth (bypass mode por padrão)
    if not await verify_auth(None):
        logger.warning(f"Conexão rejeitada de {client_ip}: não autorizado")
        await websocket.close(4001, "Unauthorized")
        return
    
    # Registrar conexão e atribuir role
    conn_id = await connection_manager.connect(websocket)
    
    try:
        async for message in websocket:
            # Atualizar last_activity
            connection_manager.update_activity(conn_id)
            # Processar mensagem com o handler dedicado
            await message_handler.process_message(websocket, message, conn_id)
    except websockets.ConnectionClosed:
        logger.info(f"Conexão fechada de {client_ip} (ID: {conn_id})")
    finally:
        await connection_manager.disconnect(conn_id)


def get_ssl_context() -> Optional[ssl.SSLContext]:
    """Cria contexto SSL se habilitado."""
    if not settings.server.ssl_enabled:
        return None
    
    cert_path = Path(settings.server.ssl_cert)
    key_path = Path(settings.server.ssl_key)
    
    if not cert_path.exists() or not key_path.exists():
        logger.warning("Certificados SSL não encontrados. Iniciando sem SSL.")
        return None
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(cert_path, key_path)
    logger.info("SSL habilitado")
    return ssl_context


async def start_server() -> None:
    """Inicia o servidor WebSocket."""
    ssl_context = get_ssl_context()
    protocol = "wss" if ssl_context else "ws"
    
    logger.info(f"Iniciando servidor {protocol}://{settings.server.host}:{settings.server.port}")
    logger.info(f"Auth: {'ENABLED' if settings.auth.enabled else 'DISABLED (bypass)'}")
    logger.info(f"Timeline CW: {game_state.timeline_cw.size} forças")
    logger.info(f"Timeline CCW: {game_state.timeline_ccw.size} forças")
    
    # Iniciar heartbeat task
    asyncio.create_task(broadcast_heartbeat())
    logger.info("Heartbeat broadcast iniciado (intervalo: 1s)")
    
    async with websockets.serve(
        handler,
        settings.server.host,
        settings.server.port,
        ssl=ssl_context,
        ping_interval=20,
        ping_timeout=60
    ):
        logger.info("Servidor WebSocket rodando. Pressione Ctrl+C para parar.")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(start_server())
