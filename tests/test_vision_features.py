"""Tests Vision features (foto_roleta_junho.md Parte 4): wheel_model / vision_confidence /
vision_source end-to-end no caminho de dados (foto->dados).

Padrão SP-13 (test_sp11_sp15_deal.py): aditivo, backward-compatible, auto-migração SQLite.
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest


def _seed_session(db_path, sid):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO sessions (id, start_time) VALUES (?, ?)",
        (sid, datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_spininput_accepts_vision_fields():
    """SpinInput aceita wheel_model/vision_confidence/vision_source; payload antigo segue válido."""
    from models.input import SpinInput
    s = SpinInput(
        numero=17, direcao="horario", trace_id="t1234", t_client=1,
        wheel_model="evo_classic", vision_confidence=0.93, vision_source="vision",
    )
    assert s.wheel_model == "evo_classic"
    assert s.vision_confidence == 0.93
    assert s.vision_source == "vision"
    # backward-compat: payload sem campos de visão
    s2 = SpinInput(numero=0, direcao="anti-horario", trace_id="abcd", t_client=1)
    assert s2.wheel_model is None
    assert s2.vision_confidence is None
    assert s2.vision_source is None


def test_spininput_confidence_bounds():
    """vision_confidence é validado em [0,1]."""
    from pydantic import ValidationError
    from models.input import SpinInput
    with pytest.raises(ValidationError):
        SpinInput(numero=1, direcao="horario", trace_id="t1234", t_client=1, vision_confidence=1.5)


def test_decision_defaults_vision_fields():
    """Decision tem defaults seguros (retrocompatível)."""
    from database.models import Decision
    d = Decision()
    assert d.wheel_model == ""
    assert d.vision_confidence == 0.0
    assert d.vision_source == ""


def test_save_and_load_roundtrip_vision(tmp_db):
    """save_decision persiste wheel_model/confidence/source e _row_to_decision os recupera."""
    from database.sqlite_repo import SQLiteDecisionRepository
    from database.models import Decision

    repo = SQLiteDecisionRepository(db_path=tmp_db)
    _seed_session(tmp_db, "s_vision")
    d = Decision(
        session_id="s_vision", spin_number=17, spin_direction="horario",
        final_action="APOSTAR", wheel_model="evo_immersive",
        vision_confidence=0.88, vision_source="fused",
    )
    decision_id = repo.save_decision(d)
    assert decision_id > 0

    loaded = repo.get_decision(decision_id)
    assert loaded is not None
    assert loaded.wheel_model == "evo_immersive"
    assert abs(loaded.vision_confidence - 0.88) < 1e-9
    assert loaded.vision_source == "fused"


def test_save_without_vision_is_backward_compatible(tmp_db):
    """Decision sem campos de visão salva e carrega com defaults (sem quebrar)."""
    from database.sqlite_repo import SQLiteDecisionRepository
    from database.models import Decision

    repo = SQLiteDecisionRepository(db_path=tmp_db)
    _seed_session(tmp_db, "s_novis")
    d = Decision(session_id="s_novis", spin_number=0, spin_direction="anti-horario", final_action="PULAR")
    decision_id = repo.save_decision(d)
    loaded = repo.get_decision(decision_id)
    assert loaded is not None
    assert loaded.wheel_model == ""
    assert loaded.vision_confidence == 0.0
    assert loaded.vision_source == ""


def test_auto_migration_adds_columns_to_legacy_db(tmp_db):
    """As colunas de visão só existem porque a auto-migração as adiciona no init
    (CREATE TABLE decisions não as inclui) — prova o caminho ADD COLUMN idempotente."""
    from database.sqlite_repo import SQLiteDecisionRepository
    SQLiteDecisionRepository(db_path=tmp_db)  # init dispara auto-migração

    conn = sqlite3.connect(tmp_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()}
    conn.close()
    assert {"wheel_model", "vision_confidence", "vision_source"}.issubset(cols)


def test_auto_migration_is_idempotent(tmp_db):
    """Reabrir o repo no mesmo arquivo não falha (SELECT wheel_model já existe → no-op)."""
    from database.sqlite_repo import SQLiteDecisionRepository
    SQLiteDecisionRepository(db_path=tmp_db)
    SQLiteDecisionRepository(db_path=tmp_db)  # 2ª init não deve levantar
    conn = sqlite3.connect(tmp_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()}
    conn.close()
    assert "wheel_model" in cols


def test_update_last_vision_persists_on_latest_decision(tmp_db):
    """Vision (foto->dados->DB): update_last_vision grava o OCR na decisão mais recente."""
    from database.sqlite_repo import SQLiteDecisionRepository
    from database.models import Decision

    repo = SQLiteDecisionRepository(db_path=tmp_db)
    _seed_session(tmp_db, "s_upd")
    # duas decisões; a foto deve cair na MAIS RECENTE
    repo.save_decision(Decision(session_id="s_upd", spin_number=1, spin_direction="horario", final_action="APOSTAR"))
    last_id = repo.save_decision(Decision(session_id="s_upd", spin_number=2, spin_direction="horario", final_action="APOSTAR"))

    did = repo.update_last_vision(dealer="Carlos", wheel_model="evo_immersive", confidence=0.91, source="vision")
    assert did == last_id

    loaded = repo.get_decision(last_id)
    assert loaded.dealer == "Carlos"
    assert loaded.wheel_model == "evo_immersive"
    assert abs(loaded.vision_confidence - 0.91) < 1e-9
    assert loaded.vision_source == "vision"


def test_update_last_vision_empty_db_returns_zero(tmp_db):
    """Sem decisões, update_last_vision retorna 0 (não quebra)."""
    from database.sqlite_repo import SQLiteDecisionRepository
    repo = SQLiteDecisionRepository(db_path=tmp_db)
    assert repo.update_last_vision(dealer="X") == 0


