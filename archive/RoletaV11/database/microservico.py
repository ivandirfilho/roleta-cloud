# RoletaV11/database/microservico.py

import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import threading
import json
import os

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÕES
# ═══════════════════════════════════════════════════════════════════════════════

DB_FILE = "microservico_datalake.db"
MAX_HISTORICO = 45  # Últimas 45 interações por sentido


# ═══════════════════════════════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PrevisaoMicroservico:
    """
    Representa uma previsão do microserviço.
    Simplificado para usar apenas Rotina (1 região de 17 números).
    """
    id: int = 0
    timestamp: str = ""
    sentido: str = ""  # "horario" ou "antihorario"
    
    # Posição de partida
    posicao_partida: int = 0
    
    # Força prevista (única - Rotina)
    forca_vicio: float = 0.0  # Mantém nome para compatibilidade
    
    # Centro (número na roleta)
    centro_vicio: int = 0  # Mantém nome para compatibilidade
    
    # Região (17 vizinhos em JSON)
    regiao_vicio: str = "[]"  # Mantém nome para compatibilidade
    
    # Resultado real (preenchido depois)
    numero_real: Optional[int] = None
    
    # Acerto (apenas Rotina agora)
    acertou: Optional[bool] = None
    acertou_vicio: Optional[bool] = None  # Mantém nome para compatibilidade
    
    # Metadados do pipeline
    taxa_sobrevivencia: float = 0.0
    last_valid_force: float = 0.0
    regime: str = "ESTAVEL"  # ACELERANDO, FREANDO ou ESTAVEL
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'sentido': self.sentido,
            'posicao_partida': self.posicao_partida,
            'forca_vicio': self.forca_vicio,
            'centro_vicio': self.centro_vicio,
            'regiao_vicio': self.regiao_vicio,
            'numero_real': self.numero_real,
            'acertou': self.acertou,
            'acertou_vicio': self.acertou_vicio,
            'taxa_sobrevivencia': self.taxa_sobrevivencia,
            'last_valid_force': self.last_valid_force,
            'regime': self.regime
        }


@dataclass
class EstatisticasSentido:
    """
    Estatísticas de performance por sentido.
    Simplificado para apenas Rotina (17 números).
    """
    sentido: str = ""
    total_previsoes: int = 0
    total_acertos: int = 0
    total_erros: int = 0
    
    acertos_vicio: int = 0  # Mantém nome para compatibilidade (= acertos Rotina)
    
    # Últimas 12 para exibição visual
    historico_12: List[bool] = field(default_factory=list)
    
    @property
    def taxa_acerto(self) -> float:
        if self.total_previsoes == 0:
            return 0.0
        return self.total_acertos / self.total_previsoes
    
    @property
    def roi(self) -> float:
        """
        Calcula ROI baseado em aposta de 17 números.
        Payout em roleta europeia: 35:1 para número exato.
        
        Nova lógica: 1 região de 17 números, aposta de 17 unidades.
        """
        if self.total_previsoes == 0:
            return 0.0
        
        ganhos = self.total_acertos * 35  # Payout por acerto
        perdas = self.total_erros * 17     # Custo = 17 números apostados
        investido = self.total_previsoes * 17
        
        if investido == 0:
            return 0.0
        
        return ((ganhos - perdas) / investido) * 100


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class MicroservicoDB:
    """
    Gerenciador do banco de dados para o microserviço.
    Thread-safe com lock de escrita.
    Simplificado para Rotina com 17 números.
    """
    
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self._lock = threading.Lock()
        self._init_database()
        print(f"[MicroservicoDB] Banco de dados '{db_file}' inicializado.")
    
    def _init_database(self):
        """Inicializa o esquema do banco de dados (simplificado)."""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            # Tabela principal de previsões (simplificada - apenas Rotina)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS previsoes_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    sentido TEXT NOT NULL,
                    
                    posicao_partida INTEGER NOT NULL,
                    
                    forca_vicio REAL NOT NULL,
                    centro_vicio INTEGER NOT NULL,
                    regiao_vicio TEXT NOT NULL,
                    
                    numero_real INTEGER,
                    
                    acertou INTEGER,
                    acertou_vicio INTEGER,
                    
                    taxa_sobrevivencia REAL,
                    last_valid_force REAL,
                    regime TEXT DEFAULT 'ESTAVEL'
                )
            """)
            
            # Índices para consultas rápidas
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sentido_v2 ON previsoes_v2 (sentido)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp_v2 ON previsoes_v2 (timestamp DESC)")
            
            conn.commit()
    
    def gravar_previsao(self, previsao: PrevisaoMicroservico) -> int:
        """
        Grava uma nova previsão no banco de dados.
        Retorna o ID da previsão gravada.
        """
        with self._lock:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO previsoes_v2 (
                        timestamp, sentido, posicao_partida,
                        forca_vicio, centro_vicio, regiao_vicio,
                        numero_real, acertou, acertou_vicio,
                        taxa_sobrevivencia, last_valid_force, regime
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    previsao.timestamp, previsao.sentido, previsao.posicao_partida,
                    previsao.forca_vicio, previsao.centro_vicio, previsao.regiao_vicio,
                    previsao.numero_real, previsao.acertou, previsao.acertou_vicio,
                    previsao.taxa_sobrevivencia, previsao.last_valid_force, previsao.regime
                ))
                
                previsao_id = cursor.lastrowid
                conn.commit()
                
                # Limpar histórico antigo (manter apenas MAX_HISTORICO por sentido)
                self._limpar_historico_antigo(conn, previsao.sentido)
                
                return previsao_id
    
    def _limpar_historico_antigo(self, conn, sentido: str):
        """Remove previsões antigas além do limite por sentido."""
        cursor = conn.cursor()
        
        # Contar previsões deste sentido
        cursor.execute("SELECT COUNT(*) FROM previsoes_v2 WHERE sentido = ?", (sentido,))
        count = cursor.fetchone()[0]
        
        if count > MAX_HISTORICO:
            # Deletar as mais antigas
            excesso = count - MAX_HISTORICO
            cursor.execute("""
                DELETE FROM previsoes_v2 
                WHERE id IN (
                    SELECT id FROM previsoes_v2 
                    WHERE sentido = ? 
                    ORDER BY timestamp ASC 
                    LIMIT ?
                )
            """, (sentido, excesso))
            conn.commit()
    
    def atualizar_resultado(self, previsao_id: int, numero_real: int) -> Dict:
        """
        Atualiza uma previsão com o resultado real e calcula acertos.
        Retorna um dicionário com os detalhes do acerto.
        """
        with self._lock:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Buscar a previsão (apenas Rotina) - buscar também o centro para debug
                cursor.execute("""
                    SELECT regiao_vicio, centro_vicio, forca_vicio, posicao_partida 
                    FROM previsoes_v2 WHERE id = ?
                """, (previsao_id,))
                
                row = cursor.fetchone()
                if not row:
                    return {'sucesso': False, 'erro': 'Previsão não encontrada'}
                
                regiao_vicio = json.loads(row[0])
                centro_vicio = row[1]
                forca_vicio = row[2]
                posicao_partida = row[3]
                
                # Verificar acerto (apenas Rotina com 17 números)
                acertou_vicio = numero_real in regiao_vicio
                acertou = acertou_vicio  # Único filtro agora
                
                # Atualizar no banco
                cursor.execute("""
                    UPDATE previsoes_v2 SET
                        numero_real = ?,
                        acertou = ?,
                        acertou_vicio = ?
                    WHERE id = ?
                """, (
                    numero_real,
                    1 if acertou else 0,
                    1 if acertou_vicio else 0,
                    previsao_id
                ))
                
                conn.commit()
                
                return {
                    'sucesso': True,
                    'acertou': acertou,
                    'acertou_vicio': acertou_vicio,
                    'numero_real': numero_real
                }
    
    def obter_ultima_previsao_pendente(self, sentido: str) -> Optional[PrevisaoMicroservico]:
        """
        Retorna a última previsão pendente (sem resultado) para um sentido.
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, timestamp, sentido, posicao_partida,
                           forca_vicio, centro_vicio, regiao_vicio,
                           numero_real, acertou, acertou_vicio,
                           taxa_sobrevivencia, last_valid_force, regime
                    FROM previsoes_v2 
                    WHERE sentido = ? AND numero_real IS NULL
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (sentido,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return PrevisaoMicroservico(
                    id=row[0], timestamp=row[1], sentido=row[2], posicao_partida=row[3],
                    forca_vicio=row[4], centro_vicio=row[5], regiao_vicio=row[6],
                    numero_real=row[7], acertou=row[8], acertou_vicio=row[9],
                    taxa_sobrevivencia=row[10], last_valid_force=row[11], regime=row[12] or "ESTAVEL"
                )
        except sqlite3.OperationalError:
            return None
    
    def obter_estatisticas(self, sentido: str) -> EstatisticasSentido:
        """
        Calcula estatísticas de performance para um sentido.
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Total de previsões com resultado (simplificado - apenas Rotina)
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN acertou = 1 THEN 1 ELSE 0 END) as acertos,
                        SUM(CASE WHEN acertou = 0 THEN 1 ELSE 0 END) as erros,
                        SUM(CASE WHEN acertou_vicio = 1 THEN 1 ELSE 0 END) as acertos_vicio
                    FROM previsoes_v2 
                    WHERE sentido = ? AND numero_real IS NOT NULL
                """, (sentido,))
                
                row = cursor.fetchone()
                if not row:
                     return EstatisticasSentido(sentido=sentido)

                # Últimas 12 para exibição visual
                cursor.execute("""
                    SELECT acertou FROM previsoes_v2 
                    WHERE sentido = ? AND numero_real IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 12
                """, (sentido,))
                
                historico_12 = [bool(r[0]) for r in cursor.fetchall()]
                
                return EstatisticasSentido(
                    sentido=sentido,
                    total_previsoes=row[0] or 0,
                    total_acertos=row[1] or 0,
                    total_erros=row[2] or 0,
                    acertos_vicio=row[3] or 0,
                    historico_12=historico_12
                )
        except sqlite3.OperationalError:
            return EstatisticasSentido(sentido=sentido)
    
    def obter_historico(self, sentido: str, limite: int = 45) -> List[PrevisaoMicroservico]:
        """
        Retorna o histórico de previsões para um sentido.
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, timestamp, sentido, posicao_partida,
                           forca_vicio, centro_vicio, regiao_vicio,
                           numero_real, acertou, acertou_vicio,
                           taxa_sobrevivencia, last_valid_force, regime
                    FROM previsoes_v2 
                    WHERE sentido = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (sentido, limite))
                
                previsoes = []
                for row in cursor.fetchall():
                    previsoes.append(PrevisaoMicroservico(
                        id=row[0], timestamp=row[1], sentido=row[2], posicao_partida=row[3],
                        forca_vicio=row[4], centro_vicio=row[5], regiao_vicio=row[6],
                        numero_real=row[7], acertou=row[8], acertou_vicio=row[9],
                        taxa_sobrevivencia=row[10], last_valid_force=row[11], regime=row[12] or "ESTAVEL"
                    ))
                
                return previsoes
        except sqlite3.OperationalError:
            return []
