"""Produtor do contexto de features para o PG (correção 06/08).

Cobre `build_pg_feature_context` (helper PURO, compartilhado por
`spin_features`, `spin_result` e pelo backfill) e o efeito da flag
`SDA_PG_FEATURE_CONTEXT` sobre os payloads publicados no outbox.

A regra que estes testes protegem: com a flag OFF o payload é BYTE-IDÊNTICO ao
legado; com ela ON, todo campo do contexto é emitido com o tipo certo e ausência
é representada como `None` — nunca como `''`, `'unknown'` ou `0` fantasma.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from database.models import Decision
from database.outbox_integration import (
    PG_FEATURE_CONTEXT_KEYS, build_pg_feature_context, pg_feature_context_enabled,
)

FLAG = "SDA_PG_FEATURE_CONTEXT"


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    from database import outbox_integration as oi
    oi.invalidate_flag_cache()


def _decision(**over) -> Decision:
    base = dict(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        id=4242,
        session_id="sess-abc",
        spin_number=12,
        spin_direction="horario",
        spin_force=85,
        sda_center=17,
        final_action="APOSTAR",
        gale_level=2,
        dealer="Ana",
        dealer_table="Roleta ao Vivo",
        provider="Evolution",
        round_id="r-991",
        wheel_model="Roleta ao Vivo",
        vision_confidence=0.87,
        vision_source="vision",
        spin_seq=31,
        direction_source="authority",
        direction_confidence=0.91,
        direction_next="anti-horario",
        phase_uncertain=False,
    )
    base.update(over)
    return Decision(**base)


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------

def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert pg_feature_context_enabled() is False


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("TRUE", True), (" on ", True), ("yes", True),
    ("0", False), ("false", False), ("", False), ("2", False), ("sim", False),
])
def test_flag_parsing(monkeypatch, value, expected):
    monkeypatch.setenv(FLAG, value)
    assert pg_feature_context_enabled() is expected


def test_flag_is_not_cached(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    assert pg_feature_context_enabled() is True
    monkeypatch.setenv(FLAG, "0")
    assert pg_feature_context_enabled() is False


# ---------------------------------------------------------------------------
# build_pg_feature_context — tipos e normalização
# ---------------------------------------------------------------------------

def test_context_is_none_without_source():
    assert build_pg_feature_context(None) is None


def test_context_exact_types_when_fully_populated():
    ctx = build_pg_feature_context(_decision())
    assert ctx == {
        "decision_id": 4242,
        "session_id": "sess-abc",
        "dealer": "Ana",
        "dealer_table": "Roleta ao Vivo",
        "provider": "Evolution",
        "round_id": "r-991",
        "wheel_model": "Roleta ao Vivo",
        "vision_confidence": 0.87,
        "vision_source": "vision",
        "spin_seq": 31,
        "direction_source": "authority",
        "direction_confidence": 0.91,
        "direction_next": "ccw",
        "phase_uncertain": False,
        "centro_previsto": 17,
        "applied_gale_level": 2,
    }
    assert isinstance(ctx["spin_seq"], int)
    assert isinstance(ctx["vision_confidence"], float)
    assert isinstance(ctx["phase_uncertain"], bool)


def test_context_keys_match_declared_contract():
    ctx = build_pg_feature_context(_decision())
    for key in PG_FEATURE_CONTEXT_KEYS:
        assert key in ctx


def test_defaults_of_a_bare_decision_become_none():
    """Decision() vazia = ausência total. Nada de '' nem 'unknown' no PG."""
    ctx = build_pg_feature_context(Decision())
    for key in PG_FEATURE_CONTEXT_KEYS:
        if key in ("centro_previsto", "applied_gale_level"):
            continue  # 0 e 1 são valores legítimos do dataclass
        assert ctx[key] is None, f"{key} deveria ser None, veio {ctx[key]!r}"


def test_dealer_unknown_is_absence_not_value():
    """'unknown' é o DEFAULT da coluna, não uma observação de dealer."""
    assert build_pg_feature_context(_decision(dealer="unknown"))["dealer"] is None
    assert build_pg_feature_context(_decision(dealer="UNKNOWN"))["dealer"] is None
    assert build_pg_feature_context(_decision(dealer="  "))["dealer"] is None
    assert build_pg_feature_context(_decision(dealer="Unknown Dealer"))["dealer"] == "Unknown Dealer"


def test_empty_strings_become_none():
    ctx = build_pg_feature_context(
        _decision(provider="", round_id="   ", wheel_model="", dealer_table="")
    )
    assert ctx["provider"] is None
    assert ctx["round_id"] is None
    assert ctx["wheel_model"] is None
    assert ctx["dealer_table"] is None


def test_confidence_requires_its_paired_source():
    """Confiança sem origem é número sem significado."""
    ctx = build_pg_feature_context(_decision(vision_source="", direction_source=""))
    assert ctx["vision_confidence"] is None
    assert ctx["direction_confidence"] is None
    assert ctx["vision_source"] is None
    assert ctx["direction_source"] is None


def test_phase_uncertain_only_when_phase_is_known():
    """Sem origem de fase, 'não incerto' seria mentira: vira NULL."""
    assert build_pg_feature_context(
        _decision(direction_source="", phase_uncertain=False))["phase_uncertain"] is None
    # Com fase conhecida, False é informação e deve ser preservado.
    assert build_pg_feature_context(
        _decision(phase_uncertain=False))["phase_uncertain"] is False
    assert build_pg_feature_context(
        _decision(phase_uncertain=True))["phase_uncertain"] is True


def test_spin_seq_zero_and_negative_are_absence():
    assert build_pg_feature_context(_decision(spin_seq=0))["spin_seq"] is None
    assert build_pg_feature_context(_decision(spin_seq=-3))["spin_seq"] is None
    assert build_pg_feature_context(_decision(spin_seq=1))["spin_seq"] == 1


def test_centro_previsto_zero_is_a_real_pocket():
    assert build_pg_feature_context(_decision(sda_center=0))["centro_previsto"] == 0


@pytest.mark.parametrize("raw,expected", [
    ("horario", "cw"), ("Horário", "cw"), ("cw", "cw"),
    ("anti-horario", "ccw"), ("CCW", "ccw"),
    ("", None), ("diagonal", None), ("norte", None),
])
def test_direction_next_normalized_or_null(raw, expected):
    """Alias conhecido vira cw|ccw; desconhecido vira NULL (sem vocabulário misto)."""
    assert build_pg_feature_context(_decision(direction_next=raw))["direction_next"] == expected


def test_accepts_mapping_source_like_a_db_row():
    """O mesmo helper serve Decision e linha/dict — usado também pelo backfill."""
    ctx = build_pg_feature_context({
        "id": 7, "session_id": "s", "dealer": "Bia", "spin_seq": 4,
        "direction_source": "dom", "phase_uncertain": 1,
    })
    assert ctx["decision_id"] == 7
    assert ctx["dealer"] == "Bia"
    assert ctx["spin_seq"] == 4
    assert ctx["phase_uncertain"] is True
    assert ctx["provider"] is None


def test_never_raises_on_hostile_source():
    class Hostile:
        def __getattr__(self, _name):
            raise RuntimeError("boom")

    ctx = build_pg_feature_context(Hostile())
    assert ctx is not None
    assert all(ctx[k] is None for k in PG_FEATURE_CONTEXT_KEYS)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), 10 ** 400, 1e400])
def test_never_raises_on_out_of_range_numbers(value):
    """OverflowError não é ValueError: sem tratá-lo, o backfill abortaria no meio.

    `build_pg_feature_context` é documentado como total e roda dentro do laço de
    varredura do backfill sem guarda — uma exceção aqui derrubaria a execução
    inteira, não só a linha.
    """
    ctx = build_pg_feature_context({
        "spin_seq": value, "vision_confidence": value, "vision_source": "vision",
        "sda_center": value, "gale_level": value, "id": value,
    })
    assert ctx["spin_seq"] is None
    assert ctx["centro_previsto"] is None
    assert ctx["applied_gale_level"] is None


def test_int_outside_postgres_integer_range_becomes_none():
    assert build_pg_feature_context({"spin_seq": 2 ** 31})["spin_seq"] is None
    assert build_pg_feature_context({"sda_center": -(2 ** 31) - 1})["centro_previsto"] is None
    assert build_pg_feature_context({"spin_seq": 2 ** 31 - 1})["spin_seq"] == 2 ** 31 - 1


def test_booleans_are_not_coerced_into_numbers():
    ctx = build_pg_feature_context({"spin_seq": True, "vision_confidence": True,
                                    "vision_source": "vision"})
    assert ctx["spin_seq"] is None
    assert ctx["vision_confidence"] is None


# ---------------------------------------------------------------------------
# Payloads publicados
# ---------------------------------------------------------------------------

def _patched(fake_pub):
    return (
        patch("database.outbox_integration._is_flag_enabled", return_value=True),
        patch("database.outbox_integration._get_publisher", return_value=fake_pub),
    )


def test_spin_result_payload_off_is_byte_identical_to_legacy():
    from database import outbox_integration as oi
    fake = MagicMock()
    p1, p2 = _patched(fake)
    with p1, p2:
        assert oi.maybe_publish_spin_result(
            777, "anti-horario", False, 0, session_id="s1",
            context=build_pg_feature_context(_decision()),
        ) is True
    payload = fake.publish.call_args.kwargs["payload"]
    assert payload == {
        "event_type": "spin_result",
        "direction": "ccw",
        "decision_id": 777,
        "hit": False,
        "actual_number": 0,
        "session_id": "s1",
    }
    assert "context" not in payload


def test_spin_result_payload_on_carries_self_contained_context(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    from database import outbox_integration as oi
    fake = MagicMock()
    context = build_pg_feature_context(_decision())
    p1, p2 = _patched(fake)
    with p1, p2:
        assert oi.maybe_publish_spin_result(
            4242, "horario", True, 32, session_id="sess-abc", context=context,
        ) is True
    payload = fake.publish.call_args.kwargs["payload"]
    assert payload["context"] == context
    assert payload["actual_number"] == 32
    assert payload["session_id"] == "sess-abc"


def test_spin_result_payload_on_without_context_stays_legacy(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    from database import outbox_integration as oi
    fake = MagicMock()
    p1, p2 = _patched(fake)
    with p1, p2:
        oi.maybe_publish_spin_result(1, "cw", True, 5, session_id="s")
    assert "context" not in fake.publish.call_args.kwargs["payload"]


def test_spin_result_context_is_copied_not_aliased(monkeypatch):
    """Mutação posterior do dict de origem não altera o evento publicado."""
    monkeypatch.setenv(FLAG, "1")
    from database import outbox_integration as oi
    fake = MagicMock()
    context = build_pg_feature_context(_decision())
    p1, p2 = _patched(fake)
    with p1, p2:
        oi.maybe_publish_spin_result(4242, "cw", True, 32, context=context)
    context["dealer"] = "MUTADO"
    assert fake.publish.call_args.kwargs["payload"]["context"]["dealer"] == "Ana"


def test_spin_features_meta_off_is_byte_identical_to_legacy():
    from database import outbox_integration as oi
    fake = MagicMock()
    p1, p2 = _patched(fake)
    with p1, p2:
        assert oi.maybe_publish_decision_features(_decision(), 4242) is True
    meta = fake.publish_spin_features.call_args.kwargs["meta"]
    assert meta == {
        "session_id": "sess-abc",
        "final_action": "APOSTAR",
        "gale_level": 2,
        "spin_number": 12,
        "centro_previsto": 17,
        "applied_gale_level": 2,
    }


def test_spin_features_meta_on_nests_context_without_collision(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    from database import outbox_integration as oi
    fake = MagicMock()
    p1, p2 = _patched(fake)
    with p1, p2:
        oi.maybe_publish_decision_features(_decision(), 4242)
    meta = fake.publish_spin_features.call_args.kwargs["meta"]
    # Chaves legadas intactas...
    assert meta["session_id"] == "sess-abc"
    assert meta["spin_number"] == 12
    assert meta["centro_previsto"] == 17
    assert meta["applied_gale_level"] == 2
    # ...e o contexto aninhado em chave própria.
    assert meta["decision_context"]["dealer"] == "Ana"
    assert meta["decision_context"]["dealer_table"] == "Roleta ao Vivo"
    assert "dealer" not in {k for k in meta if k != "decision_context"}


def test_publish_still_never_raises_with_flag_on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    from database import outbox_integration as oi
    fake = MagicMock()
    fake.publish.side_effect = RuntimeError("PG down")
    fake.publish_spin_features.side_effect = RuntimeError("PG down")
    p1, p2 = _patched(fake)
    with p1, p2:
        assert oi.maybe_publish_spin_result(
            1, "cw", True, 5, context=build_pg_feature_context(_decision())) is False
        assert oi.maybe_publish_decision_features(_decision(), 1) is False
