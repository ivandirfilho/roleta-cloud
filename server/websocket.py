# Roleta Cloud - WebSocket Server

import asyncio
import json
import logging
import ssl
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Estado global
state_lock = asyncio.Lock()
game_state: GameState = GameState.load()
strategy = SDA17Strategy()  # SDA-17 com regressão linear
message_handler = MessageHandler(game_state, strategy, state_lock)


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
