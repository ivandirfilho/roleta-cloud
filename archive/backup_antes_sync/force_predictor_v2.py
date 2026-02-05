"""
Sistema Preditivo de Forças v2 - DUAS LINHAS INDEPENDENTES

Versão corrigida que mantém duas linhas de posição absoluta:
- Uma para direção HORÁRIA (posição cresce ao infinito)
- Uma para direção ANTI-HORÁRIA (posição cresce ao infinito)

Cada direção tem seu próprio Filtro de Kalman.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from force_clustering import ForceClustering
from force_kalman import KalmanFilter


@dataclass
class ResultadoPredicaoV2:
    """Resultado completo de uma predição com direção."""
    direcao: str  # "horario" ou "anti-horario"
    posicao_prevista: int  # Posição no estator (0-37)
    posicao_absoluta_prevista: float  # Posição na linha infinita
    forcas_predominantes: List[str]  # ["X"], ["X", "Y"], etc.
    padrao: str  # "X-Y-X-X-Y"
    confianca: float  # 0-1
    tendencia: str  # "ACELERANDO", "DESACELERANDO", "ESTAVEL"
    estado: Dict  # Estado para debug


class LinhaDirecional:
    """
    Gerencia uma linha de posição absoluta para uma direção específica.
    
    Cada direção tem:
    - Sua própria posição absoluta (0 → infinito)
    - Seu próprio Filtro de Kalman
    - Seu próprio clustering de forças
    """
    
    def __init__(self, direcao: str, partes_estator: int = 37):
        """
        Args:
            direcao: "horario" ou "anti-horario"
            partes_estator: Número de partes do estator (37)
        """
        self.direcao = direcao
        self.partes_estator = partes_estator
        
        # Posição absoluta (linha infinita)
        self.posicao_absoluta_atual: float = 0
        self.ultima_posicao_estator: Optional[int] = None
        
        # Filtro de Kalman independente
        self.kalman = KalmanFilter(
            ruido_processo=0.5,
            ruido_medicao=1.0,
            dt_default=1.0
        )
        
        # Clustering independente
        self.clustering = ForceClustering(gravidade=5, minimo=2)
        
        # Histórico de forças desta direção
        self.historico_forcas: List[int] = []
        self.ultimo_resultado_clustering: Optional[Dict] = None
        
        # Estatísticas
        self.total_jogadas = 0
        self.total_outliers = 0
    
    def processar_jogada(
        self,
        posicao_estator: int,
        is_outlier: bool = False,
        delta_t: float = 1.0
    ) -> Dict:
        """
        Processa uma jogada nesta direção.
        
        Args:
            posicao_estator: Posição final no estator (0-37)
            is_outlier: Se a jogada é outlier
            delta_t: Delta de tempo desde última jogada
            
        Returns:
            Dict com força_bruta, posicao_absoluta, classificacao
        """
        # Calcular força bruta (distância desde última posição)
        if self.ultima_posicao_estator is not None:
            # Calcular delta considerando a volta no estator
            delta = posicao_estator - self.ultima_posicao_estator
            
            # Corrigir para o sentido da direção
            if self.direcao == "horario":
                # Horário: movimento positivo
                if delta < 0:
                    delta += self.partes_estator  # Passou do 37 → 0
            else:
                # Anti-horário: movimento negativo vira positivo
                if delta > 0:
                    delta = self.partes_estator - delta
                else:
                    delta = abs(delta)
            
            forca_bruta = delta
        else:
            forca_bruta = 0
        
        # Atualizar posição absoluta (sempre crescendo)
        self.posicao_absoluta_atual += forca_bruta
        
        # Atualizar última posição
        self.ultima_posicao_estator = posicao_estator
        
        # Adicionar ao histórico de forças
        if forca_bruta > 0 and not is_outlier:
            self.historico_forcas.append(forca_bruta)
            # Manter só as últimas 45
            if len(self.historico_forcas) > 45:
                self.historico_forcas = self.historico_forcas[-45:]
        
        # Atualizar clustering (últimas 12)
        if len(self.historico_forcas) >= 2:
            forcas_recentes = self.historico_forcas[-12:]
            self.ultimo_resultado_clustering = self.clustering.classificar(forcas_recentes)
        
        # Classificar a força atual
        classificacao = None
        if self.ultimo_resultado_clustering and forca_bruta > 0:
            nome, _ = self.clustering.classificar_forca(
                forca_bruta, 
                self.ultimo_resultado_clustering
            )
            classificacao = nome
        
        # Atualizar Kalman
        if is_outlier:
            self.kalman.predict(delta_t)
            self.total_outliers += 1
        else:
            self.kalman.predict_and_update(self.posicao_absoluta_atual, delta_t)
        
        self.total_jogadas += 1
        
        return {
            "forca_bruta": forca_bruta,
            "posicao_absoluta": self.posicao_absoluta_atual,
            "classificacao": classificacao,
            "is_outlier": is_outlier
        }
    
    def prever_proxima(self, delta_t_futuro: float = 1.0) -> Dict:
        """
        Prevê a próxima posição nesta direção.
        
        Returns:
            Dict com posicao_prevista, forcas_predominantes, etc.
        """
        # Prever posição absoluta futura
        pos_abs_prevista = self.kalman.prever_futuro(delta_t_futuro)
        
        # Converter para posição no estator
        pos_estator = int(pos_abs_prevista) % self.partes_estator
        
        # Forças predominantes
        predominantes = []
        if self.ultimo_resultado_clustering:
            predominantes = self.clustering.obter_predominantes(
                self.ultimo_resultado_clustering
            )
        
        # Padrão
        padrao = ""
        if self.ultimo_resultado_clustering:
            padrao = self.clustering.obter_padrao(
                self.ultimo_resultado_clustering.get("classificacao", []),
                6
            )
        
        # Tendência
        aceleracao = self.kalman.aceleracao
        if aceleracao > 0.5:
            tendencia = "ACELERANDO"
        elif aceleracao < -0.5:
            tendencia = "DESACELERANDO"
        else:
            tendencia = "ESTAVEL"
        
        return {
            "posicao_estator": pos_estator,
            "posicao_absoluta": pos_abs_prevista,
            "forcas_predominantes": predominantes,
            "padrao": padrao,
            "tendencia": tendencia,
            "confianca": self.kalman.get_confianca()
        }
    
    def get_clusters(self) -> Dict:
        """Retorna informações dos clusters."""
        if not self.ultimo_resultado_clustering:
            return {"X": None, "Y": None, "Z": None}
        
        result = {}
        for nome in ["X", "Y", "Z"]:
            cluster = self.ultimo_resultado_clustering.get(nome)
            if cluster:
                result[nome] = {
                    "centro": cluster.centro,
                    "min": cluster.range_min,
                    "max": cluster.range_max,
                    "count": cluster.count
                }
            else:
                result[nome] = None
        
        return result
    
    def get_estado(self) -> Dict:
        """Retorna estado completo da linha."""
        return {
            "direcao": self.direcao,
            "posicao_absoluta": self.posicao_absoluta_atual,
            "ultima_posicao_estator": self.ultima_posicao_estator,
            "total_jogadas": self.total_jogadas,
            "total_outliers": self.total_outliers,
            "kalman": {
                "posicao": self.kalman.posicao,
                "velocidade": self.kalman.velocidade,
                "aceleracao": self.kalman.aceleracao
            },
            "clusters": self.get_clusters(),
            "ultimas_forcas": self.historico_forcas[-12:] if self.historico_forcas else []
        }


class ForcePredictorV2:
    """
    Sistema Preditivo de Forças v2 com DUAS LINHAS INDEPENDENTES.
    
    Mantém:
    - Uma LinhaDirecional para HORÁRIO
    - Uma LinhaDirecional para ANTI-HORÁRIO
    
    Cada linha tem sua própria posição absoluta crescente
    e seu próprio Filtro de Kalman.
    """
    
    def __init__(self, partes_estator: int = 37):
        """
        Args:
            partes_estator: Número de partes do estator (37)
        """
        self.partes_estator = partes_estator
        
        # DUAS LINHAS INDEPENDENTES
        self.linha_horario = LinhaDirecional("horario", partes_estator)
        self.linha_anti_horario = LinhaDirecional("anti-horario", partes_estator)
        
        # Última direção processada
        self.ultima_direcao: Optional[str] = None
    
    def _get_linha(self, direcao: str) -> LinhaDirecional:
        """Retorna a linha correspondente à direção."""
        if direcao == "horario":
            return self.linha_horario
        else:
            return self.linha_anti_horario
    
    def processar_jogada(
        self,
        posicao_estator: int,
        direcao: str,
        is_outlier: bool = False,
        delta_t: float = 1.0
    ) -> ResultadoPredicaoV2:
        """
        Processa uma nova jogada e prevê a PRÓXIMA (direção oposta).
        
        Args:
            posicao_estator: Posição final no estator (0-37)
            direcao: "horario" ou "anti-horario"
            is_outlier: Se a jogada é outlier
            delta_t: Delta de tempo
            
        Returns:
            ResultadoPredicaoV2 para a PRÓXIMA jogada (direção oposta)
        """
        # Processar na linha correspondente
        linha = self._get_linha(direcao)
        resultado_processamento = linha.processar_jogada(
            posicao_estator, 
            is_outlier, 
            delta_t
        )
        
        self.ultima_direcao = direcao
        
        # A PRÓXIMA jogada será na direção OPOSTA
        direcao_proxima = "anti-horario" if direcao == "horario" else "horario"
        linha_proxima = self._get_linha(direcao_proxima)
        
        # Prever para a direção da próxima jogada
        previsao = linha_proxima.prever_proxima(delta_t)
        
        return ResultadoPredicaoV2(
            direcao=direcao_proxima,
            posicao_prevista=previsao["posicao_estator"],
            posicao_absoluta_prevista=previsao["posicao_absoluta"],
            forcas_predominantes=previsao["forcas_predominantes"],
            padrao=previsao["padrao"],
            confianca=previsao["confianca"],
            tendencia=previsao["tendencia"],
            estado={
                "linha_atual": linha.get_estado(),
                "linha_proxima": linha_proxima.get_estado(),
                "processamento": resultado_processamento
            }
        )
    
    def get_previsao_direcao(self, direcao: str) -> Dict:
        """
        Retorna previsão para uma direção específica.
        
        Útil para obter previsão sem processar uma jogada.
        """
        linha = self._get_linha(direcao)
        return linha.prever_proxima()
    
    def get_estado_completo(self) -> Dict:
        """Retorna estado completo de ambas as linhas."""
        return {
            "horario": self.linha_horario.get_estado(),
            "anti_horario": self.linha_anti_horario.get_estado(),
            "ultima_direcao": self.ultima_direcao
        }
    
    def get_clusters_direcao(self, direcao: str) -> Dict:
        """Retorna clusters de uma direção específica."""
        linha = self._get_linha(direcao)
        return linha.get_clusters()
    
    def get_forcas_direcao(self, direcao: str, n: int = 12) -> List[int]:
        """Retorna últimas N forças de uma direção."""
        linha = self._get_linha(direcao)
        return linha.historico_forcas[-n:] if linha.historico_forcas else []


# ==============================================================================
# TESTE
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TESTE DO SISTEMA v2 - DUAS LINHAS INDEPENDENTES")
    print("=" * 70)
    
    predictor = ForcePredictorV2()
    
    # Simular jogadas alternadas
    jogadas = [
        # (posicao, direcao)
        (15, "horario"),      # H: 0→15 (força 15)
        (0, "anti-horario"),  # AH: ?→0 (primeira)
        (30, "horario"),      # H: 15→30 (força 15)
        (22, "anti-horario"), # AH: 0→22 (força 22)
        (8, "horario"),       # H: 30→8 (força 15, passou 37→0)
        (8, "anti-horario"),  # AH: 22→8 (força 14)
        (22, "horario"),      # H: 8→22 (força 14)
        (31, "anti-horario"), # AH: 8→31 (força 14)
    ]
    
    print("\nProcessando jogadas...")
    print("-" * 70)
    
    for i, (pos, direcao) in enumerate(jogadas):
        resultado = predictor.processar_jogada(pos, direcao)
        
        print(f"\nJogada {i+1}: pos={pos}, dir={direcao}")
        print(f"  Força bruta: {resultado.estado['processamento']['forca_bruta']}")
        print(f"  Linha {direcao} pos_abs: {resultado.estado['linha_atual']['posicao_absoluta']:.0f}")
        print(f"  PRÓXIMA ({resultado.direcao}): pos={resultado.posicao_prevista}")
        print(f"  Forças {resultado.direcao}: {resultado.forcas_predominantes}")
        print(f"  Tendência: {resultado.tendencia}")
    
    print("\n" + "=" * 70)
    print("ESTADO FINAL")
    print("=" * 70)
    
    estado = predictor.get_estado_completo()
    
    print(f"\nLINHA HORÁRIA:")
    print(f"  Posição absoluta: {estado['horario']['posicao_absoluta']:.0f}")
    print(f"  Total jogadas: {estado['horario']['total_jogadas']}")
    print(f"  Últimas forças: {estado['horario']['ultimas_forcas']}")
    print(f"  Clusters: {estado['horario']['clusters']}")
    
    print(f"\nLINHA ANTI-HORÁRIA:")
    print(f"  Posição absoluta: {estado['anti_horario']['posicao_absoluta']:.0f}")
    print(f"  Total jogadas: {estado['anti_horario']['total_jogadas']}")
    print(f"  Últimas forças: {estado['anti_horario']['ultimas_forcas']}")
    print(f"  Clusters: {estado['anti_horario']['clusters']}")
    
    print("\n✓ Teste v2 concluído!")
