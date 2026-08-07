"""Dealer Signature — assinatura por dealer×sentido + bandit Thompson p/ o R2.

Proposta R2 Dealer-Aware (ADENDO 05/08 noite-2). O R2 da V5.1 spec4 hoje é
derivado (R1 + tendência Theil–Sen): quase não carrega informação
independente e não tem feedback corretivo. Este módulo aprende, POR DEALER e
POR SENTIDO, qual heurística de R2 está acertando AGORA, e corrige o centro
com o erro assinado recente — aprendizado com o erro E com o acerto.

Arquitetura (3 camadas + árbitro):
  S0 (sessão)      — EWMA do erro assinado do R2 (meia-vida 8 spins) +
                     histórico curto (12) por dealer×sentido. Vive no estado
                     adaptativo (round-trip v2.0 no sda17).
  S1 (longo prazo) — força modal do dealer no SQLite `decisions`
                     (reusa strategies/dealer_force_profile.force_profile,
                     n>=30, janela 24h) com cache TTL p/ não bater no banco
                     a cada spin.
  Bandit           — Thompson Sampling Beta(α,β) com decay γ=0.98 sobre 4
                     braços candidatos de força do R2:
                       trend    = R1 + clamp(round(slope), ±8)  (= produção)
                       residual = 2º cluster de gravidade fora do poço de R1
                                  (caminho go-live 04/08)
                       dealer   = força modal S1 do dealer (clamp ±8 de R1)
                       correct  = trend + micro-correção do EWMA de erro
                                  (gate: 3-de-4 sinais iguais e |ewma|>=2)
  O braço vencedor vira o candidato de R2; hit/miss DO R2 atualiza o braço
  escolhido. Classes DATA_SUSPECT (error_engine) congelam o update.

INV-3: nada aqui suprime indicação — só move o CENTRO do R2 (o call-site
mantém disjunção via nearest_non_overlapping e stake intactos). Puro exceto
o cache S1 (I/O SQLite defensivo, nunca levanta). Flags ficam no call-site.
Testes: tests/test_dealer_signature.py.
"""
from __future__ import annotations

import random
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Sequence, Tuple

from strategies.regions_v5 import (
    V5_GRAVITY,
    V5_R2_CLAMP,
    V5_SIG4_WINDOW,
    circ_force_dist,
    gravity_scan,
    signed_force_diff,
)

# ---- Constantes do aprendizado ----
ARMS = ("trend", "residual", "dealer", "correct")
EWMA_HALF_LIFE = 8.0                       # meia-vida do erro (spins)
EWMA_ALPHA = 1.0 - 0.5 ** (1.0 / EWMA_HALF_LIFE)   # ≈ 0.0830
BANDIT_DECAY = 0.98                        # esquecimento por update (regime muda)
ERR_HIST_MAXLEN = 12                       # histórico curto p/ SIGNATURE_SHIFT
ERR_WINSOR = 8                             # winsoriza erro assinado a ±8
CORRECT_MIN_EWMA = 2.0                     # gate do braço correct
CORRECT_SIGN_AGREE = 3                     # 3 dos últimos 4 erros no mesmo sinal
CORRECT_CLAMP = 3                          # micro-correção máxima (casas)
MAX_KEYS = 16                              # LRU de dealer×sentido no estado
S1_CACHE_TTL = 300.0                       # segundos (cache do perfil SQLite)

_LEGACY_DIR = {"cw": "horario", "ccw": "anti-horario"}


def _norm_key(dealer: Optional[str], dk: str) -> str:
    d = (str(dealer).strip().lower() if dealer else "") or "unknown"
    return f"{d}|{dk}"


def _clamp_to_r1(force: int, r1_force: int, size: int,
                 clamp: int = V5_R2_CLAMP) -> int:
    """Clampa uma força candidata ao arco ±clamp de R1 (mesma regra do compose)."""
    diff = signed_force_diff(int(force), int(r1_force), size)
    if diff > clamp:
        diff = clamp
    elif diff < -clamp:
        diff = -clamp
    return (int(r1_force) + diff) % size


# ---- S1: perfil de longo prazo (SQLite) com cache TTL ----

_s1_cache: Dict[Tuple[str, str, str], Tuple[float, Optional[int]]] = {}


def long_term_modal_force(
    db_path: str,
    dealer: Optional[str],
    dk: str,
    *,
    loader=None,
    now: Optional[float] = None,
) -> Optional[int]:
    """Força modal do dealer×sentido no SQLite (n>=30, 24h) — None se sem dado.

    Cacheia por (db_path, dealer, dk) por S1_CACHE_TTL s (inclusive resultado
    negativo, para não bater no banco a cada spin). Nunca levanta.
    `loader` injetável p/ teste (default: dealer_force_profile.force_profile).
    """
    d = (str(dealer).strip().lower() if dealer else "") or "unknown"
    if d == "unknown" or dk not in _LEGACY_DIR:
        return None
    key = (str(db_path), d, dk)
    ts = time.monotonic() if now is None else now
    hitc = _s1_cache.get(key)
    if hitc is not None and ts - hitc[0] < S1_CACHE_TTL:
        return hitc[1]
    modal: Optional[int] = None
    try:
        if loader is None:
            from strategies.dealer_force_profile import force_profile as loader
        prof = loader(str(db_path), str(dealer), direction=_LEGACY_DIR[dk])
        if prof and prof.get("n"):
            modal = int(prof["modal_force"])
    except Exception:
        modal = None
    _s1_cache[key] = (ts, modal)
    # poda defensiva do cache (processo de longa duração)
    if len(_s1_cache) > 64:
        oldest = sorted(_s1_cache.items(), key=lambda kv: kv[1][0])[:32]
        for k, _ in oldest:
            _s1_cache.pop(k, None)
    return modal


def clear_s1_cache() -> None:
    """Limpa o cache S1 (uso em testes)."""
    _s1_cache.clear()


# ---- Estado por dealer×sentido + bandit ----

def _fresh_entry() -> dict:
    return {
        "arms": {a: [1.0, 1.0] for a in ARMS},  # Beta(1,1) = uniforme
        "ewma": None,                            # EWMA do erro assinado do R2
        "hist": [],                              # últimos erros assinados (<=12)
        "n": 0,                                  # updates aprendidos
    }


class DealerSignature:
    """Assinatura adaptativa por dealer×sentido (S0 + bandit). Serializável."""

    def __init__(self) -> None:
        self._keys: "OrderedDict[str, dict]" = OrderedDict()

    # -- acesso --

    @staticmethod
    def key(dealer: Optional[str], dk: str) -> str:
        return _norm_key(dealer, dk)

    def _entry(self, key: str) -> dict:
        e = self._keys.get(key)
        if e is None:
            e = _fresh_entry()
            self._keys[key] = e
        self._keys.move_to_end(key)
        while len(self._keys) > MAX_KEYS:      # LRU: estado pequeno no snapshot
            self._keys.popitem(last=False)
        return e

    def err_hist(self, key: str) -> List[float]:
        e = self._keys.get(key)
        return list(e["hist"]) if e else []

    def stats(self, key: str) -> dict:
        """Snapshot leve p/ DNA/observabilidade (não cria entrada)."""
        e = self._keys.get(key)
        if not e:
            return {}
        return {"n": e["n"], "ewma": e["ewma"],
                "arms": {a: [round(v, 3) for v in ab]
                         for a, ab in e["arms"].items()}}

    # -- candidatos --

    def candidates(
        self,
        key: str,
        *,
        r1_force: int,
        slope: Optional[float],
        forces_recent_first: Sequence[int],
        size: int,
        dealer_modal_force: Optional[int] = None,
    ) -> Dict[str, int]:
        """Força candidata de R2 por braço. Braços sem insumo são omitidos.

        `trend` existe sempre (fallback = produção spec4); `residual` replica
        o caminho go-live; `dealer` exige S1; `correct` exige gate de erro.
        """
        size = int(size)
        r1f = int(r1_force)
        out: Dict[str, int] = {}

        # trend — byte-idêntico ao R2 spec4 de produção.
        delta = 0 if slope is None else int(round(slope))
        out["trend"] = _clamp_to_r1(r1f + delta, r1f, size, clamp=V5_R2_CLAMP)

        # residual — 2º cluster fora do poço ±7 de R1 (lógica go-live 04/08).
        window = [int(f) for f in list(forces_recent_first)[:V5_SIG4_WINDOW]]
        residual = [f for f in window
                    if circ_force_dist(f, r1f, size) > V5_GRAVITY]
        if residual:
            side = 1 if (slope is None or slope >= 0) else -1
            sided = [f for f in residual
                     if signed_force_diff(f, r1f, size) * side > 0]
            pool = sided or residual
            scan = gravity_scan(pool, size)
            if scan is not None:
                out["residual"] = _clamp_to_r1(scan[0], r1f, size)

        # dealer — força modal de longo prazo (S1), clampada ao arco de R1.
        if dealer_modal_force is not None:
            out["dealer"] = _clamp_to_r1(int(dealer_modal_force), r1f, size)

        # correct — trend + micro-correção do EWMA de erro (gate anti-ruído).
        e = self._keys.get(key)
        if e and e["ewma"] is not None and len(e["hist"]) >= 4:
            ewma = float(e["ewma"])
            last4 = e["hist"][-4:]
            sign = 1 if ewma > 0 else -1
            agree = sum(1 for v in last4 if v * sign > 0)
            if abs(ewma) >= CORRECT_MIN_EWMA and agree >= CORRECT_SIGN_AGREE:
                shift = int(round(ewma))
                shift = max(-CORRECT_CLAMP, min(CORRECT_CLAMP, shift))
                if shift:
                    out["correct"] = _clamp_to_r1(
                        out["trend"] + shift, r1f, size)
        return out

    # -- decisão (Thompson) --

    def choose(
        self,
        key: str,
        candidates: Dict[str, int],
        rng: Optional[random.Random] = None,
    ) -> Tuple[str, int]:
        """Thompson Sampling: amostra Beta(α,β) por braço ativo, maior vence."""
        if not candidates:
            raise ValueError("candidates vazio")
        e = self._entry(key)
        r = rng or random
        best_arm, best_draw = None, -1.0
        for arm in ARMS:                       # ordem fixa = desempate estável
            if arm not in candidates:
                continue
            a, b = e["arms"].get(arm, [1.0, 1.0])
            draw = r.betavariate(max(a, 1e-6), max(b, 1e-6))
            if draw > best_draw:
                best_arm, best_draw = arm, draw
        assert best_arm is not None
        return best_arm, candidates[best_arm]

    # -- aprendizado --

    def update(
        self,
        key: str,
        arm: str,
        hit: bool,
        signed_err: Optional[float] = None,
        *,
        frozen: bool = False,
    ) -> None:
        """Atualiza bandit + S0 com o resultado do R2 escolhido.

        frozen=True (error_class DATA_SUSPECT) → no-op total: nem posterior,
        nem EWMA, nem histórico — dado suspeito não ensina nada.
        """
        if frozen:
            return
        e = self._entry(key)
        for ab in e["arms"].values():          # decay: esquece regimes velhos
            ab[0] = 1.0 + (ab[0] - 1.0) * BANDIT_DECAY
            ab[1] = 1.0 + (ab[1] - 1.0) * BANDIT_DECAY
        ab = e["arms"].setdefault(arm, [1.0, 1.0])
        if hit:
            ab[0] += 1.0
        else:
            ab[1] += 1.0
        if signed_err is not None:
            err = max(-float(ERR_WINSOR), min(float(ERR_WINSOR),
                                              float(signed_err)))
            e["ewma"] = err if e["ewma"] is None else (
                (1.0 - EWMA_ALPHA) * float(e["ewma"]) + EWMA_ALPHA * err)
            e["hist"].append(err)
            del e["hist"][:-ERR_HIST_MAXLEN]
        e["n"] += 1

    # -- round-trip (estado adaptativo v2.0) --

    def to_dict(self) -> dict:
        return {
            "v": 1,
            "keys": {
                k: {
                    "arms": {a: [float(ab[0]), float(ab[1])]
                             for a, ab in e["arms"].items()},
                    "ewma": e["ewma"],
                    "hist": list(e["hist"]),
                    "n": int(e["n"]),
                }
                for k, e in self._keys.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "DealerSignature":
        """Restaura defensivamente: entradas malformadas são ignoradas."""
        inst = cls()
        if not isinstance(data, dict):
            return inst
        keys = data.get("keys")
        if not isinstance(keys, dict):
            return inst
        for k, e in list(keys.items())[:MAX_KEYS]:
            if not isinstance(k, str) or not isinstance(e, dict):
                continue
            entry = _fresh_entry()
            arms = e.get("arms")
            if isinstance(arms, dict):
                for a in ARMS:
                    ab = arms.get(a)
                    if (isinstance(ab, (list, tuple)) and len(ab) == 2):
                        try:
                            entry["arms"][a] = [max(float(ab[0]), 1e-6),
                                                max(float(ab[1]), 1e-6)]
                        except (TypeError, ValueError):
                            pass
            ewma = e.get("ewma")
            if isinstance(ewma, (int, float)):
                entry["ewma"] = float(ewma)
            hist = e.get("hist")
            if isinstance(hist, list):
                vals = [float(v) for v in hist
                        if isinstance(v, (int, float))]
                entry["hist"] = vals[-ERR_HIST_MAXLEN:]
            n = e.get("n")
            if isinstance(n, int) and n >= 0:
                entry["n"] = n
            inst._keys[k] = entry
        return inst
