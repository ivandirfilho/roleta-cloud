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

    # S-STRAT-11 — KILL v4 thresholds dinâmicos (clamps duros).
    KILL_V4_C4_MIN = 0.20
    KILL_V4_C4_MAX = 0.35
    KILL_V4_SDA_MIN = 2
    KILL_V4_SDA_MAX = 6
    KILL_V4_VOL_WINDOW = 30
    KILL_V4_EMA_ALPHA = 0.10

    def __init__(self):
        """Inicializa o advisor."""
        # S-OBS-6: counter in-process de disparos do Kill Switch v3+
        # Resetado apenas em restart do processo (estado vivo, sem SQL)
        self._kill_pulls_total: int = 0
        self._last_kill_ts: float = 0.0
        # S-STRAT-11: EMA de volatility por direção (compartilhada caso não venha direction).
        self._vol_ema: dict = {"cw": 0.30, "ccw": 0.30, "global": 0.30}
        self._kill_thr_c4: dict = {"cw": 0.30, "ccw": 0.30, "global": 0.30}
        self._kill_thr_sda: dict = {"cw": 4, "ccw": 4, "global": 4}

    def get_kill_stats(self) -> dict:
        """S-OBS-6: snapshot do estado do Kill Switch para /api/strategy."""
        return {
            "pulls_total": self._kill_pulls_total,
            "last_pull_ts": self._last_kill_ts if self._last_kill_ts else None,
            # S-STRAT-11: thresholds dinâmicos visíveis.
            "kill_v4": {
                "vol_ema": dict(self._vol_ema),
                "threshold_c4": dict(self._kill_thr_c4),
                "threshold_sda": dict(self._kill_thr_sda),
            },
        }

    def state_dict(self) -> dict:
        """S-OBS-7: estado serializavel para persistir em state.json (sobrevive restart)."""
        return {
            "kill_pulls_total": int(self._kill_pulls_total),
            "last_kill_ts": float(self._last_kill_ts),
        }

    def load_state(self, data: dict) -> None:
        """S-OBS-7: restaura counter apos restart. Tolera dict vazio/None."""
        if not data:
            return
        try:
            self._kill_pulls_total = int(data.get("kill_pulls_total", 0))
            self._last_kill_ts = float(data.get("last_kill_ts", 0.0))
        except (TypeError, ValueError):
            self._kill_pulls_total = 0
            self._last_kill_ts = 0.0
    
    def analyze(self, performance: List[bool], sda_score: int = 3,
                direction: Optional[str] = None) -> BetAdvice:
        """
        Analisa performance e retorna recomendação.

        Args:
            performance: Lista de resultados (True=acertou, False=errou), índice 0 = mais recente
            sda_score: Score de confiança do SDA17-R (1-6)
            direction: "cw"/"ccw" (S-STRAT-11) — usado para threshold dinâmico isolado.

        Returns:
            BetAdvice com recomendação
        """
        # Calcular taxas (mantidas para logging/dashboard)
        c4 = self._calculate_rate(performance, 4)
        m6 = self._calculate_rate(performance, 6)
        l12 = self._calculate_rate(performance, 12)

        # ============================================
        # S-STRAT-11 — KILL v4: thresholds DINÂMICOS por sentido
        # ============================================
        # Volatilidade do batch (binário 0/1) suavizada por EMA.
        dk = direction if direction in ("cw", "ccw") else "global"
        if len(performance) >= 4:
            window = performance[: min(self.KILL_V4_VOL_WINDOW, len(performance))]
            n = len(window)
            mean_w = sum(1 for x in window if x) / n
            var_w = sum((1.0 - mean_w if x else 0.0 - mean_w) ** 2 for x in window) / n
            std_w = var_w ** 0.5
            prev = self._vol_ema.get(dk, 0.30)
            self._vol_ema[dk] = self.KILL_V4_EMA_ALPHA * std_w + (1.0 - self.KILL_V4_EMA_ALPHA) * prev
            vol = self._vol_ema[dk]
            # Threshold dinâmico: mais volátil → mais permissivo (não vetar à toa).
            c4_thr = 0.30 - 0.5 * (vol - 0.30)
            sda_thr = 4 + round(vol * 4)
            c4_thr = max(self.KILL_V4_C4_MIN, min(self.KILL_V4_C4_MAX, c4_thr))
            sda_thr = max(self.KILL_V4_SDA_MIN, min(self.KILL_V4_SDA_MAX, sda_thr))
            self._kill_thr_c4[dk] = round(c4_thr, 4)
            self._kill_thr_sda[dk] = int(sda_thr)
        else:
            c4_thr = 0.30
            sda_thr = 4
            self._kill_thr_c4[dk] = 0.30
            self._kill_thr_sda[dk] = 4

        # Dados insuficientes → apostar (sem histórico para filtro)
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
        # KILL SWITCH v4 (S-STRAT-11): thresholds dinâmicos por direção.
        # Fallback ao v3 fixo quando direction não vier.
        # ============================================
        if len(performance) >= 4 and c4 < c4_thr and sda_score < sda_thr:
            import time as _t
            self._kill_pulls_total += 1
            self._last_kill_ts = _t.time()
            return BetAdvice(
                should_bet=False,
                confidence="baixa",
                reason=(
                    f"🛑 KILL v4 [{dk}]: c4={c4:.0%} < {c4_thr:.0%} + "
                    f"SDA={sda_score} < {sda_thr} (vol={self._vol_ema.get(dk, 0):.2f})"
                ),
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
