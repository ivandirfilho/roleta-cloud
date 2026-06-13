"""V3 (13/06) — raios de satélite ASSIMÉTRICOS adaptativos por sentido.

Satélite GORDO (raio 4) no lado mais denso do erro do sentido, MAGRO (raio 2)
no outro; (3,3) simétrico no empate/frio. Mantém N=17 (r2+r3=6). Genérico:
mesma regra, o lado vem só do DADO de cada sentido. Rollback SDA_SAT_ASYM=0.
"""
import pytest

from strategies.sda17 import SDA17Strategy
from state.timeline import Timeline

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]


@pytest.fixture
def v3_on(monkeypatch):
    monkeypatch.setenv("SDA_GEOMETRY_V2", "1")
    monkeypatch.setenv("SDA_SAT_ASYM", "1")
    monkeypatch.setenv("REGION_SHIFT_V1", "1")
    monkeypatch.setenv("SDA_SIGMOID_SATELLITES", "0")


def _warm(n=6):
    tl = Timeline(direction="cw")
    for _ in range(n):
        tl.add(10)
    return tl


def test_fat_satellite_on_denser_side(v3_on):
    s = SDA17Strategy()
    # lado + (adiante) mais denso → C2 gordo (4,2)
    for _ in range(20):
        s._region_err_hist["cw"].append(13)
    for _ in range(4):
        s._region_err_hist["cw"].append(-8)
    assert s._sat_radii("cw") == (4, 2)
    assert s._geometry_radii("cw") == (1, 4, 2)
    # lado − (atrás) mais denso → C3 gordo (2,4)
    for _ in range(20):
        s._region_err_hist["ccw"].append(-12)
    for _ in range(3):
        s._region_err_hist["ccw"].append(7)
    assert s._sat_radii("ccw") == (2, 4)


def test_balanced_is_symmetric(v3_on):
    s = SDA17Strategy()
    for _ in range(12):
        s._region_err_hist["cw"].append(13)
    for _ in range(12):
        s._region_err_hist["cw"].append(-13)
    assert s._sat_radii("cw") == (3, 3)


def test_cold_is_symmetric(v3_on):
    s = SDA17Strategy()
    assert s._sat_radii("cw") == (3, 3)            # vazio → simétrico
    for _ in range(5):
        s._region_err_hist["cw"].append(13)
    assert s._sat_radii("cw") == (3, 3)            # n<12 → simétrico (prior)


def test_footprint_17_under_asymmetry(v3_on):
    s = SDA17Strategy()
    for _ in range(20):
        s._region_err_hist["cw"].append(13)
    r = s.analyze(_warm(), 0, WHEEL)
    assert r.should_bet is True
    assert len(r.numbers) == 17                    # N=17 preservado sob assimetria
    assert r.details["geometry"] == "3+9+5"
    assert r.details["overlap"] == 0


def test_geometry_label_tracks_dense_side(v3_on):
    s = SDA17Strategy()
    for _ in range(20):
        s._region_err_hist["cw"].append(-12)      # lado − denso → C3 gordo
    r = s.analyze(_warm(), 0, WHEEL)
    assert r.details["geometry"] == "3+5+9"
    assert len(r.numbers) == 17


def test_isolation_cw_does_not_touch_ccw(v3_on):
    s = SDA17Strategy()
    for _ in range(20):
        s._region_err_hist["cw"].append(13)
    assert s._sat_radii("cw") == (4, 2)
    assert s._sat_radii("ccw") == (3, 3)           # ccw frio → simétrico (INV-1)


def test_rollback_asym_off_is_symmetric(monkeypatch):
    monkeypatch.setenv("SDA_GEOMETRY_V2", "1")
    monkeypatch.setenv("SDA_SAT_ASYM", "0")
    s = SDA17Strategy()
    for _ in range(20):
        s._region_err_hist["cw"].append(13)        # mesmo enviesado → simétrico
    assert s._sat_asym_enabled() is False
    assert s._sat_radii("cw") == (3, 3)
    assert s._geometry_radii("cw") == (1, 3, 3)
