# Roleta Cloud - Kill Switch Advisor (v2)
# Filtro minimalista: só veta quando AMBOS os sinais indicam catástrofe

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BetAdvice:
    """Resultado da análise do Kill Switch Advisor."""
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
    Kill Switch Advisor (v2).
    
    Filosofia: APOSTAR SEMPRE, só vetar catástrofe.
    
    Kill Switch ativa quando AMBOS são verdadeiros:
    - C4 = 0% (zero acertos nos últimos 4 resultados)
    - SDA Score ≤ 2 (dados muito dispersos, sem padrão)
    
    Em qualquer outra situação: APOSTAR.
    O Martingale (G1→G2→G3→STOP) é o real controle de risco.
    """
    
    MIN_DATA = 2
    
    def __init__(self):
        """Inicializa o advisor."""
        pass
    
    def analyze(self, performance: List[bool], sda_score: int = 3) -> BetAdvice:
        """
        Analisa performance e retorna recomendação.
        
        Args:
            performance: Lista de resultados (True=acertou, False=errou), índice 0 = mais recente
            sda_score: Score de confiança do SDA17-R (1-6)
        
        Returns:
            BetAdvice com recomendação
        """
        # Calcular taxas (mantidas para logging/dashboard)
        c4 = self._calculate_rate(performance, 4)
        m6 = self._calculate_rate(performance, 6)
        l12 = self._calculate_rate(performance, 12)
        
        # Dados insuficientes → apostar (sem histórico para vetar)
        if len(performance) < self.MIN_DATA:
            return BetAdvice(
                should_bet=True,
                confidence="media",
                reason="⚡ Início rápido (dados insuficientes para filtro)",
                c4_rate=c4,
                m6_rate=m6,
                l12_rate=l12
            )
        
        # ============================================
        # KILL SWITCH: Só veta catástrofe absoluta
        # ============================================
        # Condição: ZERO acertos em 4+ rounds E dados ruins do SDA
        if len(performance) >= 4 and c4 == 0 and sda_score <= 2:
            return BetAdvice(
                should_bet=False,
                confidence="baixa",
                reason=f"🛑 KILL SWITCH: 0/4 acertos + Score SDA={sda_score}",
                c4_rate=c4,
                m6_rate=m6,
                l12_rate=l12
            )
        
        # ============================================
        # TUDO MAIS: APOSTAR
        # ============================================
        # Determinar confiança para display
        if c4 >= m6 >= l12 and c4 > 0:
            confidence = "alta"
            reason = f"📈 CRESCENTE ({c4:.0%} > {m6:.0%} > {l12:.0%})"
        elif c4 >= m6:
            confidence = "alta"
            reason = f"📊 ESTÁVEL ({c4:.0%} ≥ {m6:.0%})"
        elif c4 > 0:
            confidence = "media"
            reason = f"⚡ AGRESSIVO ({c4:.0%} < {m6:.0%}, mas apostando)"
        else:
            confidence = "media"
            reason = f"⚡ COLD mas Score SDA={sda_score} (confiando nos dados)"
        
        return BetAdvice(
            should_bet=True,
            confidence=confidence,
            reason=reason,
            c4_rate=c4,
            m6_rate=m6,
            l12_rate=l12
        )
    
    def _calculate_rate(self, performance: List[bool], window: int) -> float:
        """
        Calcula taxa de acerto para uma janela específica.
        
        Args:
            performance: Lista de resultados
            window: Tamanho da janela (4, 6 ou 12)
        
        Returns:
            Taxa de acerto (0.0 a 1.0)
        """
        if len(performance) < window:
            if len(performance) == 0:
                return 0.0
            return sum(performance) / len(performance)
        
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
