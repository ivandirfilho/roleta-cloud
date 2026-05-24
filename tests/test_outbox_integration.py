"""Tests do hook S5 (outbox_integration).

- Unit tests: nao requerem PG (mockam publisher + flag).
- Integration tests: marcador `requires_pg` + skip se ROLETA_TEST_PG_ENABLED!=1.
"""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from database.models import Decision

PG_ENABLED = os.environ.get("ROLETA_TEST_PG_ENABLED") == "1"
DSN = os.environ.get("ROLETA_PG_DSN", "")


def _make_decision(direction: str = "horario", **kw) -> Decision:
    return Decision(
        timestamp=datetime.utcnow(),
        session_id="test-session",
        spin_number=12,
        spin_direction=direction,
        spin_force=85,
        tr_c4_rate=0.6,
        tr_m6_rate=0.55,
        tr_l12_rate=0.5,
        sda_score=14,
        sda_predicted_force=90,
        final_action="APOSTAR",
        gale_level=1,
        **kw,
    )


def test_normalize_direction_legacy():
    from database.outbox_integration import _normalize_direction
    assert _normalize_direction("horario") == "cw"
    assert _normalize_direction("Horário") == "cw"
    assert _normalize_direction("anti-horario") == "ccw"
    assert _normalize_direction("Anti-Horário") == "ccw"
    assert _normalize_direction("cw") == "cw"
    assert _normalize_direction("CCW") == "ccw"
    assert _normalize_direction("invalid") is None
    assert _normalize_direction("") is None


def test_extract_raw_features_stable_order():
    from database.outbox_integration import _extract_raw_features
    d = _make_decision()
    feats = _extract_raw_features(d)
    assert len(feats) == 6
    assert feats[0] == 85.0   # spin_force
    assert feats[1] == 0.6    # tr_c4_rate
    assert feats[2] == 0.55   # tr_m6_rate
    assert feats[3] == 0.5    # tr_l12_rate
    assert feats[4] == 14.0   # sda_score
    assert feats[5] == 90.0   # sda_predicted_force


def test_extract_raw_features_handles_none_zero():
    from database.outbox_integration import _extract_raw_features
    d = Decision()  # tudo default/zero
    feats = _extract_raw_features(d)
    assert feats == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_publish_returns_false_when_flag_off():
    """Se flag=false, publish_features nao deve nem tentar publisher."""
    from database import outbox_integration as oi

    oi.invalidate_flag_cache()
    with patch("database.outbox_integration._is_flag_enabled", return_value=False):
        with patch("database.outbox_integration._get_publisher") as mp:
            ok = oi.maybe_publish_decision_features(_make_decision(), 1)
            assert ok is False
            mp.assert_not_called()


def test_publish_calls_publisher_when_flag_on():
    from database import outbox_integration as oi

    oi.invalidate_flag_cache()
    fake_pub = MagicMock()
    with patch("database.outbox_integration._is_flag_enabled", return_value=True), \
         patch("database.outbox_integration._get_publisher", return_value=fake_pub):
        d = _make_decision(direction="anti-horario")
        ok = oi.maybe_publish_decision_features(d, 99)
        assert ok is True
        fake_pub.publish_spin_features.assert_called_once()
        call_kwargs = fake_pub.publish_spin_features.call_args.kwargs
        assert call_kwargs["direction"] == "ccw"
        assert call_kwargs["decision_id"] == 99
        assert len(call_kwargs["raw_features"]) == 6


def test_publish_never_raises_on_publisher_error():
    from database import outbox_integration as oi

    oi.invalidate_flag_cache()
    fake_pub = MagicMock()
    fake_pub.publish_spin_features.side_effect = RuntimeError("PG down")
    with patch("database.outbox_integration._is_flag_enabled", return_value=True), \
         patch("database.outbox_integration._get_publisher", return_value=fake_pub):
        ok = oi.maybe_publish_decision_features(_make_decision(), 1)
        assert ok is False  # nao levantou; retornou False


def test_publish_skips_unknown_direction():
    from database import outbox_integration as oi

    oi.invalidate_flag_cache()
    fake_pub = MagicMock()
    with patch("database.outbox_integration._is_flag_enabled", return_value=True), \
         patch("database.outbox_integration._get_publisher", return_value=fake_pub):
        d = _make_decision(direction="diagonal")
        ok = oi.maybe_publish_decision_features(d, 1)
        assert ok is False
        fake_pub.publish_spin_features.assert_not_called()


# ---------- Integration test (requer PG) ----------

@pytest.mark.skipif(
    not PG_ENABLED or not DSN,
    reason="ROLETA_TEST_PG_ENABLED=1 + ROLETA_PG_DSN required",
)
def test_e2e_flag_on_writes_outbox():
    """E2E: flag=true no PG real => publica em shared.outbox."""
    import psycopg2
    from database import outbox_integration as oi

    conn = psycopg2.connect(DSN)
    try:
        # Set flag on.
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO shared.feature_flags (name, enabled, pct, payload) "
                "VALUES ('dual_write_pg', true, 100, '{}'::jsonb) "
                "ON CONFLICT (name) DO UPDATE SET enabled=EXCLUDED.enabled, updated_at=now();"
            )
        conn.commit()
        oi.invalidate_flag_cache()

        try:
            d = _make_decision()
            ok = oi.maybe_publish_decision_features(d, 12345)
            assert ok, "expected publish to succeed when flag is on"

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM shared.outbox "
                    "WHERE payload->>'event_type'='spin_features' "
                    "AND payload->>'direction'='cw' "
                    "AND (payload->'decision_id')::int = 12345;"
                )
                assert cur.fetchone()[0] >= 1
        finally:
            # Cleanup: desliga flag e limpa outbox de teste.
            with conn.cursor() as cur:
                cur.execute("UPDATE shared.feature_flags SET enabled=false WHERE name='dual_write_pg';")
                cur.execute(
                    "DELETE FROM shared.outbox "
                    "WHERE (payload->'decision_id')::int = 12345;"
                )
            conn.commit()
            oi.invalidate_flag_cache()
    finally:
        conn.close()
