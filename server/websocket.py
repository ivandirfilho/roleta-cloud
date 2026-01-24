# Roleta Cloud - WebSocket Server

import asyncio
import json
import ssl
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, Optional, Dict

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
from database.models import Decision, Session, GaleWindow, WindowPlay
import uuid
from datetime import datetime

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


# ===== SISTEMA MASTER/SLAVE =====
@dataclass
class ConnectionInfo:
    """Informações de uma conexão WebSocket."""
    id: str
    websocket: WebSocketServerProtocol
    role: str  # "master" | "slave"
    connected_at: float  # timestamp
    last_activity: float = 0.0


# Dicionário de conexões ativas (substitui Set)
connections: Dict[str, ConnectionInfo] = {}

# ID do MASTER atual
master_id: Optional[str] = None

# Lock para operações de MASTER (promoção/rebaixamento)
master_lock = asyncio.Lock()

# Grace period antes de promover SLAVE (segundos)
MASTER_GRACE_PERIOD = 5

# Timestamp de quando MASTER desconectou (para grace period)
master_disconnect_time: Optional[float] = None

# Último spin hash para deduplicação
last_spin_hash: str = ""


# Propriedade para compatibilidade com código existente
@property
def active_connections_set() -> Set[WebSocketServerProtocol]:
    """Retorna set de websockets para compatibilidade."""
    return {c.websocket for c in connections.values()}


# Manter active_connections como variável global para compatibilidade
# Será atualizado dinamicamente
active_connections: Set[WebSocketServerProtocol] = set()
# ===== FIM MASTER/SLAVE =====


# Lock para acesso thread-safe ao game_state
state_lock = asyncio.Lock()

# Session ID para logging
current_session_id: str = str(uuid.uuid4())[:8]

# Última decisão ID para atualizar resultado
last_decision_id: int = None

# IDs das janelas ativas por direção
active_window_ids: dict = {"cw": None, "ccw": None}


def _init_active_window_ids():
    """
    Restaura active_window_ids do banco de dados após restart do servidor.
    Chamado na inicialização para evitar janelas órfãs.
    """
    global active_window_ids
    try:
        repo = get_repository()
        for dir_key in ["cw", "ccw"]:
            window = repo.get_active_window(dir_key)
            if window:
                active_window_ids[dir_key] = window.id
                logger.info(f"[GALE_WINDOW] Restaurada janela ativa ID={window.id} dir={dir_key}")
    except Exception as e:
        logger.warning(f"Erro ao restaurar janelas ativas: {e}")


# Inicializar janelas ativas do DB
_init_active_window_ids()


def track_gale_window(
    direction: str,
    hit: bool,
    martingale_info: dict,
    pending: dict,
    force: int,
    numero: int,
    advice_confidence: str = "",
    advice_reason: str = "",
    sda_score: int = 0
) -> None:
    """
    Gerencia o tracking de janelas de Martingale no banco de dados.
    Chamado após cada atualização do martingale.
    """
    global active_window_ids
    repo = get_repository()
    
    # Normalizar direção
    dir_key = "cw" if direction in ("cw", "horario") else "ccw"
    
    # Obter ou criar janela ativa
    window_id = active_window_ids.get(dir_key)
    
    # Se é a primeira jogada da janela (window_count == 1), criar nova janela
    if martingale_info.get("window_count", 0) == 1:
        # Se tinha janela ativa anterior, fechar primeiro (caso edge)
        if window_id is not None:
            logger.warning(f"Fechando janela órfã {window_id} para {dir_key}")
            repo.close_gale_window(window_id, "orphan", 1)
        
        # Obter taxas atuais para ML features
        stats = game_state.get_performance_stats()
        sda_rate = stats.get(f"sda17_{dir_key}", {}).get("rate", 0)
        bet_rate = stats.get(f"bet_{dir_key}", {}).get("rate", 0)
        calibration = game_state.calibration_cw if dir_key == "cw" else game_state.calibration_ccw
        
        # Criar nova janela
        new_window = GaleWindow(
            direction=dir_key,
            gale_level=martingale_info.get("level_before", 1),
            sda17_rate_at_start=sda_rate,
            bet_rate_at_start=bet_rate,
            calibration_offset=calibration.offset if calibration else 0
        )
        window_id = repo.create_gale_window(new_window)
        active_window_ids[dir_key] = window_id
        logger.info(f"[GALE_WINDOW] Nova janela criada ID={window_id} dir={dir_key} level={new_window.gale_level}")
    
    # Adicionar play à janela ativa
    if window_id is not None:
        play = WindowPlay(
            window_id=window_id,
            play_number=martingale_info.get("window_count", 0),
            spin_number=numero,
            spin_direction=direction,
            spin_force=force,
            center_predicted=pending.get("center", 0),
            hit=hit,
            actual_number=numero,
            sda_score=sda_score,
            tr_confidence=advice_confidence,
            tr_reason=advice_reason
        )
        repo.add_window_play(play)
        logger.debug(f"[GALE_WINDOW] Play adicionado: window={window_id} play={play.play_number} hit={hit}")
    
    # Se teve transição de janela (5 plays completos), fechar
    transition = martingale_info.get("transition", "")
    if transition:
        if window_id is not None:
            # Determinar resultado
            if "SUCESSO" in transition:
                result = "success"
            elif "SUBINDO" in transition:
                result = "escalated"
            else:  # STOP
                result = "stop"
            
            next_level = martingale_info.get("level_after", 1)
            repo.close_gale_window(window_id, result, next_level)
            logger.info(f"[GALE_WINDOW] Janela fechada ID={window_id} result={result} next_level={next_level}")
        
        # Limpar referência para nova janela
        active_window_ids[dir_key] = None


async def broadcast_heartbeat():
    """Envia estado atual para todos os clientes a cada 1 segundo."""
    while True:
        await asyncio.sleep(1)
        
        if not active_connections:
            continue
        
        try:
            # Obter histórico de janelas FORA do lock (I/O não deve bloquear)
            try:
                repo = get_repository()
                window_history = {
                    "cw": repo.get_window_history("cw", limit=5),
                    "ccw": repo.get_window_history("ccw", limit=5)
                }
            except Exception as db_err:
                logger.warning(f"Erro ao obter window_history: {db_err}")
                window_history = {"cw": [], "ccw": []}
            
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


def is_duplicate_spin(numero: int, timestamp: int) -> bool:
    """Verifica se é um spin duplicado (mesmo número no mesmo segundo)."""
    global last_spin_hash
    current_hash = f"{numero}_{timestamp // 1000}"
    if current_hash == last_spin_hash:
        return True
    last_spin_hash = current_hash
    return False


def get_connection_role(conn_id: str) -> str:
    """Retorna o role de uma conexão."""
    if conn_id in connections:
        return connections[conn_id].role
    return "unknown"


async def handle_message(websocket: WebSocketServerProtocol, message: str, conn_id: str = "") -> None:
    """
    Processa uma mensagem recebida.
    
    Verifica se a conexão tem permissão para enviar dados (apenas MASTER).
    """
    global current_session_id
    trace = None
    
    try:
        data = json.loads(message)
        msg_type = data.get("type", "spin")
        timestamp = data.get("timestamp", now_ms())
        trace_id = data.get("trace_id", str(timestamp))
        trace = TraceContext(trace_id=trace_id)
        trace.step("received", {"type": msg_type})
        
        # === VERIFICAÇÃO DE ROLE PARA MENSAGENS DE DADOS ===
        data_messages = ["novo_resultado", "historico_inicial", "correcao_historico"]
        if msg_type in data_messages:
            role = get_connection_role(conn_id)
            if role != "master":
                logger.warning(f"⚠️ SLAVE {conn_id} tentou enviar {msg_type} - ignorando")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": f"Apenas MASTER pode enviar {msg_type}. Seu role: {role}",
                    "code": "NOT_MASTER"
                }))
                return
            
            # Deduplicação para novo_resultado
            if msg_type == "novo_resultado":
                numero = data.get("numero")
                if is_duplicate_spin(numero, timestamp):
                    logger.info(f"🔄 Spin duplicado ignorado: {numero}")
                    return
        
        # === NOVO RESULTADO (spin único) ===
        if msg_type == "novo_resultado":
            numero = data.get("numero")
            direcao = data.get("direcao", "horario")
            
            if numero is None:
                raise ValueError("Campo 'numero' obrigatório")
            
            # Validar range da roleta (0-36)
            if not isinstance(numero, int) or not 0 <= numero <= 36:
                raise ValueError(f"Número inválido: {numero} (deve ser 0-36)")
            
            # Log da predição pendente antes de verificar
            pending = game_state.pending_prediction
            if pending:
                logger.info(f"VERIFICANDO: numero={numero}, centro_previsto={pending.get('center')}, numeros={pending.get('numbers', [])[:5]}...")
                logger.info(f"  {numero} in numeros? {numero in pending.get('numbers', [])}")
            
            # Verificar predição anterior (performance tracking)
            hit_result = game_state.check_prediction(numero)
            
            # Atualizar Martingale da direção da predição (se havia predição E apostou)
            martingale_info = {}
            if pending and hit_result is not None and pending.get("bet_placed", False):
                # Martingale da direção que FOI apostada
                bet_direction = pending.get("direction", "")
                if bet_direction in ("cw", "horario"):
                    martingale_info = game_state.martingale_cw.update(hit_result)
                else:
                    martingale_info = game_state.martingale_ccw.update(hit_result)
                    
                if martingale_info.get("transition"):
                    logger.info(f"  MARTINGALE ({bet_direction}): {martingale_info['transition']}")
                logger.info(f"  Resultado: {'HIT' if hit_result else 'MISS'} | Gale {martingale_info.get('level_after', 1)} ({martingale_info.get('window_hits', 0)}/{martingale_info.get('window_count', 0)})")
                
                # Tracking de janelas para ML/Dashboard
                try:
                    track_gale_window(
                        direction=bet_direction,
                        hit=hit_result,
                        martingale_info=martingale_info,
                        pending=pending,
                        force=pending.get("predicted_force", 0),
                        numero=numero,
                        advice_confidence=pending.get("tr_confidence", ""),
                        advice_reason=pending.get("tr_reason", ""),
                        sda_score=pending.get("sda_score", 0)
                    )
                except Exception as e:
                    logger.error(f"Erro ao trackear gale window: {e}")
            
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
            if result.should_bet:
                # SDA17 recomenda: SEMPRE registrar para Triple Rate (bet_placed depende do veto)
                if advice.should_bet:
                    acao = "APOSTAR"
                    action_reason = f"SDA17 + Triple Rate aprovaram ({advice.confidence})"
                    # Registrar com bet_placed=True (realmente apostou)
                    game_state.store_prediction(
                        result.numbers,
                        game_state.target_direction,
                        result.center,
                        predicted_force=result.details.get("predicted_force", 0),
                        bet_placed=True,
                        tr_confidence=advice.confidence,
                        tr_reason=advice.reason,
                        sda_score=result.score
                    )
                else:
                    acao = "PULAR"
                    action_reason = f"Triple Rate vetou: {advice.reason}"
                    # SDA17 recomendou mas TR vetou - registrar para TR com bet_placed=False
                    game_state.store_prediction(
                        result.numbers,
                        game_state.target_direction,
                        result.center,
                        predicted_force=result.details.get("predicted_force", 0),
                        bet_placed=False,  # Não apostou, mas registra para análise TR
                        tr_confidence=advice.confidence,
                        tr_reason=advice.reason,
                        sda_score=result.score
                    )
            else:
                acao = "PULAR"
                action_reason = "SDA17 não recomendou (forças insuficientes)"
                # SDA17 não recomendou - não há predição para verificar
            
            # Obter info do martingale da direção ALVO (para overlay)
            mg = game_state.target_martingale
            
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
        
        # === NOVA SESSÃO (reset de dealer/mesa) ===
        elif msg_type == "nova_sessao":
            logger.info("🔄 RESET DE SESSÃO SOLICITADO")
            
            keep_last = data.get("manter_ultimo", False)
            
            async with state_lock:
                reset_info = game_state.reset_session(keep_last_number=keep_last)
                
                # Criar nova sessão no DB
                new_session_id = f"session_{now_ms()}"
                try:
                    repo = get_repository()
                    from database.models import Session
                    repo.create_session(Session(id=new_session_id))
                    current_session_id = new_session_id
                except Exception as e:
                    logger.warning(f"Erro ao criar sessão no DB: {e}")
            
            # Resposta de confirmação
            response = {
                "type": "sessao_resetada",
                "data": {
                    "success": True,
                    "new_session_id": current_session_id,
                    "reset_info": reset_info,
                    "t_server": now_ms()
                }
            }
            await websocket.send(json.dumps(response))
            logger.info(f"✅ Sessão resetada: {current_session_id}")
        
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
    """
    Handler principal de conexões WebSocket.
    
    Sistema MASTER/SLAVE:
    - Nova conexão SEMPRE vira MASTER
    - MASTER anterior vira SLAVE
    - Se MASTER desconectar, último SLAVE é promovido após grace period
    """
    global master_id, master_disconnect_time
    
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    conn_id = str(uuid.uuid4())[:8]
    logger.info(f"Nova conexão de {client_ip} (ID: {conn_id})")
    
    # Verificar auth (bypass mode por padrão)
    if not await verify_auth(None):
        logger.warning(f"Conexão rejeitada de {client_ip}: não autorizado")
        await websocket.close(4001, "Unauthorized")
        return
    
    # === ATRIBUIR ROLE ===
    async with master_lock:
        # Nova conexão SEMPRE vira MASTER
        if master_id and master_id in connections:
            # Rebaixar MASTER atual para SLAVE
            old_master = connections[master_id]
            old_master.role = "slave"
            try:
                await old_master.websocket.send(json.dumps({
                    "type": "role_changed",
                    "role": "slave",
                    "reason": "Novo dispositivo conectou"
                }))
                logger.info(f"👑→📱 {master_id} rebaixado para SLAVE")
            except:
                pass  # Conexão pode ter fechado
        
        # Nova conexão é MASTER
        master_id = conn_id
        master_disconnect_time = None  # Cancelar grace period se houver
        
        connections[conn_id] = ConnectionInfo(
            id=conn_id,
            websocket=websocket,
            role="master",
            connected_at=time.time(),
            last_activity=time.time()
        )
        
        # Atualizar set de compatibilidade
        active_connections.add(websocket)
    
    # Notificar nova conexão sobre seu role
    await websocket.send(json.dumps({
        "type": "role_assigned",
        "role": "master",
        "connection_id": conn_id
    }))
    logger.info(f"👑 {conn_id} atribuído como MASTER")
    
    try:
        async for message in websocket:
            # Atualizar last_activity
            if conn_id in connections:
                connections[conn_id].last_activity = time.time()
            await handle_message(websocket, message, conn_id)
    except websockets.ConnectionClosed:
        logger.info(f"Conexão fechada de {client_ip} (ID: {conn_id})")
    finally:
        await handle_disconnect(conn_id, websocket)


async def handle_disconnect(conn_id: str, websocket: WebSocketServerProtocol) -> None:
    """
    Gerencia desconexão de um cliente.
    Se for MASTER, inicia grace period e depois promove SLAVE.
    """
    global master_id, master_disconnect_time
    
    async with master_lock:
        # Remover da lista de conexões
        if conn_id in connections:
            del connections[conn_id]
        
        # Remover do set de compatibilidade
        active_connections.discard(websocket)
        
        # Se era o MASTER, precisamos promover alguém
        if conn_id == master_id:
            logger.info(f"👑 MASTER {conn_id} desconectou - iniciando grace period de {MASTER_GRACE_PERIOD}s")
            master_disconnect_time = time.time()
            master_id = None
    
    # Grace period (fora do lock para não bloquear)
    if master_disconnect_time:
        await asyncio.sleep(MASTER_GRACE_PERIOD)
        
        # Verificar se ainda precisa promover (pode ter reconectado)
        async with master_lock:
            if master_id is None and connections:
                # Promover último SLAVE (mais recente = LIFO)
                slaves = sorted(
                    connections.values(),
                    key=lambda c: c.connected_at,
                    reverse=True  # Mais recente primeiro
                )
                
                if slaves:
                    new_master = slaves[0]
                    new_master.role = "master"
                    master_id = new_master.id
                    master_disconnect_time = None
                    
                    try:
                        await new_master.websocket.send(json.dumps({
                            "type": "role_changed",
                            "role": "master",
                            "reason": "MASTER anterior desconectou"
                        }))
                        logger.info(f"📱→👑 {new_master.id} promovido a MASTER")
                    except:
                        pass


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
