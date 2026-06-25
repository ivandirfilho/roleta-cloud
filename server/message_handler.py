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


def _build_sda_regions(result) -> list:
    """SP-16 REGION-01: monta lista enriquecida de regioes [C1, C2, C3].

    Hoje SDA17 expoe details['centers'] = [c1,c2,c3] e details['offset']/'offset_c3'
    (c1 sempre tem offset 0 por convencao SDA17). Empacotamos cada regiao com
    metadata estavel para SP-17 (calculo de realized_lift_pp por regiao).

    Retorna lista de dicts; vazia se result/details indisponivel.
    """
    try:
        d = getattr(result, "details", {}) or {}
        centers = d.get("centers") or []
        if not centers:
            return []
        off_c2 = int(d.get("offset", 0) or 0)
        off_c3 = int(d.get("offset_c3", 0) or 0)
        offsets = [0, off_c2, off_c3]
        score = int(getattr(result, "score", 0) or 0)
        offset_type = d.get("offset_type", "")
        regions = []
        for idx, c in enumerate(centers[:3]):
            regions.append({
                "slot": f"C{idx + 1}",
                "c": int(c),
                "offset": offsets[idx] if idx < len(offsets) else 0,
                "score": score,
                "offset_type": offset_type,
            })
        return regions
    except Exception:  # noqa: BLE001 — telemetria nunca quebra fluxo
        return []


class MessageHandler:
    """Manipulador de mensagens WebSocket."""

    def __init__(self, game_state: GameState, strategy: StrategyBase, state_lock: asyncio.Lock, configs_path: str):
        self.game_state = game_state
        self.strategy = strategy
        self.state_lock = state_lock
        self.current_session_id: str = str(uuid.uuid4())[:8]
        self.last_decision_id: Optional[int] = None
        self.last_spin_hash: str = ""
        self.last_spin_ts: Optional[float] = None  # S-OBS-6: epoch float do último spin
        # Phantom dedup (auditoria resultados_bancos 22/06): ultimo spin ACEITO
        # (numero/sentido/ts ms) p/ rejeitar re-envios do mesmo numero+sentido em
        # janela curta (extensao re-detecta o DOM estatico). Flag-gated, default OFF.
        self._last_accept_num: Optional[int] = None
        self._last_accept_dir: Optional[str] = None
        self._last_accept_ts_ms: Optional[int] = None
        self._decision_count: int = 0
        self.extractor_service = ExtractorService(configs_path)
        # IMPL C1/C2 variável + Block-Gale (17/06): metadados por spin (gated por flag).
        self._cs_meta = None
        self._bg_meta = None
        # Vision fill-forward (auditoria_pos_foto 21/06): último dealer REAL por
        # sessão, p/ propagar quando o giro chega sem dealer. Flag-gated, metadata
        # (não toca aposta). Ver core/dealer_fill.py + SDA_DEALER_FILL_FORWARD.
        self._ff_dealer: Optional[str] = None
        self._ff_session: Optional[str] = None
        # Vision-context fill-forward UNIFICADO (resultados_bancos 22/06): a foto/OCR
        # e' a fonte autoritativa de dealer/modelo/provider (o DOM da Evolution nao
        # os expoe). Propaga o ULTIMO valor real de cada um a TODA jogada da sessao,
        # p/ os dados ficarem 100% acoplados (auditaveis/estrategia). Metadata, nao
        # toca aposta. Mesma flag SDA_DEALER_FILL_FORWARD.
        self._ff_wheel: Optional[str] = None
        self._ff_provider: Optional[str] = None

    def _vision_ctx_reset_if_new_session(self) -> None:
        if self._ff_session != self.current_session_id:
            self._ff_dealer = None
            self._ff_wheel = None
            self._ff_provider = None
            self._ff_session = self.current_session_id

    def _apply_vision_context(self, raw_dealer, raw_wheel, raw_provider):
        """Resolve dealer/modelo/provider do giro com fill-forward do último OCR da
        sessão (flag SDA_DEALER_FILL_FORWARD). Devolve (dealer, wheel, provider).
        Metadata pura — nunca altera decisão de aposta. Corta na troca de sessão."""
        from core.dealer_fill import resolve_value
        from app_config.settings import dealer_fill_forward_enabled
        self._vision_ctx_reset_if_new_session()
        en = dealer_fill_forward_enabled()
        dealer, self._ff_dealer = resolve_value(raw_dealer, self._ff_dealer, en)
        wheel, self._ff_wheel = resolve_value(raw_wheel, self._ff_wheel, en)
        provider, self._ff_provider = resolve_value(raw_provider, self._ff_provider, en)
        return dealer, wheel, provider

    def _remember_vision(self, dealer, wheel_model, provider) -> None:
        """Registra os valores REAIS de um OCR (handle_foto_frame) como último
        conhecido da sessão, p/ os próximos giros herdarem (fill-forward)."""
        from core.dealer_fill import is_real_value
        self._vision_ctx_reset_if_new_session()
        if is_real_value(dealer):
            self._ff_dealer = str(dealer).strip()
        if is_real_value(wheel_model):
            self._ff_wheel = str(wheel_model).strip()
        if is_real_value(provider):
            self._ff_provider = str(provider).strip()

    def _resolve_spin_dealer(self, raw_dealer: Optional[str]) -> Optional[str]:
        """Vision fill-forward (21/06): resolve só o dealer (mantido p/ testes).
        Flag SDA_DEALER_FILL_FORWARD (default OFF); metadata, não toca aposta."""
        from core.dealer_fill import resolve_dealer
        from app_config.settings import dealer_fill_forward_enabled
        self._vision_ctx_reset_if_new_session()
        used, self._ff_dealer = resolve_dealer(
            raw_dealer, self._ff_dealer, dealer_fill_forward_enabled()
        )
        return used

    def _remember_dealer(self, dealer: Optional[str]) -> None:
        """Compat: registra só o dealer (delega ao vision-context unificado)."""
        self._remember_vision(dealer, None, None)

    def is_duplicate_spin(self, numero: int, timestamp: int, direcao: Optional[str] = None) -> bool:
        """Verifica se é um spin duplicado.

        (1) Mesmo número no MESMO segundo (guarda original).
        (2) PHANTOM (flag SDA_DEDUP_PHANTOM, default OFF): mesmo número+sentido do
            último spin ACEITO dentro de uma janela curta (SDA_DEDUP_PHANTOM_WINDOW_MS,
            default 20s). A extensão às vezes re-detecta o DOM estático e reenvia o
            mesmo resultado 1-7s depois (o ciclo real é ~42-48s), o que o engine
            processaria como giro real e corromperia a cadeia de predição/aposta.
            A JANELA DE TEMPO é o discriminador (não a força — força=0 é só a
            distância na roda de número repetido). Auditoria: resultados_bancos_junho.md.
        """
        current_hash = f"{numero}_{timestamp // 1000}"
        if current_hash == self.last_spin_hash:
            return True
        if direcao is not None and self._last_accept_ts_ms is not None:
            from app_config.settings import dedup_phantom_enabled, dedup_phantom_window_ms
            if (dedup_phantom_enabled()
                    and numero == self._last_accept_num
                    and direcao == self._last_accept_dir
                    and 0 <= (timestamp - self._last_accept_ts_ms) <= dedup_phantom_window_ms()):
                return True
        self.last_spin_hash = current_hash
        self._last_accept_num = numero
        self._last_accept_dir = direcao
        self._last_accept_ts_ms = timestamp
        return False

    def _is_duplicate_trace(self, trace_id: str) -> bool:
        """DIR6 (sentido-fase): idempotência por trace_id. Cada giro carrega um
        trace_id único do cliente; reenvios chegam com o mesmo. Janela de 64 —
        O(64) por checagem, trivial. Estado efêmero (não persiste)."""
        from collections import deque
        if getattr(self, "_recent_trace_ids", None) is None:
            self._recent_trace_ids = deque(maxlen=64)
        if trace_id in self._recent_trace_ids:
            return True
        self._recent_trace_ids.append(trace_id)
        return False

    # ================= IMPL C1/C2 variável + Block-Gale (17/06) =================
    # Motores isolados (state/block_gale.py, strategies/c_selection.py), gated por
    # flags (SDA_BET_PAIR, SDA_STAKING_MODE, GALE_CAP, GALE_ONLY_AFTER_GREEN).
    # Tudo defensivo: telemetria/override nunca quebra o fluxo (INV-3 preservado).

    def _engine_dk(self) -> str:
        d = self.game_state.target_direction
        return "cw" if d in ("cw", "horario") else "ccw"

    def _engine_apply_selection(self, result) -> None:
        """SDA_BET_PAIR: var_c1c2_c3 (voto C1/C2 + C3 fixo) OU c2c3/c1c3 (par
        ESTÁTICO fixo, sem voto) OU force17 (C1=ForceLast + 17#, 3 regiões).
        Substitui a cobertura. Mantém details['centers']=3 (continuidade de
        DNA/atribuição). Stasha _cs_meta."""
        self._cs_meta = None
        self.game_state.last_force17_meta = None
        try:
            from app_config.settings import bet_pair_mode
            mode = bet_pair_mode()
            if mode not in ("var_c1c2_c3", "c1c3", "c2c3", "force17"):
                return
            centers = list((getattr(result, "details", {}) or {}).get("centers") or [])
            if len(centers) < 3:
                return
            gs = self.game_state
            eng = gs.c_selection_engine
            if mode == "var_c1c2_c3":
                hist = list(gs.c_attr_cw if self._engine_dk() == "cw" else gs.c_attr_ccw)
                sel = eng.select(gs.target_direction, centers, hist, roulette.WHEEL_SEQUENCE)
            elif mode == "force17":
                # B4: o ForceLast lê os RESULTADOS BRUTOS do MESMO sentido (target),
                # de cw_history/ccw_history = [(c1, actual_result)] do SDA17 — NÃO as
                # distâncias de c_attr. target_direction é o oposto do último spin,
                # logo seu history não foi tocado por este spin (isolamento estável).
                dk = self._engine_dk()
                raw = getattr(self.strategy, "cw_history" if dk == "cw" else "ccw_history", []) or []
                last_results = [int(h[1]) for h in list(raw)[-2:]
                                if isinstance(h, (list, tuple)) and len(h) >= 2]
                from app_config.settings import force17_exact_enabled
                tn = 17 if force17_exact_enabled() else None
                sel = eng.force_select(gs.target_direction, centers, last_results,
                                       roulette.WHEEL_SEQUENCE, target_n=tn)
            else:
                sel = eng.static_select(gs.target_direction, centers, mode, roulette.WHEEL_SEQUENCE)
            if sel.numbers:
                result.numbers = list(sel.numbers)
            self._cs_meta = {
                "chosen": sel.chosen, "pair": f"{sel.chosen}+C3", "rule": sel.rule,
                "n": len(sel.numbers), "freeze": sel.freeze_candidates,
                "centers3": centers,
            }
            if (sel.scoreboard or {}).get("mode") == "force17":
                self._cs_meta["force17"] = {
                    "regioes": sel.scoreboard.get("regioes", []),
                    "c1_force": sel.scoreboard.get("c1_force"),
                    "coverage_n": sel.scoreboard.get("coverage_n", len(sel.numbers)),
                    "centros": list(sel.centers),
                    # fix BUG-FRONT #2: a cobertura viaja no meta force17 p/ o front
                    # render números e regiões da MESMA fonte (sem ler state stale).
                    "numeros": list(sel.numbers),
                }
            # Fonte única p/ os canais que o dashboard consome (trace/state_sync):
            # stasha no game_state (transiente, recomputado a cada spin, não persiste).
            self.game_state.last_force17_meta = (self._cs_meta or {}).get("force17")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[IMPL c_selection] falha: {e}")

    def _ensure_nonempty_coverage(self, result) -> None:
        """Sprint 0 / B1: a indicação NUNCA cobre zero números. Se a cobertura
        ficou vazia mas há ≥1 centro, emite a união dos centros (C2∪C3∪C1 se 3,
        senão a vizinhança do centro disponível) como rede de segurança. Corrige
        o bug pré-existente de ``sda_numbers=[]`` (~4% das decisões de calibração,
        message_handler.py comentário §615). Dispara só no caso quebrado (vazio),
        então preserva byte-identidade dos caminhos normais (full/c2c3/force17)."""
        try:
            if result.numbers:
                return
            centers = list((getattr(result, "details", {}) or {}).get("centers") or [])
            if len(centers) >= 3:
                from strategies.c_selection import coverage3
                nums = coverage3(centers[1], centers[2], centers[0], roulette.WHEEL_SEQUENCE)
            elif centers:
                nums = sorted(self.strategy.get_neighbors(centers[0], 3, roulette.WHEEL_SEQUENCE))
            else:
                return
            if nums:
                result.numbers = list(nums)
                logger.info("[B1 fix] cobertura vazia -> rede de seguranca N=%d", len(nums))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[B1 fix] falha: {e}")

    def _engine_apply_stake(self, stake_info, n_numbers, acao) -> None:
        """SDA_STAKING_MODE=block_gale: stake = nível do bloco-gale. O override de
        veto INV-3 (adiante) ainda aplica o piso/min. Stasha _bg_meta."""
        self._bg_meta = None
        try:
            from app_config.settings import staking_mode, gale_cap, gale_only_after_green
            if acao != "APOSTAR" or staking_mode() != "block_gale":
                return
            import os
            gs = self.game_state
            eng = gs.block_gale_engine
            eng.set_cap(gs.target_direction, gale_cap(gs.target_direction))
            eng.only_after_green = gale_only_after_green()
            try:
                base_bk = float(os.environ.get("GALE_BANKROLL", "1000"))
                pnl = db_service.get_session_pnl(self.current_session_id) or 0.0
            except Exception:  # noqa: BLE001
                base_bk, pnl = 1000.0, 0.0
            bankroll = max(0.0, base_bk + float(pnl))
            dec = eng.decide(gs.target_direction, bankroll, int(n_numbers))
            eff = dec["stake"] if dec["place"] else 0.0
            stake_info["effective_bet"] = int(round(eff))
            stake_info["base_bet"] = int(round(gs.block_gale_engine.base_unit * max(0, int(n_numbers))))
            stake_info["multiplier"] = float(dec["mult"])
            stake_info["mode"] = "block_gale"
            self._bg_meta = {"level": dec["level"], "cap": dec["cap"], "mult": dec["mult"],
                             "gated": dec["gated"], "solvent": dec["solvent"],
                             "placed": bool(dec["place"] and eff > 0)}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[IMPL block_gale] falha: {e}")

    def _engine_inject_pending(self) -> None:
        """Anexa metadados dos motores ao pending_prediction (resolução do próximo spin)."""
        try:
            p = self.game_state.pending_prediction
            if not p:
                return
            if self._cs_meta:
                p["shadow_candidates"] = self._cs_meta["freeze"]
                p["cs_chosen"] = self._cs_meta["chosen"]
            if self._bg_meta is not None:
                p["bg_placed"] = self._bg_meta["placed"]
        except Exception:  # noqa: BLE001
            pass

    def _engine_resolve(self, pending, hit_result=None) -> None:
        """Resolve os motores com o resultado do spin recém-verificado (t-1).

        block_gale usa o HIT REAL (hit_result = número ∈ cobertura apostada) como
        verdade de campo para escalar/resetar o bloco — é o que dita o stake real.
        c_selection segue por distância (avaliação contrafactual por candidato).
        shadow_green (recomputado de dist) é só fallback: diverge do hit real no
        fallback de calibração (N=21, raio 10) e geometrias não-radius-3 — bug
        latente corrigido na auditoria 17/06 (implantação_c_variavel_gale_junho §17)."""
        try:
            if not pending:
                return
            gs = self.game_state
            attr = getattr(gs, "last_hit_attribution", None) or {}
            bdir = pending.get("direction", "") or ""
            dk = "cw" if bdir in ("cw", "horario") else "ccw"

            def _a(x):
                return abs(x) if isinstance(x, (int, float)) else 99

            chosen = pending.get("cs_chosen")
            if chosen in ("C1", "C2"):
                d_chosen = attr.get("dist_c1") if chosen == "C1" else attr.get("dist_c2")
                shadow_green = min(_a(d_chosen), _a(attr.get("dist_c3"))) <= 3
            else:
                shadow_green = _a(attr.get("dist_min")) <= 3
            fc = pending.get("shadow_candidates")
            if fc:
                gs.c_selection_engine.feedback(bdir, fc, attr)
            placed = bool(pending.get("bg_placed", pending.get("bet_placed", False)))
            gale_green = bool(hit_result) if hit_result is not None else shadow_green
            gs.block_gale_engine.on_result(bdir, gale_green, placed)
            if attr.get("dist_c1") is not None:
                tgt = gs.c_attr_cw if dk == "cw" else gs.c_attr_ccw
                tgt.append({"dist_c1": attr.get("dist_c1"), "dist_c2": attr.get("dist_c2"),
                            "dist_c3": attr.get("dist_c3")})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[IMPL engine_resolve] falha: {e}")

    def _engine_overlay_fields(self) -> dict:
        """Campos aditivos para sugestao/state_sync (extensão ignora desconhecidos)."""
        try:
            gs = self.game_state
            out = {}
            if self._cs_meta:
                out["c_selection"] = {"chosen": self._cs_meta["chosen"], "pair": self._cs_meta["pair"],
                                      "rule": self._cs_meta["rule"], "n": self._cs_meta["n"]}
                f17 = self._cs_meta.get("force17")
                if f17:
                    out["force17"] = {
                        "active": True,
                        "regioes": f17.get("regioes", []),
                        "c1_force": f17.get("c1_force"),
                        "coverage_n": f17.get("coverage_n"),
                        "numeros": f17.get("numeros", []),
                        "dir_bias": "favoravel" if self._engine_dk() == "ccw" else "desfavoravel",
                    }
                    # Espelha as 3 regiões rotuladas no topo (consumo direto pelo overlay).
                    out["regioes"] = f17.get("regioes", [])
            st_cw = gs.block_gale_engine.states["cw"]
            st_ccw = gs.block_gale_engine.states["ccw"]
            out["block_gale"] = {
                "active": self._bg_meta is not None,
                "cw": {"level": st_cw.level, "cap": st_cw.cap, "block": f"{st_cw.block_bets}/4", "max": st_cw.max_level_seen},
                "ccw": {"level": st_ccw.level, "cap": st_ccw.cap, "block": f"{st_ccw.block_bets}/4", "max": st_ccw.max_level_seen},
            }
            if self._bg_meta is not None:
                out["bet_gate"] = {"only_after_green": gs.block_gale_engine.only_after_green,
                                   "gated": self._bg_meta.get("gated", False)}
            # ultimo_acerto (verde/vermelho + sentido analisado do spin t-1) também no
            # canal `sugestao` — o overlay da extensão marca o reflexo da sugestão.
            attr = getattr(gs, "last_hit_attribution", None)
            if isinstance(attr, dict) and attr.get("slot"):
                slot = attr["slot"]
                out["ultimo_acerto"] = {
                    "slot": slot,
                    "green": slot in ("C1", "C2", "C3"),
                    "numero": attr.get("numero", gs.last_number),
                    "direction": getattr(gs, "last_direction", "") or "",
                }
            return out
        except Exception:  # noqa: BLE001
            return {}

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
                    # DIR6 (sentido-fase): idempotência por trace_id (mais robusta que
                    # numero+dir+ms — reenvios/re-render chegam com o mesmo trace_id).
                    from app_config.settings import dedup_seq_enabled
                    if dedup_seq_enabled():
                        _tid = data.get("trace_id")
                        if _tid and self._is_duplicate_trace(_tid):
                            logger.info(f"🔁 trace_id duplicado ignorado: {_tid}")
                            return
                    if self.is_duplicate_spin(numero, timestamp, data.get("direcao")):
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
            elif msg_type == "direction_event":
                await self.handle_direction_event(websocket, data)
            elif msg_type == "set_seed":
                await self.handle_set_seed(websocket, data)
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
            elif msg_type == "foto_frame":
                await self.handle_foto_frame(websocket, data)
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
            # ISO-S2 (Seguranca / BUG-POST-004): nao expor detalhes internos.
            # Detalhe completo vai para logs server-side; cliente recebe msg generica.
            logger.error(f"JSON invalido: {e}", exc_info=True)
            error = ErrorOutput(
                trace_id=trace.trace_id if trace else "unknown",
                code=400,
                message="JSON invalido: payload nao pode ser parseado",
                t_server=now_ms()
            )
            await websocket.send(error.model_dump_json())

        except Exception as e:
            # ISO-S2 (Seguranca / BUG-POST-004): str(e) podia vazar paths/stack.
            # Logamos detalhe completo server-side; cliente recebe mensagem opaca
            # contendo apenas o trace_id para correlacao em suporte.
            logger.error(f"Erro ao processar: {e}", exc_info=True)
            _tid = trace.trace_id if trace else "unknown"
            error = ErrorOutput(
                trace_id=_tid,
                code=500,
                message=f"erro interno (trace_id={_tid})",
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
                t_client=data.get("t_client", 0),
                # SP-12 DEAL-02 (27/05): metadata opcional do DOM via extension.
                dealer=(data.get("dealer") or None),
                table=(data.get("table") or None),
                provider=(data.get("provider") or None),
                round_id=(data.get("round_id") or None),
                # Vision (foto_roleta Parte 4): foto->dados, opcional/backward-compat.
                wheel_model=(data.get("wheel_model") or None),
                vision_confidence=(data.get("vision_confidence") if data.get("vision_confidence") is not None else None),
                vision_source=(data.get("vision_source") or None),
            )
            numero = spin.numero
            direcao = spin.direcao
            # DEAL audit 27/05: loga quando dealer/provider chegarem para
            # facilitar troubleshooting pos-deploy. INFO so se algum campo set.
            if spin.dealer or spin.provider or spin.table:
                logger.info(
                    f"[DEAL] dealer={spin.dealer!r} provider={spin.provider!r} "
                    f"table={spin.table!r} round={spin.round_id!r}"
                )
        except Exception as e:
            raise ValueError(f"Entrada inválida: {e}")

        # Log da predição pendente antes de verificar
        # BUG-AUDIT-002 FIX: Ler pending DENTRO do lock para evitar race condition
        # Auditoria r3 (12/06): flag LOCAL por mensagem — atributo de instância
        # podia vazar True entre spins se exceção ocorresse entre uso e reset.
        result_updated_this_spin = False
        async with self.state_lock:
            pending = self.game_state.pending_prediction
            if pending:
                logger.info(f"VERIFICANDO: numero={numero}, centro_previsto={pending.get('center')}, numeros={pending.get('numbers', [])[:5]}...")

            hit_result = self.game_state.check_prediction(numero)

            # Atualizar Martingale da direção da predição (se havia predição E apostou)
            # NOTA: bet_direction vem de pending_prediction["direction"] que é target_direction
            #        (oposto de last_direction), ou seja, a direção que FOI predita/apostada.
            martingale_info = {}
            if pending and hit_result is not None and pending.get("bet_placed", False):
                # BUG-AUDIT-006 FIX: Validar direction antes de atualizar Martingale
                bet_direction = pending.get("direction", "")
                if bet_direction in ("cw", "horario"):
                    martingale_info = self.game_state.martingale_cw.update(hit_result, global_hit=hit_result)
                    self.game_state.martingale_ccw.sync_global(hit_result)
                elif bet_direction in ("ccw", "anti-horario"):
                    martingale_info = self.game_state.martingale_ccw.update(hit_result, global_hit=hit_result)
                    self.game_state.martingale_cw.sync_global(hit_result)
                else:
                    logger.warning(f"Direction inválida no pending: '{bet_direction}', Martingale NÃO atualizado")

                if martingale_info.get("transition"):
                    logger.info(f"  MARTINGALE ({bet_direction}): {martingale_info['transition']}")
                logger.info(f"  Resultado: {'HIT' if hit_result else 'MISS'} | Gale {martingale_info.get('level_after', 1)} | Streak {martingale_info.get('consecutive_hits', 0)}")

                # Sprint W-01 + W-02 + B-08 (26/05/2026):
                # calcula wheel_dist usando helper canonico e persiste em
                # decisions.calibration_error (coluna existia ha tempos mas
                # nunca foi populada — 1232/1232 NULL em 24h pre-fix).
                # B-09 (26/05): pending guarda chave "centers" (state/game.py:465),
                # nao "sda_centers" — fallback ambos para retro-compat / safety.
                sda_centers = pending.get("centers") or pending.get("sda_centers") or []
                wheel_dist_val: Optional[int] = None
                if sda_centers:
                    try:
                        wheel_dist_val = roulette.compute_wheel_dist_min_to_set(
                            sda_centers, numero
                        )
                        if wheel_dist_val is not None:
                            logger.info(
                                f"  DISTÂNCIA: {wheel_dist_val} casas do centro "
                                f"mais próximo (centros={sda_centers})"
                            )
                    except (ValueError, TypeError) as _e:
                        logger.debug(f"wheel_dist skipped: {_e}")

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
                # BUG-A (12/06): era `if c1_predicted > 0` — ZERO é número
                # válido da roleta; predições com C1=0 (~2.7% dos spins)
                # nunca alimentavam o feedback adaptativo.
                c1_predicted = pending.get("center", None)
                if c1_predicted is not None and bet_direction:
                    # BUG-B (12/06): feedback aprende com a APOSTA REAL
                    # (números/centros emitidos), não com cobertura recalculada.
                    self.strategy.update_adaptive(
                        bet_direction, c1_predicted, numero, roulette.WHEEL_SEQUENCE,
                        coverage=pending.get("numbers") or None,
                        centers=pending.get("centers") or None,
                    )
                    # Persistir estado adaptativo no GameState
                    self.game_state._adaptive_state = self.strategy.get_adaptive_state()

            # BUG-L (12/06): atualizar o resultado da decisão ANTERIOR (pnl,
            # region, DNA) AQUI — antes dos gates B5 — para o stop-loss ler o
            # P&L já incluindo a jogada recém-resolvida (antes havia 1 spin
            # de atraso; visto ao vivo: gate leu -53 quando o real era -54).
            if self.last_decision_id and hit_result is not None:
                try:
                    _cal_err = wheel_dist_val if 'wheel_dist_val' in locals() else None
                    _hit_attr = getattr(self.game_state, "last_hit_attribution", None) or {}
                    _region_slot = _hit_attr.get("slot")
                    db_service.update_result(
                        self.last_decision_id, hit_result, numero,
                        calibration_error=_cal_err,
                        result_region=_region_slot,
                    )
                    # SP-07: preenche realized_lift / hit / wheel_dist no DNA
                    try:
                        from database import dna_logger as _dna
                        _dna.dna_update_realized(
                            self.last_decision_id,
                            hit=bool(hit_result),
                            wheel_dist=_cal_err,
                        )
                        # B2 (12/06): feature hit_region — alimenta region_bandit
                        # (B4) e responde P5 continuamente.
                        if _region_slot:
                            _dna.dna_log_feature(
                                self.last_decision_id, "hit_region",
                                {
                                    "raw": _region_slot,
                                    "bucket": _region_slot,
                                    "dist_c1": _hit_attr.get("dist_c1"),
                                    "dist_c2": _hit_attr.get("dist_c2"),
                                    "dist_c3": _hit_attr.get("dist_c3"),
                                    "dist_min": _hit_attr.get("dist_min"),
                                },
                                spin_number=numero,
                                direction=(getattr(self, "last_decision_direction", None) or direcao),
                                hit=bool(hit_result),
                            )
                    except Exception:  # noqa: BLE001
                        pass
                    # OBS-25-01: publicar spin_result no outbox para backtest offline
                    try:
                        from database.outbox_integration import maybe_publish_spin_result
                        last_dir = getattr(self, "last_decision_direction", None) or direcao
                        maybe_publish_spin_result(
                            self.last_decision_id, last_dir, hit_result, numero
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error("spin_result_hook_raise exc=%s", exc)
                    # Evita dupla atualização no bloco de logging adiante.
                    result_updated_this_spin = True
                except Exception as _ur_e:  # noqa: BLE001
                    logger.error(f"update_result (pre-gate) falhou: {_ur_e}")

            # IMPL C1/C2 + Block-Gale (17/06): resolve os motores com o resultado
            # do spin recém-verificado (t-1) — feedback c_selection (distância) +
            # on_result block_gale (hit REAL como verdade de campo, fix audit 17/06).
            self._engine_resolve(pending, hit_result)

            # DIR4 (sentido-fase): reconciliação de fase por SHIFT. Consome allNumbers
            # (os 12 últimos que o cliente já envia mas o servidor ignorava) e conta
            # quantos giros REAIS entraram desde a última leitura. k>1 = gap (cliente
            # minimizado / 2 giros num tick) → avança a fase pelos giros perdidos.
            _phase_uncertain = False
            from app_config.settings import phase_reconcile_enabled
            if phase_reconcile_enabled():
                from state.phase import reconcile_shift
                from state import phase_metrics
                _all_nums = data.get("allNumbers") or []
                _prev_nums = list(self.game_state.recent_results)
                _k, _matched = reconcile_shift(_prev_nums, _all_nums)
                _gap = max(0, _k - 1)
                if _gap > 0:
                    self.game_state.spin_seq += _gap
                    phase_metrics.incr("gap_recuperado_total", _gap)
                    logger.info(f"[FASE] gap recuperado: k={_k} ({_gap} giro(s) perdido(s))")
                _phase_uncertain = (not _matched) and len(_prev_nums) > 0 and len(_all_nums) > 0
                if _phase_uncertain:
                    phase_metrics.incr("phase_uncertain_total")
                    logger.warning("[FASE] shift sem alinhamento (possivel troca de mesa) — phase_uncertain")

            # DIR5 (sentido-fase): AUTORIDADE da fase. Quando ligado, o servidor deixa
            # de confiar cegamente no `direcao` do cliente (que pode ter defasado) e
            # DERIVA a fase do giro pela projeção determinística, ancorada na primeira
            # direção observada (auto-seed). Imune a gaps subsequentes. Sem seed (ou flag
            # OFF) cai no comportamento atual (obedece o cliente).
            from app_config.settings import sentido_autoritativo_enabled
            if sentido_autoritativo_enabled():
                from state.phase import project_phase, normalize as _phase_norm
                _gs = self.game_state
                if not _gs.seed_parity:
                    _gs.seed_parity = _phase_norm(direcao)
                    _gs.seed_n = _gs.spin_seq
                    if not _gs.direction_source or _gs.direction_source == "reset":
                        _gs.direction_source = (getattr(spin, "direction_source", None) or "auto_seed")
                else:
                    _proj = project_phase(_gs.seed_parity, _gs.seed_n, _gs.spin_seq)
                    _fused = _proj
                    # DIR7 (sentido-fase): fusão com a fonte de VÍDEO (stand-by até
                    # acoplar). O vídeo publica direction_event (ou direction_source=
                    # 'vision' no spin); se confiável, confirma/sobrepõe o toggle.
                    from app_config.settings import direction_vision_enabled, direction_vision_min_conf
                    if direction_vision_enabled():
                        from state.phase import fuse_direction
                        _signals = [{"source": "deterministic_toggle", "direction": _proj, "confidence": 1.0}]
                        _ev = getattr(_gs, "last_direction_event", None)
                        if isinstance(_ev, dict):
                            _signals.append(_ev)
                        if getattr(spin, "direction_source", None) == "vision":
                            _signals.append({"source": "vision", "direction": _phase_norm(direcao),
                                             "confidence": float(getattr(spin, "direction_confidence", 0.0) or 0.0)})
                        _fused, _fsrc = fuse_direction(_signals, _proj, direction_vision_min_conf())
                        if _fsrc and _fsrc != "deterministic_toggle":
                            _gs.direction_source = _fsrc
                    if _fused != _phase_norm(direcao):
                        from state import phase_metrics
                        phase_metrics.incr("direction_divergence_total")
                        logger.info(f"[FASE] autoridade corrige direcao: {direcao} -> {_fused} (seq={_gs.spin_seq})")
                        direcao = _fused

            # Processar spin
            force = self.game_state.process_spin(numero, direcao)
            # DIR3 (sentido-fase): conta giros REAIS ao vivo (n). Telemetria inócua
            # até SDA_SENTIDO_AUTORITATIVO=1; base do shift/projeção de fase (DIR4/5).
            self.game_state.spin_seq += 1
            # DIR6: expõe a ambiguidade de fase ao overlay (resync_advised no state_sync).
            self.game_state.last_phase_uncertain = _phase_uncertain
            # S-OBS-6: registra timestamp epoch para /api/strategy
            import time as _t_obs6
            self.last_spin_ts = _t_obs6.time()
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
                calibration=0,  # Momentum desabilitado
                recent_numbers=list(self.game_state.recent_results),  # V4: zona fria C3
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

        # Decisão combinada — INV-3 GLOBAL (auditoria 12/06):
        # Premissa do owner: a estratégia principal SEMPRE indica a melhor
        # aposta da jogada; só não há indicação nas 2 primeiras oportunidades
        # de cada sentido (calibração: 1ª sem dados, 2ª fallback N=21).
        # Vetos (Triple Rate, CUT-POLICY v1 score<4, stop-loss) NÃO suprimem
        # a indicação — modulam o STAKE (mesmo padrão do QW-1 minimizer).
        _cut_v1_active = False
        _stop_loss_active = False
        try:
            from app_config.settings import profit_cut_v1_enabled, profit_stop_loss_units
            _cut_v1_active = profit_cut_v1_enabled()
            _sl_units = profit_stop_loss_units()
            if _sl_units > 0 and self.current_session_id:
                _sess_pnl = db_service.get_session_pnl(self.current_session_id)
                if _sess_pnl <= -_sl_units:
                    _stop_loss_active = True
                    logger.warning(
                        "[B5 STOP-LOSS] sessão %s pnl=%.1f <= -%.1f — stake mínimo (INV-3)",
                        self.current_session_id, _sess_pnl, _sl_units,
                    )
        except Exception as _b5_e:  # noqa: BLE001 — gate nunca quebra fluxo
            logger.warning(f"[B5] gates indisponíveis: {_b5_e}")

        try:
            _cut_frac = float(self.strategy._cfg.get("sda17.minimizer", "stake_fraction", 0.10))
        except Exception:  # noqa: BLE001
            _cut_frac = 0.10

        action_reason = ""
        _stake_override: Optional[float] = None  # fração do base_bet (INV-3)
        # IMPL aposta 14# (17/06): substitui a cobertura ANTES de final_numbers,
        # despachado por SDA_BET_PAIR (c2c3/c1c3 estático ou var_c1c2_c3 voto;
        # full/inválido = no-op, 21#).
        self._engine_apply_selection(result)
        # Sprint 0 (B1): garante cobertura não-vazia (rede de segurança) ANTES de
        # final_numbers/store_prediction — a indicação nunca cobre zero números.
        self._ensure_nonempty_coverage(result)
        # Indicação FINAL da jogada (auditoria 12/06): o overlay e a Decision
        # devem SEMPRE refletir o que foi indicado — inclusive no fallback de
        # calibração. Bug pré-existente confirmado em prod: 121/121 decisões
        # de fallback salvas com sda_numbers=[] (result.numbers vazio).
        final_numbers = list(result.numbers or [])
        final_center = result.center
        final_centers = result.details.get("centers", [result.center])
        final_score = result.score
        if result.should_bet:
            # SmartGale v5: calcular gale ANTES de registrar (sempre — a
            # indicação existe em toda jogada com predição).
            mg = self.game_state.target_martingale
            bet_c4_rate = self.game_state.get_bet_c4_rate()
            # S-STAKE (flat_kelly_junho.md §RN-6): só o modo gale escala por streak.
            # flat/kelly travam level=1 (sem escalação — elimina o sangramento).
            from app_config.settings import staking_mode as _staking_mode
            if _staking_mode() == "gale":
                mg.get_gale(score=result.score, c4_rate=bet_c4_rate, confidence=advice.confidence)
            else:
                mg.level = 1

            acao = "APOSTAR"
            action_reason = f"SDA score={result.score} | {mg.gale_display} | C4={bet_c4_rate:.0%}"
            if _stop_loss_active:
                mg.level = 1
                _stake_override = 0.0  # floor de 1u aplicado adiante
                action_reason = "STOP-LOSS sessão (B5): stake mínimo 1u — indicação mantida (INV-3)"
            elif _cut_v1_active and result.score < 4:
                mg.level = 1
                _stake_override = _cut_frac
                action_reason = f"CUT-POLICY v1: score={result.score} < 4 → stake ×{_cut_frac:.2f} (INV-3)"
            elif not advice.should_bet:
                mg.level = 1
                _stake_override = _cut_frac
                action_reason = f"Triple Rate cauteloso: {advice.reason} → stake ×{_cut_frac:.2f} (INV-3)"
            # Registrar com bet_placed=True (a aposta É emitida; valor modulado)
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
            action_reason = "Calibração: 1ª jogada do sentido (sem forças)"
            # Fallback early-session (calibração 2): timeline com 1 força →
            # indica N=21 G1. Nunca fica sem indicação tendo dados (INV-3).
            if self.game_state.target_timeline.size > 0:
                mg = self.game_state.target_martingale
                mg.level = 1
                center = self.game_state.last_number
                # force17: o fallback de calibração respeita a geometria 17# (raio 8 =
                # 17#) SEMPRE que a aposta é force17 — independe de SDA_FORCE17_EXACT,
                # que rege só o padding da aposta NORMAL (união ~15), não o fallback.
                # Fora de force17, mantém o histórico N=21 (raio 10). [fix BUG-FRONT #1,
                # 18/06: desacopla do exact — antes 21# em prod com EXACT=0].
                try:
                    from app_config.settings import bet_pair_mode
                    _fb_radius = 8 if bet_pair_mode() == "force17" else 10
                except Exception:  # noqa: BLE001
                    _fb_radius = 10
                fallback_nums = sorted(
                    self.strategy.get_neighbors(center, _fb_radius, roulette.WHEEL_SEQUENCE)
                )
                acao = "APOSTAR"
                action_reason = (
                    f"Calibração ({self.game_state.target_timeline.size} força no sentido) → N={len(fallback_nums)} G1"
                )
                final_numbers = list(fallback_nums)
                final_center = center
                final_centers = [center]
                final_score = 1
                # Auditoria 18/06: o fallback de calibração SOBRESCREVE a cobertura
                # (N=21). Se o force17 tivesse marcado _cs_meta (centros≥3), o overlay
                # mostraria regiões de 3 centros junto de numeros=21 (inconsistente).
                # Zera a telemetria force17 para o overlay refletir o fallback real.
                self._cs_meta = None
                self.game_state.last_force17_meta = None
                if _stop_loss_active:
                    _stake_override = 0.0
                    action_reason += " | STOP-LOSS: stake mínimo (INV-3)"
                elif _cut_v1_active:
                    _stake_override = _cut_frac
                    action_reason += f" | CUT v1: stake ×{_cut_frac:.2f} (INV-3)"
                self.game_state.store_prediction(
                    fallback_nums, self.game_state.target_direction, center,
                    predicted_force=0, bet_placed=True,
                    tr_confidence="baixa", tr_reason="Fallback early-session",
                    sda_score=1, sda_centers=[center]
                )
            # SDA não recomendou e timeline vazia - não há predição para verificar

        # Obter info do martingale da direção ALVO (para overlay)
        mg = self.game_state.target_martingale

        # v4.4 QW-1/2: Stake modulation (INV-3 — apenas valor; aposta continua)
        try:
            stake_info = self.game_state.get_effective_bet(
                self.game_state.target_direction, self.strategy,
                n_numbers=len(final_numbers),
            )
        except Exception as _qw_e:
            logger.warning(f"[QW] get_effective_bet falhou ({_qw_e}) — fallback base")
            stake_info = {
                "effective_bet": mg.current_bet,
                "base_bet": mg.current_bet,
                "multiplier": 1.0,
                "mode": "normal",
                "rolling_rate": None,
                "minimizer_active": False,
            }
        if stake_info["mode"] == "minimizer":
            logger.info(
                "[QW-1 MINIMIZER] dir=%s rate=%.3f base=%d → effective=%d (×%.2f) — APOSTA CONTINUA (INV-3)",
                self.game_state.target_direction,
                stake_info.get("rolling_rate") or 0.0,
                stake_info["base_bet"],
                stake_info["effective_bet"],
                stake_info["multiplier"],
            )
        elif stake_info["mode"] == "weight" and abs(stake_info["multiplier"] - 1.0) > 0.05:
            logger.info(
                "[QW-2 WEIGHT] dir=%s rate=%.3f base=%d → effective=%d (×%.2f)",
                self.game_state.target_direction,
                stake_info.get("rolling_rate") or 0.0,
                stake_info["base_bet"],
                stake_info["effective_bet"],
                stake_info["multiplier"],
            )

        # IMPL Block-Gale (17/06): stake = nível do bloco (gated por
        # SDA_STAKING_MODE=block_gale). Aplicado ANTES do override de veto INV-3,
        # que ainda impõe o piso/min. Default (flat/gale) não muda nada.
        self._engine_apply_stake(stake_info, len(final_numbers), acao)

        # INV-3 (12/06): override de stake dos vetos (TR/CUT v1/stop-loss),
        # aplicado APÓS QW-1/QW-2 — vale o MENOR stake entre os moduladores.
        # A indicação (números/regiões) permanece intacta.
        if acao == "APOSTAR" and _stake_override is not None:
            _ovr = max(1, int(round(stake_info["base_bet"] * _stake_override)))
            if _ovr < stake_info["effective_bet"]:
                stake_info["effective_bet"] = _ovr
                stake_info["multiplier"] = _ovr / max(1, stake_info["base_bet"])
                stake_info["mode"] = "veto_min"
            logger.info(
                "[INV-3 OVERRIDE] dir=%s base=%d → effective=%d (×%.2f) — %s",
                self.game_state.target_direction,
                stake_info["base_bet"],
                stake_info["effective_bet"],
                stake_info["multiplier"],
                action_reason,
            )

        # IMPL C1/C2 + Block-Gale (17/06): anexa metadados dos motores ao pending
        # (escolhas congeladas + bg_placed) para a resolução do próximo spin.
        self._engine_inject_pending()

        # ====================================================
        # LOGGING - Salvar decisão no banco de dados
        # ====================================================
        try:
            # BUG-FK-1 fix: garantir que session_id existe no DB antes do save
            # (current_session_id é gerado no __init__ via uuid mas nunca registrado)
            if not getattr(self, "_session_db_initialized", False):
                try:
                    db_service.create_session(self.current_session_id)
                    self._session_db_initialized = True
                    logger.info(f"✅ Sessão DB inicializada: {self.current_session_id}")
                except Exception as init_err:
                    logger.error(f"❌ Falha criando sessão {self.current_session_id}: {init_err}")

            # Atualizar resultado da decisão anterior — já feito no pre-gate
            # (BUG-L 12/06); mantém fallback se aquele caminho falhou.
            if (self.last_decision_id and hit_result is not None
                    and not result_updated_this_spin):
                _cal_err = wheel_dist_val if 'wheel_dist_val' in locals() else None
                _hit_attr = getattr(self.game_state, "last_hit_attribution", None) or {}
                _region_slot = _hit_attr.get("slot")
                db_service.update_result(
                    self.last_decision_id, hit_result, numero,
                    calibration_error=_cal_err,
                    result_region=_region_slot,
                )

            # Salvar nova decisão
            # Vision-context fill-forward (22/06): resolve dealer/modelo/provider
            # uma vez (foto autoritativa + propagação do último OCR da sessão).
            _vf_dealer, _vf_wheel, _vf_provider = self._apply_vision_context(
                getattr(spin, "dealer", None),
                getattr(spin, "wheel_model", None),
                getattr(spin, "provider", None),
            )
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
                sda_score=final_score,
                sda_center=final_center,
                sda_centers=final_centers,
                sda_numbers=final_numbers,
                sda_predicted_force=result.details.get("predicted_force", 0),
                sda_offset=result.details.get("offset", 0),
                sda_offset_type=result.details.get("offset_type", ""),
                sda_regions=_build_sda_regions(result),
                final_action=acao,
                action_reason=action_reason,
                gale_level=mg.level,
                gale_window_hits=mg.consecutive_hits,
                gale_window_count=mg.total_bets,
                # LEDGER FIX (auditoria 12/06): registrar o stake REAL apostado
                # (pós QW-1/QW-2/INV-3) — antes gravava mg.current_bet (base) e
                # o pnl_units superestimava perdas/ganhos sob modulação.
                gale_bet_value=(
                    stake_info["effective_bet"] if acao == "APOSTAR" else mg.current_bet
                ),
                calibration_offset=0,
                performance_snapshot=self.game_state.target_performance[:12],
                # SP-13 DEAL-03 (27/05) + Vision-context fill-forward (22/06):
                # dealer/modelo/provider vêm da FOTO (autoritativa; o DOM da
                # Evolution não os expõe). O fill-forward propaga o último OCR da
                # sessão a TODA jogada (flag SDA_DEALER_FILL_FORWARD; metadata, não
                # toca aposta) → dados 100% acoplados. resultados_bancos_junho.md.
                dealer=(_vf_dealer or "unknown"),
                # Mesa (auditoria 22/06): vem da FOTO/OCR (o DOM trazia 'Blackjack
                # Silver D' errado numa roleta). dealer_table = mesa do OCR
                # (= wheel_model), com fill-forward. DOM descartado.
                dealer_table=(_vf_wheel or ""),
                provider=(_vf_provider or ""),
                round_id=(getattr(spin, "round_id", None) or ""),
                wheel_model=(_vf_wheel or ""),
                vision_confidence=(getattr(spin, "vision_confidence", None) or 0.0),
                vision_source=(getattr(spin, "vision_source", None) or ""),
                # DIR3/DIR4 (sentido-fase): telemetria de fase — spin_seq reconciliado,
                # origem/confiança do sinal de direção e ambiguidade do shift. Aditivo,
                # não toca a aposta (a autoridade da fase é publicada em DIR5).
                spin_seq=self.game_state.spin_seq,
                direction_source=(getattr(spin, "direction_source", None) or ""),
                direction_confidence=(getattr(spin, "direction_confidence", None) or 0.0),
                phase_uncertain=_phase_uncertain,
            )

            # Rastrear todas as decisões que têm predição (APOSTAR e PULAR com SDA)
            decision_id = db_service.save_decision(decision)
            # SP-07: emite DNA features apos save (best-effort, nunca quebra fluxo).
            # ≥4 features por decisao conforme criterio do blueprint.
            try:
                from database import dna_logger as _dna
                _action = "APOSTAR" if result.should_bet else "PULAR"
                _sda_score = int(final_score or 0)
                _score_bucket = (
                    "sweet_spot" if _sda_score == 4
                    else ("high" if _sda_score >= 5 else "low")
                )
                _dna.dna_log_feature(
                    decision_id, "sda_score",
                    {"raw": _sda_score, "bucket": _score_bucket},
                    spin_number=numero, direction=direcao, final_action=_action,
                )
                _dna.dna_log_feature(
                    decision_id, "calibration_offset",
                    {"raw": int(getattr(result, "calibration_offset", 0) or 0)},
                    spin_number=numero, direction=direcao, final_action=_action,
                )
                _tr_c4 = float(getattr(advice, "c4_rate", 0.0) or 0.0)
                _c4_bucket = (
                    "hot" if _tr_c4 >= 0.55
                    else ("warm" if _tr_c4 >= 0.45 else "cold")
                )
                _dna.dna_log_feature(
                    decision_id, "tr_c4_rate",
                    {"raw": _tr_c4, "bucket": _c4_bucket},
                    spin_number=numero, direction=direcao, final_action=_action,
                )
                _kill = bool(getattr(advice, "should_bet", True)) is False
                _dna.dna_log_feature(
                    decision_id, "kill_v4",
                    {"raw": _kill, "bucket": "off" if _kill else "on"},
                    spin_number=numero, direction=direcao, final_action=_action,
                )
                # SP-17 REGION-02: emite uma feature DNA por regiao C1/C2/C3.
                # Permite calcular realized_lift_pp por slot e cruzar com
                # offset (sweet_spot do offset adaptativo SDA17).
                try:
                    _regions = _build_sda_regions(result) or []
                    for _r in _regions:
                        _slot = _r.get("slot", "C?")
                        _off = int(_r.get("offset", 0) or 0)
                        _off_bucket = (
                            "zero" if _off == 0
                            else ("near" if abs(_off) <= 3 else "far")
                        )
                        _dna.dna_log_feature(
                            decision_id, f"region_{_slot}",
                            {"raw": _off, "bucket": _off_bucket, "c": _r.get("c")},
                            spin_number=numero, direction=direcao, final_action=_action,
                        )
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001 — DNA nunca quebra fluxo
                pass
            # ISO-S4 (O-03 — Analisabilidade): emite UM evento estruturado canonico
            # por decisao com decision_id + trace_id + acao + score. Permite
            # correlacionar logs ad-hoc do mesmo spin sem regex em texto livre.
            try:
                import structlog as _structlog
                _structlog.get_logger("decision").info(
                    "decision_created",
                    decision_id=decision_id,
                    trace_id=trace.trace_id if trace else None,
                    direction=direcao,
                    spin_number=numero,
                    final_action=("APOSTAR" if result.should_bet else "PULAR"),
                    sda_score=getattr(result, "score", None),
                    sda_center=getattr(result, "center", None),
                    session_id=self.current_session_id,
                )
            except Exception:  # noqa: BLE001 — telemetria nunca quebra fluxo
                pass
            if result.should_bet:
                # SDA gerou predição → rastrear para verificar no próximo spin
                self.last_decision_id = decision_id
                self.last_decision_direction = direcao  # OBS-25-01
            else:
                # SDA não recomendou → sem predição para verificar
                self.last_decision_id = None
                self.last_decision_direction = None

            # Atualizar stats da sessão a cada 10 decisões
            self._decision_count += 1
            if self._decision_count % 10 == 0:
                db_service.update_session_stats(self.current_session_id)

        except Exception as db_error:
            # BUG-SILENCE-1 fix: era warning, escalado para error + métrica
            # SP-05 (26/05): instrumenta categoria + exc_type. TypeError /
            # AttributeError aqui sao quase sempre bugs de assinatura
            # (ver B-10: DatabaseService.update_result kwarg engolido).
            # Em modo STRICT_SILENT_EXCEPT=1 esses tipos sao re-raised.
            from core.safe_except import _CTR as _silent_ctr, _STRICT, _RERAISE_TYPES
            _exc_type = type(db_error).__name__
            logger.error(
                f"❌ Erro ao salvar decisão no DB ({_exc_type}): {db_error} "
                f"(session={self.current_session_id}, spin={numero})"
            )
            if _silent_ctr is not None:
                try:
                    _silent_ctr.labels(
                        module="server.message_handler",
                        category="db_save_decision",
                        exc_type=_exc_type,
                    ).inc()
                except Exception:
                    pass
            try:
                from database.outbox_integration import save_decision_failed_total
                save_decision_failed_total.labels(reason=_exc_type).inc()
            except Exception:
                pass
            if _STRICT and isinstance(db_error, _RERAISE_TYPES):
                logger.warning(
                    "STRICT_SILENT_EXCEPT re-raising %s — provavel bug assinatura",
                    _exc_type,
                )
                raise

        # Formato esperado pelo overlay
        overlay_response = {
            "type": "sugestao",
            "data": {
                "acao": acao,
                "numeros": final_numbers,
                "centro": final_center,
                "centros": final_centers,
                "regiao": result.visual,
                "ultimo_numero": self.game_state.last_number,
                "confianca": {"alta": 80, "media": 50, "baixa": 20}.get(advice.confidence, 50),
                "martingale": mg.multiplier,
                "aposta": stake_info["effective_bet"],
                "aposta_base": stake_info["base_bet"],
                "stake_mode": stake_info["mode"],
                "stake_multiplier": stake_info["multiplier"],
                "gale_level": mg.level,
                "gale_display": mg.gale_display,
                "gale_reasoning": action_reason,
                "consecutive_hits": mg.consecutive_hits,
                "estrategia": self.strategy.name,
                "trace_id": trace.trace_id,
                "t_server": now_ms(),
                # Novo: Triple Rate advice
                "bet_advice": advice.to_dict(),
                "action_reason": action_reason,
                # SV-01/SV-03 (12/06): viés/correção do M5 visíveis ao operador
                # (additive — extension ignora campos desconhecidos).
                "region_bias": {
                    "shift": result.details.get("region_shift", 0),
                    "shift_sat": result.details.get("region_shift_sat", [0, 0]),
                },
            }
        }

        # IMPL C1/C2 + Block-Gale (17/06): campos aditivos (extensão ignora desconhecidos).
        try:
            overlay_response["data"].update(self._engine_overlay_fields())
        except Exception:  # noqa: BLE001
            pass

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
                "centro": final_center,
                "centros": final_centers,
                "score": final_score,
                "numeros": final_numbers,
                "unique_count": result.details.get("unique_count", len(final_numbers)),
                "trend": result.details.get("trend", ""),
                "offset": result.details.get("offset", 12),
                "offset_type": result.details.get("offset_type", "fixed"),
                "cw_history_size": result.details.get("cw_history_size", 0),
            },
            "strategy": {
                "name": self.strategy.name,
                "description": getattr(self.strategy, 'description', ''),
            },
            "performance": self.game_state.get_performance_stats(),
            "martingale_cw": self.game_state.martingale_cw.to_dict(),
            "martingale_ccw": self.game_state.martingale_ccw.to_dict(),
            "state": {
                "timeline_cw": self.game_state.timeline_cw.size,
                "timeline_ccw": self.game_state.timeline_ccw.size,
                "last_number": self.game_state.last_number
            }
        }
        # IMPL C1/C2 + Block-Gale (17/06, tarde): overlay aditivo no canal `trace`.
        # O Glass Box consome `trace`/`state_sync` (não `sugestao`), então sem isto
        # c_selection/block_gale/bet_gate/ultimo_acerto nunca chegam ao dashboard.
        # Fonte única em game_state (sem depender de _cs_meta do handler). Defensivo.
        try:
            trace_broadcast.update(self.game_state.engine_overlay_fields())
        except Exception:  # noqa: BLE001
            pass
        await connection_manager.broadcast(json.dumps(trace_broadcast), exclude_disconnected=False)

        logger.info(trace.to_log_line())

    async def handle_initial_history(self, websocket: WebSocketServerProtocol, data: Dict):
        resultados = data.get("resultados", [])
        count = 0

        from app_config.settings import historico_nao_direcional_enabled
        nao_direcional = historico_nao_direcional_enabled()

        # IMPORTANTE: Extensão envia índice 0 = mais recente
        # Precisamos processar do mais antigo para o mais recente
        for item in reversed(resultados):
            numero = item.get("numero")
            direcao = item.get("direcao", "horario")
            if numero is not None:
                if nao_direcional:
                    # DIR2: o histórico do DOM não carrega direção real (a extensão a
                    # FABRICA por alternância retroativa). Alimentar timeline_cw/ccw com
                    # isso envenena o motor. Registra só como contexto não-direcional.
                    self.game_state.register_history_number(numero)
                else:
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

        from app_config.settings import historico_nao_direcional_enabled
        nao_direcional = historico_nao_direcional_enabled()

        # Reset das timelines
        self.game_state.timeline_cw.clear()
        self.game_state.timeline_ccw.clear()
        self.game_state.recent_results.clear()  # V4: reprocessa do zero (zona fria C3)
        self.game_state.last_number = 0
        self.game_state.last_direction = ""

        count = 0
        # Processar do mais antigo para o mais recente
        for item in reversed(resultados):
            numero = item.get("numero")
            direcao = item.get("direcao", "horario")
            if numero is not None:
                if nao_direcional:
                    # DIR2: reancoragem não-direcional — não repopula timelines com
                    # direção fabricada (que envenena o motor); só o contexto C3.
                    self.game_state.register_history_number(numero)
                else:
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

            # B1 (12/06): zera TAMBÉM o estado adaptativo do SDA17 (P10).
            # Sem isto, o dealer novo herdava _sigmoid_off/históricos do
            # anterior e o warmup de 2 jogadas (P9) nunca recomeçava.
            try:
                if hasattr(self.strategy, "reset_adaptive"):
                    discarded = self.strategy.reset_adaptive()
                    reset_info["strategy_reset"] = discarded
                    self.game_state._adaptive_state = self.strategy.get_adaptive_state()
                    self.game_state.save()
            except Exception as _rs_err:  # noqa: BLE001 — reset nunca quebra fluxo
                logger.error(f"strategy_reset falhou: {_rs_err}")

            # Criar nova sessão no DB
            new_session_id = uuid.uuid4().hex[:8]  # S-MIG-2: UUID em vez de session_<epoch_ms>
            db_service.create_session(new_session_id)
            self.current_session_id = new_session_id
            # Vision-context fill-forward (22/06): nova sessão (troca de dealer/mesa)
            # invalida o contexto de visão — refila do zero na sessão nova.
            self._ff_dealer = None
            self._ff_wheel = None
            self._ff_provider = None
            self._ff_session = new_session_id

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

    async def handle_direction_event(self, websocket: WebSocketServerProtocol, data: Dict):
        """DIR7 (sentido-fase): ingestão STAND-BY do sinal de direção do futuro serviço
        de vídeo. Armazena o último sinal (efêmero) para fusão por prioridade quando
        SDA_DIRECTION_VISION=1. Inerte (apenas ack) enquanto a flag estiver OFF — permite
        acoplar o módulo de vídeo sem nenhuma outra mudança no servidor."""
        from state.phase import normalize as _norm
        direction = _norm(data.get("direction") or "")
        try:
            conf = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if direction in ("horario", "anti-horario"):
            self.game_state.last_direction_event = {
                "source": "vision", "direction": direction,
                "confidence": conf, "ts": now_ms(),
            }
        await websocket.send(json.dumps({
            "type": "ack", "message": "direction_event recebido",
            "direction": direction, "t_server": now_ms(),
        }))

    async def handle_set_seed(self, websocket: WebSocketServerProtocol, data: Dict):
        """DIR8 (sentido-fase): o operador define a fase-semente UMA vez (e opcionalmente
        trava). A partir daí a fase é projetada deterministicamente; persistido (round-trip
        save/load). É o ponto de RE-ANCORAGEM de fase pelo operador (não recálculo cego)."""
        from state.phase import normalize as _norm
        direction = _norm(data.get("direction") or "")
        locked = bool(data.get("locked", False))
        ok = direction in ("horario", "anti-horario")
        if ok:
            async with self.state_lock:
                self.game_state.seed_parity = direction
                self.game_state.seed_n = self.game_state.spin_seq
                self.game_state.direction_source = "operator_seed"
                self.game_state.direction_locked = locked
                self.game_state.save()
            logger.info(f"[FASE] seed do operador: {direction} (locked={locked}, seq={self.game_state.spin_seq})")
        await websocket.send(json.dumps({
            "type": "ack", "message": ("seed definido" if ok else "direction invalida"),
            "direction": direction, "locked": locked, "t_server": now_ms(),
        }))

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
        """DEPRECATED (S-CLEAN-1): caminho legacy sem kill-switch nem gale.

        Master Extractor sempre envia type='novo_resultado'; este path é dead-code
        defensivo. Resposta agora avisa o cliente para migrar e NÃO processa o spin
        (evita risco de aposta sem gate de risco — vide BUG-NOVO-04).
        """
        logger.warning(
            "[S-CLEAN-1] handle_legacy_spin invocado (cliente sem 'type'); "
            "ignorando — kill-switch e martingale não cobrem este path"
        )
        await websocket.send(json.dumps({
            "type": "error",
            "error": "legacy_spin_deprecated",
            "message": (
                "Spin sem 'type' não é mais aceito. "
                "Use type='novo_resultado' com payload completo."
            ),
            "t_server": now_ms(),
        }))
        if trace:
            trace.step("legacy_spin_rejected", {"reason": "deprecated"})
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

    async def handle_foto_frame(self, websocket: WebSocketServerProtocol, data: Dict):
        """Vision (foto_roleta): recebe um frame capturado pela extensao e extrai
        dados via OCR (server/vision_ocr.py). Responde foto_resultado com
        dealer/wheel_model/confidence. NAO toca o caminho de aposta; o cliente
        funde o resultado no proximo novo_resultado (campos vision_* ja persistidos).
        """
        from server import vision_ocr

        image = data.get("image") or data.get("image_b64")
        roi = data.get("roi")
        trace_id = data.get("trace_id")
        if not image:
            vision_ocr.mark_frame("empty")
            await websocket.send(json.dumps({
                "type": "foto_resultado", "ok": False, "error": "sem image",
                "trace_id": trace_id,
            }))
            return

        # SINGLE-FLIGHT: se já há um OCR em andamento, descarta esta foto na hora
        # (não enfileira). No CPU QEMU o OCR leva alguns segundos; sem isto, fotos
        # empilham, saturam o thread-pool e estouram o keepalive do WebSocket
        # (1011 ping timeout = as "travadas"). Melhor pular 1 giro do que travar.
        if getattr(self, "_vision_busy", False):
            vision_ocr.mark_frame("busy")
            await websocket.send(json.dumps({
                "type": "foto_resultado", "ok": False, "busy": True,
                "trace_id": trace_id,
            }))
            return

        self._vision_busy = True
        try:
            # OCR roda em thread separada (CPU-bound) para nao bloquear o event loop.
            result = await asyncio.to_thread(vision_ocr.extract, image, roi)
        finally:
            self._vision_busy = False
        vision_ocr.mark_frame("ok" if result.get("ok") else "error")

        # cache do ultimo resultado de visao (para metricas/merge opcional)
        self._last_vision = {
            "dealer": result.get("dealer"),
            "wheel_model": result.get("wheel_model"),
            "confidence": result.get("confidence", 0.0),
            "source": "vision",
            "ts": now_ms(),
        }
        if result.get("ok"):
            logger.info(
                "[FOTO] dealer=%r wheel=%r provider=%r conf=%.2f texts=%d ms=%d",
                result.get("dealer"), result.get("wheel_model"), result.get("provider"),
                result.get("confidence", 0.0), len(result.get("texts", [])),
                result.get("ms", 0),
            )
            # Vision-context fill-forward (22/06): dealer+modelo+provider reais do
            # OCR viram o "último conhecido" da sessão, p/ TODA jogada seguinte
            # herdar (flag SDA_DEALER_FILL_FORWARD; metadata, não toca aposta).
            self._remember_vision(
                result.get("dealer"), result.get("wheel_model"), result.get("provider")
            )
            # Persiste o OCR na decisão mais recente (foto->dados->DB). Defensivo:
            # safe_except nunca deixa a persistência derrubar o handler.
            if result.get("dealer") or result.get("wheel_model") or result.get("provider"):
                from core.safe_except import safe_except
                with safe_except("foto_persist", logger):
                    did = db_service.update_last_vision(
                        dealer=result.get("dealer"),
                        wheel_model=result.get("wheel_model"),
                        provider=result.get("provider"),
                        confidence=result.get("confidence", 0.0),
                        source="vision",
                    )
                    if did:
                        logger.info("[FOTO] persistido na decision %s", did)
                        vision_ocr.mark_persisted()
        await websocket.send(json.dumps({
            "type": "foto_resultado",
            "ok": result.get("ok", False),
            "enabled": result.get("enabled", False),
            "available": result.get("available", False),
            "trace_id": trace_id,
            "dealer": result.get("dealer"),
            "wheel_model": result.get("wheel_model"),
            "provider": result.get("provider"),
            "confidence": result.get("confidence", 0.0),
            "texts": result.get("texts", []),
            "ms": result.get("ms", 0),
        }))

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
