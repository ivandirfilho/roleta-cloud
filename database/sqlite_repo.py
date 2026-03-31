# Roleta Cloud - SQLite Repository Implementation
# Implementação do repositório usando SQLite

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .repository import DecisionRepository
from .models import Decision, Session

logger = logging.getLogger(__name__)


class SQLiteDecisionRepository(DecisionRepository):
    """
    Implementação do repositório usando SQLite.
    
    Arquivo único, zero configuração, perfeito para desenvolvimento
    e produção de pequena/média escala.
    """
    
    DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "decisions.db"
    
    def __init__(self, db_path: str = None):
        """
        Inicializa conexão com SQLite.
        
        Args:
            db_path: Caminho para o arquivo .db (usa default se None)
        """
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        
        # Criar diretório se não existe
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inicializar schema
        self._init_schema()
        
        logger.info(f"SQLite repository initialized: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Retorna nova conexão com SQLite (WAL mode + busy timeout + FK)."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
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
    
    def save_decision(self, decision: Decision) -> int:
        """Salva uma nova decisão."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                INSERT INTO decisions (
                    timestamp, session_id,
                    spin_number, spin_direction, spin_force,
                    tr_should_bet, tr_confidence, tr_reason,
                    tr_c4_rate, tr_m6_rate, tr_l12_rate,
                    sda_should_bet, sda_score, sda_center, sda_centers,
                    sda_numbers, sda_predicted_force,
                    sda_offset, sda_offset_type,
                    final_action, action_reason,
                    gale_level, gale_window_hits, gale_window_count, gale_bet_value,
                    result_hit, result_actual,
                    calibration_offset, calibration_error,
                    performance_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                json.dumps(decision.performance_snapshot)
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def update_result(self, decision_id: int, hit: bool, actual_number: int) -> None:
        """Atualiza o resultado de uma decisão."""
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE decisions 
                SET result_hit = ?, result_actual = ?
                WHERE id = ?
            """, (hit, actual_number, decision_id))
            conn.commit()
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
            performance_snapshot=self._safe_json_loads(row["performance_snapshot"], [])
        )
    
    # =========================================================================
    # CRUD de Sessões
    # =========================================================================
    
    def create_session(self, session: Session) -> str:
        """Cria uma nova sessão."""
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO sessions (id, start_time)
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
            """, (datetime.utcnow().isoformat(), session_id))
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
            """, (datetime.utcnow().isoformat(), result, next_level, window_id))
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

