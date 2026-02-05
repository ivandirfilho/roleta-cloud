"""
Sistema Preditivo de Forças - Pipeline Completo

Integra banco de dados, clustering e Filtro de Kalman em um único
sistema para predição de forças.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from force_predictor_db import (
    ForcePredictorDB, 
    Jogada, 
    Derivada, 
    Predicao,
    DEFAULT_CONFIG
)
from force_clustering import ForceClustering, converter_para_db_clusters
from force_kalman import KalmanFilter


@dataclass
class ResultadoPredicao:
    """Resultado completo de uma predição."""
    posicao_prevista: int  # Posição no estator (0-37)
    posicao_absoluta_prevista: float  # Posição desenrolada
    forcas_predominantes: List[str]  # ["X"], ["X", "Y"], etc.
    padrao: str  # "X-Y-X-X-Y"
    confianca: float  # 0-1
    tendencia: str  # "ACELERANDO", "DESACELERANDO", "ESTAVEL"
    outliers_recentes: int  # Quantidade de outliers nas últimas jogadas
    estado: Dict  # Estado completo para debug


class ForcePredictor:
    """
    Sistema completo de predição de forças.
    
    Pipeline:
    1. Receber nova jogada
    2. Desenrolar posição (unwrap)
    3. Calcular derivadas
    4. Atualizar clusters
    5. Atualizar Kalman
    6. Gerar predição
    """
    
    def __init__(self, db_path: str = "force_predictor.db"):
        """
        Args:
            db_path: Caminho para o banco de dados SQLite
        """
        # Banco de dados
        self.db = ForcePredictorDB(db_path)
        
        # Parâmetros
        self.partes_estator = self.db.get_config("PARTES_ESTATOR")
        self.gravidade = self.db.get_config("GRAVIDADE")
        self.minimo_forca = self.db.get_config("MINIMO_FORCA")
        self.janela_classificacao = self.db.get_config("JANELA_CLASSIFICACAO")
        self.janela_filtro = self.db.get_config("JANELA_FILTRO")
        
        # Clustering
        self.clustering = ForceClustering(
            gravidade=self.gravidade,
            minimo=self.minimo_forca
        )
        
        # Filtro de Kalman
        self.kalman = KalmanFilter(
            ruido_processo=0.5,
            ruido_medicao=1.0,
            dt_default=1.0
        )
        
        # Carregar estado do Kalman do banco
        estado_kalman = self.db.get_estado_kalman()
        if estado_kalman.posicao_estimada != 0:
            self.kalman.from_estado_kalman(estado_kalman)
        
        # Cache
        self._ultimo_resultado_clustering: Optional[Dict] = None
    
    def _desenrolar_posicao(
        self, 
        posicao_final: int, 
        direcao: int
    ) -> Tuple[int, int]:
        """
        Calcula posição absoluta (desenrolada) e força bruta.
        
        Args:
            posicao_final: Posição atual no estator (0-37)
            direcao: +1 (horário) ou -1 (anti-horário)
            
        Returns:
            Tupla (posicao_absoluta, forca_bruta)
        """
        ultima_jogada = self.db.get_ultima_jogada()
        
        if ultima_jogada is None:
            # Primeira jogada
            return posicao_final, 0
        
        ultima_pos_bruta = ultima_jogada.posicao_final
        ultima_pos_absoluta = ultima_jogada.posicao_absoluta
        
        # Calcular delta
        delta = posicao_final - ultima_pos_bruta
        
        # Correção de volta
        if direcao == 1 and delta < 0:
            # Sentido horário, passou do 37 → 0
            delta += self.partes_estator
        elif direcao == -1 and delta > 0:
            # Sentido anti-horário, passou do 0 → 37
            delta -= self.partes_estator
        
        posicao_absoluta = ultima_pos_absoluta + delta
        forca_bruta = delta
        
        return posicao_absoluta, forca_bruta
    
    def _calcular_derivadas(self, jogada: Jogada) -> Derivada:
        """
        Calcula velocidade, aceleração e arranco.
        
        Args:
            jogada: Jogada atual
            
        Returns:
            Objeto Derivada
        """
        ultima_jogada = self.db.get_ultima_jogada()
        ultima_derivada = None
        
        if ultima_jogada:
            ultima_derivada = self.db.get_derivada(ultima_jogada.id)
        
        # Delta de tempo
        if ultima_jogada:
            delta_t = (jogada.timestamp - ultima_jogada.timestamp) / 1000.0
            if delta_t <= 0:
                delta_t = 1.0  # Fallback
        else:
            delta_t = 1.0
        
        # Velocidade = força / tempo
        if jogada.voltas_por_segundo is not None:
            # Se temos VPS, usar para calcular velocidade
            velocidade = jogada.voltas_por_segundo * self.partes_estator
        else:
            # Calcular a partir do delta
            velocidade = jogada.forca_bruta / delta_t if delta_t > 0 else 0
        
        # Aceleração
        if ultima_derivada:
            aceleracao = (velocidade - ultima_derivada.velocidade) / delta_t
        else:
            aceleracao = 0
        
        # Arranco (jerk)
        if ultima_derivada and ultima_derivada.aceleracao != 0:
            arranco = (aceleracao - ultima_derivada.aceleracao) / delta_t
        else:
            arranco = 0
        
        return Derivada(
            jogada_id=jogada.id,
            delta_t=delta_t,
            velocidade=velocidade,
            aceleracao=aceleracao,
            arranco=arranco
        )
    
    def _atualizar_clusters(self):
        """Recalcula clusters com base nas últimas jogadas."""
        forcas = self.db.get_ultimas_forcas(self.janela_classificacao)
        
        if len(forcas) >= self.minimo_forca:
            resultado = self.clustering.classificar(forcas)
            self._ultimo_resultado_clustering = resultado
            
            # Converter e salvar no banco
            clusters_db = converter_para_db_clusters(resultado)
            self.db.update_clusters(clusters_db)
    
    def _classificar_jogada(self, jogada: Jogada) -> Tuple[Optional[int], bool]:
        """
        Classifica a jogada atual em um cluster.
        
        Returns:
            Tupla (cluster_id, is_outlier)
        """
        if self._ultimo_resultado_clustering is None:
            return None, False
        
        nome_cluster, is_outlier = self.clustering.classificar_forca(
            jogada.forca_bruta,
            self._ultimo_resultado_clustering
        )
        
        cluster_id = None
        if nome_cluster == "X":
            cluster_id = 1
        elif nome_cluster == "Y":
            cluster_id = 2
        elif nome_cluster == "Z":
            cluster_id = 3
        
        return cluster_id, is_outlier
    
    def _atualizar_kalman(self, posicao_absoluta: float, delta_t: float, is_outlier: bool):
        """Atualiza o Filtro de Kalman."""
        if is_outlier:
            # Para outliers, só fazer predict (não corrigir com observação ruidosa)
            self.kalman.predict(delta_t)
        else:
            # Predict + Update normal
            self.kalman.predict_and_update(posicao_absoluta, delta_t)
        
        # Salvar estado no banco
        estado = self.kalman.to_estado_kalman()
        self.db.update_estado_kalman(estado)
    
    def _gerar_predicao(self, jogada_id: int) -> ResultadoPredicao:
        """Gera a predição para a próxima jogada."""
        # Prever posição futura
        posicao_absoluta_prevista = self.kalman.prever_futuro(1.0)
        posicao_estator = int(posicao_absoluta_prevista) % self.partes_estator
        
        # Forças predominantes
        predominantes = []
        if self._ultimo_resultado_clustering:
            predominantes = self.clustering.obter_predominantes(
                self._ultimo_resultado_clustering
            )
        
        # Padrão
        padrao = ""
        if self._ultimo_resultado_clustering:
            padrao = self.clustering.obter_padrao(
                self._ultimo_resultado_clustering["classificacao"],
                6
            )
        
        # Confiança
        confianca = self.kalman.get_confianca()
        
        # Tendência
        aceleracao = self.kalman.aceleracao
        if aceleracao > 0.5:
            tendencia = "ACELERANDO"
        elif aceleracao < -0.5:
            tendencia = "DESACELERANDO"
        else:
            tendencia = "ESTAVEL"
        
        # Outliers recentes
        ultimas = self.db.get_ultimas_jogadas(self.janela_classificacao)
        outliers_recentes = sum(1 for j in ultimas if j.is_outlier)
        
        # Persistir predição
        predicao = Predicao(
            timestamp_predicao=int(datetime.now().timestamp() * 1000),
            jogada_alvo=jogada_id,
            posicao_prevista=posicao_estator,
            forca_prevista=",".join(predominantes) if predominantes else "?",
            confianca=confianca
        )
        self.db.insert_predicao(predicao)
        
        return ResultadoPredicao(
            posicao_prevista=posicao_estator,
            posicao_absoluta_prevista=posicao_absoluta_prevista,
            forcas_predominantes=predominantes,
            padrao=padrao,
            confianca=confianca,
            tendencia=tendencia,
            outliers_recentes=outliers_recentes,
            estado={
                "kalman": {
                    "posicao": self.kalman.posicao,
                    "velocidade": self.kalman.velocidade,
                    "aceleracao": self.kalman.aceleracao
                },
                "clusters": {
                    "X": self._ultimo_resultado_clustering["X"].__dict__ if self._ultimo_resultado_clustering and self._ultimo_resultado_clustering["X"] else None,
                    "Y": self._ultimo_resultado_clustering["Y"].__dict__ if self._ultimo_resultado_clustering and self._ultimo_resultado_clustering["Y"] else None,
                    "Z": self._ultimo_resultado_clustering["Z"].__dict__ if self._ultimo_resultado_clustering and self._ultimo_resultado_clustering["Z"] else None,
                }
            }
        )
    
    # ==========================================================================
    # API PÚBLICA
    # ==========================================================================
    
    def processar_jogada(
        self,
        posicao_inicial: int,
        posicao_final: int,
        direcao: int,
        voltas_por_segundo: Optional[float] = None,
        timestamp: Optional[int] = None
    ) -> ResultadoPredicao:
        """
        Processa uma nova jogada e retorna a predição.
        
        Args:
            posicao_inicial: Posição inicial no estator (0-37)
            posicao_final: Posição final no estator (0-37)
            direcao: +1 (horário) ou -1 (anti-horário)
            voltas_por_segundo: VPS se disponível
            timestamp: Timestamp em ms (usa atual se não fornecido)
            
        Returns:
            ResultadoPredicao com a predição para a próxima jogada
        """
        if timestamp is None:
            timestamp = int(datetime.now().timestamp() * 1000)
        
        # 1. Desenrolar posição
        posicao_absoluta, forca_bruta = self._desenrolar_posicao(
            posicao_final, 
            direcao
        )
        
        # 2. Criar e persistir jogada
        jogada = Jogada(
            timestamp=timestamp,
            posicao_inicial=posicao_inicial,
            posicao_final=posicao_final,
            voltas_por_segundo=voltas_por_segundo,
            direcao=direcao,
            posicao_absoluta=posicao_absoluta,
            forca_bruta=forca_bruta
        )
        jogada.id = self.db.insert_jogada(jogada)
        
        # 3. Calcular derivadas
        derivada = self._calcular_derivadas(jogada)
        self.db.insert_derivada(derivada)
        
        # 4. Atualizar clusters
        self._atualizar_clusters()
        
        # 5. Classificar jogada
        cluster_id, is_outlier = self._classificar_jogada(jogada)
        self.db.update_jogada_cluster(jogada.id, cluster_id, is_outlier)
        
        # 6. Atualizar Kalman
        self._atualizar_kalman(posicao_absoluta, derivada.delta_t, is_outlier)
        
        # 7. Gerar predição
        return self._gerar_predicao(jogada.id)
    
    def get_estado_atual(self) -> Dict:
        """Retorna o estado atual do sistema."""
        clusters = self.db.get_clusters()
        stats = self.db.get_estatisticas()
        ultima_predicao = self.db.get_ultima_predicao()
        
        return {
            "estatisticas": stats,
            "clusters": {c.nome: {"centro": c.centro, "count": c.membros_count} for c in clusters},
            "kalman": {
                "posicao": self.kalman.posicao,
                "velocidade": self.kalman.velocidade,
                "aceleracao": self.kalman.aceleracao,
                "confianca": self.kalman.get_confianca()
            },
            "ultima_predicao": {
                "posicao": ultima_predicao.posicao_prevista if ultima_predicao else None,
                "forca": ultima_predicao.forca_prevista if ultima_predicao else None,
                "confianca": ultima_predicao.confianca if ultima_predicao else None
            }
        }
    
    def reset(self):
        """Reinicia o sistema (limpa banco e estados)."""
        # Reinicializar Kalman
        self.kalman.inicializar(0, 0, 0)
        self.db.update_estado_kalman(self.kalman.to_estado_kalman())
        
        # Limpar cache
        self._ultimo_resultado_clustering = None
    
    def close(self):
        """Fecha conexão com banco."""
        self.db.close()


# ==============================================================================
# TESTE
# ==============================================================================

if __name__ == "__main__":
    import os
    
    print("=" * 70)
    print("TESTE DO SISTEMA COMPLETO DE PREDIÇÃO DE FORÇAS")
    print("=" * 70)
    
    # Usar banco de teste
    db_test = "test_force_predictor_full.db"
    
    try:
        predictor = ForcePredictor(db_test)
        
        # Simular jogadas
        jogadas_simuladas = [
            # (pos_inicial, pos_final, direcao, vps)
            (0, 15, 1, None),   # Força ~15
            (15, 30, 1, None),  # Força ~15
            (30, 8, 1, None),   # Força ~15 (cruzou 37→0)
            (8, 22, 1, None),   # Força ~14
            (22, 35, 1, None),  # Força ~13
            (35, 12, 1, None),  # Força ~14 (cruzou)
            (12, 40, 1, None),  # Força ~28 (mudança!)
            (3, 32, 1, None),   # Força ~29
            (32, 25, 1, None),  # Força ~30 (cruzou)
            (25, 40, 1, None),  # Força ~15 (voltou)
            (3, 5, 1, None),    # Força ~2 (OUTLIER!)
            (5, 20, 1, None),   # Força ~15
        ]
        
        print(f"\nSimulando {len(jogadas_simuladas)} jogadas...\n")
        
        for i, (pos_i, pos_f, direcao, vps) in enumerate(jogadas_simuladas):
            resultado = predictor.processar_jogada(
                posicao_inicial=pos_i,
                posicao_final=pos_f,
                direcao=direcao,
                voltas_por_segundo=vps
            )
            
            print(f"Jogada {i+1}: {pos_i} → {pos_f}")
            print(f"  Predição próxima: parte {resultado.posicao_prevista}")
            print(f"  Forças ativas: {resultado.forcas_predominantes}")
            print(f"  Padrão: {resultado.padrao}")
            print(f"  Confiança: {resultado.confianca:.1%}")
            print(f"  Tendência: {resultado.tendencia}")
            print()
        
        # Estado final
        print("=" * 70)
        print("ESTADO FINAL")
        print("=" * 70)
        estado = predictor.get_estado_atual()
        print(f"\nEstatísticas: {estado['estatisticas']}")
        print(f"Clusters: {estado['clusters']}")
        print(f"Kalman: pos={estado['kalman']['posicao']:.1f}, vel={estado['kalman']['velocidade']:.1f}")
        
        predictor.close()
        
    finally:
        # Limpar arquivo de teste
        if os.path.exists(db_test):
            os.remove(db_test)
    
    print("\n" + "=" * 70)
    print("✓ Teste completo finalizado!")
