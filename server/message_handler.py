# Roleta Cloud - Message Handler

import asyncio
import json
import logging
import uuid
from typing import Optional, Dict, Any

from websockets.server import WebSocketServerProtocol

from app_config.settings import settings
from database.models import Decision
from database.service import db_service
from models.input import SpinInput
from models.output import ErrorOutput
from models.trace import TraceContext, now_ms
from server.connection_manager import connection_manager
from state.game import GameState
from strategies.base import StrategyBase

logger = logging.getLogger(__name__)

class MessageHandler:
    """Manipulador de mensagens WebSocket."""

    def __init__(self, game_state: GameState, strategy: StrategyBase, state_lock: asyncio.Lock):
        self.game_state = game_state
        self.strategy = strategy
        self.state_lock = state_lock
        self.current_session_id: str = str(uuid.uuid4())[:8]
        self.last_decision_id: Optional[int] = None
        self.last_spin_hash: str = ""

    def is_duplicate_spin(self, numero: int, timestamp: int) -> bool:
        """Verifica se é um spin duplicado (mesmo número no mesmo segundo)."""
        current_hash = f"{numero}_{timestamp // 1000}"
        if current_hash == self.last_spin_hash:
            return True
        self.last_spin_hash = current_hash
        return False

    async def process_message(self, websocket: WebSocketServerProtocol, message: str, conn_id: str) -> None:
        """Processa uma mensagem recebida."""
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
                role = connection_manager.get_role(conn_id)
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
                    if self.is_duplicate_spin(numero, timestamp):
                        logger.info(f"🔄 Spin duplicado ignorado: {numero}")
                        return

            # === Dispatch por tipo ===
            if msg_type == "novo_resultado":
                await self.handle_new_result(websocket, data, trace)
            elif msg_type == "historico_inicial":
                await self.handle_initial_history(websocket, data)
            elif msg_type == "correcao_historico":
                await self.handle_history_correction(websocket, data)
            elif msg_type == "nova_sessao":
                await self.handle_new_session(websocket, data)
            elif msg_type == "get_state":
                await self.handle_get_state(websocket)
            else:
                # Compatibilidade legado
                await self.handle_legacy_spin(websocket, data, trace)

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

    async def handle_new_result(self, websocket: WebSocketServerProtocol, data: Dict, trace: TraceContext):
        numero = data.get("numero")
        direcao = data.get("direcao", "horario")

        if numero is None:
            raise ValueError("Campo 'numero' obrigatório")

        # Validar range da roleta (0-36)
        if not isinstance(numero, int) or not 0 <= numero <= 36:
            raise ValueError(f"Número inválido: {numero} (deve ser 0-36)")

        # Log da predição pendente antes de verificar
        pending = self.game_state.pending_prediction
        if pending:
            logger.info(f"VERIFICANDO: numero={numero}, centro_previsto={pending.get('center')}, numeros={pending.get('numbers', [])[:5]}...")

        # Verificar predição anterior (performance tracking)
        hit_result = self.game_state.check_prediction(numero)

        # Atualizar Martingale da direção da predição (se havia predição E apostou)
        martingale_info = {}
        if pending and hit_result is not None and pending.get("bet_placed", False):
            # Martingale da direção que FOI apostada
            bet_direction = pending.get("direction", "")
            if bet_direction in ("cw", "horario"):
                martingale_info = self.game_state.martingale_cw.update(hit_result)
            else:
                martingale_info = self.game_state.martingale_ccw.update(hit_result)

            if martingale_info.get("transition"):
                logger.info(f"  MARTINGALE ({bet_direction}): {martingale_info['transition']}")
            logger.info(f"  Resultado: {'HIT' if hit_result else 'MISS'} | Gale {martingale_info.get('level_after', 1)} ({martingale_info.get('window_hits', 0)}/{martingale_info.get('window_count', 0)})")

            # Tracking de janelas para ML/Dashboard
            try:
                db_service.track_gale_window(
                    game_state=self.game_state,
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
        force = self.game_state.process_spin(numero, direcao)
        trace.step("processed", {
            "numero": numero,
            "direcao": direcao,
            "force": force,
            "prediction_hit": hit_result
        })

        # Salvar estado
        self.game_state.save()
        trace.step("saved")

        # Analisar com estratégia (incluindo calibração)
        result = self.strategy.analyze(
            self.game_state.target_timeline,
            self.game_state.last_number,
            settings.game.wheel_sequence,
            calibration=self.game_state.target_calibration
        )
        trace.step("analyzed", {
            "should_bet": result.should_bet,
            "score": result.score,
            "trend": result.details.get("trend", ""),
            "calibration": self.game_state.target_calibration
        })

        # ====================================================
        # TRIPLE RATE ADVISOR - Pode vetar a aposta
        # ====================================================
        advice = self.game_state.get_bet_advice()
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
                self.game_state.store_prediction(
                    result.numbers,
                    self.game_state.target_direction,
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
                self.game_state.store_prediction(
                    result.numbers,
                    self.game_state.target_direction,
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
        mg = self.game_state.target_martingale

        # ====================================================
        # LOGGING - Salvar decisão no banco de dados
        # ====================================================
        try:
            # Atualizar resultado da decisão anterior (se existia)
            if self.last_decision_id and hit_result is not None:
                db_service.update_result(self.last_decision_id, hit_result, numero)

            # Salvar nova decisão
            decision = Decision(
                session_id=self.current_session_id,
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
                calibration_offset=self.game_state.target_calibration,
                performance_snapshot=self.game_state.target_performance[:12]
            )

            # Atualizar last_decision_id apenas se apostou
            if acao == "APOSTAR":
                self.last_decision_id = db_service.save_decision(decision)
            else:
                db_service.save_decision(decision)
                self.last_decision_id = None  # Não há predição para verificar

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
                "ultimo_numero": self.game_state.last_number,
                "confianca": int(result.score / 6 * 100),
                "martingale": mg.multiplier,
                "aposta": mg.current_bet,
                "gale_level": mg.level,
                "gale_display": mg.gale_display,
                "estrategia": self.strategy.name,
                "trace_id": trace.trace_id,
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
            "trace_id": trace.trace_id,
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
                "name": self.strategy.name,
                "description": getattr(self.strategy, 'description', ''),
            },
            "performance": self.game_state.get_performance_stats(),
            "state": {
                "timeline_cw": self.game_state.timeline_cw.size,
                "timeline_ccw": self.game_state.timeline_ccw.size,
                "last_number": self.game_state.last_number
            }
        }
        await connection_manager.broadcast(json.dumps(trace_broadcast), exclude_disconnected=False)

        logger.info(trace.to_log_line())

    async def handle_initial_history(self, websocket: WebSocketServerProtocol, data: Dict):
        resultados = data.get("resultados", [])
        count = 0

        # IMPORTANTE: Extensão envia índice 0 = mais recente
        # Precisamos processar do mais antigo para o mais recente
        for item in reversed(resultados):
            numero = item.get("numero")
            direcao = item.get("direcao", "horario")
            if numero is not None:
                self.game_state.process_spin(numero, direcao)
                count += 1

        self.game_state.save()

        # ACK
        ack_response = {
            "type": "ack",
            "received": count,
            "message": f"Histórico inicial: {count} spins processados",
            "t_server": now_ms()
        }
        await websocket.send(json.dumps(ack_response))
        logger.info(f"Histórico inicial: {count} spins processados")

    async def handle_history_correction(self, websocket: WebSocketServerProtocol, data: Dict):
        resultados = data.get("resultados", [])

        # Reset das timelines
        self.game_state.timeline_cw.clear()
        self.game_state.timeline_ccw.clear()
        self.game_state.last_number = 0
        self.game_state.last_direction = ""

        count = 0
        # Processar do mais antigo para o mais recente
        for item in reversed(resultados):
            numero = item.get("numero")
            direcao = item.get("direcao", "horario")
            if numero is not None:
                self.game_state.process_spin(numero, direcao)
                count += 1

        self.game_state.save()

        # ACK
        ack_response = {
            "type": "ack",
            "received": count,
            "message": f"Correção: {count} spins reprocessados",
            "t_server": now_ms()
        }
        await websocket.send(json.dumps(ack_response))
        logger.info(f"Correção histórico: {count} spins reprocessados")

    async def handle_new_session(self, websocket: WebSocketServerProtocol, data: Dict):
        logger.info("🔄 RESET DE SESSÃO SOLICITADO")

        keep_last = data.get("manter_ultimo", False)

        async with self.state_lock:
            reset_info = self.game_state.reset_session(keep_last_number=keep_last)

            # Criar nova sessão no DB
            new_session_id = f"session_{now_ms()}"
            db_service.create_session(new_session_id)
            self.current_session_id = new_session_id

        # Resposta de confirmação
        response = {
            "type": "sessao_resetada",
            "data": {
                "success": True,
                "new_session_id": self.current_session_id,
                "reset_info": reset_info,
                "t_server": now_ms()
            }
        }
        await websocket.send(json.dumps(response))
        logger.info(f"✅ Sessão resetada: {self.current_session_id}")

    async def handle_get_state(self, websocket: WebSocketServerProtocol):
        state_response = {
            "type": "state",
            "timeline_cw": self.game_state.timeline_cw.size,
            "timeline_ccw": self.game_state.timeline_ccw.size,
            "last_number": self.game_state.last_number,
            "last_direction": self.game_state.last_direction,
            "t_server": now_ms()
        }
        await websocket.send(json.dumps(state_response))
        logger.info("Estado enviado para dashboard")

    async def handle_legacy_spin(self, websocket: WebSocketServerProtocol, data: Dict, trace: TraceContext):
        # Tentar processar como SpinInput direto
        spin = SpinInput(**data)
        self.game_state.process_spin(spin.numero, spin.direcao)
        self.game_state.save()

        result = self.strategy.analyze(
            self.game_state.target_timeline,
            self.game_state.last_number,
            settings.game.wheel_sequence
        )

        acao = "APOSTAR" if result.should_bet else "PULAR"

        overlay_response = {
            "type": "sugestao",
            "data": {
                "acao": acao,
                "numeros": result.numbers,
                "centro": result.center,
                "regiao": result.visual,
                "ultimo_numero": self.game_state.last_number,
                "confianca": int(result.score / 6 * 100),
                "martingale": "1x",
                "estrategia": self.strategy.name,
                "trace_id": spin.trace_id,
                "t_server": now_ms()
            }
        }
        await websocket.send(json.dumps(overlay_response))
        if trace:
            logger.info(trace.to_log_line())
