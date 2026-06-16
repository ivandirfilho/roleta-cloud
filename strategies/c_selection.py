"""CSelectionEngine — seleção C1/C2 variável (últimas 3 não-C3) + C3 fixo.

Pós-processador de cobertura: dado os 3 centros do SDA17 e o histórico de
atribuições (``hit_region`` com ``dist_c1/c2/c3``), escolhe **qual par apostar**
(``{C1|C2, C3}``) e devolve os números (união real dos raios). **Isolado por sentido.**

Camada evolutiva (shadow-first): além da regra incumbente, avalia regras
**candidatas em paralelo**, com escolhas **congeladas** (anti look-ahead), e um
guardrail de promoção baseado no **intervalo de Newcombe** da diferença de duas
proporções (human-in-the-loop, default OFF).

Correções incorporadas da auditoria de design (§10):
- B5: escolhas dos candidatos congeladas em ``freeze_candidates`` e avaliadas
  no resultado seguinte (sem recomputar após conhecer o número).
- B7: ``state_dict``/``load_state`` convertem ``deque(maxlen)`` <-> ``list``.
- B8: ``reset`` para troca de dealer/mesa.
- B10: N é a **união real** (pode ser <14 se C_win e C3 se sobrepõem).
- B11: guardrail = **Newcombe** (não comparar dois IC95) + ``min_n`` realista.
- B12: empate ``|d1|==|d2|`` é **voto neutro** (não força C2); sem maioria
  estrita -> incumbente.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

R_DEFAULT: int = 3
WINDOW_NONC3: int = 3
MIN_N_PROMOTE: int = 150  # B11: amostra mínima por candidato/sentido p/ promover
MAXLEN: int = 200         # >= MIN_N_PROMOTE (issue#1): senão a promoção nunca matura
EMA_ALPHA: float = 0.05
_FAR: int = 99            # distância "não-informativa" (None/ausente)


def _ad(x: Any) -> int:
    """abs() tolerante a None/ausente — `_attribute_hit_region` põe dist_c2/c3=None
    em jogadas com <3 centros ou miss total (issue#2)."""
    return abs(x) if x is not None else _FAR

# Regras candidatas avaliadas em shadow. A incumbente default é a 1ª.
CANDIDATE_RULES: Tuple[str, ...] = (
    "always_strong",   # baseline: região com maior taxa-base no sentido
    "vote_k2_nonc3",
    "vote_k3_nonc3",   # a regra do operador
    "vote_k4_nonc3",
    "vote_k5_nonc3",
    "always_c2",
)
DEFAULT_INCUMBENT: str = "always_strong"


def _dk(direction: str) -> str:
    return "cw" if direction in ("cw", "horario") else "ccw"


def _neighbors(center: int, radius: int, wheel: List[int]) -> List[int]:
    """Vizinhos de `center` na roda (inclui o centro). Defensivo a wheel vazia."""
    if not wheel:
        return [center]
    try:
        idx = wheel.index(center)
    except ValueError:
        return [center]
    n = len(wheel)
    return [wheel[(idx + o) % n] for o in range(-radius, radius + 1)]


def coverage_numbers(c_win: int, c3: int, wheel: List[int], radius: int = R_DEFAULT) -> List[int]:
    """União real dos raios de C_win e C3 (B10: pode ser <14 se sobrepõem)."""
    nums = set(_neighbors(c_win, radius, wheel)) | set(_neighbors(c3, radius, wheel))
    return sorted(nums)


def _vote_window(history: List[Dict[str, Any]], k: int) -> str:
    """Voto das últimas `k` jogadas NÃO-C3. Retorna 'C1'|'C2'|'' (sem maioria estrita).

    Cada entrada de `history` (mais antiga->mais nova) deve ter dist_c1/c2/c3
    (assinadas ou não — usamos o |.|). 'não-C3' = C3 não é o centro mais próximo.
    """
    picked: List[Dict[str, Any]] = []
    for h in reversed(history):
        d1, d2, d3 = _ad(h.get("dist_c1")), _ad(h.get("dist_c2")), _ad(h.get("dist_c3"))
        if d3 < d1 and d3 < d2:  # mais perto de C3 -> ignora (não informa C1 vs C2)
            continue
        picked.append(h)
        if len(picked) >= k:
            break
    c1 = c2 = 0
    for h in picked:
        d1, d2 = _ad(h.get("dist_c1")), _ad(h.get("dist_c2"))
        if d1 < d2:
            c1 += 1
        elif d2 < d1:
            c2 += 1
        # empate -> voto neutro (B12), não conta
    if c1 > c2:
        return "C1"
    if c2 > c1:
        return "C2"
    return ""  # sem maioria estrita


def _rule_choice(rule: str, history: List[Dict[str, Any]], strong: str, incumbent_choice: str) -> str:
    """Mapeia uma regra candidata -> 'C1'|'C2' (escolha do par {C?, C3})."""
    if rule == "always_strong":
        return strong
    if rule == "always_c2":
        return "C2"
    if rule.startswith("vote_k"):
        try:
            k = int(rule.split("_k")[1].split("_")[0])
        except (IndexError, ValueError):
            k = WINDOW_NONC3
        v = _vote_window(history, k)
        return v or incumbent_choice  # sem maioria estrita -> incumbente (B12)
    return strong


def _wilson_bounds(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe_diff_ci(k1: int, n1: int, k2: int, n2: int, z: float = 1.96) -> Tuple[float, float]:
    """IC da diferença p1-p2 (Newcombe 1998, método 10 — Wilson score based).

    Usado no guardrail de promoção (B11): só promove se o intervalo EXCLUI 0.
    """
    if n1 <= 0 or n2 <= 0:
        return (-1.0, 1.0)
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = _wilson_bounds(k1, n1, z)
    l2, u2 = _wilson_bounds(k2, n2, z)
    diff = p1 - p2
    lower = diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (lower, upper)


@dataclass
class CSelection:
    """Saída da seleção para uma jogada."""
    chosen: str                       # 'C1' | 'C2'
    pair: Tuple[str, str]             # ('C1','C3') | ('C2','C3')
    numbers: List[int]               # união real (N pode ser <14)
    centers: List[int]               # [c_win, c3]
    rule: str                        # regra incumbente usada
    scoreboard: Dict[str, Dict[str, Any]]
    confidence: float
    reason: str
    freeze_candidates: Dict[str, str]  # rule -> 'C1'/'C2' congelado (anti look-ahead, B5)


@dataclass
class _CandStat:
    hits: deque = field(default_factory=lambda: deque(maxlen=MAXLEN))
    ema: float = 0.0

    @property
    def n(self) -> int:
        return len(self.hits)

    @property
    def k(self) -> int:
        return sum(1 for x in self.hits if x)

    @property
    def rate(self) -> float:
        return (self.k / self.n) if self.n else 0.0


class CSelectionEngine:
    """Motor de seleção C1/C2 por sentido (incumbente + shadow de candidatos)."""

    def __init__(self, radius: int = R_DEFAULT) -> None:
        self.radius = int(radius)
        self._dirs: Dict[str, Dict[str, Any]] = {
            "cw": self._new_dir_state(),
            "ccw": self._new_dir_state(),
        }

    @staticmethod
    def _new_dir_state() -> Dict[str, Any]:
        return {
            "incumbent": DEFAULT_INCUMBENT,
            "candidates": {r: _CandStat() for r in CANDIDATE_RULES},
            "strong": "C2",          # taxa-base rolante (atualizada no feedback)
            "region_hits": {"C1": deque(maxlen=MAXLEN), "C2": deque(maxlen=MAXLEN)},
            "suggested": None,       # {rule, applied, ts}
        }

    # ---- seleção ----
    def select(
        self,
        direction: str,
        centers: List[int],
        attribution_history: List[Dict[str, Any]],
        wheel: List[int],
    ) -> CSelection:
        st = self._dirs[_dk(direction)]
        if not centers or len(centers) < 3:
            # Fallback defensivo (B-impl): caminho early-session/calibração do SDA17
            # pode trazer <3 centros. Não dá para separar C1/C2/C3 — devolve cobertura
            # do único centro disponível sem quebrar (caller decide se usa).
            base = centers[0] if centers else 0
            nums = coverage_numbers(base, base, wheel, self.radius)
            return CSelection(
                chosen="C1", pair=("C1", "C3"), numbers=nums, centers=[base, base],
                rule=st["incumbent"], scoreboard={}, confidence=0.0,
                reason="fallback:<3 centros", freeze_candidates={},
            )
        c1, c2, c3 = centers[0], centers[1], centers[2]
        strong = st["strong"]
        incumbent = st["incumbent"]
        incumbent_choice = strong  # fallback p/ regras sem maioria

        # Congela a escolha de TODOS os candidatos (B5) com a história ATUAL.
        freeze: Dict[str, str] = {}
        for rule in CANDIDATE_RULES:
            freeze[rule] = _rule_choice(rule, attribution_history, strong, incumbent_choice)

        chosen = freeze.get(incumbent, strong)
        c_win = c1 if chosen == "C1" else c2
        numbers = coverage_numbers(c_win, c3, wheel, self.radius)

        scoreboard = {
            r: {"n": cs.n, "rate": round(cs.rate, 4), "ema": round(cs.ema, 5)}
            for r, cs in st["candidates"].items()
        }
        inc_stat = st["candidates"][incumbent]
        confidence = min(1.0, inc_stat.n / float(MIN_N_PROMOTE)) if inc_stat.n else 0.0
        return CSelection(
            chosen=chosen,
            pair=(chosen, "C3"),
            numbers=numbers,
            centers=[c_win, c3],
            rule=incumbent,
            scoreboard=scoreboard,
            confidence=round(confidence, 3),
            reason=f"incumbent={incumbent} strong={strong}",
            freeze_candidates=freeze,
        )

    # ---- feedback ----
    def feedback(
        self,
        direction: str,
        freeze_candidates: Dict[str, str],
        hit_attr: Dict[str, Any],
        auto_promote: bool = False,
    ) -> Dict[str, Any]:
        """Avalia as escolhas CONGELADAS contra o resultado (hit_attr) e atualiza.

        `hit_attr` deve ter dist_c1/c2/c3 (do `hit_region`). O par {Cx, C3}
        acerta se min(|d_x|, |d_c3|) <= raio.
        """
        st = self._dirs[_dk(direction)]
        d1, d2, d3 = _ad(hit_attr.get("dist_c1")), _ad(hit_attr.get("dist_c2")), _ad(hit_attr.get("dist_c3"))
        dist_by = {"C1": d1, "C2": d2}

        # taxa-base rolante por região (B11/always_strong) — só quando informativo.
        if not (d3 < d1 and d3 < d2):
            st["region_hits"]["C1"].append(1 if d1 <= self.radius else 0)
            st["region_hits"]["C2"].append(1 if d2 <= self.radius else 0)
        rc1 = st["region_hits"]["C1"]
        rc2 = st["region_hits"]["C2"]
        if rc1 and rc2:
            r1 = sum(rc1) / len(rc1)
            r2 = sum(rc2) / len(rc2)
            st["strong"] = "C1" if r1 > r2 else "C2"

        # avalia cada candidato pela sua escolha CONGELADA (B5).
        for rule, choice in (freeze_candidates or {}).items():
            cs = st["candidates"].get(rule)
            if cs is None:
                continue
            d_chosen = dist_by.get(choice, d1)
            won = 1 if min(d_chosen, d3) <= self.radius else 0
            cs.hits.append(won)
            cs.ema = cs.ema * (1 - EMA_ALPHA) + won * EMA_ALPHA

        promo = self._maybe_promote(st) if auto_promote else None
        return {"strong": st["strong"], "incumbent": st["incumbent"], "promotion": promo}

    def _maybe_promote(self, st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Promoção human-in-the-loop: só sugere se Newcombe(challenger, incumbente)
        exclui 0 e ambos têm n>=MIN_N_PROMOTE. NÃO troca sozinho a menos que opt-in."""
        inc = st["incumbent"]
        inc_stat = st["candidates"][inc]
        if inc_stat.n < MIN_N_PROMOTE:
            return None
        best = None
        for rule, cs in st["candidates"].items():
            if rule == inc or cs.n < MIN_N_PROMOTE:
                continue
            lo, _hi = newcombe_diff_ci(cs.k, cs.n, inc_stat.k, inc_stat.n)
            if lo > 0.0 and (best is None or cs.rate > best[1]):
                best = (rule, cs.rate)
        if best is None:
            return None
        st["incumbent"] = best[0]  # auto_promote=True já é opt-in do caller
        st["suggested"] = {"rule": best[0], "applied": True}
        return {"promoted_to": best[0], "rate": round(best[1], 4)}

    # ---- reset / persistência ----
    def reset(self, direction: Optional[str] = None) -> None:
        keys = [_dk(direction)] if direction else ["cw", "ccw"]
        for k in keys:
            self._dirs[k] = self._new_dir_state()

    def state_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"radius": self.radius}
        for dk, st in self._dirs.items():
            out[dk] = {
                "incumbent": st["incumbent"],
                "strong": st["strong"],
                "suggested": st["suggested"],
                "candidates": {
                    r: {"hits": list(cs.hits), "ema": cs.ema}
                    for r, cs in st["candidates"].items()
                },
                "region_hits": {
                    "C1": list(st["region_hits"]["C1"]),
                    "C2": list(st["region_hits"]["C2"]),
                },
            }
        return out

    def load_state(self, d: Dict[str, Any]) -> None:
        if not d:
            return
        self.radius = int(d.get("radius", self.radius))
        for dk in ("cw", "ccw"):
            sd = d.get(dk)
            if not sd:
                continue
            st = self._new_dir_state()
            inc = sd.get("incumbent", DEFAULT_INCUMBENT)
            st["incumbent"] = inc if inc in CANDIDATE_RULES else DEFAULT_INCUMBENT  # issue#3
            st["strong"] = "C1" if sd.get("strong") == "C1" else "C2"
            st["suggested"] = sd.get("suggested")
            for r, cd in (sd.get("candidates") or {}).items():
                if r not in st["candidates"]:
                    continue
                cs = _CandStat()
                cs.hits = deque(cd.get("hits", []), maxlen=MAXLEN)
                cs.ema = float(cd.get("ema", 0.0))
                st["candidates"][r] = cs
            rh = sd.get("region_hits") or {}
            st["region_hits"]["C1"] = deque(rh.get("C1", []), maxlen=MAXLEN)
            st["region_hits"]["C2"] = deque(rh.get("C2", []), maxlen=MAXLEN)
            self._dirs[dk] = st
