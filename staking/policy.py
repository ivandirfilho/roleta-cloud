"""Políticas de staking flat / kelly por sentido (spec flat_kelly_junho.md §6).

Substituem o Gale (anti-martingale 17/34/51) quando ``SDA_STAKING_MODE`` é
``flat`` ou ``kelly``. O modo ``gale`` NÃO passa por aqui — ``get_effective_bet``
retorna cedo no dispatcher, mantendo o caminho legado byte-idêntico.

Princípios (provados nos estudos, ver §2 do spec):
- o stake NÃO depende de vitórias/derrotas recentes (jogadas são independentes);
- ``flat`` = stake constante ``U·N`` (U por número, N = nº de números apostados);
- ``kelly`` = Kelly fracionário por sentido, com ``p̂`` rolling (janela longa),
  cap e floor INV-3; ``f*≤0`` ou ``p̂`` indefinido (warmup) → floor/flat.

Estas funções são PURAS (sem efeitos colaterais, sem ler env diretamente) para
serem trivialmente testáveis; toda a configuração entra por parâmetro.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Fallback de N quando o nº de números não é informado/é inválido (geometria V4).
DEFAULT_N = 21

# Payout da roda europeia (paga 36× a fração apostada por número).
PAYOUT = 36.0


def _cfg_get(cfg: Any, section: str, key: str, default: Any) -> Any:
    """Lê ``cfg.get(section, key, default)`` de forma tolerante a falhas."""
    if cfg is None:
        return default
    try:
        return cfg.get(section, key, default)
    except Exception:  # noqa: BLE001 — config nunca quebra o fluxo de aposta
        return default


def _safe_n(n_numbers: Optional[int]) -> int:
    try:
        n = int(n_numbers)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_N
    return n if n > 0 else DEFAULT_N


def _rolling_rate(strategy: Any, direction: str, window: int) -> Optional[float]:
    """p̂ do sentido via janela LONGA (``rolling_hit_rate``). None se indisponível
    (estratégia sem o método, ou warmup). NUNCA reusa o rate de 30 do QW-1."""
    fn = getattr(strategy, "rolling_hit_rate", None)
    if not callable(fn):
        return None
    try:
        return fn(direction, window)
    except Exception:  # noqa: BLE001
        return None


def flat_stake(n_numbers: Optional[int], unit: float) -> int:
    """Stake TOTAL constante = round(unit · N), piso 1u (INV-3)."""
    n = _safe_n(n_numbers)
    return max(1, int(round(float(unit) * n)))


def kelly_stake(
    p: Optional[float],
    n_numbers: Optional[int],
    *,
    unit: float,
    fraction: float,
    cap: float,
    bankroll: float,
) -> int:
    """Stake TOTAL pelo critério de Kelly fracionário.

    b = (36 − N) / N ; f* = p − (1 − p) / b ; stake = round(bankroll · k · f*),
    limitado a [1u, round(cap · bankroll)]. Casos de borda:
    - ``p is None`` (warmup): comporta-se como ``flat`` (stake constante);
    - ``f* ≤ 0`` (sem edge, p ≤ N/36): stake = 1u (floor INV-3, nunca escala).
    """
    n = _safe_n(n_numbers)
    if p is None:  # warmup → flat
        return flat_stake(n, unit)
    b = (PAYOUT - n) / n if 0 < n < PAYOUT else 0.0
    if b <= 0:
        return 1
    f_star = p - (1.0 - p) / b
    if f_star <= 0:  # sem edge → floor INV-3
        return 1
    cap_units = max(1, int(round(float(cap) * float(bankroll))))
    raw = int(round(float(bankroll) * float(fraction) * f_star))
    return max(1, min(cap_units, raw))


def _result(stake: int, mode: str, rate: Optional[float]) -> Dict[str, Any]:
    """Mesmo shape que ``GameState.get_effective_bet`` devolve no caminho gale."""
    stake = max(1, int(stake))
    return {
        "effective_bet": stake,
        "base_bet": stake,          # vetos pós-dispatcher reduzem fração DESTE stake
        "multiplier": 1.0,
        "mode": mode,               # vira "stake_mode" no payload do front
        "rolling_rate": rate,
        "minimizer_active": False,
    }


def compute_staking(
    mode: str,
    *,
    direction: str,
    n_numbers: Optional[int],
    strategy: Any,
) -> Dict[str, Any]:
    """Dispatcher flat/kelly. Lê parâmetros de ``strategy._cfg`` (``[sda17.staking]``).

    Retorna o dict de stake consumido por ``message_handler`` (``effective_bet``,
    ``base_bet``, ``mode`` etc.). Não trata ``gale`` — esse caminho não chega aqui.
    """
    cfg = getattr(strategy, "_cfg", None)
    unit = float(_cfg_get(cfg, "sda17.staking", "unit", 1.0))

    if mode == "flat":
        return _result(flat_stake(n_numbers, unit), "flat", None)

    # mode == "kelly"
    window = int(_cfg_get(cfg, "sda17.staking", "kelly_window", 100))
    fraction = float(_cfg_get(cfg, "sda17.staking", "kelly_fraction", 0.5))
    cap = float(_cfg_get(cfg, "sda17.staking", "kelly_cap", 0.02))
    bankroll = float(_cfg_get(cfg, "sda17.staking", "kelly_bankroll", 100.0))
    p = _rolling_rate(strategy, direction, window)
    stake = kelly_stake(
        p, n_numbers, unit=unit, fraction=fraction, cap=cap, bankroll=bankroll
    )
    return _result(stake, "kelly", p)
