# RoletaV11/database/persistence.py

import json
import os
import sqlite3
from typing import Dict, Any, List

from core import config

class DataPersistence:
    """Lida com o salvamento e carregamento de dados do aplicativo."""

    def __init__(self, sda_vetor_names: List[str] = None):
        """Inicializa o gerenciador de persistência."""
        self.json_filepath = config.NOME_ARQUIVO_DADOS_JSON
        self.log_filepath = config.NOME_ARQUIVO_LOG_TXT
        self.db_filepath = config.NOME_ARQUIVO_SDA_DATALAKE_DB
        self.sda_vetor_names = sda_vetor_names or []
        print("Módulo de Persistência (Clean) inicializado.")

    def _get_db_conn(self):
        """Cria e retorna uma nova conexão com o banco de dados."""
        return sqlite3.connect(self.db_filepath)

    def setup_datalake(self):
        """Cria e configura o banco de dados SQLite para o Data Lake da SDA."""
        conn = None
        try:
            conn = self._get_db_conn()
            cursor = conn.cursor()
            
            cols_vetores = ""
            if self.sda_vetor_names:
                cols_vetores = ",\n" + ",\n".join([f'"{name}_pred" INTEGER, "{name}_score" REAL' for name in self.sda_vetor_names])
            
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS performance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                dna_string TEXT NOT NULL,
                resultado_real INTEGER NOT NULL,
                media REAL, desvio_padrao REAL, assimetria REAL, curtose REAL,
                hurst REAL, entropia REAL, determinismo REAL
                {cols_vetores}
            );
            """
            cursor.execute(create_table_query)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON performance_log (timestamp);")
            conn.commit()
            print(f"Data Lake SQLite '{self.db_filepath}' configurado.")
        except sqlite3.Error as e:
            print(f"ERRO CRÍTICO ao configurar o Data Lake SQLite: {e}")
        finally:
            if conn: conn.close()

    def log_performance_vetores(self, registro_completo: Dict[str, Any]):
        """Salva um registro completo de performance de todos os vetores no Data Lake."""
        conn = None
        try:
            conn = self._get_db_conn()
            cursor = conn.cursor()
            colunas = ["timestamp", "dna_string", "resultado_real", "media", "desvio_padrao", 
                         "assimetria", "curtose", "hurst", "entropia", "determinismo"]
            valores = [registro_completo.get(c) for c in colunas]
            
            for name in self.sda_vetor_names:
                colunas.append(f"{name}_pred")
                colunas.append(f"{name}_score")
                valores.append(registro_completo['previsoes_vetores'].get(name))
                valores.append(registro_completo['scores_vetores'].get(name, 0.0))
            
            query = f"INSERT INTO performance_log ({', '.join(colunas)}) VALUES ({', '.join(['?'] * len(colunas))})"
            cursor.execute(query, tuple(valores))
            conn.commit()
        except sqlite3.Error as e:
            print(f"ERRO ao escrever no Data Lake SQLite: {e}")
        finally:
            if conn: conn.close()

    def save_data(self, state: Dict[str, Any]):
        try:
            with open(self.json_filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"ERRO CRÍTICO ao salvar dados JSON: {e}")

    def load_data(self) -> Dict[str, Any]:
        if not os.path.exists(self.json_filepath): return {}
        try:
            with open(self.json_filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, TypeError) as e:
            print(f"ERRO ao carregar dados JSON: {e}. Começando com um estado novo.")
            return {}

    def write_to_log(self, log_message: str):
        full_log_entry = f"{log_message}\n"
        try:
            with open(self.log_filepath, "a", encoding="utf-8") as f_log:
                f_log.write(full_log_entry)
        except IOError as e:
            print(f"ERRO ao escrever no arquivo de log de texto: {e}")
