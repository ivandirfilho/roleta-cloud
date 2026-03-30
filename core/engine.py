# Roleta Cloud - Game Engine
# Encapsula lógica pura de jogo sem dependências de I/O (WebSocket, DB)

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from core.roulette import roulette
from state.game import GameState
from state.bet_advisor import BetAdvice
from strategies.base import StrategyBase

logger = logging.getLogger(__name__)


@dataclass
class SpinDecision:
    """Resultado completo do processamento de um spin."""
    acao: str                      # "APOSTAR" | "PULAR"
    action_reason: str
    numbers: List[int]             # Números preditos
    center: int                    # Centro da previsão
    visual: str                    # Região visual (ex: "17 [25,2,17,34,6]")
    score: int                     # Score SDA (1-6)
    confidence: int                # Confiança numérica (0-100)
    advice: BetAdvice              # Resultado completo do Triple Rate
    martingale_display: str        # Ex: "G1", "G2", "1x"
    martingale_multiplier: str     # Multiplicador do Martingale
    current_bet: float             # Valor da aposta atual
    gale_level: int
    gale_display: str
    hit_result: Optional[bool]     # Resultado da predição anterior
    martingale_info: Dict          # Info de transição do Martingale
    force: int                     # Força calculada do spin
    sda_should_bet: bool           # Se o SDA recomendou
    sda_details: Dict              # Detalhes da análise SDA
    performance_stats: Dict        # Snapshot de performance


class GameEngine:
    """
    Motor de jogo puro — recebe spins, retorna decisões.
    
    Sem WebSocket, sem Database, sem serialização JSON.
    O MessageHandler é o adaptador que conecta este engine ao mundo externo.
    """

    def __init__(self, game_state: GameState, strategy: StrategyBase):
        self.game_state = game_state
        self.strategy = strategy
        self.last_decision_id: Optional[int] = None

    def process_spin(self, numero: int, direcao: str) -> SpinDecision:
        """
        Processa um novo resultado de spin e retorna a decisão completa.
        
        Fluxo:
        1. Verifica predição anterior (performance tracking)
        2. Atualiza Martingale se havia aposta
        3. Processa spin no game_state (timeline, força)
        4. Analisa com SDA-17
        5. Aplica Triple Rate Advisor (kill switch)
        6. Retorna decisão estruturada
        """
        # 1. Verificar predição anterior
        pending = self.game_state.pending_prediction.copy()
        hit_result = self.game_state.check_prediction(numero)

        # 2. Atualizar Martingale da direção predita (se havia predição E apostou)
        martingale_info = {}
        if pending and hit_result is not None and pending.get("bet_placed", False):
            bet_direction = pending.get("direction", "")
            if bet_direction in ("cw", "horario"):
                martingale_info = self.game_state.martingale_cw.update(hit_result, global_hit=hit_result)
                self.game_state.martingale_ccw.sync_global(hit_result)
            else:
                martingale_info = self.game_state.martingale_ccw.update(hit_result, global_hit=hit_result)
                self.game_state.martingale_cw.sync_global(hit_result)

            if martingale_info.get("transition"):
                logger.info(f"  MARTINGALE ({bet_direction}): {martingale_info['transition']}")

        # 3. Processar spin
        force = self.game_state.process_spin(numero, direcao)
        
        # BUG-TASK-001 FIX: Atualizar estado adaptativo no engine (espelho do message_handler)
        if pending and hit_result is not None:
            bet_direction = pending.get("direction", "")
            c1_predicted = pending.get("center", 0)
            if c1_predicted > 0 and hasattr(self.strategy, 'update_adaptive'):
                self.strategy.update_adaptive(
                    bet_direction, c1_predicted, numero, roulette.WHEEL_SEQUENCE
                )
                self.game_state._adaptive_state = self.strategy.get_adaptive_state()
        
        self.game_state.save()

        # 4. Analisar com SDA-21
        result = self.strategy.analyze(
            self.game_state.target_timeline,
            self.game_state.last_number,
            roulette.WHEEL_SEQUENCE,
            calibration=0
        )

        # 5. Triple Rate Advisor
        advice = self.game_state.get_bet_advice(sda_score=result.score)
        c4_rate = getattr(advice, 'c4_rate', 0.5)

        # 6. Decisão combinada — Smart Gale v6: SEMPRE aposta
        #    BUG-28-03/M-01: c4_rate para gale vem de performance_bet (apostas reais)
        bet_c4_rate = self.game_state.get_bet_c4_rate()

        if result.should_bet:
            mg = self.game_state.target_martingale
            mg.get_gale(score=result.score, c4_rate=bet_c4_rate, confidence=advice.confidence)
            
            acao = "APOSTAR"
            action_reason = f"SDA score={result.score} | {mg.gale_display} | C4={bet_c4_rate:.0%}"
            self.game_state.store_prediction(
                result.numbers, self.game_state.target_direction, result.center,
                predicted_force=result.details.get("predicted_force", 0),
                bet_placed=True,
                tr_confidence=advice.confidence,
                tr_reason=advice.reason,
                sda_score=result.score,
                sda_centers=result.details.get("centers", [result.center])
            )
        elif self.game_state.target_timeline.size > 0:
            # BUG-28-01/M-02: SDA insuficiente mas com dados → G1 seguro
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
        else:
            acao = "PULAR"
            action_reason = "Timeline vazia — sem dados para predição"

        mg = self.game_state.target_martingale
        confidence = {"alta": 80, "media": 50, "baixa": 20}.get(advice.confidence, 50)

        return SpinDecision(
            acao=acao,
            action_reason=action_reason,
            numbers=result.numbers,
            center=result.center,
            visual=result.visual,
            score=result.score,
            confidence=confidence,
            advice=advice,
            martingale_display=mg.gale_display,
            martingale_multiplier=mg.multiplier,
            current_bet=mg.current_bet,
            gale_level=mg.level,
            gale_display=mg.gale_display,
            hit_result=hit_result,
            martingale_info=martingale_info,
            force=force,
            sda_should_bet=result.should_bet,
            sda_details=result.details,
            performance_stats=self.game_state.get_performance_stats()
        )
