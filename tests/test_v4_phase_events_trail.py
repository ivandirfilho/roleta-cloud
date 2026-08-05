"""SPR-V4 — trilha `phase_events`: DDL aditiva, idempotência e ATOMICIDADE.

Prometheus não satisfaz o gate T4: counters zeram a cada restart do container e logs
têm retenção limitada. `phase_events` é requisito de EVIDÊNCIA, não luxo analítico —
e evidência com buraco (decisão sem disposição) não é evidência.
"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from database.models import Decision
from database.sqlite_repo import (
    PhaseTrailCommitAmbiguous, PhaseTrailRolledBack, SQLiteDecisionRepository,
)
from state.game import GameState
from state.phase import ANTI, HORARIO


def _decision(session_id="s1", spin_number=17):
    return Decision(
        session_id=session_id, spin_number=spin_number, spin_direction=HORARIO,
        spin_force=3, final_action="APOSTAR", action_reason="teste",
        sda_numbers=[1, 2, 3], sda_centers=[1], sda_center=1,
        performance_snapshot=[], timestamp=datetime.now(),
    )


def _row(kind="agree", event_id="e1", session_id="s1", target=1, **over):
    row = {
        "event_id": event_id, "ts_srv_ms": 1_700_000_000_000,
        "session_id": session_id, "round_id": None, "target_spin_seq": target,
        "kind": kind, "source": "vision", "observed_direction": ANTI,
        "reference_direction": HORARIO, "confidence": 0.9,
        "decision_ref": None, "meta_json": {"reason": "teste"},
    }
    row.update(over)
    return row


@pytest.fixture()
def repo(tmp_path):
    from database.models import Session
    r = SQLiteDecisionRepository(str(tmp_path / "trail.db"))
    # FK: decisions.session_id REFERENCES sessions(id).
    r.create_session(Session(id="s1"))
    return r


def _count(repo, table="phase_events", where=""):
    conn = sqlite3.connect(str(repo.db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------- DDL

def test_ddl_aditiva_e_idempotente(tmp_path):
    """Rodar 2x não pode quebrar: em produção o schema in-code roda a cada boot."""
    db = str(tmp_path / "idem.db")
    r1 = SQLiteDecisionRepository(db)
    r1.insert_phase_events([_row(kind="received")])
    r2 = SQLiteDecisionRepository(db)  # segunda passada do DDL
    assert _count(r2) == 1, "a segunda inicializacao nao pode apagar/duplicar a trilha"


def test_schema_tem_colunas_e_unique_do_contrato(repo):
    conn = sqlite3.connect(str(repo.db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(phase_events)")}
        assert cols == {
            "id", "event_id", "ts_srv_ms", "session_id", "round_id",
            "target_spin_seq", "kind", "source", "observed_direction",
            "reference_direction", "confidence", "decision_ref", "meta_json",
        }
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='phase_events'").fetchone()[0]
        assert "UNIQUE(event_id, kind, target_spin_seq)" in ddl
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='phase_events'").fetchall()
        assert any("ix_phase_events_session_spin" in n[0] for n in idx)
    finally:
        conn.close()


def test_frames_nunca_entram_no_banco(repo):
    """Só metadados (~100-300 bytes/giro). Não existe coluna para imagem."""
    conn = sqlite3.connect(str(repo.db_path))
    try:
        cols = {r[1].lower() for r in conn.execute("PRAGMA table_info(phase_events)")}
        assert not (cols & {"frame", "frames", "image", "blob", "payload"})
    finally:
        conn.close()


# ---------------------------------------------------------- idempotência

def test_retry_do_mesmo_event_id_kind_nao_duplica(repo):
    """Retry do MESMO evento no MESMO giro é idempotente."""
    assert repo.insert_phase_events([_row(kind="agree", event_id="e9", target=3)]) == 1
    assert repo.insert_phase_events([_row(kind="agree", event_id="e9", target=3)]) == 0
    assert _count(repo) == 1


def test_mesmo_event_id_em_giros_DIFERENTES_nao_e_descartado(repo):
    """DESVIO do DDL literal do brief (`UNIQUE(event_id, kind)`), e a razão dele.

    `event_id` é o valor DO CLIENTE quando presente e nada o prende a um giro. Com a
    chave global, um produtor que reutilize um id estável gravaria UMA linha por kind
    para a vida inteira enquanto os counters continuam subindo: a trilha
    sub-registraria em silêncio e a taxa de acordo subiria artificialmente (some
    `missing` do denominador) — exatamente a métrica enganosa que este sprint existe
    para impedir.
    """
    for giro in (1, 2, 3):
        assert repo.insert_phase_events(
            [_row(kind="agree", event_id="cam-fixa", target=giro)]) == 1
    assert _count(repo) == 3


def test_kinds_diferentes_do_mesmo_evento_coexistem(repo):
    repo.insert_phase_events([
        _row(kind="received", event_id="e9"),
        _row(kind="bound", event_id="e9"),
        _row(kind="agree", event_id="e9"),
    ])
    assert _count(repo) == 3


def test_missing_usa_id_deterministico_e_e_idempotente(repo):
    ev_id = "missing:s1:42"
    assert repo.insert_phase_events(
        [_row(kind="missing", event_id=ev_id, target=42, source="server")]) == 1
    assert repo.insert_phase_events(
        [_row(kind="missing", event_id=ev_id, target=42, source="server")]) == 0
    assert _count(repo) == 1


def test_supressao_por_conflito_e_reportada_ao_caller(repo):
    """Linha suprimida é evidência que NÃO existe. Se a supressão não voltar ao
    caller, a trilha sub-registra sem nenhuma métrica subir."""
    repo.insert_phase_events([_row(kind="agree", event_id="dup", target=1)])
    suprimidas = []
    repo.save_decision_with_phase_events(
        _decision(), [_row(kind="agree", event_id="dup", target=1)],
        on_suppressed=suprimidas.extend)
    assert len(suprimidas) == 1 and suprimidas[0]["event_id"] == "dup"


# ------------------------------------------------------------ atomicidade

def test_decisao_e_disposicao_na_mesma_transacao(repo):
    did = repo.save_decision_with_phase_events(
        _decision(), [_row(kind="bound"), _row(kind="agree")])
    assert did >= 1
    assert _count(repo, "decisions") == 1
    assert _count(repo) == 2
    conn = sqlite3.connect(str(repo.db_path))
    try:
        refs = {r[0] for r in conn.execute("SELECT decision_ref FROM phase_events")}
        assert refs == {str(did)}, "a trilha precisa apontar para a decisao do giro"
    finally:
        conn.close()


def test_falha_injetada_entre_os_writes_faz_rollback_total(repo, monkeypatch):
    """Falha ENTRE os dois writes ⇒ NEM decisão NEM disposição ficam gravadas.
    Sem isto existiria decisão sem disposição e a trilha deixaria de ser prova."""
    original = SQLiteDecisionRepository._insert_phase_event_row

    def _boom(self, conn, row, decision_ref=None):
        raise RuntimeError("falha injetada apos o INSERT da decisao")

    monkeypatch.setattr(SQLiteDecisionRepository, "_insert_phase_event_row", _boom)
    with pytest.raises(PhaseTrailRolledBack):
        repo.save_decision_with_phase_events(_decision(), [_row()])
    assert _count(repo, "decisions") == 0, "decisao vazou apesar do rollback"
    assert _count(repo) == 0

    # Retry idempotente depois de restaurar o caminho: grava UMA vez.
    monkeypatch.setattr(SQLiteDecisionRepository, "_insert_phase_event_row", original)
    repo.save_decision_with_phase_events(_decision(), [_row()])
    repo.save_decision_with_phase_events(_decision(), [_row()])
    assert _count(repo) == 1, "UNIQUE(event_id, kind) deveria tornar o retry idempotente"


def test_linha_invalida_estoura_em_vez_de_ser_engolida(repo):
    """`ON CONFLICT DO NOTHING` (e não `INSERT OR IGNORE`): o `OR IGNORE` engoliria
    violação de NOT NULL e a decisão comitaria com a disposição descartada em
    silêncio — o teste de rollback passaria por engano."""
    with pytest.raises(PhaseTrailRolledBack):
        repo.save_decision_with_phase_events(_decision(), [_row(kind=None)])
    assert _count(repo, "decisions") == 0
    assert _count(repo) == 0


def test_commit_ambiguo_nao_permite_retry(repo, monkeypatch):
    """Se o próprio `commit()` levanta, não dá para afirmar se gravou — re-tentar
    duplicaria a decisão. Exceção DISTINTA para o caller não cair no fallback."""
    real_connect = sqlite3.connect

    class _BadCommit(sqlite3.Connection):
        def commit(self):
            raise sqlite3.OperationalError("disk I/O error no commit")

    monkeypatch.setattr(
        sqlite3, "connect",
        lambda *a, **k: real_connect(*a, factory=_BadCommit, **k))
    with pytest.raises(PhaseTrailCommitAmbiguous):
        repo.save_decision_with_phase_events(_decision(), [_row()])


def test_outbox_publica_uma_vez_e_so_apos_commit(repo, monkeypatch):
    """Paridade com `save_decision`: o hook do outbox roda exatamente uma vez e
    NUNCA depois de um rollback (senão o PG receberia uma decisão inexistente)."""
    chamadas = []
    monkeypatch.setattr(
        SQLiteDecisionRepository, "_publish_decision_outbox",
        staticmethod(lambda d, i: chamadas.append(i)))
    repo.save_decision_with_phase_events(_decision(), [_row()])
    assert len(chamadas) == 1

    monkeypatch.setattr(
        SQLiteDecisionRepository, "_insert_phase_event_row",
        lambda self, conn, row, decision_ref=None: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(PhaseTrailRolledBack):
        repo.save_decision_with_phase_events(_decision(), [_row(event_id="e2")])
    assert len(chamadas) == 1, "outbox publicou apesar do rollback"


def test_paridade_de_colunas_entre_os_dois_caminhos(repo):
    """Os dois caminhos gravam a MESMA decisão: um campo novo não pode existir só
    em `save_decision`."""
    d = _decision(spin_number=21)
    id_legado = repo.save_decision(d)
    id_atomico = repo.save_decision_with_phase_events(d, [_row(event_id="par")])
    conn = sqlite3.connect(str(repo.db_path))
    conn.row_factory = sqlite3.Row
    try:
        a = dict(conn.execute("SELECT * FROM decisions WHERE id=?", (id_legado,)).fetchone())
        b = dict(conn.execute("SELECT * FROM decisions WHERE id=?", (id_atomico,)).fetchone())
    finally:
        conn.close()
    a.pop("id"), b.pop("id")
    assert a == b


# ------------------------------------------------------ pendente/reconstrução

def test_pendente_e_reconstruido_do_received_sem_terminal(repo):
    repo.insert_phase_events([_row(kind="received", event_id="orfao")])
    pend = repo.get_pending_phase_event("s1")
    assert pend and pend["event_id"] == "orfao"
    repo.insert_phase_events([_row(kind="agree", event_id="orfao")])
    assert repo.get_pending_phase_event("s1") is None


def test_bound_nao_encerra_o_evento(repo):
    """`bound` é transição, não disposição — só os terminais fecham o ciclo."""
    repo.insert_phase_events([
        _row(kind="received", event_id="b1"), _row(kind="bound", event_id="b1")])
    assert repo.get_pending_phase_event("s1")["event_id"] == "b1"


@pytest.mark.parametrize("kind", SQLiteDecisionRepository.TERMINAL_PHASE_EVENT_KINDS)
def test_todo_kind_terminal_encerra_o_pendente(repo, kind):
    repo.insert_phase_events([
        _row(kind="received", event_id=f"t-{kind}"), _row(kind=kind, event_id=f"t-{kind}")])
    assert repo.get_pending_phase_event("s1") is None


# ============================================================================
# Integração pelo handler real
# ============================================================================

class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, m):
        self.sent.append(m)


@pytest.fixture()
def handler(tmp_path, monkeypatch):
    import database
    from app_config.settings import settings
    from strategies.sda17 import SDA17Strategy
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler
    from state import phase_metrics

    database.init_database(str(tmp_path / "d.db"))
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json")
    monkeypatch.setattr(
        mh_mod.connection_manager, "broadcast",
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)))
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "master")
    monkeypatch.setenv("SDA_PHASE_EVENT_AUDIT", "1")
    monkeypatch.setenv("SDA_DIRECTION_VISION_SHADOW", "1")
    phase_metrics.reset()
    h = MessageHandler(
        game_state=GameState(), strategy=SDA17Strategy(),
        state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"))
    h.current_session_id = "sess-int"
    yield h
    phase_metrics.reset()


def _spin(h, ws, numero, direcao=HORARIO, i=0):
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": numero, "direcao": direcao,
        "timestamp": 1_700_000_000_000 + i * 45_000, "trace_id": f"trace-{i:03d}",
        "allNumbers": [numero],
    }), "c1"))


def _event(h, ws, **payload):
    data = {"type": "direction_event", "direction": ANTI, "confidence": 0.9}
    data.update(payload)
    asyncio.run(h.process_message(ws, json.dumps(data), "c1"))


def _kinds(h):
    from database import get_repository
    return get_repository().count_phase_events_by_kind()


def test_fluxo_completo_grava_received_bound_e_disposicao(handler, monkeypatch):
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "0")
    ws = _FakeWS()
    _event(handler, ws, event_id="cam-1", direction=HORARIO)
    _spin(handler, ws, 17, HORARIO, 0)
    k = _kinds(handler)
    assert k.get("received") == 1 and k.get("bound") == 1 and k.get("agree") == 1
    from state import phase_metrics
    assert phase_metrics.snapshot()["vision_agree_total"] == 1


def test_giro_sem_evento_grava_missing(handler):
    ws = _FakeWS()
    _spin(handler, ws, 17, HORARIO, 0)
    assert _kinds(handler).get("missing") == 1


def test_one_shot_o_evento_nao_atravessa_dois_giros(handler, monkeypatch):
    """O coração do bug latente: o veredito CORRETO do giro N é a direção ERRADA do
    giro N+1 (a mesa alterna). O evento tem de morrer no primeiro giro."""
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "0")
    ws = _FakeWS()
    _event(handler, ws, event_id="cam-1", direction=HORARIO)
    _spin(handler, ws, 17, HORARIO, 0)
    _spin(handler, ws, 21, ANTI, 1)
    k = _kinds(handler)
    assert k.get("agree") == 1
    assert k.get("missing") == 1, "o segundo giro reaproveitou o evento do primeiro"
    assert handler.game_state.pending_direction_event is None


def test_supersede_nao_polui_o_denominador_da_cobertura(handler, monkeypatch):
    """5 frames antes de UM giro que concorda ⇒ cobertura 1.0, não 0.2.

    `roleta_vision_coverage_ratio` é a métrica que o runbook manda ler ANTES de
    confiar em qualquer taxa de acordo; um denominador inflado por frames extras
    faria a decisão do gate T4 em cima de um número errado.
    """
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "0")
    from state import phase_metrics
    from server import health_server
    ws = _FakeWS()
    for i in range(5):
        _event(handler, ws, event_id=f"frame-{i}", direction=HORARIO)
    _spin(handler, ws, 17, HORARIO, 0)
    snap = phase_metrics.snapshot()
    assert snap["vision_event_total"] == 5
    assert snap["vision_agree_total"] == 1
    elegiveis = sum(snap[c] for c in (
        "vision_agree_total", "vision_disagree_total", "vision_stale_total",
        "vision_unbound_total", "vision_selfcontradict_total", "vision_missing_total"))
    assert elegiveis == 1, "frames extras entraram no denominador da cobertura"
    if health_server._METRICS_AVAILABLE:
        health_server._refresh_custom_metrics()
        assert health_server._PROM_METRICS["vision_coverage_ratio"]._value.get() == 1.0
    # Os 4 superseded continuam auditáveis na trilha (não somem em silêncio).
    assert _kinds(handler).get("unbound") == 4


def test_falha_de_escrita_da_trilha_nao_altera_o_giro_nem_a_aposta(handler, monkeypatch):
    """Banco indisponível: a decisão do giro é preservada (política explícita —
    decisão obrigatória, auditoria best-effort), o contador de erro sobe e a
    janela deixa de valer como evidência T4."""
    from state import phase_metrics
    from database import service as _svc

    ws = _FakeWS()
    _event(handler, ws, event_id="cam-err", direction=HORARIO)
    monkeypatch.setattr(
        _svc.db_service, "save_decision_with_phase_events",
        lambda d, r, on_suppressed=None: (_ for _ in ()).throw(
            PhaseTrailRolledBack("banco fora")))
    _spin(handler, ws, 17, HORARIO, 0)

    from database import get_repository
    conn = sqlite3.connect(str(get_repository().db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1, (
            "a decisao do giro foi perdida por causa da trilha")
    finally:
        conn.close()
    assert phase_metrics.snapshot()["phase_events_write_error_total"] == 1
    assert handler.game_state.last_number == 17
    assert handler.game_state.spin_seq == 1


def test_commit_ambiguo_no_handler_nao_duplica_decisao(handler, monkeypatch):
    from state import phase_metrics
    from database import service as _svc

    ws = _FakeWS()
    _event(handler, ws, event_id="cam-amb", direction=HORARIO)
    monkeypatch.setattr(
        _svc.db_service, "save_decision_with_phase_events",
        lambda d, r, on_suppressed=None: (_ for _ in ()).throw(
            PhaseTrailCommitAmbiguous("indeterminado")))
    _spin(handler, ws, 17, HORARIO, 0)
    from database import get_repository
    conn = sqlite3.connect(str(get_repository().db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
    finally:
        conn.close()
    assert phase_metrics.snapshot()["phase_events_write_error_total"] == 1
    assert handler.game_state.spin_seq == 1, "o giro foi rejeitado por causa da trilha"


def test_excecao_desconhecida_pos_commit_nao_duplica_decisao(handler, monkeypatch):
    """Só `PhaseTrailRolledBack` prova que nada foi gravado. Qualquer outra falha
    (hook do outbox, `close()`) acontece DEPOIS do commit — re-tentar duplicaria a
    decisão no ledger."""
    from state import phase_metrics
    from database import service as _svc

    ws = _FakeWS()
    _event(handler, ws, event_id="cam-pos", direction=HORARIO)
    real = _svc.db_service.save_decision_with_phase_events

    def _commit_e_explode(d, r, on_suppressed=None):
        real(d, r, on_suppressed=on_suppressed)          # grava de verdade
        raise RuntimeError("falha DEPOIS do commit (hook/close)")

    monkeypatch.setattr(
        _svc.db_service, "save_decision_with_phase_events", _commit_e_explode)
    _spin(handler, ws, 17, HORARIO, 0)
    from database import get_repository
    conn = sqlite3.connect(str(get_repository().db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1, (
            "a decisao foi duplicada apos falha pos-commit")
    finally:
        conn.close()
    assert phase_metrics.snapshot()["phase_events_write_error_total"] == 1


def test_audit_off_nao_grava_nada(handler, monkeypatch):
    monkeypatch.setenv("SDA_PHASE_EVENT_AUDIT", "0")
    ws = _FakeWS()
    _event(handler, ws, event_id="cam-off", direction=HORARIO)
    _spin(handler, ws, 17, HORARIO, 0)
    assert _kinds(handler) == {}


def test_nova_sessao_fecha_o_received_orfao(handler):
    ws = _FakeWS()
    _event(handler, ws, event_id="cam-reset", direction=HORARIO)
    asyncio.run(handler.process_message(ws, json.dumps({"type": "nova_sessao"}), "c1"))
    from database import get_repository
    conn = sqlite3.connect(str(get_repository().db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = {r["kind"]: dict(r) for r in conn.execute(
            "SELECT * FROM phase_events WHERE event_id='cam-reset'")}
    finally:
        conn.close()
    assert set(rows) == {"received", "unbound"}
    assert json.loads(rows["unbound"]["meta_json"])["reason"] == "session_reset"


def test_trilha_e_counters_contam_a_mesma_historia(handler):
    """Guarda-corpo contra sub-registro silencioso: para cada giro elegível existe
    UMA disposição no banco E um incremento no counter. Se a trilha descartar linha
    em silêncio, os dois números divergem."""
    from state import phase_metrics
    ws = _FakeWS()
    for i, (n, d) in enumerate([(17, HORARIO), (21, ANTI), (5, HORARIO), (9, ANTI)]):
        if i % 2 == 0:
            # `event_id` REUTILIZADO de propósito entre giros (produtor com id fixo).
            _event(handler, ws, event_id="cam-fixa", direction=d)
        _spin(handler, ws, n, d, i)
    k = _kinds(handler)
    snap = phase_metrics.snapshot()
    terminais = sum(k.get(t, 0) for t in (
        "agree", "disagree", "stale", "unbound", "missing", "selfcontradict"))
    counters = sum(snap[c] for c in (
        "vision_agree_total", "vision_disagree_total", "vision_stale_total",
        "vision_unbound_total", "vision_selfcontradict_total", "vision_missing_total"))
    assert terminais == counters == 4, (k, snap)
    assert snap["phase_events_write_error_total"] == 0


def test_supressao_de_linha_conta_erro_de_escrita(handler):
    """Se uma linha da trilha for descartada por conflito, a métrica sobe — a
    janela deixa de valer como evidência T4 em vez de passar por completa."""
    from database import get_repository
    from state import phase_metrics
    ws = _FakeWS()
    # Pré-grava a linha `missing` do giro 1 para forçar o conflito.
    get_repository().insert_phase_events([{
        "event_id": "missing:sess-int:1", "ts_srv_ms": 1, "session_id": "sess-int",
        "round_id": None, "target_spin_seq": 1, "kind": "missing", "source": "server",
        "observed_direction": None, "reference_direction": None, "confidence": None,
        "decision_ref": None, "meta_json": {},
    }])
    _spin(handler, ws, 17, HORARIO, 0)
    assert phase_metrics.snapshot()["phase_events_write_error_total"] == 1


def test_pendente_e_reconstruido_da_trilha_quando_o_state_json_some(handler):
    """Rede de segurança do restart: o `received` gravado antes do crash não pode
    virar órfão eterno. Reconstruído SEM o monotônico ⇒ `stale` por definição."""
    from state import phase_metrics
    ws = _FakeWS()
    _event(handler, ws, event_id="cam-crash", direction=HORARIO)
    # Simula perda do state.json (o pendente vive só na trilha).
    handler.game_state.pending_direction_event = None
    _spin(handler, ws, 17, HORARIO, 0)
    k = _kinds(handler)
    assert k.get("stale") == 1, k
    assert phase_metrics.snapshot()["vision_stale_total"] == 1
    # A busca roda UMA vez por sessão: o giro seguinte volta a ser `missing`.
    _spin(handler, ws, 21, ANTI, 1)
    assert _kinds(handler).get("missing") == 1


def test_ingresso_persiste_o_pendente_no_state_json(handler):
    """Sem `save()` no ingresso o round-trip seria teatro: o `save()` do giro roda
    DEPOIS do consumo e gravaria sempre `None`."""
    from app_config.settings import settings
    ws = _FakeWS()
    _event(handler, ws, event_id="cam-persist", direction=HORARIO)
    data = json.loads(Path(settings.state_file).read_text(encoding="utf-8"))
    ev = data["pending_direction_event"]
    assert ev["event_id"] == "cam-persist"
    assert "received_at_mono" not in ev and ev["mono_lost"] is True
