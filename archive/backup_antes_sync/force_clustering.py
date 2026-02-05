"""
Sistema Preditivo de Forças - Algoritmo de Clustering

Implementa o clustering de forças com "gravidade 5" (centro ± 2).
Classifica forças em X, Y, Z ou Outlier.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import Counter

from force_predictor_db import ForcePredictorDB, Cluster


@dataclass
class ClusterResult:
    """Resultado do algoritmo de clustering."""
    centro: int
    range_min: int
    range_max: int
    membros: List[int]
    count: int


class ForceClustering:
    """
    Algoritmo de clustering para classificação de forças.
    
    Usa "gravidade 5" = centro ± 2 (5 números consecutivos).
    Mínimo de 2 membros para formar um cluster válido.
    """
    
    def __init__(self, gravidade: int = 5, minimo: int = 2):
        """
        Args:
            gravidade: Total de números no cluster (5 = centro ± 2)
            minimo: Mínimo de membros para ser um cluster válido
        """
        self.raio = (gravidade - 1) // 2  # gravidade 5 → raio 2
        self.minimo = minimo
    
    def _encontrar_melhor_cluster(
        self, 
        forcas: List[int], 
        excluir: List[int]
    ) -> Optional[ClusterResult]:
        """
        Encontra o centro que tem mais vizinhos dentro do raio.
        
        Args:
            forcas: Lista de forças brutas
            excluir: Lista de forças já classificadas (ignorar)
            
        Returns:
            ClusterResult ou None se não encontrar cluster válido
        """
        # Filtrar forças já classificadas
        disponiveis = [f for f in forcas if f not in excluir]
        
        if len(disponiveis) < self.minimo:
            return None
        
        melhor_centro = None
        melhor_count = 0
        membros_melhor = []
        
        # Para cada valor único, contar vizinhos
        for candidato in set(disponiveis):
            range_min = candidato - self.raio
            range_max = candidato + self.raio
            
            # Contar membros dentro do range
            membros = [f for f in disponiveis 
                       if range_min <= f <= range_max]
            
            if len(membros) > melhor_count:
                melhor_count = len(membros)
                melhor_centro = candidato
                membros_melhor = membros
        
        # Verificar mínimo
        if melhor_count >= self.minimo:
            return ClusterResult(
                centro=melhor_centro,
                range_min=melhor_centro - self.raio,
                range_max=melhor_centro + self.raio,
                membros=membros_melhor,
                count=melhor_count
            )
        
        return None
    
    def classificar(self, forcas: List[int]) -> Dict:
        """
        Classifica as forças em clusters X, Y, Z e identifica outliers.
        
        Args:
            forcas: Lista das últimas N forças brutas (ex: últimas 12)
            
        Returns:
            Dict com clusters X, Y, Z e lista de outliers
        """
        resultado = {
            "X": None,
            "Y": None,
            "Z": None,
            "outliers": [],
            "classificacao": []  # Mapeamento força → cluster
        }
        
        if not forcas:
            return resultado
        
        excluir = []
        
        # Cluster X (mais populoso)
        cluster_x = self._encontrar_melhor_cluster(forcas, excluir)
        if cluster_x:
            resultado["X"] = cluster_x
            excluir.extend(cluster_x.membros)
        
        # Cluster Y (segundo mais populoso)
        cluster_y = self._encontrar_melhor_cluster(forcas, excluir)
        if cluster_y:
            resultado["Y"] = cluster_y
            excluir.extend(cluster_y.membros)
        
        # Cluster Z (terceiro)
        cluster_z = self._encontrar_melhor_cluster(forcas, excluir)
        if cluster_z:
            resultado["Z"] = cluster_z
            excluir.extend(cluster_z.membros)
        
        # Outliers = tudo que sobrou
        resultado["outliers"] = [f for f in forcas if f not in excluir]
        
        # Classificar cada força
        for forca in forcas:
            if resultado["X"] and resultado["X"].range_min <= forca <= resultado["X"].range_max:
                resultado["classificacao"].append(("X", forca))
            elif resultado["Y"] and resultado["Y"].range_min <= forca <= resultado["Y"].range_max:
                resultado["classificacao"].append(("Y", forca))
            elif resultado["Z"] and resultado["Z"].range_min <= forca <= resultado["Z"].range_max:
                resultado["classificacao"].append(("Z", forca))
            else:
                resultado["classificacao"].append(("OUTLIER", forca))
        
        return resultado
    
    def classificar_forca(
        self, 
        forca: int, 
        clusters: Dict
    ) -> Tuple[Optional[str], bool]:
        """
        Classifica uma única força com base nos clusters existentes.
        
        Args:
            forca: Valor da força bruta
            clusters: Dict com clusters X, Y, Z (resultado de classificar())
            
        Returns:
            Tupla (nome_cluster, is_outlier)
            Ex: ("X", False) ou (None, True)
        """
        if clusters["X"] and clusters["X"].range_min <= forca <= clusters["X"].range_max:
            return ("X", False)
        elif clusters["Y"] and clusters["Y"].range_min <= forca <= clusters["Y"].range_max:
            return ("Y", False)
        elif clusters["Z"] and clusters["Z"].range_min <= forca <= clusters["Z"].range_max:
            return ("Z", False)
        else:
            return (None, True)
    
    def obter_predominantes(self, clusters: Dict) -> List[str]:
        """
        Retorna lista das forças predominantes (ativas).
        
        Args:
            clusters: Dict com clusters X, Y, Z
            
        Returns:
            Lista ordenada por frequência: ["X"], ["X", "Y"] ou ["X", "Y", "Z"]
        """
        predominantes = []
        
        if clusters["X"] and clusters["X"].count >= self.minimo:
            predominantes.append(("X", clusters["X"].count))
        if clusters["Y"] and clusters["Y"].count >= self.minimo:
            predominantes.append(("Y", clusters["Y"].count))
        if clusters["Z"] and clusters["Z"].count >= self.minimo:
            predominantes.append(("Z", clusters["Z"].count))
        
        # Ordenar por frequência (decrescente)
        predominantes.sort(key=lambda x: -x[1])
        
        return [p[0] for p in predominantes]
    
    def obter_padrao(self, classificacao: List[Tuple[str, int]], ultimas_n: int = 6) -> str:
        """
        Retorna o padrão das últimas N classificações.
        
        Args:
            classificacao: Lista de (cluster, forca)
            ultimas_n: Quantas últimas classificações analisar
            
        Returns:
            String do padrão, ex: "X-X-Y-X-Y-X"
        """
        if not classificacao:
            return ""
        
        ultimas = classificacao[-ultimas_n:]
        return "-".join([c[0] for c in ultimas])


def converter_para_db_clusters(resultado: Dict) -> List[Cluster]:
    """
    Converte resultado do clustering para objetos Cluster do DB.
    
    Args:
        resultado: Dict retornado por ForceClustering.classificar()
        
    Returns:
        Lista de 3 objetos Cluster (X, Y, Z)
    """
    clusters_db = []
    
    for idx, nome in enumerate(["X", "Y", "Z"], start=1):
        cluster_data = resultado.get(nome)
        
        if cluster_data:
            clusters_db.append(Cluster(
                id=idx,
                nome=nome,
                centro=cluster_data.centro,
                range_min=cluster_data.range_min,
                range_max=cluster_data.range_max,
                membros_count=cluster_data.count,
                atualizado_em=0  # Será preenchido pelo DB
            ))
        else:
            clusters_db.append(Cluster(
                id=idx,
                nome=nome,
                centro=None,
                range_min=None,
                range_max=None,
                membros_count=0,
                atualizado_em=0
            ))
    
    return clusters_db


# ==============================================================================
# TESTE
# ==============================================================================

if __name__ == "__main__":
    # Dados de teste
    forcas_teste = [14, 15, 16, 14, 28, 29, 15, 30, 14, 3, 15, 28]
    
    print("=" * 60)
    print("TESTE DO ALGORITMO DE CLUSTERING")
    print("=" * 60)
    print(f"\nForças de entrada: {forcas_teste}")
    print(f"Gravidade: 5 (centro ± 2)")
    print(f"Mínimo para cluster: 2")
    
    clustering = ForceClustering(gravidade=5, minimo=2)
    resultado = clustering.classificar(forcas_teste)
    
    print("\n--- CLUSTERS ---")
    for nome in ["X", "Y", "Z"]:
        cluster = resultado[nome]
        if cluster:
            print(f"\n{nome}: centro={cluster.centro}, range=[{cluster.range_min}-{cluster.range_max}]")
            print(f"   membros: {cluster.membros} ({cluster.count} ocorrências)")
        else:
            print(f"\n{nome}: (não existe)")
    
    print(f"\nOUTLIERS: {resultado['outliers']}")
    
    print("\n--- CLASSIFICAÇÃO ---")
    for cluster_nome, forca in resultado["classificacao"]:
        print(f"  Força {forca:3d} → {cluster_nome}")
    
    print("\n--- PREDOMINANTES ---")
    predominantes = clustering.obter_predominantes(resultado)
    print(f"Forças ativas: {predominantes}")
    
    print("\n--- PADRÃO ---")
    padrao = clustering.obter_padrao(resultado["classificacao"], 6)
    print(f"Últimas 6: {padrao}")
    
    print("\n" + "=" * 60)
    print("✓ Teste concluído!")
    
    # Verificações
    assert resultado["X"].centro in [14, 15], "Centro X deveria ser ~14-15"
    assert resultado["Y"].centro in [28, 29], "Centro Y deveria ser ~28-29"
    assert 3 in resultado["outliers"], "3 deveria ser outlier"
    print("✓ Todas as verificações passaram!")
