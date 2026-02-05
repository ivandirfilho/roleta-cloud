"""
Sistema Preditivo de Forças - Modelos de Dados e Banco de Dados

Este módulo define as tabelas e operações de banco de dados para o sistema
preditivo que usa Filtro de Kalman e clustering de forças.
"""

import sqlite3
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import os


# ==============================================================================
# DATA CLASSES (Modelos)
# ==============================================================================

@dataclass
class Jogada:
    """Representa uma jogada/ciclo do sistema."""
    id: Optional[int] = None
    timestamp: int = 0
    posicao_inicial: int = 0
    posicao_final: int = 0
    voltas_por_segundo: Optional[float] = None
    direcao: int = 1  # +1 (horário) ou -1 (anti-horário)
    posicao_absoluta: int = 0
    forca_bruta: int = 0
    is_outlier: bool = False
    cluster_id: Optional[int] = None


@dataclass
class Derivada:
    """Representa as derivadas calculadas para uma jogada."""
    jogada_id: int = 0
    delta_t: float = 0.0
    velocidade: float = 0.0
    aceleracao: float = 0.0
    arranco: float = 0.0


@dataclass
class Cluster:
    """Representa um cluster de força (X, Y ou Z)."""
    id: int = 0
    nome: str = ""
    centro: Optional[int] = None
    range_min: Optional[int] = None
    range_max: Optional[int] = None
    membros_count: int = 0
    atualizado_em: int = 0


@dataclass
class EstadoKalman:
    """Estado interno do Filtro de Kalman."""
    id: int = 1
    posicao_estimada: float = 0.0
    velocidade_estimada: float = 0.0
    aceleracao_estimada: float = 0.0
    matriz_P: str = "[[1,0,0],[0,10,0],[0,0,10]]"  # JSON
    atualizado_em: int = 0


@dataclass
class Predicao:
    """Representa uma predição gerada pelo sistema."""
    id: Optional[int] = None
    timestamp_predicao: int = 0
    jogada_alvo: Optional[int] = None
    posicao_prevista: int = 0
    forca_prevista: str = ""  # Ex: "X,Y" ou "X"
    confianca: float = 0.0
    posicao_real: Optional[int] = None
    acertou: Optional[bool] = None


# ==============================================================================
# CONFIGURAÇÕES PADRÃO
# ==============================================================================

DEFAULT_CONFIG = {
    "PARTES_ESTATOR": 37,
    "GRAVIDADE": 5,  # 5 números = centro ± 2
    "MINIMO_FORCA": 2,  # Mínimo para ser cluster
    "JANELA_CLASSIFICACAO": 12,  # Últimas N para clustering
    "JANELA_FILTRO": 45,  # Histórico para Kalman
}


# ==============================================================================
# BANCO DE DADOS
# ==============================================================================

class ForcePredictorDB:
    """Gerencia o banco de dados do sistema preditivo de forças."""
    
    def __init__(self, db_path: str = "force_predictor.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
        self._initialize_config()
        self._initialize_clusters()
        self._initialize_kalman_state()
    
    def _connect(self):
        """Estabelece conexão com o banco de dados."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def _create_tables(self):
        """Cria as tabelas do sistema se não existirem."""
        cursor = self.conn.cursor()
        
        # Tabela: jogadas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jogadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                posicao_inicial INTEGER NOT NULL,
                posicao_final INTEGER NOT NULL,
                voltas_por_segundo REAL,
                direcao INTEGER NOT NULL DEFAULT 1,
                posicao_absoluta INTEGER NOT NULL,
                forca_bruta INTEGER NOT NULL,
                is_outlier INTEGER NOT NULL DEFAULT 0,
                cluster_id INTEGER,
                FOREIGN KEY (cluster_id) REFERENCES clusters(id)
            )
        """)
        
        # Tabela: derivadas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS derivadas (
                jogada_id INTEGER PRIMARY KEY,
                delta_t REAL NOT NULL,
                velocidade REAL NOT NULL,
                aceleracao REAL NOT NULL,
                arranco REAL NOT NULL,
                FOREIGN KEY (jogada_id) REFERENCES jogadas(id)
            )
        """)
        
        # Tabela: clusters
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clusters (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                centro INTEGER,
                range_min INTEGER,
                range_max INTEGER,
                membros_count INTEGER NOT NULL DEFAULT 0,
                atualizado_em INTEGER NOT NULL
            )
        """)
        
        # Tabela: configuracoes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)
        
        # Tabela: estado_kalman
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estado_kalman (
                id INTEGER PRIMARY KEY DEFAULT 1,
                posicao_estimada REAL NOT NULL DEFAULT 0,
                velocidade_estimada REAL NOT NULL DEFAULT 0,
                aceleracao_estimada REAL NOT NULL DEFAULT 0,
                matriz_P TEXT NOT NULL DEFAULT '[[1,0,0],[0,10,0],[0,0,10]]',
                atualizado_em INTEGER NOT NULL
            )
        """)
        
        # Tabela: predicoes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predicoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_predicao INTEGER NOT NULL,
                jogada_alvo INTEGER,
                posicao_prevista INTEGER NOT NULL,
                forca_prevista TEXT NOT NULL,
                confianca REAL NOT NULL,
                posicao_real INTEGER,
                acertou INTEGER,
                FOREIGN KEY (jogada_alvo) REFERENCES jogadas(id)
            )
        """)
        
        # Índices para performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jogadas_timestamp 
            ON jogadas(timestamp DESC)
        """)
        
        self.conn.commit()
    
    def _initialize_config(self):
        """Inicializa configurações padrão se não existirem."""
        cursor = self.conn.cursor()
        for key, value in DEFAULT_CONFIG.items():
            cursor.execute("""
                INSERT OR IGNORE INTO configuracoes (chave, valor)
                VALUES (?, ?)
            """, (key, str(value)))
        self.conn.commit()
    
    def _initialize_clusters(self):
        """Inicializa clusters X, Y, Z se não existirem."""
        cursor = self.conn.cursor()
        now = int(datetime.now().timestamp() * 1000)
        
        clusters = [
            (1, "X", None, None, None, 0, now),
            (2, "Y", None, None, None, 0, now),
            (3, "Z", None, None, None, 0, now),
        ]
        
        for cluster in clusters:
            cursor.execute("""
                INSERT OR IGNORE INTO clusters 
                (id, nome, centro, range_min, range_max, membros_count, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, cluster)
        
        self.conn.commit()
    
    def _initialize_kalman_state(self):
        """Inicializa estado do Kalman se não existir."""
        cursor = self.conn.cursor()
        now = int(datetime.now().timestamp() * 1000)
        
        cursor.execute("""
            INSERT OR IGNORE INTO estado_kalman 
            (id, posicao_estimada, velocidade_estimada, aceleracao_estimada, matriz_P, atualizado_em)
            VALUES (1, 0, 0, 0, '[[1,0,0],[0,10,0],[0,0,10]]', ?)
        """, (now,))
        
        self.conn.commit()
    
    # --------------------------------------------------------------------------
    # CONFIGURAÇÕES
    # --------------------------------------------------------------------------
    
    def get_config(self, key: str) -> int:
        """Obtém um valor de configuração."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (key,))
        row = cursor.fetchone()
        return int(row["valor"]) if row else DEFAULT_CONFIG.get(key, 0)
    
    def set_config(self, key: str, value: int):
        """Define um valor de configuração."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO configuracoes (chave, valor)
            VALUES (?, ?)
        """, (key, str(value)))
        self.conn.commit()
    
    # --------------------------------------------------------------------------
    # JOGADAS
    # --------------------------------------------------------------------------
    
    def insert_jogada(self, jogada: Jogada) -> int:
        """Insere uma nova jogada e retorna o ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO jogadas 
            (timestamp, posicao_inicial, posicao_final, voltas_por_segundo, 
             direcao, posicao_absoluta, forca_bruta, is_outlier, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            jogada.timestamp,
            jogada.posicao_inicial,
            jogada.posicao_final,
            jogada.voltas_por_segundo,
            jogada.direcao,
            jogada.posicao_absoluta,
            jogada.forca_bruta,
            1 if jogada.is_outlier else 0,
            jogada.cluster_id
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_jogada_cluster(self, jogada_id: int, cluster_id: Optional[int], is_outlier: bool):
        """Atualiza a classificação de uma jogada."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE jogadas 
            SET cluster_id = ?, is_outlier = ?
            WHERE id = ?
        """, (cluster_id, 1 if is_outlier else 0, jogada_id))
        self.conn.commit()
    
    def get_ultimas_jogadas(self, n: int = 45) -> List[Jogada]:
        """Retorna as últimas N jogadas."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM jogadas 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (n,))
        
        jogadas = []
        for row in cursor.fetchall():
            jogadas.append(Jogada(
                id=row["id"],
                timestamp=row["timestamp"],
                posicao_inicial=row["posicao_inicial"],
                posicao_final=row["posicao_final"],
                voltas_por_segundo=row["voltas_por_segundo"],
                direcao=row["direcao"],
                posicao_absoluta=row["posicao_absoluta"],
                forca_bruta=row["forca_bruta"],
                is_outlier=bool(row["is_outlier"]),
                cluster_id=row["cluster_id"]
            ))
        
        return list(reversed(jogadas))  # Ordem cronológica
    
    def get_ultimas_forcas(self, n: int = 12) -> List[int]:
        """Retorna as últimas N forças brutas (para clustering)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT forca_bruta FROM jogadas 
            WHERE is_outlier = 0
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (n,))
        
        forcas = [row["forca_bruta"] for row in cursor.fetchall()]
        return list(reversed(forcas))  # Ordem cronológica
    
    def get_ultima_posicao_absoluta(self) -> int:
        """Retorna a última posição absoluta registrada."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT posicao_absoluta FROM jogadas 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row["posicao_absoluta"] if row else 0
    
    def get_ultima_jogada(self) -> Optional[Jogada]:
        """Retorna a última jogada."""
        jogadas = self.get_ultimas_jogadas(1)
        return jogadas[0] if jogadas else None
    
    # --------------------------------------------------------------------------
    # DERIVADAS
    # --------------------------------------------------------------------------
    
    def insert_derivada(self, derivada: Derivada):
        """Insere ou atualiza as derivadas de uma jogada."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO derivadas 
            (jogada_id, delta_t, velocidade, aceleracao, arranco)
            VALUES (?, ?, ?, ?, ?)
        """, (
            derivada.jogada_id,
            derivada.delta_t,
            derivada.velocidade,
            derivada.aceleracao,
            derivada.arranco
        ))
        self.conn.commit()
    
    def get_derivada(self, jogada_id: int) -> Optional[Derivada]:
        """Retorna as derivadas de uma jogada."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM derivadas WHERE jogada_id = ?
        """, (jogada_id,))
        row = cursor.fetchone()
        
        if row:
            return Derivada(
                jogada_id=row["jogada_id"],
                delta_t=row["delta_t"],
                velocidade=row["velocidade"],
                aceleracao=row["aceleracao"],
                arranco=row["arranco"]
            )
        return None
    
    # --------------------------------------------------------------------------
    # CLUSTERS
    # --------------------------------------------------------------------------
    
    def update_clusters(self, clusters: List[Cluster]):
        """Atualiza os clusters X, Y, Z."""
        cursor = self.conn.cursor()
        now = int(datetime.now().timestamp() * 1000)
        
        for cluster in clusters:
            cursor.execute("""
                UPDATE clusters 
                SET centro = ?, range_min = ?, range_max = ?, 
                    membros_count = ?, atualizado_em = ?
                WHERE id = ?
            """, (
                cluster.centro,
                cluster.range_min,
                cluster.range_max,
                cluster.membros_count,
                now,
                cluster.id
            ))
        
        self.conn.commit()
    
    def get_clusters(self) -> List[Cluster]:
        """Retorna os clusters atuais."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clusters ORDER BY id")
        
        clusters = []
        for row in cursor.fetchall():
            clusters.append(Cluster(
                id=row["id"],
                nome=row["nome"],
                centro=row["centro"],
                range_min=row["range_min"],
                range_max=row["range_max"],
                membros_count=row["membros_count"],
                atualizado_em=row["atualizado_em"]
            ))
        
        return clusters
    
    # --------------------------------------------------------------------------
    # ESTADO KALMAN
    # --------------------------------------------------------------------------
    
    def update_estado_kalman(self, estado: EstadoKalman):
        """Atualiza o estado do Filtro de Kalman."""
        cursor = self.conn.cursor()
        now = int(datetime.now().timestamp() * 1000)
        
        cursor.execute("""
            UPDATE estado_kalman 
            SET posicao_estimada = ?, velocidade_estimada = ?, 
                aceleracao_estimada = ?, matriz_P = ?, atualizado_em = ?
            WHERE id = 1
        """, (
            estado.posicao_estimada,
            estado.velocidade_estimada,
            estado.aceleracao_estimada,
            estado.matriz_P,
            now
        ))
        
        self.conn.commit()
    
    def get_estado_kalman(self) -> EstadoKalman:
        """Retorna o estado atual do Kalman."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM estado_kalman WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            return EstadoKalman(
                id=row["id"],
                posicao_estimada=row["posicao_estimada"],
                velocidade_estimada=row["velocidade_estimada"],
                aceleracao_estimada=row["aceleracao_estimada"],
                matriz_P=row["matriz_P"],
                atualizado_em=row["atualizado_em"]
            )
        
        return EstadoKalman()
    
    # --------------------------------------------------------------------------
    # PREDIÇÕES
    # --------------------------------------------------------------------------
    
    def insert_predicao(self, predicao: Predicao) -> int:
        """Insere uma nova predição."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO predicoes 
            (timestamp_predicao, jogada_alvo, posicao_prevista, 
             forca_prevista, confianca, posicao_real, acertou)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            predicao.timestamp_predicao,
            predicao.jogada_alvo,
            predicao.posicao_prevista,
            predicao.forca_prevista,
            predicao.confianca,
            predicao.posicao_real,
            predicao.acertou
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_predicao_resultado(self, predicao_id: int, posicao_real: int, acertou: bool):
        """Atualiza o resultado de uma predição."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE predicoes 
            SET posicao_real = ?, acertou = ?
            WHERE id = ?
        """, (posicao_real, 1 if acertou else 0, predicao_id))
        self.conn.commit()
    
    def get_ultima_predicao(self) -> Optional[Predicao]:
        """Retorna a última predição."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM predicoes 
            ORDER BY timestamp_predicao DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        
        if row:
            return Predicao(
                id=row["id"],
                timestamp_predicao=row["timestamp_predicao"],
                jogada_alvo=row["jogada_alvo"],
                posicao_prevista=row["posicao_prevista"],
                forca_prevista=row["forca_prevista"],
                confianca=row["confianca"],
                posicao_real=row["posicao_real"],
                acertou=bool(row["acertou"]) if row["acertou"] is not None else None
            )
        return None
    
    # --------------------------------------------------------------------------
    # ESTATÍSTICAS
    # --------------------------------------------------------------------------
    
    def get_estatisticas(self) -> Dict:
        """Retorna estatísticas gerais do sistema."""
        cursor = self.conn.cursor()
        
        # Total de jogadas
        cursor.execute("SELECT COUNT(*) as total FROM jogadas")
        total_jogadas = cursor.fetchone()["total"]
        
        # Total de outliers
        cursor.execute("SELECT COUNT(*) as total FROM jogadas WHERE is_outlier = 1")
        total_outliers = cursor.fetchone()["total"]
        
        # Taxa de acerto das predições
        cursor.execute("""
            SELECT COUNT(*) as total, SUM(acertou) as acertos 
            FROM predicoes WHERE acertou IS NOT NULL
        """)
        row = cursor.fetchone()
        total_predicoes = row["total"] or 0
        acertos = row["acertos"] or 0
        taxa_acerto = (acertos / total_predicoes * 100) if total_predicoes > 0 else 0
        
        return {
            "total_jogadas": total_jogadas,
            "total_outliers": total_outliers,
            "total_predicoes": total_predicoes,
            "taxa_acerto": round(taxa_acerto, 2)
        }
    
    def close(self):
        """Fecha a conexão com o banco."""
        if self.conn:
            self.conn.close()


# ==============================================================================
# TESTE
# ==============================================================================

if __name__ == "__main__":
    # Teste básico
    db = ForcePredictorDB("test_force_predictor.db")
    
    print("✓ Banco de dados criado com sucesso!")
    print(f"  Configurações: {DEFAULT_CONFIG}")
    print(f"  Clusters inicializados: {[c.nome for c in db.get_clusters()]}")
    print(f"  Estado Kalman: P={db.get_estado_kalman().posicao_estimada}")
    
    # Limpar teste
    db.close()
    os.remove("test_force_predictor.db")
    print("✓ Teste concluído!")
