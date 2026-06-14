"""Testes da implantação flat/kelly (flat_kelly_junho.md §6-§8) — auditoria 14/06.

Cobertura:
  Pure policy:
    P1 flat_stake = round(U·N), piso 1u, default N
    P2 kelly_stake: f*≤0 → 1u (floor INV-3)
    P3 kelly_stake: p=None (warmup) → flat
    P4 kelly_stake: edge positivo respeita cap
    P5 kelly_stake: edge positivo abaixo do cap
  Dispatcher (compute_staking):
    C1 flat → mode/efetivo corretos
    C2 kelly warmup → cai no flat
  Integração (GameState.get_effective_bet):
    I1 flat ignora mg.level (stake constante mesmo em G3) — INVARIANTE central
    I2 gale BYTE-IDÊNTICO (default) — mg.level=2 → 34, mode 'normal'
    I3 kelly despacha e respeita cap
    I4 propriedade: flat constante ao longo de qualquer streak de level
"""
import pytest

from staking.policy import compute_staking, flat_stake, kelly_stake
from state.game import GameState


# --------------------------------------------------------------------------- #
# Stubs duck-typed
# --------------------------------------------------------------------------- #
class FakeCfg:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, section, key, default=None):
        return self.values.get((section, key), default)


class FakeStrategy:
    """Strategy mínima para staking. SEM should_minimize/get_stake_weight →
    no caminho gale, get_effective_bet retorna base sem QW (previsível)."""

    def __init__(self, cfg=None, rate=None):
        self._cfg = cfg or FakeCfg()
        self._rate = rate

    def rolling_hit_rate(self, direction, window=100):
        return self._rate


KELLY_CFG = FakeCfg({
    ("sda17.staking", "unit"): 1.0,
    ("sda17.staking", "kelly_window"): 100,
    ("sda17.staking", "kelly_fraction"): 0.5,
    ("sda17.staking", "kelly_cap"): 0.02,
    ("sda17.staking", "kelly_bankroll"): 100.0,
})


# --------------------------------------------------------------------------- #
# Pure policy
# --------------------------------------------------------------------------- #
class TestFlatStakePure:
    def test_flat_basic_v4(self):
        assert flat_stake(21, 1.0) == 21          # P1: U=1, N=21 → 21u total

    def test_flat_scales_with_geometry(self):
        assert flat_stake(17, 1.0) == 17          # N=17 → 17u
        assert flat_stake(21, 2.0) == 42          # U=2 → 42u

    def test_flat_invalid_n_uses_default(self):
        assert flat_stake(0, 1.0) == 21           # N inválido → DEFAULT_N
        assert flat_stake(None, 1.0) == 21

    def test_flat_floor_1u(self):
        assert flat_stake(21, 0.0) == 1           # piso INV-3


class TestKellyStakePure:
    def test_no_edge_floors_to_1(self):
        # p = break-even (21/36 ≈ 0.583): f* ≤ 0 → 1u
        assert kelly_stake(0.50, 21, unit=1.0, fraction=0.5, cap=0.02, bankroll=100.0) == 1  # P2
        assert kelly_stake(0.583, 21, unit=1.0, fraction=0.5, cap=0.02, bankroll=100.0) == 1

    def test_warmup_none_behaves_as_flat(self):
        # p=None → flat (= round(unit·N))                                       # P3
        assert kelly_stake(None, 21, unit=1.0, fraction=0.5, cap=0.02, bankroll=100.0) == 21
        assert kelly_stake(None, 17, unit=1.0, fraction=0.5, cap=0.02, bankroll=100.0) == 17

    def test_positive_edge_respects_cap(self):
        # p=0.70, N=21: b=0.714, f*≈0.28, raw≈14, cap=2% de 100 = 2 → 2         # P4
        s = kelly_stake(0.70, 21, unit=1.0, fraction=0.5, cap=0.02, bankroll=100.0)
        assert s == 2

    def test_positive_edge_below_cap(self):
        # bankroll grande + cap alto → caminho não-capado                        # P5
        # p=0.62, N=21: b=0.714, f*≈0.088, raw=round(1000*0.5*0.088)=44; cap=500
        s = kelly_stake(0.62, 21, unit=1.0, fraction=0.5, cap=0.5, bankroll=1000.0)
        assert s == 44

    def test_full_kelly_doubles_half(self):
        half = kelly_stake(0.62, 21, unit=1.0, fraction=0.5, cap=1.0, bankroll=1000.0)
        full = kelly_stake(0.62, 21, unit=1.0, fraction=1.0, cap=1.0, bankroll=1000.0)
        assert full == pytest.approx(2 * half, abs=1)


# --------------------------------------------------------------------------- #
# Dispatcher compute_staking
# --------------------------------------------------------------------------- #
class TestComputeStaking:
    def test_flat_dispatch(self):
        res = compute_staking("flat", direction="cw", n_numbers=21,
                              strategy=FakeStrategy(cfg=KELLY_CFG))
        assert res["mode"] == "flat"               # C1
        assert res["effective_bet"] == 21
        assert res["base_bet"] == 21
        assert res["multiplier"] == 1.0

    def test_kelly_warmup_falls_back_to_flat(self):
        res = compute_staking("kelly", direction="ccw", n_numbers=21,
                              strategy=FakeStrategy(cfg=KELLY_CFG, rate=None))
        assert res["mode"] == "kelly"              # C2
        assert res["effective_bet"] == 21          # = flat
        assert res["rolling_rate"] is None

    def test_kelly_with_edge_capped(self):
        res = compute_staking("kelly", direction="cw", n_numbers=21,
                              strategy=FakeStrategy(cfg=KELLY_CFG, rate=0.70))
        assert res["mode"] == "kelly"
        assert res["effective_bet"] == 2           # cap 2% de 100
        assert res["rolling_rate"] == 0.70


# --------------------------------------------------------------------------- #
# Integração: GameState.get_effective_bet
# --------------------------------------------------------------------------- #
class TestGetEffectiveBetDispatch:
    def test_flat_ignores_martingale_level(self, monkeypatch):
        """INVARIANTE central: sob flat, o stake NÃO depende de mg.level/streak."""
        monkeypatch.setenv("SDA_STAKING_MODE", "flat")
        gs = GameState()
        gs.martingale_cw.level = 3                 # herdou G3 do gale
        res = gs.get_effective_bet("cw", FakeStrategy(cfg=KELLY_CFG), n_numbers=21)
        assert res["mode"] == "flat"               # I1
        assert res["effective_bet"] == 21          # constante, ignora G3 (≠ 51)

    def test_gale_byte_identical_default(self, monkeypatch):
        """Sob gale (default), o caminho legado roda inalterado."""
        monkeypatch.setenv("SDA_STAKING_MODE", "gale")
        gs = GameState()
        gs.martingale_cw.level = 2                 # G2 → current_bet=34
        res = gs.get_effective_bet("cw", FakeStrategy(), n_numbers=21)
        assert res["mode"] == "normal"             # I2
        assert res["effective_bet"] == 34
        assert res["base_bet"] == 34
        assert res["minimizer_active"] is False

    def test_gale_is_default_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("SDA_STAKING_MODE", raising=False)
        gs = GameState()
        gs.martingale_ccw.level = 1
        res = gs.get_effective_bet("ccw", FakeStrategy(), n_numbers=21)
        assert res["mode"] == "normal"
        assert res["effective_bet"] == 17          # G1 base, inalterado

    def test_kelly_dispatch_caps(self, monkeypatch):
        monkeypatch.setenv("SDA_STAKING_MODE", "kelly")
        gs = GameState()
        res = gs.get_effective_bet("cw", FakeStrategy(cfg=KELLY_CFG, rate=0.70), n_numbers=21)
        assert res["mode"] == "kelly"              # I3
        assert res["effective_bet"] == 2

    def test_flat_constant_across_streak(self, monkeypatch):
        """Propriedade: nenhum nível/streak altera o stake flat."""
        monkeypatch.setenv("SDA_STAKING_MODE", "flat")
        gs = GameState()
        seen = set()
        for lvl in (1, 2, 3, 2, 1, 3):
            gs.martingale_cw.level = lvl
            res = gs.get_effective_bet("cw", FakeStrategy(cfg=KELLY_CFG), n_numbers=21)
            seen.add(res["effective_bet"])
        assert seen == {21}                        # I4: sempre 21u
