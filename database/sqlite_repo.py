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
        """Retorna nova conexão com SQLite."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
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
                    total_stops INTEGER DEFAULT 0
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
                    
                    -- SDA17 Strategy
                    sda_should_bet BOOLEAN,
                    sda_score INTEGER,
                    sda_center INTEGER,
                    sda_numbers TEXT,  -- JSON array
                    sda_predicted_force INTEGER,
                    
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
                    
                    -- Calibração
                    calibration_offset INTEGER,
                    calibration_error INTEGER,
                    
                    -- Performance snapshot
                    performance_snapshot TEXT,  -- JSON array
                    
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
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
            """)
            conn.commit()
    
    # =========================================================================
    # CRUD de Decisões
    # =========================================================================
    
    def save_decision(self, decision: Decision) -> int:
        """Salva uma nova decisão."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO decisions (
                    timestamp, session_id,
                    spin_number, spin_direction, spin_force,
                    tr_should_bet, tr_confidence, tr_reason,
                    tr_c4_rate, tr_m6_rate, tr_l12_rate,
                    sda_should_bet, sda_score, sda_center,
                    sda_numbers, sda_predicted_force,
                    final_action, action_reason,
                    gale_level, gale_window_hits, gale_window_count, gale_bet_value,
                    result_hit, result_actual,
                    calibration_offset, calibration_error,
                    performance_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(decision.sda_numbers),
                decision.sda_predicted_force,
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
    
    def update_result(self, decision_id: int, hit: bool, actual_number: int) -> None:
        """Atualiza o resultado de uma decisão."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE decisions 
                SET result_hit = ?, result_actual = ?
                WHERE id = ?
            """, (hit, actual_number, decision_id))
            conn.commit()
    
    def get_decision(self, decision_id: int) -> Optional[Decision]:
        """Busca uma decisão por ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decisions WHERE id = ?",
                (decision_id,)
            ).fetchone()
            
            if row:
                return self._row_to_decision(row)
            return None
    
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
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_decision(row) for row in rows]
    
    def get_last_decision_id(self, session_id: str) -> Optional[int]:
        """Retorna o ID da última decisão da sessão."""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT id FROM decisions 
                WHERE session_id = ? AND final_action = 'APOSTAR'
                ORDER BY timestamp DESC LIMIT 1
            """, (session_id,)).fetchone()
            
            return row["id"] if row else None
    
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
            sda_numbers=json.loads(row["sda_numbers"]) if row["sda_numbers"] else [],
            sda_predicted_force=row["sda_predicted_force"] or 0,
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
            performance_snapshot=json.loads(row["performance_snapshot"]) if row["performance_snapshot"] else []
        )
    
    # =========================================================================
    # CRUD de Sessões
    # =========================================================================
    
    def create_session(self, session: Session) -> str:
        """Cria uma nova sessão."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (id, start_time)
                VALUES (?, ?)
            """, (session.id, session.start_time.isoformat()))
            conn.commit()
            return session.id
    
    def update_session(self, session: Session) -> None:
        """Atualiza estatísticas da sessão."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sessions SET
                    total_spins = ?,
                    total_bets = ?,
                    total_hits = ?,
                    total_profit = ?,
                    max_gale_reached = ?,
                    total_stops = ?
                WHERE id = ?
            """, (
                session.total_spins,
                session.total_bets,
                session.total_hits,
                session.total_profit,
                session.max_gale_reached,
                session.total_stops,
                session.id
            ))
            conn.commit()
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Busca sessão por ID."""
        with self._get_connection() as conn:
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
                    total_stops=row["total_stops"] or 0
                )
            return None
    
    def end_session(self, session_id: str) -> None:
        """Marca sessão como finalizada."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sessions SET end_time = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), session_id))
            conn.commit()
    
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
        
        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            
            return {
                "total_decisions": row["total_decisions"] or 0,
                "total_bets": row["total_bets"] or 0,
                "total_hits": row["total_hits"] or 0,
                "hit_rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0
            }
    
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
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            
            return {
                f"gale_{row['gale_level']}": {
                    "total": row["total"],
                    "hits": row["hits"] or 0,
                    "rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0
                }
                for row in rows
            }
    
    def get_triple_rate_analysis(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Analisa eficácia do Triple Rate Advisor."""
        base_query = "FROM decisions WHERE 1=1"
        params = []
        
        if session_id:
            base_query += " AND session_id = ?"
            params.append(session_id)
        
        with self._get_connection() as conn:
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
