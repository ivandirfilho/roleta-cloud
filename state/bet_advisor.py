# Roleta Cloud - Triple Rate Advisor
# Sistema de aconselhamento de apostas baseado em análise de tendência multi-timeframe

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BetAdvice:
    """Resultado da análise do Triple Rate Advisor."""
    should_bet: bool      # True = APOSTAR, False = PULAR
    confidence: str       # "alta", "media", "baixa"
    reason: str           # Explicação em português
    c4_rate: float        # Taxa curto prazo (últimos 4)
    m6_rate: float        # Taxa médio prazo (últimos 6)
    l12_rate: float       # Taxa longo prazo (últimos 12)
    
    def to_dict(self) -> dict:
        """Converte para dicionário para serialização JSON."""
        return {
            "should_bet": self.should_bet,
            "confidence": self.confidence,
            "reason": self.reason,
            "rates": {
                "c4": round(self.c4_rate, 3),
                "m6": round(self.m6_rate, 3),
                "l12": round(self.l12_rate, 3)
            }
        }


class TripleRateAdvisor:
    """
    Analisa tendência usando 3 janelas temporais (Triple Rate).
    
    Conceito:
    - C4: Taxa de acerto nos últimos 4 resultados (curto prazo)
    - M6: Taxa de acerto nos últimos 6 resultados (médio prazo)
    - L12: Taxa de acerto nos últimos 12 resultados (longo prazo)
    
    Lógica:
    - Se C4 >= M6 → Tendência positiva/estável → APOSTAR
    - Se C4 < M6  → Tendência negativa → PULAR
    
    Baseado no backtest:
    - Score: 39.0 (2º melhor)
    - STOPs no Gale: 0 (melhor resultado)
    - Máximo perdas consecutivas: 4 (melhor resultado)
    """
    
    MIN_DATA = 4  # Mínimo de dados para análise
    
    def __init__(self):
        """Inicializa o advisor."""
        pass
    
    def analyze(self, performance: List[bool]) -> BetAdvice:
        """
        Analisa performance histórica e retorna recomendação.
        
        Args:
            performance: Lista de resultados (True=acertou, False=errou)
                         Índice 0 = mais recente
        
        Returns:
            BetAdvice com recomendação e estatísticas
        """
        # Dados insuficientes
        if len(performance) < self.MIN_DATA:
            return BetAdvice(
                should_bet=True,  # Default: apostar se sem dados
                confidence="baixa",
                reason="⚠️ Dados insuficientes para análise",
                c4_rate=0.0,
                m6_rate=0.0,
                l12_rate=0.0
            )
        
        # Calcular taxas por janela temporal
        c4 = self._calculate_rate(performance, 4)
        m6 = self._calculate_rate(performance, 6)
        l12 = self._calculate_rate(performance, 12)
        
        # Verificação de taxa mínima (cold streak protection)
        if c4 < 0.25:
            return BetAdvice(
                should_bet=False,
                confidence="baixa",
                reason=f"🥶 COLD STREAK ({c4:.0%} taxa muito baixa)",
                c4_rate=c4,
                m6_rate=m6,
                l12_rate=l12
            )
        
        # Decisão baseada na tendência
        if c4 >= m6 >= l12 and c4 > 0:
            # Tendência claramente crescente
            return BetAdvice(
                should_bet=True,
                confidence="alta",
                reason=f"📈 CRESCENTE ({c4:.0%} > {m6:.0%} > {l12:.0%})",
                c4_rate=c4,
                m6_rate=m6,
                l12_rate=l12
            )
        elif c4 >= m6:
            # Tendência estável ou recuperando
            return BetAdvice(
                should_bet=True,
                confidence="media",
                reason=f"📊 ESTÁVEL ({c4:.0%} ≥ {m6:.0%})",
                c4_rate=c4,
                m6_rate=m6,
                l12_rate=l12
            )
        else:
            # Tendência negativa - pular
            return BetAdvice(
                should_bet=False,
                confidence="baixa",
                reason=f"📉 DECRESCENTE ({c4:.0%} < {m6:.0%})",
                c4_rate=c4,
                m6_rate=m6,
                l12_rate=l12
            )
    
    def _calculate_rate(self, performance: List[bool], window: int) -> float:
        """
        Calcula taxa de acerto para uma janela específica.
        
        Args:
            performance: Lista de resultados
            window: Tamanho da janela (4, 6, ou 12)
        
        Returns:
            Taxa de acerto (0.0 a 1.0)
        """
        if len(performance) < window:
            # Se não tem dados suficientes, usa o que tem
            if len(performance) == 0:
                return 0.0
            return sum(performance) / len(performance)
        
        # Usa exatamente a janela solicitada
        window_data = performance[:window]
        return sum(window_data) / len(window_data)
    
    def get_stats(self, performance: List[bool]) -> dict:
        """
        Retorna estatísticas detalhadas para debug/dashboard.
        
        Args:
            performance: Lista de resultados
            
        Returns:
            Dicionário com estatísticas
        """
        advice = self.analyze(performance)
        
        # Streak atual
        streak = 0
        streak_type = performance[0] if performance else None
        for result in performance:
            if result == streak_type:
                streak += 1
            else:
                break
        
        return {
            "advice": advice.to_dict(),
            "stats": {
                "total_results": len(performance),
                "total_hits": sum(performance) if performance else 0,
                "overall_rate": sum(performance) / len(performance) if performance else 0,
                "current_streak": streak,
                "streak_type": "hit" if streak_type else "miss" if streak_type is not None else None
            }
        }
