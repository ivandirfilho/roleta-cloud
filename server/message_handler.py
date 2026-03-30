# Roleta Cloud - Message Handler

import asyncio
import json
import logging
import uuid
from typing import Optional, Dict, Any

from websockets.server import WebSocketServerProtocol

from app_config.settings import settings
from core.roulette import roulette
from database.models import Decision
from database.service import db_service
from models.input import SpinInput
from models.output import ErrorOutput
from models.trace import TraceContext, now_ms
from server.connection_manager import connection_manager
from state.game import GameState
from strategies.base import StrategyBase
from server.extractor_service import ExtractorService
from server.analytics_handler import analytics_handler

logger = logging.getLogger(__name__)

class MessageHandler:
    """Manipulador de mensagens WebSocket."""

    def __init__(self, game_state: GameState, strategy: StrategyBase, state_lock: asyncio.Lock, configs_path: str):
        self.game_state = game_state
        self.strategy = strategy
        self.state_lock = state_lock
        self.current_session_id: str = str(uuid.uuid4())[:8]
        self.last_decision_id: Optional[int] = None
        self.last_spin_hash: str = ""
        self._decision_count: int = 0
        self.extractor_service = ExtractorService(configs_path)

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
            elif msg_type == "register":
                device_id = data.get("device_id")
                logger.info(f"📩 Recebido REGISTER de {conn_id} com device_id={device_id}")
                await connection_manager.update_device_id(conn_id, device_id)
            elif msg_type == "force_master":
                await connection_manager.force_master(conn_id)
            elif msg_type == "extrair_mesa":
                await self.handle_extrair_mesa(websocket, data, trace)
            elif msg_type == "listar_mesas":
                await self.handle_listar_mesas(websocket)
            elif msg_type == "obter_config_mesa":
                await self.handle_get_mesa_config(websocket, data)
            elif msg_type.startswith("get_analytics") or msg_type in (
                "get_sessions_list", "get_gale_history",
                "get_performance_timeline", "get_decision_log"
            ):
                response = await analytics_handler.handle_analytics(msg_type, data)
                await websocket.send(json.dumps(response))
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
        # Validação via Pydantic (campos obrigatórios de entrada)
        try:
            spin = SpinInput(
                numero=data.get("numero", -1),
                direcao=data.get("direcao", "horario"),
                trace_id=trace.trace_id if trace else "auto",
                t_client=data.get("t_client", 0)
            )
            numero = spin.numero
            direcao = spin.direcao
        except Exception as e:
            raise ValueError(f"Entrada inválida: {e}")

        # Log da predição pendente antes de verificar
        pending = self.game_state.pending_prediction
        if pending:
            logger.info(f"VERIFICANDO: numero={numero}, centro_previsto={pending.get('center')}, numeros={pending.get('numbers', [])[:5]}...")

        # Verificar predição anterior (performance tracking)
        async with self.state_lock:
            hit_result = self.game_state.check_prediction(numero)

            # Atualizar Martingale da direção da predição (se havia predição E apostou)
            # NOTA: bet_direction vem de pending_prediction["direction"] que é target_direction
            #        (oposto de last_direction), ou seja, a direção que FOI predita/apostada.
            martingale_info = {}
            if pending and hit_result is not None and pending.get("bet_placed", False):
                # Martingale da direção que FOI apostada
                bet_direction = pending.get("direction", "")
                if bet_direction in ("cw", "horario"):
                    martingale_info = self.game_state.martingale_cw.update(hit_result, global_hit=hit_result)
                    self.game_state.martingale_ccw.sync_global(hit_result)
                else:
                    martingale_info = self.game_state.martingale_ccw.update(hit_result, global_hit=hit_result)
                    self.game_state.martingale_cw.sync_global(hit_result)

                if martingale_info.get("transition"):
                    logger.info(f"  MARTINGALE ({bet_direction}): {martingale_info['transition']}")
                logger.info(f"  Resultado: {'HIT' if hit_result else 'MISS'} | Gale {martingale_info.get('level_after', 1)} | Streak {martingale_info.get('consecutive_hits', 0)}")

                # Log distância ao centro predito (diagnóstico E4)
                sda_centers = pending.get("sda_centers", [])
                if sda_centers:
                    wheel = roulette.WHEEL_SEQUENCE
                    try:
                        idx_actual = wheel.index(numero)
                        min_dist = min(
                            min(abs(idx_actual - wheel.index(c)), len(wheel) - abs(idx_actual - wheel.index(c)))
                            for c in sda_centers if c in wheel
                        )
                        logger.info(f"  DISTÂNCIA: {min_dist} casas do centro mais próximo (centros={sda_centers})")
                    except (ValueError, TypeError):
                        pass

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

            # ★ M15-ADA: Atualizar estado adaptativo com resultado real
            if pending and hit_result is not None:
                bet_direction = pending.get("direction", "")
                c1_predicted = pending.get("center", 0)
                if c1_predicted > 0:
                    self.strategy.update_adaptive(
                        bet_direction, c1_predicted, numero, roulette.WHEEL_SEQUENCE
                    )
                    # Persistir estado adaptativo no GameState
                    self.game_state._adaptive_state = self.strategy.get_adaptive_state()

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

            # Analisar com estratégia (sem calibração momentum - removido)
            result = self.strategy.analyze(
                self.game_state.target_timeline,
                self.game_state.last_number,
                roulette.WHEEL_SEQUENCE,
                calibration=0  # Momentum desabilitado
            )
        trace.step("analyzed", {
            "should_bet": result.should_bet,
            "score": result.score,
            "trend": result.details.get("trend", ""),
            "calibration": 0
        })

        # ====================================================
        # TRIPLE RATE ADVISOR - Pode vetar a aposta
        # ====================================================
        advice = self.game_state.get_bet_advice(sda_score=result.score)
        trace.step("triple_rate", {
            "should_bet": advice.should_bet,
            "confidence": advice.confidence,
            "reason": advice.reason,
            "rates": {"c4": advice.c4_rate, "m6": advice.m6_rate, "l12": advice.l12_rate}
        })

        # Decisão combinada: Triple Rate pode VETAR
        action_reason = ""
        if result.should_bet:
            # SDA recomenda: SEMPRE registrar para Triple Rate (bet_placed depende do veto)
            if advice.should_bet:
                # SmartGale v5: calcular gale ANTES de registrar
                mg = self.game_state.target_martingale
                bet_c4_rate = self.game_state.get_bet_c4_rate()
                mg.get_gale(score=result.score, c4_rate=bet_c4_rate, confidence=advice.confidence)
                
                acao = "APOSTAR"
                action_reason = f"SDA score={result.score} | {mg.gale_display} | C4={bet_c4_rate:.0%}"
                # Registrar com bet_placed=True (realmente apostou)
                self.game_state.store_prediction(
                    result.numbers,
                    self.game_state.target_direction,
                    result.center,
                    predicted_force=result.details.get("predicted_force", 0),
                    bet_placed=True,
                    tr_confidence=advice.confidence,
                    tr_reason=advice.reason,
                    sda_score=result.score,
                    sda_centers=result.details.get("centers", [result.center])
                )
            else:
                acao = "PULAR"
                action_reason = f"Triple Rate vetou: {advice.reason}"
                # SDA recomendou mas TR vetou - registrar para TR com bet_placed=False
                self.game_state.store_prediction(
                    result.numbers,
                    self.game_state.target_direction,
                    result.center,
                    predicted_force=result.details.get("predicted_force", 0),
                    bet_placed=False,  # Não apostou, mas registra para análise TR
                    tr_confidence=advice.confidence,
                    tr_reason=advice.reason,
                    sda_score=result.score,
                    sda_centers=result.details.get("centers", [result.center])
                )
        else:
            acao = "PULAR"
            action_reason = "SDA não recomendou (forças insuficientes)"
            # Fallback early-session: timeline com dados mas SDA insuficiente → G1 seguro
            if self.game_state.target_timeline.size > 0:
                mg = self.game_state.target_martingale
                mg.level = 1
                center = self.game_state.last_number
                fallback_nums = sorted(
                    self.strategy.get_neighbors(center, 10, roulette.WHEEL_SEQUENCE)
                )
                acao = "APOSTAR"
                action_reason = f"SDA insuficiente ({self.game_state.target_timeline.size} forças) → G1 seguro"
                self.game_state.store_prediction(
                    fallback_nums, self.game_state.target_direction, center,
                    predicted_force=0, bet_placed=True,
                    tr_confidence="baixa", tr_reason="Fallback early-session",
                    sda_score=1, sda_centers=[center]
                )
            # SDA não recomendou - não há predição para verificar

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
                sda_centers=result.details.get("centers", [result.center]),
                sda_numbers=result.numbers,
                sda_predicted_force=result.details.get("predicted_force", 0),
                sda_offset=result.details.get("offset", 0),
                sda_offset_type=result.details.get("offset_type", ""),
                final_action=acao,
                action_reason=action_reason,
                gale_level=mg.level,
                gale_window_hits=mg.consecutive_hits,
                gale_window_count=mg.total_bets,
                gale_bet_value=mg.current_bet,
                calibration_offset=0,
                performance_snapshot=self.game_state.target_performance[:12]
            )

            # Rastrear todas as decisões que têm predição (APOSTAR e PULAR com SDA)
            decision_id = db_service.save_decision(decision)
            if result.should_bet:
                # SDA gerou predição → rastrear para verificar no próximo spin
                self.last_decision_id = decision_id
            else:
                # SDA não recomendou → sem predição para verificar
                self.last_decision_id = None

            # Atualizar stats da sessão a cada 10 decisões
            self._decision_count += 1
            if self._decision_count % 10 == 0:
                db_service.update_session_stats(self.current_session_id)

        except Exception as db_error:
            logger.warning(f"Erro ao salvar decisão no DB: {db_error}")

        # Formato esperado pelo overlay
        overlay_response = {
            "type": "sugestao",
            "data": {
                "acao": acao,
                "numeros": result.numbers,
                "centro": result.center,
                "centros": result.details.get("centers", [result.center]),
                "regiao": result.visual,
                "ultimo_numero": self.game_state.last_number,
                "confianca": {"alta": 80, "media": 50, "baixa": 20}.get(advice.confidence, 50),
                "martingale": mg.multiplier,
                "aposta": mg.current_bet,
                "gale_level": mg.level,
                "gale_display": mg.gale_display,
                "gale_reasoning": action_reason,
                "consecutive_hits": mg.consecutive_hits,
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
                "centros": result.details.get("centers", [result.center]),
                "score": result.score,
                "numeros": result.numbers,
                "unique_count": result.details.get("unique_count", len(result.numbers)),
                "trend": result.details.get("trend", ""),
                "offset": result.details.get("offset", 12),
                "offset_type": result.details.get("offset_type", "fixed"),
                "cw_ema": result.details.get("cw_ema", 12.0),
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
            # Finalizar sessão anterior (atualiza stats + end_time)
            if self.current_session_id:
                db_service.end_session(self.current_session_id)

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
            roulette.WHEEL_SEQUENCE
        )

        acao = "APOSTAR" if result.should_bet else "PULAR"

        overlay_response = {
            "type": "sugestao",
            "data": {
                "acao": acao,
                "numeros": result.numbers,
                "centro": result.center,
                "centros": result.details.get("centers", [result.center]),
                "regiao": result.visual,
                "ultimo_numero": self.game_state.last_number,
                "confianca": int(result.score / 6 * 100),  # Legacy: sem Triple Rate
                "martingale": "1x",
                "estrategia": self.strategy.name,
                "trace_id": spin.trace_id,
                "t_server": now_ms()
            }
        }
        await websocket.send(json.dumps(overlay_response))
        if trace:
            logger.info(trace.to_log_line())

    async def handle_extrair_mesa(self, websocket: WebSocketServerProtocol, data: Dict, trace: TraceContext):
        """Processa extração de mesa e salva config."""
        logger.info(f"📥 Recebida solicitação de extração: {data.get('url')}")
        result = await self.extractor_service.process_mesa(data)
        
        response = {
            "type": "mesa_configurada",
            "auto_start": True,
            **result
        }
        await websocket.send(json.dumps(response))
        if trace:
            trace.step("mesa_extraida", {"mesa_id": result.get("mesa_id")})

    async def handle_listar_mesas(self, websocket: WebSocketServerProtocol):
        """Retorna lista de mesas configuradas."""
        mesas = await self.extractor_service.list_mesas()
        await websocket.send(json.dumps({
            "type": "mesas_disponiveis",
            "mesas": mesas
        }))

    async def handle_get_mesa_config(self, websocket: WebSocketServerProtocol, data: Dict):
        """Retorna config de uma mesa específica."""
        mesa_id = data.get("mesa_id")
        config = await self.extractor_service.get_mesa_config(mesa_id)
        if config:
            await websocket.send(json.dumps({
                "type": "config_mesa",
                "mesa_id": mesa_id,
                "config": config
            }))
        else:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Mesa {mesa_id} não encontrada",
                "code": "MESA_NOT_FOUND"
            }))
