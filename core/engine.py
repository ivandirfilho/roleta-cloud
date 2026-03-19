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
                martingale_info = self.game_state.martingale_cw.update(hit_result)
            else:
                martingale_info = self.game_state.martingale_ccw.update(hit_result)

            if martingale_info.get("transition"):
                logger.info(f"  MARTINGALE ({bet_direction}): {martingale_info['transition']}")

        # 3. Processar spin
        force = self.game_state.process_spin(numero, direcao)
        self.game_state.save()

        # 4. Analisar com SDA-17
        result = self.strategy.analyze(
            self.game_state.target_timeline,
            self.game_state.last_number,
            roulette.WHEEL_SEQUENCE,
            calibration=0
        )

        # 5. Triple Rate Advisor
        advice = self.game_state.get_bet_advice(sda_score=result.score)

        # 6. Decisão combinada
        if result.should_bet:
            if advice.should_bet:
                acao = "APOSTAR"
                action_reason = f"SDA17 + Triple Rate aprovaram ({advice.confidence})"
                self.game_state.store_prediction(
                    result.numbers, self.game_state.target_direction, result.center,
                    predicted_force=result.details.get("predicted_force", 0),
                    bet_placed=True,
                    tr_confidence=advice.confidence,
                    tr_reason=advice.reason,
                    sda_score=result.score
                )
            else:
                acao = "PULAR"
                action_reason = f"Triple Rate vetou: {advice.reason}"
                self.game_state.store_prediction(
                    result.numbers, self.game_state.target_direction, result.center,
                    predicted_force=result.details.get("predicted_force", 0),
                    bet_placed=False,
                    tr_confidence=advice.confidence,
                    tr_reason=advice.reason,
                    sda_score=result.score
                )
        else:
            acao = "PULAR"
            action_reason = "SDA17 não recomendou (forças insuficientes)"

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
