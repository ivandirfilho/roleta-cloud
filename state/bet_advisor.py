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
    # S-STRAT-8/12 integração — sinais informativos não-bloqueantes.
    # Populados só quando há dados suficientes (≥ MIN_FEATURE_ROWS por direção)
    # e os readers foram passados. should_bet NÃO é influenciado por eles ainda.
    feature_signal: Optional[dict] = None
    regime_signal: Optional[dict] = None

    def to_dict(self) -> dict:
        """Converte para dicionário para serialização JSON."""
        out = {
            "should_bet": self.should_bet,
            "confidence": self.confidence,
            "reason": self.reason,
            "rates": {
                "c4": round(self.c4_rate, 3),
                "m6": round(self.m6_rate, 3),
                "l12": round(self.l12_rate, 3)
            }
        }
        if self.feature_signal is not None:
            out["feature_signal"] = self.feature_signal
        if self.regime_signal is not None:
            out["regime_signal"] = self.regime_signal
        return out


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

    # S-STRAT-8 + S-STRAT-12 — feature/regime signals só são emitidos
    # quando há dados suficientes (evita decisão sobre ruído inicial).
    MIN_FEATURE_ROWS = 50
    REGIME_TOPK = 20

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
        # S-STRAT-11 (BUG-V3-02 fix): EMA de volatility por direção.
        # Baseline 0.45 (mais realista para sinal binário com acc≈0.45-0.50)
        # — antes era 0.30 que considerava ruído normal como "alta volatility".
        self._vol_ema: dict = {"cw": 0.45, "ccw": 0.45, "global": 0.45}
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
        """S-OBS-7 + BUG-V3-05: estado serializavel persiste vol_ema e thresholds."""
        return {
            "kill_pulls_total": int(self._kill_pulls_total),
            "last_kill_ts": float(self._last_kill_ts),
            "vol_ema": dict(self._vol_ema),
            "kill_thr_c4": dict(self._kill_thr_c4),
            "kill_thr_sda": dict(self._kill_thr_sda),
        }

    def load_state(self, data: dict) -> None:
        """S-OBS-7 + BUG-V3-05: restaura counter + vol_ema. Tolera dict vazio/None."""
        if not data:
            return
        try:
            self._kill_pulls_total = int(data.get("kill_pulls_total", 0))
            self._last_kill_ts = float(data.get("last_kill_ts", 0.0))
            vol = data.get("vol_ema") or {}
            for k in ("cw", "ccw", "global"):
                if k in vol:
                    self._vol_ema[k] = float(vol[k])
            thr_c4 = data.get("kill_thr_c4") or {}
            for k in ("cw", "ccw", "global"):
                if k in thr_c4:
                    self._kill_thr_c4[k] = float(thr_c4[k])
            thr_sda = data.get("kill_thr_sda") or {}
            for k in ("cw", "ccw", "global"):
                if k in thr_sda:
                    self._kill_thr_sda[k] = int(thr_sda[k])
        except (TypeError, ValueError):
            self._kill_pulls_total = 0
            self._last_kill_ts = 0.0
    
    def analyze(self, performance: List[bool], sda_score: int = 3,
                direction: Optional[str] = None,
                *,
                feature_reader: "Optional[object]" = None,
                regime_reader: "Optional[object]" = None,
                query_vec: "Optional[List[float]]" = None) -> BetAdvice:
        """
        Analisa performance e retorna recomendação.

        Args:
            performance: Lista de resultados (True=acertou, False=errou), índice 0 = mais recente
            sda_score: Score de confiança do SDA17-R (1-6)
            direction: "cw"/"ccw" (S-STRAT-11) — usado para threshold dinâmico isolado.
            feature_reader: opcional, FeatureStoreReader (S-STRAT-8). Quando
                            presente + direction válida + ≥MIN_FEATURE_ROWS
                            populadas, anexa `feature_signal` ao BetAdvice
                            (telemetria, NÃO altera should_bet).
            regime_reader:  opcional, RegimeSimilarityReader (S-STRAT-12). Idem.
                            Requer também `query_vec` (6d) para a busca.
            query_vec:      vetor 6-d do spin/regime atual para similaridade.

        Returns:
            BetAdvice com recomendação
        """
        # Calcular taxas (mantidas para logging/dashboard)
        c4 = self._calculate_rate(performance, 4)
        m6 = self._calculate_rate(performance, 6)
        l12 = self._calculate_rate(performance, 12)

        # S-STRAT-8 / S-STRAT-12 — sinais informativos opt-in.
        # Computa UMA vez para todos os returns abaixo.
        feature_signal = self._compute_feature_signal(direction, feature_reader)
        regime_signal = self._compute_regime_signal(direction, regime_reader, query_vec)

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
            # Threshold dinâmico (BUG-V3-02 fix): baseline vol=0.45 é o regime
            # estável. Vol > 0.45 ⇒ regime errático ⇒ KILL menos sensível.
            # BUG-V3-01 fix: sda_thr DECRESCE com vol (antes crescia).
            c4_thr = 0.30 - 0.5 * (vol - 0.45)
            sda_thr = 4 - round((vol - 0.45) * 4)
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
                l12_rate=l12,
                feature_signal=feature_signal,
                regime_signal=regime_signal,
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
                l12_rate=l12,
                feature_signal=feature_signal,
                regime_signal=regime_signal,
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
            l12_rate=l12,
            feature_signal=feature_signal,
            regime_signal=regime_signal,
        )
    
    # ------------------------------------------------------------------
    # S-STRAT-8 / S-STRAT-12 — helpers de sinais opt-in (não-bloqueantes)
    # ------------------------------------------------------------------
    def _compute_feature_signal(self, direction, feature_reader) -> Optional[dict]:
        """Lê last row + window do feature_store. Falha-aberta (retorna None)."""
        if feature_reader is None or direction not in ("cw", "ccw"):
            return None
        try:
            window = feature_reader.get_window(direction, limit=self.MIN_FEATURE_ROWS)
        except Exception:
            return None
        if not window or len(window) < self.MIN_FEATURE_ROWS:
            return None
        try:
            latest = window[0]
            hits = [1 for r in window if r.get("hit") is True]
            return {
                "source": "spin_features",
                "direction": direction,
                "rows": len(window),
                "recent_acc_10": latest.get("recent_acc_10"),
                "recent_acc_50": latest.get("recent_acc_50"),
                "streak_miss": latest.get("streak_miss"),
                "streak_hit": latest.get("streak_hit"),
                "window_hit_rate": round(len(hits) / len(window), 3),
            }
        except Exception:
            return None

    def _compute_regime_signal(self, direction, regime_reader, query_vec) -> Optional[dict]:
        """Score agregado top-K via pgvector. Falha-aberta."""
        if regime_reader is None or direction not in ("cw", "ccw"):
            return None
        if not query_vec or not isinstance(query_vec, list) or len(query_vec) != 6:
            return None
        try:
            score = regime_reader.regime_score(direction, query_vec, limit=self.REGIME_TOPK)
        except Exception:
            return None
        if not score or score.get("n", 0) < 5:
            return None
        return {
            "source": "spins_vectors",
            "direction": direction,
            "n": score.get("n"),
            "avg_distance": score.get("avg_distance"),
            "hit_rate": score.get("hit_rate"),
        }

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
