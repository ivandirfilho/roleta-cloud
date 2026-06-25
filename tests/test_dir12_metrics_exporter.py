"""DIR12 (sentido-fase): /metrics Prometheus exporta os 3 contadores DIR8.

Antes: gap_recuperado_total/phase_uncertain_total/direction_divergence_total
viviam APENAS em state.phase_metrics + sentido.stats do state_sync (cliente).
Grafana externo cego.

Depois: health_server._refresh_custom_metrics le do snapshot() a cada scrape e
publica 3 Gauges (roleta_phase_*_total). Tolerante a ausencia do modulo.
"""

import importlib


def test_phase_metrics_module_disponivel():
    """O modulo state.phase_metrics existe e expoe snapshot()."""
    pm = importlib.import_module("state.phase_metrics")
    snap = pm.snapshot()
    assert isinstance(snap, dict)
    assert set(snap.keys()) == {
        "gap_recuperado_total",
        "phase_uncertain_total",
        "direction_divergence_total",
    }


def test_health_server_define_metricas_phase():
    """As 3 Gauges DIR12 estao registradas em _PROM_METRICS (sem precisar subir scrape)."""
    from server import health_server
    if not health_server._METRICS_AVAILABLE:
        # prometheus_client ausente — modulo nao registra; pulamos.
        return
    pm = health_server._PROM_METRICS
    assert pm is not None
    assert "phase_gap_recuperado" in pm
    assert "phase_uncertain" in pm
    assert "phase_divergence" in pm


def test_refresh_custom_metrics_atualiza_phase(monkeypatch):
    """_refresh_custom_metrics le do phase_metrics.snapshot() e publica."""
    from state import phase_metrics
    from server import health_server
    if not health_server._METRICS_AVAILABLE:
        return
    # Snapshot inicial limpo
    phase_metrics.reset()
    # Simular eventos:
    phase_metrics.incr("gap_recuperado_total", 3)
    phase_metrics.incr("phase_uncertain_total", 1)
    phase_metrics.incr("direction_divergence_total", 2)
    # Forcar refresh
    health_server._refresh_custom_metrics()
    # Validar Gauges
    pm = health_server._PROM_METRICS
    # Cada Gauge expoe _value.get() ou .collect() — usamos _value._value para simplicidade.
    assert pm["phase_gap_recuperado"]._value.get() == 3.0
    assert pm["phase_uncertain"]._value.get() == 1.0
    assert pm["phase_divergence"]._value.get() == 2.0
    # Limpar
    phase_metrics.reset()


def test_refresh_tolerante_a_falha_silenciosa(monkeypatch):
    """Se phase_metrics for substituido por algo que lance, refresh NAO quebra."""
    import sys
    from server import health_server
    if not health_server._METRICS_AVAILABLE:
        return
    # Quebra o modulo (simulando erro de import):
    bad = type("Bad", (), {"snapshot": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("oops")))})
    monkeypatch.setitem(sys.modules, "state.phase_metrics", bad)
    # Refresh nao deve lancar
    health_server._refresh_custom_metrics()
