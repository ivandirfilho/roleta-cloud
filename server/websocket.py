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
from strategies.sda17 import SDA17Strategy
from database import get_repository
from database.models import Decision, Session
import uuid

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
strategy = SDA17Strategy()  # SDA-17 com regressão linear

# Conexões ativas
active_connections: Set[WebSocketServerProtocol] = set()

# Lock para acesso thread-safe ao game_state
state_lock = asyncio.Lock()

# Session ID para logging
current_session_id: str = str(uuid.uuid4())[:8]

# Última decisão ID para atualizar resultado
last_decision_id: int = None


async def broadcast_heartbeat():
    """Envia estado atual para todos os clientes a cada 1 segundo."""
    while True:
        await asyncio.sleep(1)
        
        if not active_connections:
            continue
        
        try:
            # Snapshot do estado com lock para evitar race condition
            async with state_lock:
                mg = game_state.martingale
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
                        "pending_prediction": game_state.pending_prediction,
                        "timestamp": now_ms()
                    }
                }
            
            message = json.dumps(state_sync)
            
            # Broadcast para todas as conexões (coletar desconectados separado)
            disconnected = set()
            for conn in active_connections:
                try:
                    await conn.send(message)
                except:
                    disconnected.add(conn)
            
            # Limpar desconectados APÓS iteração
            for conn in disconnected:
                active_connections.discard(conn)
                
        except Exception as e:
            logger.error(f"Erro no heartbeat: {e}")


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
            
            # Log da predição pendente antes de verificar
            pending = game_state.pending_prediction
            if pending:
                logger.info(f"VERIFICANDO: numero={numero}, centro_previsto={pending.get('center')}, numeros={pending.get('numbers', [])[:5]}...")
                logger.info(f"  {numero} in numeros? {numero in pending.get('numbers', [])}")
            
            # Verificar predição anterior (performance tracking)
            hit_result = game_state.check_prediction(numero)
            
            # Atualizar Martingale (se havia predição pendente)
            martingale_info = {}
            if pending and hit_result is not None:
                martingale_info = game_state.martingale.update(hit_result)
                if martingale_info.get("transition"):
                    logger.info(f"  MARTINGALE: {martingale_info['transition']}")
                logger.info(f"  Resultado: {'HIT' if hit_result else 'MISS'} | Gale {martingale_info.get('level_after', 1)} ({martingale_info.get('window_hits', 0)}/{martingale_info.get('window_count', 0)})")
            
            # Processar spin
            force = game_state.process_spin(numero, direcao)
            trace.step("processed", {
                "numero": numero,
                "direcao": direcao,
                "force": force,
                "prediction_hit": hit_result
            })
            
            # Salvar estado
            game_state.save()
            trace.step("saved")
            
            # Analisar com estratégia (incluindo calibração)
            result = strategy.analyze(
                game_state.target_timeline,
                game_state.last_number,
                config.WHEEL_SEQUENCE,
                calibration=game_state.target_calibration
            )
            trace.step("analyzed", {
                "should_bet": result.should_bet,
                "score": result.score,
                "trend": result.details.get("trend", ""),
                "calibration": game_state.target_calibration
            })
            
            # ====================================================
            # TRIPLE RATE ADVISOR - Pode vetar a aposta
            # ====================================================
            advice = game_state.get_bet_advice()
            trace.step("triple_rate", {
                "should_bet": advice.should_bet,
                "confidence": advice.confidence,
                "reason": advice.reason,
                "rates": {"c4": advice.c4_rate, "m6": advice.m6_rate, "l12": advice.l12_rate}
            })
            
            # Decisão combinada: Triple Rate pode VETAR
            action_reason = ""
            if not advice.should_bet:
                acao = "PULAR"
                action_reason = f"Triple Rate vetou: {advice.reason}"
                # NÃO armazenar predição quando Triple Rate veta
            elif result.should_bet:
                acao = "APOSTAR"
                action_reason = f"SDA17 + Triple Rate aprovaram ({advice.confidence})"
                # Armazenar predição para verificar no próximo spin
                game_state.store_prediction(
                    result.numbers,
                    game_state.target_direction,
                    result.center,
                    predicted_force=result.details.get("predicted_force", 0)
                )
            else:
                acao = "PULAR"
                action_reason = "SDA17 não recomendou (forças insuficientes)"
            
            # Obter info do martingale atual
            mg = game_state.martingale
            
            # ====================================================
            # LOGGING - Salvar decisão no banco de dados
            # ====================================================
            try:
                global last_decision_id
                repo = get_repository()
                
                # Atualizar resultado da decisão anterior (se existia)
                if last_decision_id and hit_result is not None:
                    repo.update_result(last_decision_id, hit_result, numero)
                
                # Salvar nova decisão
                decision = Decision(
                    session_id=current_session_id,
                    spin_number=numero,
                    spin_direction=direcao,
                    spin_force=force,
                    tr_should_bet=advice.should_bet,
                    tr_confidence=advice.confidence,
                    tr_reason=advice.reason,
                    tr_c4_rate=advice.c4_rate,
                    tr_m6_rate=advice.m6_rate,
                    tr_l12_rate=advice.l12_rate,
                    sda_should_bet=result.should_bet,
                    sda_score=result.score,
                    sda_center=result.center,
                    sda_numbers=result.numbers,
                    sda_predicted_force=result.details.get("predicted_force", 0),
                    final_action=acao,
                    action_reason=action_reason,
                    gale_level=mg.level,
                    gale_window_hits=mg.window_hits,
                    gale_window_count=mg.window_count,
                    gale_bet_value=mg.current_bet,
                    calibration_offset=game_state.target_calibration,
                    performance_snapshot=game_state.target_performance[:12]
                )
                
                # Atualizar last_decision_id apenas se apostou
                if acao == "APOSTAR":
                    last_decision_id = repo.save_decision(decision)
                else:
                    repo.save_decision(decision)
                    last_decision_id = None  # Não há predição para verificar
                    
            except Exception as db_error:
                logger.warning(f"Erro ao salvar decisão no DB: {db_error}")
            
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
                    "martingale": mg.multiplier,
                    "aposta": mg.current_bet,
                    "gale_level": mg.level,
                    "gale_display": mg.gale_display,
                    "estrategia": strategy.name,
                    "trace_id": trace_id,
                    "t_server": now_ms(),
                    # Novo: Triple Rate advice
                    "bet_advice": advice.to_dict(),
                    "action_reason": action_reason
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
                    "numeros": result.numbers,
                    "trend": result.details.get("trend", "")
                },
                "strategy": {
                    "name": strategy.name,
                    "description": getattr(strategy, 'description', ''),
                },
                "performance": game_state.get_performance_stats(),
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
    
    # Iniciar heartbeat task
    asyncio.create_task(broadcast_heartbeat())
    logger.info("Heartbeat broadcast iniciado (intervalo: 1s)")
    
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
