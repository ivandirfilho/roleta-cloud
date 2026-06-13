"""REGRA 13/06 — Geometria V2 (fat-SAT 3+7+7 + offsets-KDE por sentido).

Valida a regra implantada direto em produção (backtest de decisão P2):
- footprint 3+7+7 = 17 (redistribui os MESMOS 17 p/ fora do centro previsto);
- offsets dos satélites = picos de densidade do erro C1 do PRÓPRIO sentido (KDE);
- fallback ao prior enquanto frio (n<12) — INV-3: nunca pula aposta;
- reset zera o histograma; persistência roundtrip; rollback por env (legado 7+5+5).
"""
import pytest

from strategies.sda17 import SDA17Strategy
from state.timeline import Timeline

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]


@pytest.fixture
def v2_on(monkeypatch):
    monkeypatch.setenv("SDA_GEOMETRY_V2", "1")
    monkeypatch.setenv("REGION_SHIFT_V1", "1")
    monkeypatch.setenv("SDA_SIGMOID_SATELLITES", "0")


def _warm_timeline(direction="cw", n=8):
    tl = Timeline(direction=direction)
    for _ in range(n):
        tl.add(10)
    return tl


def test_radii_and_footprint_v2(v2_on):
    s = SDA17Strategy()
    assert s._geometry_v2_enabled() is True
    assert s._geometry_radii() == (1, 3, 3)
    tl = _warm_timeline()
    r = s.analyze(tl, 0, WHEEL)
    assert r.should_bet is True
    assert len(r.numbers) == 17
    assert r.details["geometry"] == "3+7+7"
    assert r.details["offset_type"] == "kde_v2"
    c1, c2, c3 = r.details["centers"]
    assert len(set(s.get_neighbors(c1, 1, WHEEL))) == 3
    assert len(set(s.get_neighbors(c2, 3, WHEEL))) == 7
    assert len(set(s.get_neighbors(c3, 3, WHEEL))) == 7


def test_cold_offsets_fallback_to_prior(v2_on):
    s = SDA17Strategy()
    # histograma vazio → offsets = prior (BAYESIAN_DEFAULT), nunca pula aposta
    off2, off3 = s._kde_offsets("cw")
    assert off2 == s.BAYESIAN_DEFAULT
    assert off3 == s.BAYESIAN_DEFAULT


def test_kde_offsets_track_density_peaks(v2_on):
    s = SDA17Strategy()
    # densidade real: bola cai +13 adiante e -8 atrás do C1 (cauda bimodal)
    for _ in range(18):
        s._region_err_hist["cw"].append(13)
    for _ in range(18):
        s._region_err_hist["cw"].append(-8)
    off2, off3 = s._kde_offsets("cw")
    assert off2 == 13          # satélite + no pico de densidade adiante
    assert off3 == 8           # satélite - no pico de densidade atrás
    # offsets em lados opostos preservam N=17 na aposta
    tl = _warm_timeline()
    r = s.analyze(tl, 0, WHEEL)
    assert len(r.numbers) == 17
    assert r.details["offset"] == 13
    assert r.details["offset_c3"] == 8


def test_kde_offsets_clamped_to_bounds(v2_on):
    s = SDA17Strategy()
    for _ in range(15):
        s._region_err_hist["cw"].append(17)   # além do teto V2 (15)
    for _ in range(15):
        s._region_err_hist["cw"].append(-4)   # logo acima do mínimo (3<|x|)
    off2, off3 = s._kde_offsets("cw")
    assert s.OFFSET_MIN <= off2 <= s.OFFSET_MAX_V2
    assert s.OFFSET_MIN <= off3 <= s.OFFSET_MAX_V2
    assert off2 == s.OFFSET_MAX_V2             # 17 clampado a 15


def test_hist_fed_by_feedback(v2_on):
    s = SDA17Strategy()
    last = 0
    for _ in range(5):
        nxt = WHEEL[(WHEEL.index(last) + 10) % 37]
        c1 = last
        c2 = WHEEL[(WHEEL.index(last) + 10) % 37]
        c3 = WHEEL[(WHEEL.index(last) - 10) % 37]
        s.update_adaptive("cw", c1, nxt, WHEEL, coverage=None, centers=[c1, c2, c3])
        last = nxt
    assert len(s._region_err_hist["cw"]) == 5
    assert len(s._region_err_hist["ccw"]) == 0   # INV-1: sentidos isolados


def test_reset_clears_hist(v2_on):
    s = SDA17Strategy()
    for _ in range(10):
        s._region_err_hist["cw"].append(11)
    s.reset_adaptive()
    assert len(s._region_err_hist["cw"]) == 0
    assert len(s._region_err_hist["ccw"]) == 0


def test_persist_roundtrip_hist(v2_on):
    s = SDA17Strategy()
    for v in (12, -9, 13, -7, 14):
        s._region_err_hist["cw"].append(v)
    state = s.get_adaptive_state()
    assert state["region_err_hist"]["cw"] == [12, -9, 13, -7, 14]
    s2 = SDA17Strategy()
    s2.load_adaptive_state(state)
    assert list(s2._region_err_hist["cw"]) == [12, -9, 13, -7, 14]


def test_inv3_always_17_even_extreme(v2_on):
    s = SDA17Strategy()
    # densidade degenerada (tudo num bucket extremo) ainda gera 17 e aposta
    for _ in range(20):
        s._region_err_hist["cw"].append(15)
    tl = _warm_timeline()
    r = s.analyze(tl, 0, WHEEL)
    assert r.should_bet is True
    assert len(r.numbers) == 17


def test_legacy_geometry_when_disabled(monkeypatch):
    monkeypatch.setenv("SDA_GEOMETRY_V2", "0")
    s = SDA17Strategy()
    assert s._geometry_v2_enabled() is False
    assert s._geometry_radii() == (s.num_neighbors, s.C2_RADIUS, s.C3_RADIUS)
    tl = _warm_timeline()
    r = s.analyze(tl, 0, WHEEL)
    assert r.details["geometry"] == "7+5+5"
    assert len(r.numbers) == 17
