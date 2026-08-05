"""SPR-V1 — NÃO-INTERFERÊNCIA: com as flags do sprint OFF, o comportamento é
byte-idêntico ao de antes do sprint.

A fixture `fixtures/spr_v1_replay_baseline.json` foi congelada rodando
`tests/replay_harness_v1.py` contra o código ORIGINAL (antes de qualquer edição de
fonte deste sprint). Este teste RE-EXECUTA o mesmo replay contra o código ATUAL e
compara campo a campo. Ele NUNCA regenera a fixture — se regenerasse, não provaria
nada.

Cobre a exigência da DoD: decisão, cobertura, stake, timelines, contadores de fase e
buffers idênticos com `SDA_PHASE_BUFFER_SYNC=0`, `SDA_PHASE_MIN_OVERLAP=0`,
`SDA_MIN_SPIN_INTERVAL_MS=0` e `SDA_PHASE_ALT_METRIC=0`.
"""

import json
from pathlib import Path

import pytest

from replay_harness_v1 import PROD_ENV, run_replay

FIXTURE = Path(__file__).parent / "fixtures" / "spr_v1_replay_baseline.json"


@pytest.fixture()
def baseline():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def atual(monkeypatch):
    from state import phase_metrics

    for k, v in PROD_ENV.items():
        monkeypatch.setenv(k, v)
    phase_metrics.reset()
    try:
        return run_replay()
    finally:
        phase_metrics.reset()


def test_fixture_congelada_existe_e_tem_conteudo(baseline):
    """Guarda-corpo: fixture vazia passaria em tudo silenciosamente."""
    assert baseline["decisions"], "fixture sem decisoes — replay nao rodou no baseline"
    assert baseline["spin_seq"] > 0
    assert baseline["ws_errors"] == 0


def test_estado_global_identico(baseline, atual):
    """Âncora de fase, contador de giros e buffers não se mexem com flags OFF."""
    for campo in (
        "spin_seq", "seed_parity", "seed_n", "direction_source", "direction_locked",
        "last_direction", "last_number", "target_direction",
        "recent_results", "phase_results", "ws_errors",
    ):
        assert atual[campo] == baseline[campo], f"campo divergente: {campo}"


def test_timelines_identicas(baseline, atual):
    assert atual["timeline_cw"] == baseline["timeline_cw"]
    assert atual["timeline_ccw"] == baseline["timeline_ccw"]


def test_decisoes_identicas_campo_a_campo(baseline, atual):
    """Decisão/cobertura/stake por giro — o que de fato vira dinheiro."""
    assert len(atual["decisions"]) == len(baseline["decisions"])
    for i, (a, b) in enumerate(zip(atual["decisions"], baseline["decisions"])):
        assert a == b, f"decisao {i} divergente:\natual={a}\nbaseline={b}"


def test_cobertura_e_stake_explicitos(baseline, atual):
    """Redundante de propósito: falha aqui aponta direto para risco financeiro."""
    for i, (a, b) in enumerate(zip(atual["decisions"], baseline["decisions"])):
        assert a["final_action"] == b["final_action"], f"acao divergente no giro {i}"
        assert a["sda_numbers"] == b["sda_numbers"], f"cobertura divergente no giro {i}"
        assert a["gale_bet_value"] == b["gale_bet_value"], f"stake divergente no giro {i}"


def test_replay_e_deterministico(atual, monkeypatch):
    """Duas execuções seguidas do harness dão o mesmo snapshot (sem random/relógio)."""
    from state import phase_metrics

    for k, v in PROD_ENV.items():
        monkeypatch.setenv(k, v)
    phase_metrics.reset()
    try:
        segundo = run_replay()
    finally:
        phase_metrics.reset()
    assert segundo == atual
