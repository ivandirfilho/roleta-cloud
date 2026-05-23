"""
Quick Wins v4.4 — INV-3 compliant test suite.

Cobre:
  - QW-1 Stake Minimizer  → tests_minimizer_*
  - QW-2 Stake Weight     → tests_weight_*
  - QW-3 MG reset metric  → tests_mg_reset
  - QW-4 Hot Substitution → tests_hot_substitution_*
  - QW-5 TOML config      → tests_config
  - QW-6 Warmup Adaptativo→ tests_warmup
  - QW-7 Drift Freeze     → tests_drift

Mais 2 invariantes obrigatórios (CI bloqueante):
  - INV-3 minimizer: get_effective_bet sempre devolve effective_bet >= 1
  - INV-3 mg_cap:    nenhuma path em get_effective_bet retorna 0
"""
import pytest
from pathlib import Path

from strategies.sda17 import SDA17Strategy
from state.game import GameState, MartingaleState
from app_config.strategy_config import StrategyConfig


WHEEL = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
]


# =========================================================================
# QW-5 — Config TOML
# =========================================================================
class TestConfig:
    def test_loads_defaults_when_file_missing(self, tmp_path):
        cfg = StrategyConfig(path=tmp_path / "absent.toml")
        # Sem arquivo → defaults embutidos
        assert cfg.get("sda17.minimizer", "enabled") is True
        assert cfg.get("sda17.minimizer", "threshold") == 0.487
        assert cfg.get("sda17.hot_substitution", "cooldown_spins") == 3

    def test_loads_real_file(self):
        # Real strategy.toml deve existir
        cfg = StrategyConfig()
        assert cfg.get("sda17.minimizer", "threshold") == 0.487
        assert cfg.get("sda17.drift_freeze", "freeze_spins") == 5

    def test_invalid_toml_keeps_previous_snapshot(self, tmp_path):
        f = tmp_path / "bad.toml"
        f.write_text("[sda17.minimizer]\nthreshold = 0.5\n")
        cfg = StrategyConfig(path=f)
        assert cfg.get("sda17.minimizer", "threshold") == 0.5
        f.write_text("invalid toml :::: ===")
        cfg.maybe_reload()
        # Reload falhou — mantém 0.5
        assert cfg.get("sda17.minimizer", "threshold") == 0.5


# =========================================================================
# Helpers comuns
# =========================================================================
def make_strategy_with_hits(direction_key: str, hits_pattern):
    """Cria SDA17 com _recent_hits[dk] populado diretamente."""
    s = SDA17Strategy()
    s._wheel = WHEEL
    s._recent_hits[direction_key] = list(hits_pattern)
    # Garantir histórico para passar warmup adaptativo se for o caso
    s.cw_history = [(0, 0)] * 10
    s.ccw_history = [(0, 0)] * 10
    return s


# =========================================================================
# QW-1 — Stake Minimizer
# =========================================================================
class TestMinimizer:
    def test_minimizer_inactive_during_warmup(self):
        s = make_strategy_with_hits("cw", [0] * 5)  # < warmup_n=10
        minimize, rate = s.should_minimize("cw")
        assert minimize is False
        assert rate is None

    def test_minimizer_active_when_rate_below_threshold(self):
        # 30 hits, rate = 0.4 < 0.487
        s = make_strategy_with_hits("cw", [1] * 12 + [0] * 18)
        minimize, rate = s.should_minimize("cw")
        assert minimize is True
        assert rate is not None
        assert 0.39 < rate < 0.41

    def test_minimizer_inactive_when_rate_above_threshold(self):
        s = make_strategy_with_hits("cw", [1] * 20 + [0] * 10)  # 0.667
        minimize, _ = s.should_minimize("cw")
        assert minimize is False

    def test_minimizer_isolated_per_direction_INV1(self):
        s = make_strategy_with_hits("cw", [0] * 30)  # CW losing
        s._recent_hits["ccw"] = [1] * 30  # CCW winning
        mcw, _ = s.should_minimize("cw")
        mccw, _ = s.should_minimize("ccw")
        assert mcw is True and mccw is False

    def test_minimizer_accepts_horario_alias(self):
        s = make_strategy_with_hits("cw", [0] * 30)
        m1, _ = s.should_minimize("horario")
        m2, _ = s.should_minimize("cw")
        assert m1 == m2 is True


# =========================================================================
# QW-2 — Stake Weight
# =========================================================================
class TestStakeWeight:
    def test_weight_returns_1_during_warmup(self):
        s = make_strategy_with_hits("cw", [1] * 5)
        assert s.get_stake_weight("cw") == 1.0

    def test_weight_above_1_when_winning(self):
        s = make_strategy_with_hits("cw", [1] * 25 + [0] * 5)  # 0.833
        w = s.get_stake_weight("cw")
        assert 1.4 < w <= 1.5  # cap upper 1.5

    def test_weight_below_1_when_losing(self):
        s = make_strategy_with_hits("cw", [1] * 10 + [0] * 20)  # 0.333
        w = s.get_stake_weight("cw")
        assert 0.3 <= w < 1.0  # cap lower 0.3

    def test_weight_clamped_at_caps(self):
        s = make_strategy_with_hits("cw", [1] * 30)  # 1.0 → 1/0.472 ≈ 2.12 → cap 1.5
        assert s.get_stake_weight("cw") == 1.5
        s = make_strategy_with_hits("cw", [0] * 30)  # 0.0 → cap 0.3
        assert s.get_stake_weight("cw") == 0.3


# =========================================================================
# QW-3 — Reset metric
# =========================================================================
class TestMgReset:
    def test_record_mg_reset_increments(self):
        s = SDA17Strategy()
        assert s._mg_resets["cw"] == 0
        s.record_mg_reset("cw")
        s.record_mg_reset("horario")  # alias
        s.record_mg_reset("ccw")
        assert s._mg_resets["cw"] == 2
        assert s._mg_resets["ccw"] == 1


# =========================================================================
# QW-4 — Hot Center Substitution
# =========================================================================
class TestHotSubstitution:
    def test_no_substitution_when_cooldown_zero(self):
        s = SDA17Strategy()
        assert s._get_effective_offset("cw", "c2", 10) == 10

    def test_substitution_when_cooldown_active(self):
        s = SDA17Strategy()
        s._cooldown["cw"]["c2"] = 3
        # base_off=8 < PRIOR_CENTER=10 → alt = 9
        assert s._get_effective_offset("cw", "c2", 8) == 9
        # base_off=12 > PRIOR_CENTER → alt = 11
        assert s._get_effective_offset("cw", "c2", 12) == 11

    def test_substitution_respects_offset_bounds(self):
        s = SDA17Strategy()
        s._cooldown["cw"]["c2"] = 1
        # base_off=OFFSET_MAX=13 > center → alt = 12 (válido)
        assert s._get_effective_offset("cw", "c2", 13) == 12
        # base_off=OFFSET_MIN=7 < center → alt = 8 (válido)
        assert s._get_effective_offset("cw", "c2", 7) == 8


# =========================================================================
# QW-6 — Warmup adaptativo
# =========================================================================
class TestWarmupAdaptive:
    def test_default_warmup_during_data_warmup(self):
        s = SDA17Strategy()  # _recent_hits vazio
        assert s._get_warmup("cw") == s.BAYESIAN_WARMUP

    def test_warmup_low_when_winning(self):
        s = make_strategy_with_hits("cw", [1] * 25 + [0] * 5)
        assert s._get_warmup("cw") == 2

    def test_warmup_high_when_losing(self):
        s = make_strategy_with_hits("cw", [0] * 25 + [1] * 5)
        assert s._get_warmup("cw") == 5


# =========================================================================
# QW-7 — Drift Freeze
# =========================================================================
class TestDriftFreeze:
    def test_no_drift_with_insufficient_data(self):
        s = make_strategy_with_hits("cw", [1] * 30)
        assert s._detect_drift("cw") is False

    def test_drift_detected_on_regime_break(self):
        # 25 first all hit, 25 last all miss → diff=1.0 >> 0.15
        s = make_strategy_with_hits("cw", [1] * 25 + [0] * 25)
        assert s._detect_drift("cw") is True

    def test_no_drift_in_stable_regime(self):
        # alternating: each half has same rate ≈ 0.5
        s = make_strategy_with_hits("cw", [1, 0] * 25)
        assert s._detect_drift("cw") is False


# =========================================================================
# INV-3 — Invariantes Críticos (bloqueia CI se violado)
# =========================================================================
class TestInvariantINV3:
    """
    INV-3: Aposta a toda jogada. get_effective_bet NUNCA deve resultar em
    valor 0 ou "PULAR" — apenas pode reduzir o stake.

    O TR Advisor pré-existente (sda_should_bet=False / advice.should_bet=False)
    continua podendo gerar "PULAR" — esse é comportamento legado, NÃO
    introduzido pelos Quick Wins. Os QW NUNCA causam skip novo.
    """

    def _build_gamestate(self):
        gs = GameState()
        gs.last_direction = "anti-horario"  # target = "horario" (cw)
        return gs

    def test_always_bet_minimizer_INV3(self):
        """QW-1 ativo: effective_bet >= 1 mesmo em rate=0."""
        s = make_strategy_with_hits("cw", [0] * 30)
        gs = self._build_gamestate()
        out = gs.get_effective_bet("horario", s)
        assert out["mode"] == "minimizer"
        assert out["effective_bet"] >= 1
        # 17 * 0.10 = 1.7 → round → 2
        assert out["effective_bet"] == 2

    def test_always_bet_mg_cap_INV3(self):
        """Mesmo se forçarmos level=3 + minimizer, aposta continua > 0."""
        s = make_strategy_with_hits("cw", [0] * 30)
        gs = self._build_gamestate()
        gs.martingale_cw.level = 3  # 51u
        out = gs.get_effective_bet("horario", s)
        # Minimizer reseta para level=1 (17u), aplica 10% → 2u
        assert out["effective_bet"] >= 1
        assert gs.martingale_cw.level == 1  # reset implícito QW-1
        # E contou métrica QW-3
        assert s._mg_resets["cw"] >= 1

    def test_weight_path_never_zero(self):
        """QW-2: weight=0.3 sobre stake=17 → 5 (>=1)."""
        s = make_strategy_with_hits("cw", [0] * 10 + [1] * 5)
        # rate = 5/15 ≈ 0.333 (mas warmup_n=10, len>=10 → ok)
        # actually len=15 >= 10, rate = 5/15 = 0.333
        gs = self._build_gamestate()
        out = gs.get_effective_bet("horario", s)
        assert out["effective_bet"] >= 1

    def test_normal_path_returns_base_bet(self):
        """Sem dados (warmup): mode=normal, effective=base."""
        s = SDA17Strategy()
        gs = self._build_gamestate()
        out = gs.get_effective_bet("horario", s)
        assert out["mode"] == "normal"
        assert out["effective_bet"] == out["base_bet"] == 17

    def test_no_skip_introduced_by_qw(self):
        """get_effective_bet jamais retorna acao='PULAR' ou effective_bet=0."""
        # Cenários adversariais
        cases = [
            [0] * 100,       # tudo miss
            [0] * 30,        # rate=0
            [1] * 30,        # rate=1
            [],              # vazio (warmup)
            [0, 1] * 30,     # alternado
        ]
        gs = self._build_gamestate()
        for pattern in cases:
            s = make_strategy_with_hits("cw", pattern)
            out = gs.get_effective_bet("horario", s)
            assert out["effective_bet"] >= 1, f"INV-3 violado em {pattern[:5]}…"
            assert "mode" in out


# =========================================================================
# Persistência state.json v1.7 (compat ascendente v1.6)
# =========================================================================
class TestPersistenceV17:
    def test_get_adaptive_state_includes_qw_fields(self):
        s = SDA17Strategy()
        s._recent_hits["cw"] = [1, 0, 1]
        s._cooldown["cw"]["c2"] = 2
        s._drift_freeze["ccw"] = 3
        s._mg_resets["cw"] = 5
        state = s.get_adaptive_state()
        assert state["version"] == "1.7"
        assert state["recent_hits"]["cw"] == [1, 0, 1]
        assert state["cooldown"]["cw"]["c2"] == 2
        assert state["drift_freeze"]["ccw"] == 3
        assert state["mg_resets"]["cw"] == 5

    def test_load_adaptive_state_backward_compat_v16(self):
        """state v1.6 (sem campos QW) carrega sem erro com defaults."""
        s = SDA17Strategy()
        v16_state = {
            "cw_history": [[10, 15], [12, 8]],
            "ccw_history": [],
            "last_offset": {"cw": 11, "ccw": 9},
            "sigmoid_off": {"cw_off2": 10.5, "cw_off3": 9.5},
        }
        s.load_adaptive_state(v16_state)
        assert s.cw_history == [(10, 15), (12, 8)]
        assert s._recent_hits == {"cw": [], "ccw": []}
        assert s._cooldown["cw"]["c2"] == 0
        assert s._drift_freeze == {"cw": 0, "ccw": 0}

    def test_roundtrip_v17(self):
        s = SDA17Strategy()
        s._recent_hits["cw"] = [1, 0, 1, 1]
        s._cooldown["ccw"]["c3"] = 2
        s._drift_freeze["cw"] = 4
        s._mg_resets["ccw"] = 7
        state = s.get_adaptive_state()

        s2 = SDA17Strategy()
        s2.load_adaptive_state(state)
        assert s2._recent_hits["cw"] == [1, 0, 1, 1]
        assert s2._cooldown["ccw"]["c3"] == 2
        assert s2._drift_freeze["cw"] == 4
        assert s2._mg_resets["ccw"] == 7
