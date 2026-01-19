# Roleta Cloud - WebSocket Server

import asyncio
import json
import ssl
import logging
from pathlib import Path
from typing import Set, Optional

import websockets
from websockets.server import WebSocketServerProtocol

import config
from auth.middleware import verify_auth
from models.input import SpinInput
from models.output import SuggestionOutput, AckOutput, ErrorOutput
from models.trace import TraceContext, now_ms
from state.game import GameState
from strategies.sda import SDAStrategy

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Estado global
game_state: GameState = GameState.load()
strategy = SDAStrategy(num_neighbors=5)  # SDA-11

# Conexões ativas
active_connections: Set[WebSocketServerProtocol] = set()


async def handle_message(websocket: WebSocketServerProtocol, message: str) -> None:
    """Processa uma mensagem recebida."""
    trace = None
    
    try:
        data = json.loads(message)
        msg_type = data.get("type", "spin")
        timestamp = data.get("timestamp", now_ms())
        trace_id = data.get("trace_id", str(timestamp))
        trace = TraceContext(trace_id=trace_id)
        trace.step("received", {"type": msg_type})
        
        # === NOVO RESULTADO (spin único) ===
        if msg_type == "novo_resultado":
            numero = data.get("numero")
            direcao = data.get("direcao", "horario")
            
            if numero is None:
                raise ValueError("Campo 'numero' obrigatório")
            
            # Processar spin
            force = game_state.process_spin(numero, direcao)
            trace.step("processed", {"numero": numero, "direcao": direcao, "force": force})
            
            # Salvar estado
            game_state.save()
            trace.step("saved")
            
            # Analisar com estratégia
            result = strategy.analyze(
                game_state.target_timeline,
                game_state.last_number,
                config.WHEEL_SEQUENCE
            )
            trace.step("analyzed", {"should_bet": result.should_bet, "score": result.score})
            
            # Determinar ação
            acao = "APOSTAR" if result.should_bet else "PULAR"
            
            # Formato esperado pelo overlay
            overlay_response = {
                "type": "sugestao",
                "data": {
                    "acao": acao,
                    "numeros": result.numbers,
                    "centro": result.center,
                    "regiao": result.visual,
                    "ultimo_numero": game_state.last_number,
                    "confianca": int(result.score / 6 * 100),
                    "martingale": "1x",
                    "estrategia": strategy.name,
                    "trace_id": trace_id,
                    "t_server": now_ms()
                }
            }
            
            await websocket.send(json.dumps(overlay_response))
            trace.step("sent")
            
            # Broadcast trace para dashboards conectados
            trace_broadcast = {
                "type": "trace",
                "trace_id": trace_id,
                "steps": trace.steps_dict,
                "total_ms": trace.total_ms(),
                "spin": {
                    "numero": numero,
                    "direcao": direcao,
                    "force": force
                },
                "result": {
                    "acao": acao,
                    "centro": result.center,
                    "score": result.score,
                    "numeros": result.numbers
                },
                "state": {
                    "timeline_cw": game_state.timeline_cw.size,
                    "timeline_ccw": game_state.timeline_ccw.size,
                    "last_number": game_state.last_number
                }
            }
            # Enviar para todas as conexões (dashboards receberão)
            for conn in active_connections:
                try:
                    await conn.send(json.dumps(trace_broadcast))
                except:
                    pass
            
            logger.info(trace.to_log_line())
        
        # === HISTÓRICO INICIAL (batch) ===
        elif msg_type == "historico_inicial":
            resultados = data.get("resultados", [])
            count = 0
            
            # IMPORTANTE: Extensão envia índice 0 = mais recente
            # Precisamos processar do mais antigo para o mais recente
            for item in reversed(resultados):
                numero = item.get("numero")
                direcao = item.get("direcao", "horario")
                if numero is not None:
                    game_state.process_spin(numero, direcao)
                    count += 1
            
            game_state.save()
            
            # ACK
            ack_response = {
                "type": "ack",
                "received": count,
                "message": f"Histórico inicial: {count} spins processados",
                "t_server": now_ms()
            }
            await websocket.send(json.dumps(ack_response))
            logger.info(f"Histórico inicial: {count} spins processados")
        
        # === CORREÇÃO DE HISTÓRICO ===
        elif msg_type == "correcao_historico":
            resultados = data.get("resultados", [])
            
            # Reset das timelines
            game_state.timeline_cw.clear()
            game_state.timeline_ccw.clear()
            game_state.last_number = 0
            game_state.last_direction = ""
            
            count = 0
            # Processar do mais antigo para o mais recente
            for item in reversed(resultados):
                numero = item.get("numero")
                direcao = item.get("direcao", "horario")
                if numero is not None:
                    game_state.process_spin(numero, direcao)
                    count += 1
            
            game_state.save()
            
            # ACK
            ack_response = {
                "type": "ack",
                "received": count,
                "message": f"Correção: {count} spins reprocessados",
                "t_server": now_ms()
            }
            await websocket.send(json.dumps(ack_response))
            logger.info(f"Correção histórico: {count} spins reprocessados")
        
        # === GET STATE (para dashboard) ===
        elif msg_type == "get_state":
            state_response = {
                "type": "state",
                "timeline_cw": game_state.timeline_cw.size,
                "timeline_ccw": game_state.timeline_ccw.size,
                "last_number": game_state.last_number,
                "last_direction": game_state.last_direction,
                "t_server": now_ms()
            }
            await websocket.send(json.dumps(state_response))
            logger.info("Estado enviado para dashboard")
        
        # === FORMATO ANTIGO (compatibilidade) ===
        else:
            # Tentar processar como SpinInput direto
            spin = SpinInput(**data)
            force = game_state.process_spin(spin.numero, spin.direcao)
            game_state.save()
            
            result = strategy.analyze(
                game_state.target_timeline,
                game_state.last_number,
                config.WHEEL_SEQUENCE
            )
            
            acao = "APOSTAR" if result.should_bet else "PULAR"
            
            overlay_response = {
                "type": "sugestao",
                "data": {
                    "acao": acao,
                    "numeros": result.numbers,
                    "centro": result.center,
                    "regiao": result.visual,
                    "ultimo_numero": game_state.last_number,
                    "confianca": int(result.score / 6 * 100),
                    "martingale": "1x",
                    "estrategia": strategy.name,
                    "trace_id": spin.trace_id,
                    "t_server": now_ms()
                }
            }
            await websocket.send(json.dumps(overlay_response))
            logger.info(trace.to_log_line())
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido: {e}")
        error = ErrorOutput(
            trace_id=trace.trace_id if trace else "unknown",
            code=400,
            message=f"JSON inválido: {str(e)}",
            t_server=now_ms()
        )
        await websocket.send(error.model_dump_json())
        
    except Exception as e:
        logger.error(f"Erro ao processar: {e}")
        error = ErrorOutput(
            trace_id=trace.trace_id if trace else "unknown",
            code=500,
            message=str(e),
            t_server=now_ms()
        )
        await websocket.send(error.model_dump_json())


async def handler(websocket: WebSocketServerProtocol, path: str = "") -> None:
    """Handler principal de conexões WebSocket."""
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    logger.info(f"Nova conexão de {client_ip}")
    
    # Verificar auth (bypass mode por padrão)
    # Em produção, o token viria no primeiro frame ou query param
    if not await verify_auth(None):
        logger.warning(f"Conexão rejeitada de {client_ip}: não autorizado")
        await websocket.close(4001, "Unauthorized")
        return
    
    active_connections.add(websocket)
    
    try:
        async for message in websocket:
            await handle_message(websocket, message)
    except websockets.ConnectionClosed:
        logger.info(f"Conexão fechada de {client_ip}")
    finally:
        active_connections.discard(websocket)


def get_ssl_context() -> Optional[ssl.SSLContext]:
    """Cria contexto SSL se habilitado."""
    if not config.SSL_ENABLED:
        return None
    
    cert_path = Path(config.SSL_CERT)
    key_path = Path(config.SSL_KEY)
    
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
    
    logger.info(f"Iniciando servidor {protocol}://{config.WS_HOST}:{config.WS_PORT}")
    logger.info(f"Auth: {'ENABLED' if config.AUTH_ENABLED else 'DISABLED (bypass)'}")
    logger.info(f"Timeline CW: {game_state.timeline_cw.size} forças")
    logger.info(f"Timeline CCW: {game_state.timeline_ccw.size} forças")
    
    async with websockets.serve(
        handler,
        config.WS_HOST,
        config.WS_PORT,
        ssl=ssl_context,
        ping_interval=20,
        ping_timeout=60
    ):
        logger.info("Servidor WebSocket rodando. Pressione Ctrl+C para parar.")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(start_server())
