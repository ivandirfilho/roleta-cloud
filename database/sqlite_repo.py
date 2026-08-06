# Roleta Cloud - SQLite Repository Implementation
# Implementação do repositório usando SQLite

import sqlite3
import json
import logging
import time
from datetime import datetime, timezone as _tz
from pathlib import Path
from typing import List, Optional, Dict, Any

from .repository import DecisionRepository
from .models import Decision, Session

logger = logging.getLogger(__name__)


# ============================================================================
# MEL-ISO-004 — Circuit Breaker para SQLite (Confiabilidade 5.3 Tolerância)
# ============================================================================

class CircuitBreakerOpen(RuntimeError):
    """Levantada quando o circuit breaker do SQLite esta OPEN.

    Sinaliza que muitas falhas consecutivas ocorreram e a aplicacao deve
    parar de tentar I/O ate o cooldown expirar. Callers devem capturar e
    degradar elegantemente (ex.: skip persistencia, logar warning).
    """


class PhaseTrailRolledBack(RuntimeError):
    """SPR-V4: a transacao decisao+disposicao falhou ANTES do commit.

    Garante ao caller que NADA foi gravado (nem a decisao, nem a trilha), o que
    torna seguro re-tentar a decisao sozinha. E o unico caso em que o fallback
    "decisao obrigatoria / auditoria best-effort" pode agir sem risco de duplicar
    a decisao.
    """


class PhaseTrailCommitAmbiguous(RuntimeError):
    """SPR-V4: o proprio `commit()` levantou — nao da para afirmar se gravou.

    Deliberadamente distinta de `PhaseTrailRolledBack`: o caller NAO pode
    re-tentar a decisao (duplicaria a linha se o commit tiver sido aplicado).
    So conta erro e segue — a janela deixa de valer como evidencia T4.
    """


class _SQLiteCircuitBreaker:
    """Circuit breaker stateful para conexoes SQLite.

    Estados:
      CLOSED   — operacao normal; conta falhas em janela deslizante
      OPEN     — bloqueia todas as conexoes ate cooldown expirar
      HALF_OPEN— testa UMA conexao; sucesso -> CLOSED, falha -> OPEN

    Default thresholds (defensivos, podem ser tunados via ctor):
      failure_threshold = 5 falhas em window_seconds
      window_seconds    = 60s
      cooldown_seconds  = 30s
    """

    _CLOSED = "CLOSED"
    _OPEN = "OPEN"
    _HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5,
                 window_seconds: float = 60.0,
                 cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._state = self._CLOSED
        self._failures: List[float] = []
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> str:
        return self._state

    def before_call(self) -> None:
        """Decide se a chamada pode prosseguir. Raises CircuitBreakerOpen se nao."""
        now = time.monotonic()
        if self._state == self._OPEN:
            if self._opened_at is None or now - self._opened_at >= self.cooldown_seconds:
                self._state = self._HALF_OPEN
                logger.warning("SQLite circuit HALF_OPEN — tentando reabrir")
            else:
                remaining = self.cooldown_seconds - (now - self._opened_at)
                raise CircuitBreakerOpen(
                    f"SQLite circuit OPEN — cooldown {remaining:.1f}s restantes"
                )

    def record_success(self) -> None:
        if self._state != self._CLOSED:
            logger.info(f"SQLite circuit RESET para CLOSED (era {self._state})")
        self._state = self._CLOSED
        self._failures.clear()
        self._opened_at = None

    def record_failure(self, exc: BaseException) -> None:
        now = time.monotonic()
        # Janela deslizante
        self._failures = [t for t in self._failures if now - t <= self.window_seconds]
        self._failures.append(now)
        if self._state == self._HALF_OPEN:
            # Falha na tentativa de reabrir -> re-abre
            self._state = self._OPEN
            self._opened_at = now
            logger.error(
                f"SQLite circuit re-OPEN (HALF_OPEN falhou): {type(exc).__name__}: {exc}"
            )
        elif len(self._failures) >= self.failure_threshold:
            self._state = self._OPEN
            self._opened_at = now
            logger.error(
                f"SQLite circuit OPEN — {len(self._failures)} falhas em "
                f"{self.window_seconds}s. Cooldown {self.cooldown_seconds}s. "
                f"Ultimo erro: {type(exc).__name__}: {exc}"
            )


class SQLiteDecisionRepository(DecisionRepository):
    """
    Implementação do repositório usando SQLite.
    
    Arquivo único, zero configuração, perfeito para desenvolvimento
    e produção de pequena/média escala.
    """
    
    DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "decisions.db"
    
    def __init__(self, db_path: str = None,
                 circuit_breaker: Optional[_SQLiteCircuitBreaker] = None):
        """
        Inicializa conexão com SQLite.
        
        Args:
            db_path: Caminho para o arquivo .db (usa default se None)
            circuit_breaker: MEL-ISO-004 — instancia opcional (default cria nova).
                             Use mesmo instance entre repos para coordenar.
        """
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        
        # Criar diretório se não existe
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # MEL-ISO-004: circuit breaker para evitar tempestade de retries
        self._cb = circuit_breaker if circuit_breaker is not None else _SQLiteCircuitBreaker()

        # Inicializar schema
        self._init_schema()
        
        logger.info(f"SQLite repository initialized: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Retorna nova conexão com SQLite (WAL mode + busy timeout + FK).

        MEL-ISO-004: aplica circuit breaker. Se circuito OPEN, raises
        CircuitBreakerOpen sem nem tentar a conexao. Falhas reais sao
        contadas e podem abrir o circuito.
        """
        self._cb.before_call()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            self._cb.record_failure(e)
            raise
        else:
            self._cb.record_success()
            return conn

    def _execute_with_connection(self, func):
        """Executa função com conexão gerenciada (auto-close)."""
        conn = self._get_connection()
        try:
            return func(conn)
        finally:
            conn.close()
    
    def _init_schema(self) -> None:
        """Cria tabelas se não existirem."""
        with self._get_connection() as conn:
            conn.executescript("""
                -- Tabela de sessões
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME,
                    total_spins INTEGER DEFAULT 0,
                    total_bets INTEGER DEFAULT 0,
                    total_hits INTEGER DEFAULT 0,
                    total_profit REAL DEFAULT 0.0,
                    max_gale_reached INTEGER DEFAULT 1,
                    total_stops INTEGER DEFAULT 0,  -- DEPRECATED: Smart Gale v4 não tem stop
                    total_resets INTEGER DEFAULT 0   -- Smart Gale v4: vezes que voltou a G1 após miss
                );
                
                -- Tabela de decisões
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT,
                    
                    -- Contexto do Spin
                    spin_number INTEGER,
                    spin_direction TEXT,
                    spin_force INTEGER,
                    
                    -- Triple Rate Advisor
                    tr_should_bet BOOLEAN,
                    tr_confidence TEXT,
                    tr_reason TEXT,
                    tr_c4_rate REAL,
                    tr_m6_rate REAL,
                    tr_l12_rate REAL,
                    
                    -- SDA Strategy
                    sda_should_bet BOOLEAN,
                    sda_score INTEGER,
                    sda_center INTEGER,
                    sda_centers TEXT,  -- JSON array [C1, C2, C3] — SDA-21
                    sda_numbers TEXT,  -- JSON array
                    sda_predicted_force INTEGER,
                    sda_offset INTEGER,              -- Offset adaptativo real
                    sda_offset_type TEXT,             -- "sigmoid" (v4.3+), "bayesian" (v4.1-4.2)
                    
                    -- Decisão Final
                    final_action TEXT,
                    action_reason TEXT,
                    
                    -- Martingale State
                    gale_level INTEGER,
                    gale_window_hits INTEGER,
                    gale_window_count INTEGER,
                    gale_bet_value INTEGER,
                    
                    -- Resultado
                    result_hit BOOLEAN,
                    result_actual INTEGER,
                    
                    -- DEPRECATED: calibração removida na v1.5.0 (sempre 0/NULL para dados novos)
                    calibration_offset INTEGER,
                    calibration_error INTEGER,
                    
                    -- Performance snapshot
                    performance_snapshot TEXT,  -- JSON array
                    
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );
                
                -- Tabela de janelas de gale (ML-ready)
                CREATE TABLE IF NOT EXISTS gale_windows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    direction TEXT NOT NULL,
                    gale_level INTEGER NOT NULL,
                    started_at DATETIME NOT NULL,
                    ended_at DATETIME,
                    total_hits INTEGER DEFAULT 0,
                    total_plays INTEGER DEFAULT 0,
                    result TEXT,
                    next_level INTEGER,
                    sda17_rate_at_start REAL,
                    bet_rate_at_start REAL,
                    calibration_offset INTEGER
                );
                
                -- Tabela de jogadas por janela
                CREATE TABLE IF NOT EXISTS window_plays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    window_id INTEGER NOT NULL,
                    play_number INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    spin_number INTEGER,
                    spin_direction TEXT,
                    spin_force INTEGER,
                    center_predicted INTEGER,
                    hit BOOLEAN,
                    actual_number INTEGER,
                    sda_score INTEGER,
                    tr_confidence TEXT,
                    tr_reason TEXT,
                    FOREIGN KEY (window_id) REFERENCES gale_windows(id)
                );
                
                -- Índices para consultas frequentes
                CREATE INDEX IF NOT EXISTS idx_decisions_session 
                    ON decisions(session_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_timestamp 
                    ON decisions(timestamp);
                CREATE INDEX IF NOT EXISTS idx_decisions_action 
                    ON decisions(final_action);
                CREATE INDEX IF NOT EXISTS idx_decisions_gale 
                    ON decisions(gale_level);
                
                -- Índices para novas tabelas ML
                CREATE INDEX IF NOT EXISTS idx_gale_windows_direction 
                    ON gale_windows(direction);
                CREATE INDEX IF NOT EXISTS idx_gale_windows_level 
                    ON gale_windows(gale_level);
                CREATE INDEX IF NOT EXISTS idx_gale_windows_started 
                    ON gale_windows(started_at);
                CREATE INDEX IF NOT EXISTS idx_window_plays_window 
                    ON window_plays(window_id);
                
                -- 🔧 MEL-006: apenas 1 janela ativa (não-fechada) por direção
                CREATE UNIQUE INDEX IF NOT EXISTS idx_gale_windows_active 
                    ON gale_windows(direction) WHERE ended_at IS NULL;

                -- SPR-V4 (05/08): trilha de fase APPEND-ONLY. Cada transicao de um
                -- `direction_event` e uma linha IMUTAVEL. Frames NUNCA entram aqui —
                -- so metadados. Sem Alembic nesta fase: a trilha nasce em SQLite
                -- local (o caminho de migracao in-code abaixo ja e o usado em
                -- producao). Aditivo: rollback desliga a flag e a tabela PERMANECE
                -- (inofensiva, o deploy nao faz downgrade de schema).
                --
                -- DESVIO DELIBERADO do DDL literal do brief, que pedia
                -- `UNIQUE(event_id, kind)`: `event_id` e o valor DO CLIENTE quando
                -- presente e nada o prende a um giro nem a uma sessao. Com a chave
                -- global, um produtor que reutilize o mesmo id (id estavel de
                -- camera/sensor) gravaria UMA linha por kind para a vida inteira
                -- enquanto os counters continuam subindo — a trilha SUB-REGISTRA em
                -- silencio e a taxa de acordo sobe artificialmente (some `missing` do
                -- denominador), que e exatamente a metrica enganosa que este sprint
                -- existe para impedir. Reproduzido: 6 giros com `event_id` constante
                -- => counters 6, trilha 1.
                --
                -- A chave inclui `session_id` porque `spin_seq` REINICIA em cada
                -- sessao: sem ele, o giro 1 da sessao B colidiria com o giro 1 da
                -- sessao A sempre que o `event_id` se repetisse, e a linha da sessao
                -- nova seria suprimida. Suspensoes por conflito sao CONTADAS
                -- (`phase_events_write_error_total`), nunca silenciosas.
                --
                -- DUAS COORDENADAS, ambas CONSULTAVEIS (nao escondidas em meta_json):
                --   `session_id`/`target_spin_seq` = coordenadas do EVENTO — o slot do
                --     ciclo de vida. E por elas que um terminal fecha o seu `received`.
                --   `spin_session_id`/`spin_seq`   = coordenadas do GIRO que decidiu.
                --     NULL em linhas que NAO sao disposicao de giro (`received`,
                --     supersede, invalidacao por `nova_sessao`, faxina de orfao).
                -- Invariante consultavel: `spin_seq IS NOT NULL` <=> a linha participa
                -- da particao dos GIROS ELEGIVEIS (denominador da cobertura).
                -- A chave de ciclo de vida vive num INDICE UNICO EXPLICITO (e nao
                -- num `UNIQUE` de tabela) de proposito: indice e ADITIVO — um banco
                -- criado por um commit intermediario deste PR ganha a chave certa no
                -- proximo boot, sem DROP/rebuild. Um `UNIQUE` de tabela so mudaria
                -- recriando a tabela, e `ON CONFLICT(...)` exige um indice unico que
                -- CASE exatamente com as colunas — sem ele, TODO insert da trilha
                -- estoura com OperationalError e a auditoria morre inteira.
                CREATE TABLE IF NOT EXISTS phase_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    ts_srv_ms INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    round_id TEXT,
                    target_spin_seq INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_direction TEXT,
                    reference_direction TEXT,
                    confidence REAL,
                    decision_ref TEXT,
                    spin_session_id TEXT,
                    spin_seq INTEGER,
                    meta_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS ix_phase_events_session_spin
                    ON phase_events(session_id, target_spin_seq);
            """)
            conn.commit()
            
            # Auto-migration: add sda_centers column for existing databases
            try:
                conn.execute("SELECT sda_centers FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN sda_centers TEXT")
                conn.execute("UPDATE decisions SET sda_centers = json_array(sda_center) WHERE sda_centers IS NULL")
                conn.commit()
                logger.info("Migration: added sda_centers column to decisions")
            
            # Auto-migration: add total_resets column for Smart Gale v4
            try:
                conn.execute("SELECT total_resets FROM sessions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE sessions ADD COLUMN total_resets INTEGER DEFAULT 0")
                conn.commit()
                logger.info("Migration: added total_resets column to sessions")
            
            # Auto-migration: add sda_offset and sda_offset_type for M15-ADA v4.0.3
            try:
                conn.execute("SELECT sda_offset FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN sda_offset INTEGER DEFAULT 0")
                conn.execute("ALTER TABLE decisions ADD COLUMN sda_offset_type TEXT DEFAULT ''")
                conn.commit()
                logger.info("Migration: added sda_offset, sda_offset_type columns to decisions")

            # SP-16 (REGION-01): coluna sda_regions JSON para guardar
            # [{c, offset, score, ...}] por regiao C1/C2/C3. Permite SP-17
            # calcular realized_lift_pp por regiao.
            try:
                conn.execute("SELECT sda_regions FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN sda_regions TEXT")
                conn.commit()
                logger.info("Migration SP-16: added sda_regions column to decisions")

            # SP-13 DEAL-03 (27/05): colunas dealer/table/provider/round_id.
            try:
                conn.execute("SELECT dealer FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN dealer TEXT DEFAULT 'unknown'")
                conn.execute("ALTER TABLE decisions ADD COLUMN dealer_table TEXT")
                conn.execute("ALTER TABLE decisions ADD COLUMN provider TEXT")
                conn.execute("ALTER TABLE decisions ADD COLUMN round_id TEXT")
                conn.execute("CREATE INDEX IF NOT EXISTS ix_decisions_dealer ON decisions(dealer)")
                conn.commit()
                logger.info("Migration SP-13: added dealer/dealer_table/provider/round_id to decisions")

            # B2+B5 (12/06): result_region = slot onde o resultado caiu
            # (C1/C2/C3/miss — pergunta P5 do owner); pnl_units = P&L real
            # da decisão (PROFIT-LEDGER — sistema nunca tinha medido lucro).
            try:
                conn.execute("SELECT result_region FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN result_region TEXT")
                conn.execute("ALTER TABLE decisions ADD COLUMN pnl_units REAL")
                conn.commit()
                logger.info("Migration B2/B5 12/06: added result_region, pnl_units to decisions")

            # Vision (foto_roleta_junho.md Parte 4): wheel_model/vision_confidence/
            # vision_source — foto->dados. Aditivo idempotente (mesmo padrao SP-13).
            try:
                conn.execute("SELECT wheel_model FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN wheel_model TEXT DEFAULT ''")
                conn.execute("ALTER TABLE decisions ADD COLUMN vision_confidence REAL DEFAULT 0.0")
                conn.execute("ALTER TABLE decisions ADD COLUMN vision_source TEXT DEFAULT ''")
                conn.execute("CREATE INDEX IF NOT EXISTS ix_decisions_wheel_model ON decisions(wheel_model)")
                conn.commit()
                logger.info("Migration Vision (foto_roleta): added wheel_model/vision_confidence/vision_source to decisions")

            # DIR3 (sentido-fase): contador de fase + origem/confiança do sentido +
            # próxima fase + flag de ambiguidade. Aditivo idempotente (padrão SP-13).
            try:
                conn.execute("SELECT spin_seq FROM decisions LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE decisions ADD COLUMN spin_seq INTEGER")
                conn.execute("ALTER TABLE decisions ADD COLUMN direction_source TEXT")
                conn.execute("ALTER TABLE decisions ADD COLUMN direction_confidence REAL")
                conn.execute("ALTER TABLE decisions ADD COLUMN direction_next TEXT")
                conn.execute("ALTER TABLE decisions ADD COLUMN phase_uncertain BOOLEAN")
                conn.commit()
                logger.info("Migration DIR3 (sentido-fase): added spin_seq/direction_source/direction_confidence/direction_next/phase_uncertain to decisions")

            # ISO-S6 (Sprint B-03 reescopado 26/05): gale_windows.result enum.
            # Enum oficial observado em prod: 'streak', 'reset', 'info'.
            # (1) Backfill defensivo: qualquer NULL legado vira 'info' (neutro).
            # (2) Indice parcial para queries de filtro por enum.
            # NOTA: SQLite nao suporta ALTER TABLE ADD CONSTRAINT — CHECK seria
            # exigido em CREATE TABLE; usamos backfill + indice como salvaguarda
            # mais migrar PG (futuro NEW-10) com CHECK real.
            try:
                conn.execute(
                    "UPDATE gale_windows SET result='info' "
                    "WHERE result IS NULL AND ended_at IS NOT NULL"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_gale_windows_result "
                    "ON gale_windows(result)"
                )
                conn.commit()
            except sqlite3.OperationalError as _e:
                logger.warning(f"Migration ISO-S6 (gale_windows.result) skipped: {_e}")

            # SPR-V4: coordenadas do GIRO como colunas consultaveis. Aditivo
            # idempotente (padrao SP-13). `phase_events` nasce neste sprint, entao
            # este caminho so encontra bancos criados por um commit intermediario
            # do PROPRIO PR — nunca um banco de producao.
            try:
                conn.execute("SELECT spin_seq FROM phase_events LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    conn.execute("ALTER TABLE phase_events ADD COLUMN spin_session_id TEXT")
                    conn.execute("ALTER TABLE phase_events ADD COLUMN spin_seq INTEGER")
                    conn.commit()
                    logger.info("Migration SPR-V4: added spin_session_id/spin_seq to phase_events")
                except sqlite3.OperationalError as _e:
                    logger.warning(f"Migration SPR-V4 (phase_events spin coords) skipped: {_e}")

            # SPR-V4: a identidade do ciclo de vida PRECISA incluir `session_id`
            # (`spin_seq` reinicia a cada sessao). Criada como INDICE UNICO — e o
            # alvo do `ON CONFLICT` do insert da trilha e, por ser indice, e ADITIVA:
            # um banco criado por um commit intermediario deste PR ganha a chave
            # certa aqui, sem DROP/rebuild. Sem este indice, TODO insert da trilha
            # estouraria com "ON CONFLICT clause does not match any PRIMARY KEY or
            # UNIQUE constraint" e a auditoria ficaria 100% morta.
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_phase_events_lifecycle "
                    "ON phase_events(session_id, event_id, kind, target_spin_seq)"
                )
                conn.commit()
            except sqlite3.OperationalError as _e:
                logger.error(
                    "phase_events: falha ao criar ux_phase_events_lifecycle (%s) — "
                    "os inserts da trilha vao falhar ate isto ser resolvido", _e,
                )

            # Um banco criado pelo commit intermediario ainda carrega o UNIQUE de
            # TABELA antigo, que e ESTRITO DEMAIS (sem `session_id`): a linha da
            # sessao nova colide com a da anterior sempre que o `event_id` se repetir.
            # Remover um UNIQUE de tabela exige recriar a tabela (DROP), proibido
            # pelos invioaveis — e nenhum banco de PRODUCAO tem a forma antiga
            # (`phase_events` nasce neste PR). Avisa ALTO e segue.
            try:
                _ddl = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='phase_events'"
                ).fetchone()
                if _ddl and "UNIQUE(" in (_ddl[0] or ""):
                    logger.error(
                        "phase_events com UNIQUE de TABELA legado (sem session_id): "
                        "linhas de uma sessao nova podem ser rejeitadas quando o "
                        "event_id se repete. Banco criado por um commit intermediario "
                        "do SPR-V4 — APAGUE o .db de desenvolvimento para recria-lo."
                    )
            except sqlite3.Error as _e:
                logger.warning(f"Checagem do UNIQUE de phase_events falhou: {_e}")
    
    # SPR-V4: SQL + params da decisão extraídos para constante/helper porque agora
    # existem DOIS caminhos de escrita (`save_decision` e o atômico
    # `save_decision_with_phase_events`). Duplicar 43 colunas garantiria divergência
    # silenciosa entre os dois no primeiro campo novo.
    _DECISION_INSERT_SQL = """
                INSERT INTO decisions (
                    timestamp, session_id,
                    spin_number, spin_direction, spin_force,
                    tr_should_bet, tr_confidence, tr_reason,
                    tr_c4_rate, tr_m6_rate, tr_l12_rate,
                    sda_should_bet, sda_score, sda_center, sda_centers,
                    sda_numbers, sda_predicted_force,
                    sda_offset, sda_offset_type, sda_regions,
                    final_action, action_reason,
                    gale_level, gale_window_hits, gale_window_count, gale_bet_value,
                    result_hit, result_actual,
                    calibration_offset, calibration_error,
                    performance_snapshot,
                    dealer, dealer_table, provider, round_id,
                    wheel_model, vision_confidence, vision_source,
                    spin_seq, direction_source, direction_confidence, direction_next, phase_uncertain
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

    @staticmethod
    def _decision_params(decision: Decision) -> tuple:
        """Parâmetros posicionais de `_DECISION_INSERT_SQL` (fonte única)."""
        return (
            decision.timestamp.isoformat(),
            decision.session_id,
            decision.spin_number,
            decision.spin_direction,
            decision.spin_force,
            decision.tr_should_bet,
            decision.tr_confidence,
            decision.tr_reason,
            decision.tr_c4_rate,
            decision.tr_m6_rate,
            decision.tr_l12_rate,
            decision.sda_should_bet,
            decision.sda_score,
            decision.sda_center,
            json.dumps(decision.sda_centers) if decision.sda_centers else json.dumps([decision.sda_center]),
            json.dumps(decision.sda_numbers),
            decision.sda_predicted_force,
            decision.sda_offset,
            decision.sda_offset_type,
            json.dumps(decision.sda_regions) if getattr(decision, "sda_regions", None) else None,
            decision.final_action,
            decision.action_reason,
            decision.gale_level,
            decision.gale_window_hits,
            decision.gale_window_count,
            decision.gale_bet_value,
            decision.result_hit,
            decision.result_actual,
            decision.calibration_offset,
            decision.calibration_error,
            json.dumps(decision.performance_snapshot),
            getattr(decision, "dealer", "unknown") or "unknown",
            getattr(decision, "dealer_table", "") or "",
            getattr(decision, "provider", "") or "",
            getattr(decision, "round_id", "") or "",
            getattr(decision, "wheel_model", "") or "",
            float(getattr(decision, "vision_confidence", 0.0) or 0.0),
            getattr(decision, "vision_source", "") or "",
            int(getattr(decision, "spin_seq", 0) or 0),
            getattr(decision, "direction_source", "") or "",
            float(getattr(decision, "direction_confidence", 0.0) or 0.0),
            getattr(decision, "direction_next", "") or "",
            bool(getattr(decision, "phase_uncertain", False)),
        )

    @staticmethod
    def _publish_decision_outbox(decision: Decision, decision_id: int) -> None:
        """S5 dual-write pós-commit (best-effort, nunca quebra a escrita SQLite)."""
        try:
            from database.outbox_integration import maybe_publish_decision_features
            maybe_publish_decision_features(decision, decision_id)
        except Exception as exc:  # noqa: BLE001 — never break SQLite write
            # H-1 fix (v4 §XIX): bloco mantido apenas como guard rail.
            # maybe_publish_decision_features tem try/except interno e NUNCA
            # deve levantar. Se levantar é bug grave — logar ERROR.
            logger.error(
                "dual_write_hook_unexpected_raise decision_id=%s err=%s",
                decision_id, exc,
            )

    def save_decision(self, decision: Decision) -> int:
        """Salva uma nova decisão."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                self._DECISION_INSERT_SQL, self._decision_params(decision)
            )
            conn.commit()
            decision_id = cursor.lastrowid
            # S5 dual-write: publica features no outbox PG se feature flag estiver on.
            # Defensivo: nunca quebra o app se PG offline.
            self._publish_decision_outbox(decision, decision_id)
            return decision_id
        finally:
            conn.close()

    # ========================================================================
    # SPR-V4 — trilha `phase_events` (append-only, shadow-only)
    # ========================================================================

    #: `kind`s que ENCERRAM o ciclo de vida de um evento. `received` e `bound` são
    #: transições intermediárias: um `received` sem nenhum destes é um evento
    #: PENDENTE. Depois de um restart ele é `stale` por definição, porque
    #: `time.monotonic()` não sobrevive ao processo.
    TERMINAL_PHASE_EVENT_KINDS = (
        "agree", "disagree", "stale", "unbound", "missing", "selfcontradict",
    )

    #: `ON CONFLICT ... DO NOTHING` e NÃO `INSERT OR IGNORE`: o `OR IGNORE` engoliria
    #: também violações de NOT NULL/CHECK, e uma linha inválida da trilha sairia
    #: silenciosamente da transação atômica — a decisão comitaria sem disposição e o
    #: teste de rollback total passaria por engano. Ainda assim, TODA supressão por
    #: conflito é devolvida ao caller (ver `_insert_phase_event_row`): evidência que
    #: não foi gravada precisa aparecer numa métrica, nunca sumir.
    _PHASE_EVENT_INSERT_SQL = """
                INSERT INTO phase_events (
                    event_id, ts_srv_ms, session_id, round_id, target_spin_seq,
                    kind, source, observed_direction, reference_direction,
                    confidence, decision_ref, spin_session_id, spin_seq, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, event_id, kind, target_spin_seq) DO NOTHING
            """

    @staticmethod
    def _phase_event_params(row: Dict[str, Any], decision_ref: Optional[str] = None) -> tuple:
        """Parâmetros da linha da trilha. NÃO aplica defaults às colunas NOT NULL:
        uma linha malformada TEM de estourar dentro da transação (é o que garante o
        rollback total), em vez de virar `''`/`0` e poluir a evidência."""
        _meta = row.get("meta_json")
        if not isinstance(_meta, str):
            _meta = json.dumps(_meta or {}, ensure_ascii=False, sort_keys=True)
        return (
            row.get("event_id"),
            row.get("ts_srv_ms"),
            row.get("session_id"),
            row.get("round_id"),
            row.get("target_spin_seq"),
            row.get("kind"),
            row.get("source"),
            row.get("observed_direction"),
            row.get("reference_direction"),
            row.get("confidence"),
            (decision_ref if decision_ref is not None else row.get("decision_ref")),
            row.get("spin_session_id"),
            row.get("spin_seq"),
            _meta,
        )

    def _insert_phase_event_row(self, conn: sqlite3.Connection, row: Dict[str, Any],
                                decision_ref: Optional[str] = None) -> bool:
        """Insere UMA linha da trilha na conexão dada (sem commit).

        Devolve `True` se a linha ENTROU e `False` se foi suprimida pelo
        `ON CONFLICT`. O caller precisa dessa distinção: linha suprimida é
        evidência que não existe, e evidência ausente sem métrica é pior que
        evidência ausente com métrica.

        Ponto de costura único: é aqui que os testes injetam falha para provar o
        rollback total da transação decisão+disposição.
        """
        cur = conn.execute(self._PHASE_EVENT_INSERT_SQL,
                           self._phase_event_params(row, decision_ref))
        return cur.rowcount > 0

    @staticmethod
    def _log_suppressed(rows: List[Dict[str, Any]]) -> None:
        for r in rows:
            logger.warning(
                "phase_events linha SUPRIMIDA por conflito "
                "(event_id=%s kind=%s target_spin_seq=%s) — evidencia nao gravada",
                r.get("event_id"), r.get("kind"), r.get("target_spin_seq"),
            )

    def insert_phase_events(self, rows: List[Dict[str, Any]]) -> int:
        """Grava linhas da trilha FORA do ciclo de uma decisão (ingresso `received`,
        invalidação por `nova_sessao`, evento superseded).

        Retorna quantas linhas ENTRARAM de fato (≠ len(rows) quando houve conflito).
        Levanta em falha — quem chama conta a métrica.
        """
        if not rows:
            return 0
        conn = self._get_connection()
        try:
            inserted = 0
            suprimidas = []
            for row in rows:
                if self._insert_phase_event_row(conn, row):
                    inserted += 1
                else:
                    suprimidas.append(row)
            conn.commit()
            self._log_suppressed(suprimidas)
            return inserted
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.Error as _rb:
                logger.error("phase_events rollback falhou: %s", _rb)
            raise
        finally:
            conn.close()

    def save_decision_with_phase_events(self, decision: Decision,
                                        rows: List[Dict[str, Any]],
                                        on_suppressed=None) -> int:
        """SPR-V4: grava decisão do giro + disposição terminal na MESMA transação.

        Sem isto existe decisão sem disposição e a trilha deixa de ser prova para o
        gate T4. Não há alternativa "justificada": `save_decision()` abre a própria
        conexão e comita sozinho, então a única forma de amarrar os dois writes é
        esta operação explícita.

        `on_suppressed(rows)` é chamado APÓS o commit com as linhas que o
        `ON CONFLICT` descartou (retry legítimo, ou colisão de id) — uma supressão
        silenciosa recriaria, por outro caminho, a "decisão sem disposição" que a
        atomicidade existe para impedir.

        Contrato de erro (o caller depende dele para não duplicar a decisão):
          * `PhaseTrailRolledBack`   — falhou ANTES do commit ⇒ NADA foi gravado.
          * `PhaseTrailCommitAmbiguous` — o próprio `commit()` levantou ⇒ não se
            pode afirmar se gravou; re-tentar duplicaria a decisão.
          * qualquer OUTRA exceção só pode vir DEPOIS do commit (hook do outbox,
            `close()`), e por isso também nunca autoriza retry.
        """
        conn = self._get_connection()
        committed = False
        suprimidas: List[Dict[str, Any]] = []
        try:
            try:
                cursor = conn.execute(
                    self._DECISION_INSERT_SQL, self._decision_params(decision)
                )
                decision_id = cursor.lastrowid
                for row in rows or []:
                    if not self._insert_phase_event_row(conn, row, str(decision_id)):
                        suprimidas.append(row)
            except BaseException as exc:
                try:
                    conn.rollback()
                except sqlite3.Error as _rb:
                    logger.error("rollback da transacao decisao+trilha falhou: %s", _rb)
                raise PhaseTrailRolledBack(
                    f"decisao+trilha revertidas ({type(exc).__name__}: {exc})"
                ) from exc
            try:
                conn.commit()
                committed = True
            except BaseException as exc:
                raise PhaseTrailCommitAmbiguous(
                    f"commit da transacao decisao+trilha indeterminado "
                    f"({type(exc).__name__}: {exc})"
                ) from exc
            if suprimidas:
                self._log_suppressed(suprimidas)
                if on_suppressed is not None:
                    on_suppressed(suprimidas)
            # Só depois do commit — um rollback jamais pode publicar no outbox.
            self._publish_decision_outbox(decision, decision_id)
            return decision_id
        finally:
            if not committed:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    logger.error("rollback defensivo da trilha falhou", exc_info=True)
            conn.close()

    def get_pending_phase_events(self, session_id: Optional[str] = None,
                                 limit: int = 20,
                                 scan: int = 200) -> List[Dict[str, Any]]:
        """Linhas `received` SEM disposição terminal (eventos com o ciclo em aberto).

        **A correlação é `(session_id, event_id, target_spin_seq)` — exatamente a
        identidade do `UNIQUE` do DDL.** Fechar por `event_id` sozinho era o BUG-2:
        com um produtor reutilizando um id estável, o terminal do giro N mascarava o
        `received` do giro N+1 (ou de outra sessão), que aparecia como já encerrado.

        Trabalho LIMITADO por construção (isto pode ser chamado no caminho do giro):
        varre no máximo os `scan` `received` mais recentes (varredura pelo índice da
        PK, independente do tamanho da tabela) e devolve no máximo `limit`.
        """
        _kinds = self.TERMINAL_PHASE_EVENT_KINDS
        _placeholders = ",".join("?" for _ in _kinds)
        conn = self._get_connection()
        try:
            cur = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT * FROM phase_events
                     WHERE kind = 'received'
                       AND (? IS NULL OR session_id = ?)
                     ORDER BY id DESC LIMIT ?
                ) pe
                 WHERE NOT EXISTS (
                       SELECT 1 FROM phase_events t
                        WHERE t.event_id = pe.event_id
                          AND t.session_id = pe.session_id
                          AND t.target_spin_seq = pe.target_spin_seq
                          AND t.kind IN ({_placeholders})
                   )
                 ORDER BY pe.id DESC LIMIT ?
                """,
                (session_id, session_id, int(scan), *_kinds, int(limit)),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_pending_phase_event(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Último `received` sem disposição terminal (ou `None`)."""
        rows = self.get_pending_phase_events(session_id=session_id, limit=1)
        return rows[0] if rows else None

    def count_phase_events_by_kind(self, session_id: Optional[str] = None) -> Dict[str, int]:
        """Agregado por `kind` (auditoria/gate T4).

        O filtro por sessão usa `COALESCE(spin_session_id, session_id)`: uma
        disposição pertence à sessão do GIRO que a decidiu (é ela que particiona os
        giros elegíveis), enquanto `received`/manutenção — que não têm giro —
        pertencem à sessão do EVENTO.
        """
        conn = self._get_connection()
        try:
            if session_id:
                cur = conn.execute(
                    "SELECT kind, COUNT(*) AS n FROM phase_events "
                    "WHERE COALESCE(spin_session_id, session_id) = ? GROUP BY kind",
                    (session_id,))
            else:
                cur = conn.execute(
                    "SELECT kind, COUNT(*) AS n FROM phase_events GROUP BY kind")
            return {r["kind"]: int(r["n"]) for r in cur.fetchall()}
        finally:
            conn.close()

    
    def update_result(self, decision_id: int, hit: bool, actual_number: int,
                       calibration_error: Optional[int] = None,
                       result_region: Optional[str] = None) -> None:
        """Atualiza o resultado de uma decisão.

        Args:
            decision_id: id da decisão a atualizar.
            hit: True se o número apostado bateu na vizinhança prevista.
            actual_number: número sorteado (0-36).
            calibration_error: distância em casas da roda entre o centro
                previsto e o número real (sprint W-02 + B-08 — 26/05/2026).
                Quando None, a coluna não é atualizada para preservar valor
                histórico (ex.: backfill).
            result_region: B2 (12/06) — slot onde o resultado caiu
                ('C1'/'C2'/'C3'/'miss'). None preserva valor existente.

        B5 PROFIT-LEDGER (12/06): calcula pnl_units da decisão (stake total
        gale_bet_value distribuído pelos N números, payout 36:1) e agrega em
        sessions.total_profit — coluna que existia desde janeiro e NUNCA
        tinha sido escrita (0.0 em 151/151 sessões).
        """
        conn = self._get_connection()
        try:
            sets = ["result_hit = ?", "result_actual = ?"]
            params: list = [hit, actual_number]
            if calibration_error is not None:
                sets.append("calibration_error = ?")
                params.append(int(calibration_error))
            if result_region is not None:
                sets.append("result_region = ?")
                params.append(str(result_region))

            # B5: P&L exato — aposta de gale_bet_value distribuída por N
            # números; hit paga 36× a fração do número; miss perde tudo.
            pnl: Optional[float] = None
            session_id: Optional[str] = None
            try:
                row = conn.execute(
                    "SELECT final_action, sda_numbers, gale_bet_value, session_id "
                    "FROM decisions WHERE id = ?",
                    (decision_id,),
                ).fetchone()
                if row:
                    final_action, sda_numbers_json, bet_value, session_id = row
                    if (final_action or "") == "APOSTAR" and bet_value:
                        try:
                            n_numbers = len(json.loads(sda_numbers_json or "[]"))
                        except (ValueError, TypeError):
                            n_numbers = 0
                        if n_numbers > 0:
                            stake = float(bet_value)
                            pnl = round(
                                stake * (36.0 / n_numbers - 1.0) if hit else -stake,
                                4,
                            )
            except sqlite3.OperationalError as _pnl_e:
                logger.warning(f"pnl_units skipped (schema?): {_pnl_e}")

            if pnl is not None:
                sets.append("pnl_units = ?")
                params.append(pnl)

            params.append(decision_id)
            conn.execute(
                f"UPDATE decisions SET {', '.join(sets)} WHERE id = ?", params
            )
            if pnl is not None and session_id:
                conn.execute(
                    "UPDATE sessions SET total_profit = COALESCE(total_profit, 0) + ? "
                    "WHERE id = ?",
                    (pnl, session_id),
                )
            conn.commit()
        finally:
            conn.close()

    def update_last_vision(self, *, dealer: Optional[str] = None,
                           wheel_model: Optional[str] = None,
                           provider: Optional[str] = None,
                           confidence: Optional[float] = None,
                           source: str = "vision") -> int:
        """Vision (foto_roleta): grava o resultado do OCR na decisão MAIS RECENTE.
        Só escreve campos não-vazios (não sobrescreve com branco) e NÃO toca o
        caminho de aposta. Retorna o decision_id atualizado, ou 0 se não houver
        decisão. O foto_frame chega logo após o novo_resultado, então a última
        decisão (MAX id) é a do giro corrente."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT id, timestamp FROM decisions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row or row[0] is None:
                return 0
            decision_id = int(row[0])
            # Hardening (auditoria_pos_foto 21/06 §7.4): janela máxima opcional p/
            # a foto colar na última decisão. Se SDA_VISION_ATTACH_MAX_AGE_S>0 e a
            # decisão é mais velha que isso, NÃO sobrescreve (evita contaminar o
            # giro seguinte quando o OCR atrasa). Default 0 = sem limite (byte-
            # idêntico ao comportamento anterior). Defensivo: nunca derruba o fluxo.
            try:
                from app_config.settings import vision_attach_max_age_s
                max_age = vision_attach_max_age_s()
                if max_age > 0 and row[1] is not None:
                    age_row = conn.execute(
                        "SELECT (julianday('now') - julianday(?)) * 86400.0",
                        (row[1],),
                    ).fetchone()
                    if age_row and age_row[0] is not None and float(age_row[0]) > max_age:
                        return 0
            except Exception:
                pass
            sets: list = []
            params: list = []
            if dealer:
                sets.append("dealer = ?")
                params.append(str(dealer)[:120])
            if wheel_model:
                sets.append("wheel_model = ?")
                params.append(str(wheel_model)[:80])
                # Mesa (auditoria 22/06): a mesa vem da FOTO. dealer_table espelha
                # o modelo/jogo do OCR (o DOM trazia mesa errada). Assim a foto
                # também carimba a mesa na decisão mais recente.
                sets.append("dealer_table = ?")
                params.append(str(wheel_model)[:80])
            if provider:
                sets.append("provider = ?")
                params.append(str(provider)[:40])
            if confidence is not None:
                sets.append("vision_confidence = ?")
                params.append(float(confidence))
            if source:
                sets.append("vision_source = ?")
                params.append(str(source)[:20])
            if not sets:
                return 0
            params.append(decision_id)
            conn.execute(
                f"UPDATE decisions SET {', '.join(sets)} WHERE id = ?", params
            )
            conn.commit()
            return decision_id
        finally:
            conn.close()

    def get_session_pnl(self, session_id: str) -> float:
        """B5: P&L acumulado de uma sessão (para stop-loss)."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT COALESCE(total_profit, 0) FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            return float(row[0]) if row else 0.0
        finally:
            conn.close()

    def session_pnl_stats(self) -> dict:
        """B5: snapshot de P&L para o gauge Prometheus roleta_session_pnl.

        Returns:
            dict: current_session_id, current_session_pnl, all_time_pnl.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT id, COALESCE(total_profit, 0) FROM sessions "
                "ORDER BY start_time DESC LIMIT 1"
            ).fetchone()
            try:
                total = conn.execute(
                    "SELECT COALESCE(SUM(pnl_units), 0) FROM decisions"
                ).fetchone()
                all_time = float(total[0]) if total else 0.0
            except sqlite3.OperationalError:
                all_time = 0.0
            return {
                "current_session_id": row[0] if row else None,
                "current_session_pnl": float(row[1]) if row else 0.0,
                "all_time_pnl": all_time,
            }
        finally:
            conn.close()

    def wheel_dist_stats(self, window_minutes: int = 60) -> dict:
        """SP-30 OBS-02: percentis p50/p95/p99 de calibration_error na janela.

        calibration_error = wheel_dist (W-01/B-08). Mede saúde fina da
        previsão SDA17 — alvo p50 <= 3 slots; alerta em SP-31.

        Returns:
            dict {"n": int, "p50": float, "p95": float, "p99": float}.
            n=0 -> percentis 0.0 (alertas devem skipar quando n<30).
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"""
                SELECT calibration_error FROM decisions
                WHERE timestamp >= datetime('now', '-{int(window_minutes)} minutes')
                  AND calibration_error IS NOT NULL
                ORDER BY calibration_error ASC
                """
            ).fetchall()
            vals = [float(r[0]) for r in rows if r[0] is not None]
            n = len(vals)
            if n == 0:
                return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
            def _pct(p: float) -> float:
                # nearest-rank, conservador
                k = max(0, min(n - 1, int(round(p * (n - 1)))))
                return vals[k]
            return {
                "n": n,
                "p50": _pct(0.50),
                "p95": _pct(0.95),
                "p99": _pct(0.99),
            }
        except Exception:
            return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        finally:
            conn.close()

    def dealer_stats(self, limit: int = 50, window_minutes: int = 1440) -> list:
        """SP-14 DEAL-04 (27/05): ranking de dealers por hit_rate em janela.

        Retorna lista [{dealer, provider, n, hits, hit_rate}], ordenado
        por hit_rate desc, filtrando dealers com n >= 10 (estatistica fraca).
        Tolera ausencia da coluna dealer (deploy antes do SP-13).
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    f"""
                    SELECT
                      COALESCE(dealer, 'unknown') AS d,
                      COALESCE(provider, '')      AS p,
                      COUNT(*)                    AS n,
                      SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) AS hits
                    FROM decisions
                    WHERE final_action = 'APOSTAR'
                      AND result_actual IS NOT NULL
                      AND timestamp >= datetime('now', '-{int(window_minutes)} minutes')
                    GROUP BY d, p
                    HAVING n >= 10
                    ORDER BY (CAST(hits AS REAL)/n) DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                )
            except sqlite3.OperationalError:
                return []
            out = []
            for r in cur.fetchall():
                n = int(r["n"]) or 1
                hits = int(r["hits"] or 0)
                out.append(
                    {
                        "dealer": r["d"],
                        "provider": r["p"],
                        "n": n,
                        "hits": hits,
                        "hit_rate": round(hits / n, 4),
                    }
                )
            return out
        except Exception:
            return []
        finally:
            conn.close()

    def calibration_fill_stats(self, window_minutes: int = 60) -> dict:
        """NEW-12 (26/05): conta decisoes APOSTAR com result_actual e
        quantas dessas tem calibration_error NOT NULL na janela. Usado
        como provider Prometheus para alertar bugs silenciosos do tipo
        B-09 (pending key mismatch — fill rate cai a 0 silenciosamente).

        Returns:
            dict {"total": int, "filled": int}. total=0 quando nao ha
            spins recentes (alerta nao dispara — fill_rate default=1.0).
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(calibration_error) AS filled
                FROM decisions
                WHERE timestamp >= datetime('now', '-{int(window_minutes)} minutes')
                  AND result_actual IS NOT NULL
                  AND final_action = 'APOSTAR'
                """
            ).fetchone()
            if row is None:
                return {"total": 0, "filled": 0}
            return {"total": int(row[0] or 0), "filled": int(row[1] or 0)}
        except Exception:
            return {"total": 0, "filled": 0}
        finally:
            conn.close()

    def get_decision(self, decision_id: int) -> Optional[Decision]:
        """Busca uma decisão por ID."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM decisions WHERE id = ?",
                (decision_id,)
            ).fetchone()
            
            if row:
                return self._row_to_decision(row)
            return None
        finally:
            conn.close()
    
    def get_decisions(
        self,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        final_action: Optional[str] = None,
        limit: int = 100
    ) -> List[Decision]:
        """Busca decisões com filtros."""
        query = "SELECT * FROM decisions WHERE 1=1"
        params = []
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if final_action:
            query += " AND final_action = ?"
            params.append(final_action)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        conn = self._get_connection()
        try:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_decision(row) for row in rows]
        finally:
            conn.close()
    
    def get_last_decision_id(self, session_id: str) -> Optional[int]:
        """Retorna o ID da última decisão da sessão."""
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT id FROM decisions 
                WHERE session_id = ? AND final_action = 'APOSTAR'
                ORDER BY timestamp DESC LIMIT 1
            """, (session_id,)).fetchone()
            
            return row["id"] if row else None
        finally:
            conn.close()
    
    @staticmethod
    def _safe_json_loads(raw: str, default):
        """BUG-AUDIT-004 FIX: json.loads defensivo com fallback."""
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    def _row_to_decision(self, row: sqlite3.Row) -> Decision:
        """Converte row do SQLite para objeto Decision."""
        return Decision(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
            session_id=row["session_id"] or "",
            spin_number=row["spin_number"] or 0,
            spin_direction=row["spin_direction"] or "",
            spin_force=row["spin_force"] or 0,
            tr_should_bet=bool(row["tr_should_bet"]) if row["tr_should_bet"] is not None else True,
            tr_confidence=row["tr_confidence"] or "",
            tr_reason=row["tr_reason"] or "",
            tr_c4_rate=row["tr_c4_rate"] or 0.0,
            tr_m6_rate=row["tr_m6_rate"] or 0.0,
            tr_l12_rate=row["tr_l12_rate"] or 0.0,
            sda_should_bet=bool(row["sda_should_bet"]) if row["sda_should_bet"] is not None else True,
            sda_score=row["sda_score"] or 0,
            sda_center=row["sda_center"] or 0,
            sda_centers=self._safe_json_loads(row["sda_centers"], [row["sda_center"] or 0]),
            sda_numbers=self._safe_json_loads(row["sda_numbers"], []),
            sda_predicted_force=row["sda_predicted_force"] or 0,
            sda_offset=row["sda_offset"] if "sda_offset" in row.keys() else 0,
            sda_offset_type=row["sda_offset_type"] if "sda_offset_type" in row.keys() else "",
            sda_regions=self._safe_json_loads(row["sda_regions"], []) if "sda_regions" in row.keys() else [],
            final_action=row["final_action"] or "",
            action_reason=row["action_reason"] or "",
            gale_level=row["gale_level"] or 1,
            gale_window_hits=row["gale_window_hits"] or 0,
            gale_window_count=row["gale_window_count"] or 0,
            gale_bet_value=row["gale_bet_value"] or 17,
            result_hit=bool(row["result_hit"]) if row["result_hit"] is not None else None,
            result_actual=row["result_actual"],
            calibration_offset=row["calibration_offset"] or 0,
            calibration_error=row["calibration_error"],
            performance_snapshot=self._safe_json_loads(row["performance_snapshot"], []),
            # SP-13 DEAL-03 (defensivo: colunas podem nao existir em snapshots antigos)
            dealer=(row["dealer"] if "dealer" in row.keys() else "unknown") or "unknown",
            dealer_table=(row["dealer_table"] if "dealer_table" in row.keys() else "") or "",
            provider=(row["provider"] if "provider" in row.keys() else "") or "",
            round_id=(row["round_id"] if "round_id" in row.keys() else "") or "",
            # Vision (foto_roleta Parte 4, defensivo: colunas podem nao existir em snapshots antigos)
            wheel_model=(row["wheel_model"] if "wheel_model" in row.keys() else "") or "",
            vision_confidence=(row["vision_confidence"] if "vision_confidence" in row.keys() else 0.0) or 0.0,
            vision_source=(row["vision_source"] if "vision_source" in row.keys() else "") or "",
            # DIR3 (sentido-fase, defensivo: colunas podem nao existir em snapshots antigos)
            spin_seq=(row["spin_seq"] if "spin_seq" in row.keys() else 0) or 0,
            direction_source=(row["direction_source"] if "direction_source" in row.keys() else "") or "",
            direction_confidence=(row["direction_confidence"] if "direction_confidence" in row.keys() else 0.0) or 0.0,
            direction_next=(row["direction_next"] if "direction_next" in row.keys() else "") or "",
            phase_uncertain=bool(row["phase_uncertain"]) if ("phase_uncertain" in row.keys() and row["phase_uncertain"] is not None) else False,
        )
    
    # =========================================================================
    # CRUD de Sessões
    # =========================================================================
    
    def create_session(self, session: Session) -> str:
        """Cria uma nova sessão."""
        conn = self._get_connection()
        try:
            # BUG-FK-1 fix: idempotente para evitar FK constraint quando
            # message_handler recria session_id após restart sem REGISTER novo
            conn.execute("""
                INSERT OR IGNORE INTO sessions (id, start_time)
                VALUES (?, ?)
            """, (session.id, session.start_time.isoformat()))
            conn.commit()
            return session.id
        finally:
            conn.close()
    
    def update_session(self, session: Session) -> None:
        """Atualiza estatísticas da sessão."""
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE sessions SET
                    total_spins = ?,
                    total_bets = ?,
                    total_hits = ?,
                    total_profit = ?,
                    max_gale_reached = ?,
                    total_stops = ?,
                    total_resets = ?
                WHERE id = ?
            """, (
                session.total_spins,
                session.total_bets,
                session.total_hits,
                session.total_profit,
                session.max_gale_reached,
                session.total_stops,
                session.total_resets,
                session.id
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Busca sessão por ID."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
            
            if row:
                return Session(
                    id=row["id"],
                    start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
                    end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
                    total_spins=row["total_spins"] or 0,
                    total_bets=row["total_bets"] or 0,
                    total_hits=row["total_hits"] or 0,
                    total_profit=row["total_profit"] or 0.0,
                    max_gale_reached=row["max_gale_reached"] or 1,
                    total_stops=row["total_stops"] or 0,
                    total_resets=row["total_resets"] or 0 if "total_resets" in row.keys() else 0
                )
            return None
        finally:
            conn.close()
    
    def end_session(self, session_id: str) -> None:
        """Marca sessão como finalizada."""
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE sessions SET end_time = ?
                WHERE id = ?
            """, (datetime.now(_tz.utc).replace(tzinfo=None).isoformat(), session_id))
            conn.commit()
        finally:
            conn.close()
    
    # =========================================================================
    # Analytics
    # =========================================================================
    
    def get_stats(
        self,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Retorna estatísticas agregadas."""
        query = """
            SELECT 
                COUNT(*) as total_decisions,
                SUM(CASE WHEN final_action = 'APOSTAR' THEN 1 ELSE 0 END) as total_bets,
                SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) as total_hits,
                AVG(CASE WHEN final_action = 'APOSTAR' AND result_hit IS NOT NULL 
                    THEN CAST(result_hit AS REAL) ELSE NULL END) as hit_rate
            FROM decisions WHERE 1=1
        """
        params = []
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        conn = self._get_connection()
        try:
            row = conn.execute(query, params).fetchone()
            
            return {
                "total_decisions": row["total_decisions"] or 0,
                "total_bets": row["total_bets"] or 0,
                "total_hits": row["total_hits"] or 0,
                "hit_rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0
            }
        finally:
            conn.close()
    
    def get_gale_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Retorna estatísticas por nível de gale."""
        query = """
            SELECT 
                gale_level,
                COUNT(*) as total,
                SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) as hits,
                AVG(CASE WHEN result_hit IS NOT NULL 
                    THEN CAST(result_hit AS REAL) ELSE NULL END) as hit_rate
            FROM decisions 
            WHERE final_action = 'APOSTAR'
        """
        params = []
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        query += " GROUP BY gale_level ORDER BY gale_level"
        
        conn = self._get_connection()
        try:
            rows = conn.execute(query, params).fetchall()
            
            return {
                f"gale_{row['gale_level']}": {
                    "total": row["total"],
                    "hits": row["hits"] or 0,
                    "rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0
                }
                for row in rows
            }
        finally:
            conn.close()
    
    def get_triple_rate_analysis(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Analisa eficácia do Triple Rate Advisor."""
        base_query = "FROM decisions WHERE 1=1"
        params = []
        
        if session_id:
            base_query += " AND session_id = ?"
            params.append(session_id)
        
        conn = self._get_connection()
        try:
            # Vezes que Triple Rate recomendou pular
            skipped = conn.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) as would_have_hit
                {base_query} AND tr_should_bet = 0 AND sda_should_bet = 1
            """, params).fetchone()
            
            # Eficácia por nível de confiança
            by_confidence = conn.execute(f"""
                SELECT 
                    tr_confidence,
                    COUNT(*) as total,
                    SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) as hits
                {base_query} AND final_action = 'APOSTAR'
                GROUP BY tr_confidence
            """, params).fetchall()
            
            return {
                "vetoed_by_triple_rate": {
                    "total": skipped["total"] or 0,
                    "would_have_hit": skipped["would_have_hit"] or 0
                },
                "by_confidence": {
                    row["tr_confidence"]: {
                        "total": row["total"],
                        "hits": row["hits"] or 0,
                        "rate": round((row["hits"] or 0) / row["total"] * 100, 1) if row["total"] else 0
                    }
                    for row in by_confidence
                }
            }
        finally:
            conn.close()
    
    # =========================================================================
    # CRUD de Gale Windows (ML-Ready)
    # =========================================================================
    
    def create_gale_window(self, window: "GaleWindow") -> int:
        """Cria uma nova janela de gale."""
        from .models import GaleWindow
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                INSERT INTO gale_windows (
                    direction, gale_level, started_at,
                    sda17_rate_at_start, bet_rate_at_start, calibration_offset
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                window.direction,
                window.gale_level,
                window.started_at.isoformat(),
                window.sda17_rate_at_start,
                window.bet_rate_at_start,
                window.calibration_offset
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def add_window_play(self, play: "WindowPlay") -> int:
        """Adiciona uma jogada a uma janela com transação atômica."""
        from .models import WindowPlay
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                INSERT INTO window_plays (
                    window_id, play_number, timestamp,
                    spin_number, spin_direction, spin_force, center_predicted,
                    hit, actual_number, sda_score, tr_confidence, tr_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                play.window_id,
                play.play_number,
                play.timestamp.isoformat(),
                play.spin_number,
                play.spin_direction,
                play.spin_force,
                play.center_predicted,
                play.hit,
                play.actual_number,
                play.sda_score,
                play.tr_confidence,
                play.tr_reason
            ))
            
            conn.execute("""
                UPDATE gale_windows 
                SET total_plays = total_plays + 1,
                    total_hits = total_hits + ?
                WHERE id = ?
            """, (1 if play.hit else 0, play.window_id))
            
            conn.commit()
            return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def close_gale_window(self, window_id: int, result: str, next_level: int) -> None:
        """Fecha uma janela de gale com resultado."""
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE gale_windows 
                SET ended_at = ?, result = ?, next_level = ?
                WHERE id = ?
            """, (datetime.now(_tz.utc).replace(tzinfo=None).isoformat(), result, next_level, window_id))
            conn.commit()
        finally:
            conn.close()
    
    def get_active_window(self, direction: str) -> Optional["GaleWindow"]:
        """Retorna janela ativa (não fechada) para uma direção."""
        from .models import GaleWindow
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT * FROM gale_windows 
                WHERE direction = ? AND ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1
            """, (direction,)).fetchone()
            
            if row:
                return GaleWindow(
                    id=row["id"],
                    direction=row["direction"],
                    gale_level=row["gale_level"],
                    started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                    total_hits=row["total_hits"] or 0,
                    total_plays=row["total_plays"] or 0,
                    sda17_rate_at_start=row["sda17_rate_at_start"] or 0.0,
                    bet_rate_at_start=row["bet_rate_at_start"] or 0.0,
                    calibration_offset=row["calibration_offset"] or 0
                )
            return None
        finally:
            conn.close()
    
    def get_window_history(self, direction: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna histórico de janelas para uma direção com plays (otimizado com JOIN)."""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT 
                    w.id, w.gale_level, w.total_hits, w.total_plays, 
                    w.result, w.started_at,
                    p.play_number, p.spin_number, p.hit, p.center_predicted
                FROM gale_windows w
                LEFT JOIN window_plays p ON p.window_id = w.id
                WHERE w.direction = ?
                ORDER BY w.started_at DESC, p.play_number ASC
                LIMIT ?
            """, (direction, limit * 6)).fetchall()
            
            windows_map = {}
            for row in rows:
                wid = row["id"]
                if wid not in windows_map:
                    windows_map[wid] = {
                        "id": wid,
                        "gale_level": row["gale_level"],
                        "total_hits": row["total_hits"],
                        "total_plays": row["total_plays"],
                        "result": row["result"],
                        "started_at": row["started_at"],
                        "plays": []
                    }
                
                if row["play_number"] is not None:
                    windows_map[wid]["plays"].append({
                        "play_number": row["play_number"],
                        "spin_number": row["spin_number"],
                        "hit": bool(row["hit"]) if row["hit"] is not None else None,
                        "center_predicted": row["center_predicted"]
                    })
            
            result = list(windows_map.values())[:limit]
            return result
        finally:
            conn.close()

    # =========================================================================
    # Analytics Queries (para AnalyticsHandler)
    # =========================================================================

    def get_sessions_list(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lista sessões com estatísticas individuais."""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT 
                    s.id,
                    s.start_time,
                    s.end_time,
                    COUNT(d.id) as total_decisions,
                    SUM(CASE WHEN d.final_action = 'APOSTAR' THEN 1 ELSE 0 END) as total_bets,
                    SUM(CASE WHEN d.result_hit = 1 THEN 1 ELSE 0 END) as total_hits,
                    MAX(d.gale_level) as max_gale,
                    AVG(CASE WHEN d.final_action = 'APOSTAR' AND d.result_hit IS NOT NULL
                        THEN CAST(d.result_hit AS REAL) ELSE NULL END) as hit_rate
                FROM sessions s
                LEFT JOIN decisions d ON d.session_id = s.id
                GROUP BY s.id
                ORDER BY s.start_time DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return [
                {
                    "id": row["id"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "total_decisions": row["total_decisions"] or 0,
                    "total_bets": row["total_bets"] or 0,
                    "total_hits": row["total_hits"] or 0,
                    "max_gale": row["max_gale"] or 1,
                    "hit_rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0,
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_gale_window_history(self, direction: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Histórico de janelas Martingale finalizadas com plays."""
        conn = self._get_connection()
        try:
            query = """
                SELECT 
                    gw.id, gw.direction, gw.gale_level,
                    gw.started_at, gw.ended_at,
                    gw.total_hits, gw.total_plays, gw.result,
                    gw.next_level,
                    gw.sda17_rate_at_start, gw.bet_rate_at_start
                FROM gale_windows gw
                WHERE gw.ended_at IS NOT NULL
            """
            params = []
            if direction:
                query += " AND gw.direction = ?"
                params.append(direction)
            query += " ORDER BY gw.started_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            if not rows:
                return []

            # 🔧 TASK-02: Batch query em vez de N+1
            window_ids = [row["id"] for row in rows]
            placeholders = ",".join(["?"] * len(window_ids))

            plays_rows = conn.execute(f"""
                SELECT window_id, play_number, hit, spin_number, spin_force,
                       sda_score, tr_confidence
                FROM window_plays
                WHERE window_id IN ({placeholders})
                ORDER BY window_id, play_number
            """, window_ids).fetchall()

            plays_by_window = {}
            for p in plays_rows:
                wid = p["window_id"]
                if wid not in plays_by_window:
                    plays_by_window[wid] = []
                plays_by_window[wid].append({
                    "play_number": p["play_number"],
                    "hit": bool(p["hit"]),
                    "spin_number": p["spin_number"],
                    "spin_force": p["spin_force"],
                    "sda_score": p["sda_score"],
                    "tr_confidence": p["tr_confidence"],
                })

            windows = []
            for row in rows:
                wid = row["id"]
                windows.append({
                    "id": wid,
                    "direction": row["direction"],
                    "gale_level": row["gale_level"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "total_hits": row["total_hits"],
                    "total_plays": row["total_plays"],
                    "result": row["result"],
                    "next_level": row["next_level"],
                    "sda17_rate_at_start": row["sda17_rate_at_start"],
                    "bet_rate_at_start": row["bet_rate_at_start"],
                    "plays": plays_by_window.get(wid, []),
                })
            return windows
        finally:
            conn.close()

    def get_performance_timeline(self, period: str = "hour", limit: int = 48) -> List[Dict[str, Any]]:
        """Performance agrupada por hora/dia para gráficos de tendência."""
        fmt = "%Y-%m-%d %H:00:00" if period == "hour" else "%Y-%m-%d"
        conn = self._get_connection()
        try:
            rows = conn.execute(f"""
                SELECT 
                    strftime('{fmt}', timestamp) as period,
                    COUNT(*) as total_decisions,
                    SUM(CASE WHEN final_action = 'APOSTAR' THEN 1 ELSE 0 END) as bets,
                    SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) as hits,
                    AVG(CASE WHEN final_action = 'APOSTAR' AND result_hit IS NOT NULL
                        THEN CAST(result_hit AS REAL) ELSE NULL END) as hit_rate,
                    AVG(sda_score) as avg_sda_score
                FROM decisions
                WHERE timestamp IS NOT NULL
                GROUP BY strftime('{fmt}', timestamp)
                ORDER BY period DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return [
                {
                    "period": row["period"],
                    "total": row["total_decisions"],
                    "bets": row["bets"] or 0,
                    "hits": row["hits"] or 0,
                    "hit_rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0,
                    "avg_sda_score": round(row["avg_sda_score"], 1) if row["avg_sda_score"] else 0,
                }
                for row in rows
            ]
        finally:
            conn.close()

