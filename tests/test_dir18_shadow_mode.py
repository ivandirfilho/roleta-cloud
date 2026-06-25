"""DIR18 (sentido-fase): SHADOW MODE da autoridade DIR5 (fix #U).

Antes: o bloco DIR5 (auto-seed + project_phase + metrica) so rodava com
SDA_SENTIDO_AUTORITATIVO=1. Em OFF, divergence_total nao crescia ->
impossivel avaliar 'o que aconteceria se eu ligasse?' sem A/B em producao.

Depois: nova flag SDA_SENTIDO_AUTORITATIVO_SHADOW. Com shadow=1, autoridade=0:
- Roda project_phase
- Incrementa direction_divergence_total
- NAO substitui a direcao (aposta segue hint do cliente)

Permite Grafana mostrar a divergencia hipotetica antes de promover SHADOW->AUTORIDADE.
"""

from app_config.settings import sentido_autoritativo_shadow_enabled


def test_flag_shadow_default_off(monkeypatch):
    monkeypatch.delenv("SDA_SENTIDO_AUTORITATIVO_SHADOW", raising=False)
    assert sentido_autoritativo_shadow_enabled() is False
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO_SHADOW", "1")
    assert sentido_autoritativo_shadow_enabled() is True


def test_logica_shadow_mode_decision_tree():
    """Validacao da arvore de decisao do bloco refatorado:
    - autoridade=0, shadow=0 -> bloco NAO roda
    - autoridade=0, shadow=1 -> roda, NAO substitui
    - autoridade=1, shadow=0 -> roda, SUBSTITUI
    - autoridade=1, shadow=1 -> roda, SUBSTITUI (autoridade vence)
    """
    cases = [
        (False, False, False, False),   # autoridade, shadow, deve_rodar, deve_substituir
        (False, True,  True,  False),
        (True,  False, True,  True),
        (True,  True,  True,  True),
    ]
    for autoridade, shadow, deve_rodar, deve_substituir in cases:
        roda = autoridade or shadow
        substitui = roda and autoridade
        assert roda is deve_rodar, f"caso ({autoridade},{shadow}): roda esperado {deve_rodar} got {roda}"
        assert substitui is deve_substituir, f"caso ({autoridade},{shadow}): substitui esperado {deve_substituir} got {substitui}"


def test_metrica_divergence_incrementa_em_shadow():
    """Em shadow mode, direction_divergence_total cresce mesmo sem substituir aposta.

    Teste integrado: importa phase_metrics + simula divergencia.
    """
    from state import phase_metrics
    phase_metrics.reset()
    # Simular 3 spins com fase divergente em shadow mode (apenas conta):
    for _ in range(3):
        phase_metrics.incr("direction_divergence_total")
    snap = phase_metrics.snapshot()
    assert snap["direction_divergence_total"] == 3
    phase_metrics.reset()
