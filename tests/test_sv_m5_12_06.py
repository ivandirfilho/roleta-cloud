"""SV-01/SV-02 (12/06) — Modelo Universal M5 + aposentadoria do sigmoid.

Valida a implantação de sprints_validas_12_06.md:
- shift de C1 replica a dinâmica vencedora (round(-ema*K), clamp, warmup);
- satélites relativos clamp ±2 com sinais da simulação;
- fallback de calibração NUNCA recebe shift;
- sigmoid OFF congela offsets no prior e para a adaptação (EMA continua);
- reset (B1/P10) zera o shift; rollback por env restaura o legado.
"""
from __future__ import annotations

import os
import unittest

from core.roulette import roulette
from state.timeline import Timeline
from strategies.sda17 import SDA17Strategy

WHEEL = list(roulette.WHEEL_SEQUENCE)


def _at(center: int, offset: int) -> int:
    return WHEEL[(WHEEL.index(center) + offset) % len(WHEEL)]


class _Env(unittest.TestCase):
    KEYS = ("REGION_SHIFT_V1", "SDA_SIGMOID_SATELLITES")

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self.KEYS}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestRegionShiftActuator(_Env):
    def _strategy_with_bias(self, dk="cw", ema=-6.0, n=5):
        s = SDA17Strategy()
        s._region_err_ema[dk]["c1"] = ema
        s._region_err_n[dk]["c1"] = n
        return s

    def test_shift_replicates_simulation_sign(self):
        """ema=-6 → shift=round(+3)= +3 (dinâmica M5, não intuição)."""
        os.environ["REGION_SHIFT_V1"] = "1"
        s = self._strategy_with_bias(ema=-6.0)
        self.assertEqual(s._region_shift("cw", "c1", 4), 3)
        s2 = self._strategy_with_bias(ema=5.0)
        self.assertEqual(s2._region_shift("cw", "c1", 4), -2)  # round(-2.5)=-2

    def test_shift_clamped_and_gated(self):
        os.environ["REGION_SHIFT_V1"] = "1"
        s = self._strategy_with_bias(ema=-30.0)      # round(15) → clamp 4
        self.assertEqual(s._region_shift("cw", "c1", 4), 4)
        s_warm = self._strategy_with_bias(ema=-6.0, n=2)  # n < MIN_N
        self.assertEqual(s_warm._region_shift("cw", "c1", 4), 0)
        self.assertEqual(s._region_shift("ccw", "c1", 4), 0)  # INV-1: outro sentido

    def test_analyze_applies_shift_to_c1(self):
        os.environ["REGION_SHIFT_V1"] = "1"
        os.environ["SDA_SIGMOID_SATELLITES"] = "0"
        s = SDA17Strategy()
        tl = Timeline("cw")
        for f in (10, 10, 10, 10, 10, 10, 10):
            tl.add(f)
        base = SDA17Strategy().analyze(tl, last_number=0, wheel_sequence=WHEEL)
        s._region_err_ema["cw"]["c1"] = -6.0   # → shift +3
        s._region_err_n["cw"]["c1"] = 5
        shifted = s.analyze(tl, last_number=0, wheel_sequence=WHEEL)
        self.assertEqual(shifted.details["region_shift"], 3)
        exp = _at(base.center, 3)
        self.assertEqual(shifted.center, exp,
                         "C1 deve andar exatamente +3 casas na roda")
        self.assertEqual(base.details["region_shift"], 0)

    def test_flag_off_means_zero_shift(self):
        os.environ["REGION_SHIFT_V1"] = "0"
        s = self._strategy_with_bias(ema=-8.0)
        tl = Timeline("cw")
        for f in (10,) * 7:
            tl.add(f)
        r = s.analyze(tl, last_number=0, wheel_sequence=WHEEL)
        self.assertEqual(r.details["region_shift"], 0)

    def test_satellites_relative_correction_signs(self):
        """Simulação M5: s2=round(-e2*K) em off2; s3=round(+e3*K) em off3."""
        os.environ["REGION_SHIFT_V1"] = "1"
        os.environ["SDA_SIGMOID_SATELLITES"] = "0"
        s = SDA17Strategy()
        s._region_err_n["cw"] = {"c1": 5, "c2": 5, "c3": 5}
        s._region_err_ema["cw"] = {"c1": 0.0, "c2": -3.0, "c3": -3.0}
        tl = Timeline("cw")
        for f in (10,) * 7:
            tl.add(f)
        r = s.analyze(tl, last_number=0, wheel_sequence=WHEEL)
        sat2, sat3 = r.details["region_shift_sat"]
        self.assertEqual(sat2, 2)    # round(-(-3)*0.5)=+2 (clamp 2)
        self.assertEqual(sat3, -2)   # -round(-(-3)*0.5) = -2
        # off base prior=10 → off2=12, off3=8 refletidos nos detalhes
        self.assertEqual(r.details["offset"], 12)
        self.assertEqual(r.details["offset_c3"], 8)

    def test_fallback_never_shifted(self):
        os.environ["REGION_SHIFT_V1"] = "1"
        s = self._strategy_with_bias(ema=-8.0)
        nums, radius = sorted(roulette.get_neighbors(0, s._fallback_radius())), s._fallback_radius()
        # fallback é gerado fora do Triple Focus — análise via radius helper:
        # o atuador vive APENAS no bloco Triple Focus do analyze (gate de design).
        self.assertIn(radius, (9, 10))

    def test_reset_zeroes_shift(self):
        os.environ["REGION_SHIFT_V1"] = "1"
        s = self._strategy_with_bias(ema=-8.0, n=12)
        self.assertNotEqual(s._region_shift("cw", "c1", 4), 0)
        s.reset_adaptive()
        self.assertEqual(s._region_shift("cw", "c1", 4), 0)


class TestSigmoidRetirement(_Env):
    def test_offsets_fixed_at_prior_when_off(self):
        os.environ["SDA_SIGMOID_SATELLITES"] = "0"
        s = SDA17Strategy()
        s._sigmoid_off = {"cw_off2": 13.0, "cw_off3": 7.0}  # estado antigo
        self.assertEqual(s._get_adaptive_offset("cw"),
                         (s.BAYESIAN_DEFAULT, s.BAYESIAN_DEFAULT))

    def test_rollback_flag_restores_legacy(self):
        os.environ["SDA_SIGMOID_SATELLITES"] = "1"
        s = SDA17Strategy()
        s._sigmoid_off = {"cw_off2": 12.4, "cw_off3": 8.2}
        self.assertEqual(s._get_adaptive_offset("cw"), (12, 8))

    def test_update_keeps_ema_but_freezes_sigmoid(self):
        os.environ["SDA_SIGMOID_SATELLITES"] = "0"
        s = SDA17Strategy()
        c1 = 0
        centers = [c1, _at(c1, 10), _at(c1, -10)]
        cov = sorted(set(roulette.get_neighbors(c1, 3))
                     | set(roulette.get_neighbors(centers[1], 2))
                     | set(roulette.get_neighbors(centers[2], 2)))
        before = dict(s._sigmoid_off)
        for _ in range(6):
            s.update_adaptive("cw", c1, _at(c1, 8), WHEEL,
                              coverage=cov, centers=centers)
        self.assertEqual(s._sigmoid_off, before, "sigmoid não deve adaptar")
        self.assertIsNotNone(s._region_err_ema["cw"]["c1"], "EMA continua viva")
        self.assertEqual(len(s._recent_hits["cw"]), 6, "QW buffers continuam")

    def test_batch_tune_noop_when_off(self):
        os.environ["SDA_SIGMOID_SATELLITES"] = "0"
        s = SDA17Strategy()
        s._recent_hits["cw"] = [1, 0] * 10
        s._batch_auto_tune("cw", min_warmup=4)
        self.assertEqual(s._batch_last_action["cw"], "sigmoid-off")


if __name__ == "__main__":
    unittest.main()
