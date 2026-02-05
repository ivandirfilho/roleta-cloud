"""
Integração do Sistema Preditivo de Forças V2 com o Sistema Existente

Este módulo conecta o ForcePredictorV2 (duas linhas independentes)
ao GameStateManager existente.
"""

from typing import Dict, List, Optional
from force_predictor_v2 import ForcePredictorV2, ResultadoPredicaoV2


class ForcePredictorIntegrationV2:
    """
    Integra o sistema de predição v2 (duas linhas) com o GameStateManager.
    """
    
    _instance: Optional['ForcePredictorIntegrationV2'] = None
    
    @classmethod
    def get_instance(cls) -> 'ForcePredictorIntegrationV2':
        """Singleton para manter estado entre chamadas."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Inicializa o preditor v2."""
        self.predictor = ForcePredictorV2(partes_estator=37)
        self.ultima_predicao: Optional[ResultadoPredicaoV2] = None
        self.inicializado = False
        
        print("[ForcePredictorV2] Inicializado com duas linhas independentes.")
    
    def sincronizar_com_historico(self, banco_de_dados_completo: List[Dict]):
        """
        Sincroniza o preditor com o histórico existente.
        
        Processa todas as jogadas do histórico para reconstruir
        as duas linhas de posição absoluta.
        
        Args:
            banco_de_dados_completo: Lista de jogadas (índice 0 = mais recente)
        """
        if not banco_de_dados_completo:
            return
        
        # Resetar o preditor
        self.predictor = ForcePredictorV2(partes_estator=37)
        
        # Processar do mais antigo para o mais recente
        for jogada in reversed(banco_de_dados_completo):
            posicao = jogada.get('numero', 0)
            direcao_str = jogada.get('direcao', 'horario')
            is_outlier = jogada.get('is_outlier', False)
            
            # Converter direção
            direcao = "horario" if direcao_str == "horario" else "anti-horario"
            
            # Processar no preditor
            self.predictor.processar_jogada(
                posicao_estator=posicao,
                direcao=direcao,
                is_outlier=is_outlier,
                delta_t=1.0
            )
        
        self.inicializado = True
        print(f"[ForcePredictorV2] Sincronizado com {len(banco_de_dados_completo)} jogadas.")
    
    def processar_jogada(
        self,
        posicao_estator: int,
        direcao: str,
        is_outlier: bool = False
    ) -> ResultadoPredicaoV2:
        """
        Processa uma nova jogada.
        
        Args:
            posicao_estator: Número sorteado (0-36)
            direcao: "horario" ou "anti-horario"
            is_outlier: Se é outlier
            
        Returns:
            ResultadoPredicaoV2 com previsão para próxima jogada
        """
        resultado = self.predictor.processar_jogada(
            posicao_estator=posicao_estator,
            direcao=direcao,
            is_outlier=is_outlier,
            delta_t=1.0
        )
        
        self.ultima_predicao = resultado
        return resultado
    
    def get_clusters_para_direcao_alvo(self, direcao_alvo: str) -> Dict:
        """
        Retorna os clusters X, Y, Z para a direção alvo.
        
        Args:
            direcao_alvo: "horario" ou "anti-horario"
            
        Returns:
            Dict com clusters X, Y, Z
        """
        return self.predictor.get_clusters_direcao(direcao_alvo)
    
    def get_forcas_para_direcao_alvo(self, direcao_alvo: str, n: int = 12) -> List[int]:
        """
        Retorna as últimas N forças da direção alvo.
        
        Args:
            direcao_alvo: "horario" ou "anti-horario"
            n: Quantidade de forças
            
        Returns:
            Lista de forças
        """
        return self.predictor.get_forcas_direcao(direcao_alvo, n)
    
    def get_previsao_para_direcao(self, direcao: str) -> Dict:
        """
        Retorna previsão para uma direção específica.
        
        Args:
            direcao: "horario" ou "anti-horario"
            
        Returns:
            Dict com posição prevista, forças, tendência
        """
        return self.predictor.get_previsao_direcao(direcao)
    
    def get_estado_completo(self) -> Dict:
        """Retorna estado completo de ambas as linhas."""
        return self.predictor.get_estado_completo()
    
    def calcular_clusters_localmente(self, forcas: List[int]) -> Dict:
        """
        Calcula clusters X, Y, Z para uma lista de forças.
        Útil para exibição na UI sem modificar o estado do preditor.
        
        Args:
            forcas: Lista de forças brutas
            
        Returns:
            Dict com clusters X, Y, Z
        """
        if len(forcas) < 2:
            return {"X": None, "Y": None, "Z": None, "classificacao": []}
        
        GRAVIDADE = 5
        RAIO = (GRAVIDADE - 1) // 2  # 2
        MINIMO = 2
        
        def encontrar_cluster(forcas_disponiveis, excluir):
            disponiveis = [f for f in forcas_disponiveis if f not in excluir]
            if len(disponiveis) < MINIMO:
                return None
            
            melhor_centro = None
            melhor_count = 0
            membros_melhor = []
            
            for candidato in set(disponiveis):
                range_min = candidato - RAIO
                range_max = candidato + RAIO
                membros = [f for f in disponiveis if range_min <= f <= range_max]
                if len(membros) > melhor_count:
                    melhor_count = len(membros)
                    melhor_centro = candidato
                    membros_melhor = membros
            
            if melhor_count >= MINIMO:
                return {
                    "centro": melhor_centro, 
                    "min": melhor_centro - RAIO, 
                    "max": melhor_centro + RAIO, 
                    "membros": membros_melhor, 
                    "count": melhor_count
                }
            return None
        
        excluir = []
        clusters = {}
        
        cluster_x = encontrar_cluster(forcas, excluir)
        if cluster_x:
            clusters["X"] = cluster_x
            excluir.extend(cluster_x["membros"])
        
        cluster_y = encontrar_cluster(forcas, excluir)
        if cluster_y:
            clusters["Y"] = cluster_y
            excluir.extend(cluster_y["membros"])
        
        cluster_z = encontrar_cluster(forcas, excluir)
        if cluster_z:
            clusters["Z"] = cluster_z
        
        # Classificar cada força
        classificacao = []
        for forca in forcas:
            if "X" in clusters and clusters["X"]["min"] <= forca <= clusters["X"]["max"]:
                classificacao.append(("X", forca))
            elif "Y" in clusters and clusters["Y"]["min"] <= forca <= clusters["Y"]["max"]:
                classificacao.append(("Y", forca))
            elif "Z" in clusters and clusters["Z"]["min"] <= forca <= clusters["Z"]["max"]:
                classificacao.append(("Z", forca))
            else:
                classificacao.append(("?", forca))
        
        clusters["classificacao"] = classificacao
        return clusters


# Singleton global para acesso fácil
_predictor_v2: Optional[ForcePredictorIntegrationV2] = None


def get_predictor_v2() -> ForcePredictorIntegrationV2:
    """Retorna a instância global do preditor v2."""
    global _predictor_v2
    if _predictor_v2 is None:
        _predictor_v2 = ForcePredictorIntegrationV2()
    return _predictor_v2


# ==============================================================================
# TESTE
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TESTE DE INTEGRAÇÃO V2")
    print("=" * 70)
    
    # Simular banco_de_dados_completo
    banco_simulado = [
        {"numero": 25, "distancia": 15, "direcao": "horario", "is_outlier": False},
        {"numero": 10, "distancia": 14, "direcao": "anti-horario", "is_outlier": False},
        {"numero": 33, "distancia": 15, "direcao": "horario", "is_outlier": False},
        {"numero": 18, "distancia": 28, "direcao": "anti-horario", "is_outlier": False},
        {"numero": 27, "distancia": 14, "direcao": "horario", "is_outlier": False},
        {"numero": 13, "distancia": 29, "direcao": "anti-horario", "is_outlier": False},
        {"numero": 36, "distancia": 15, "direcao": "horario", "is_outlier": False},
        {"numero": 21, "distancia": 14, "direcao": "anti-horario", "is_outlier": False},
    ]
    
    integration = ForcePredictorIntegrationV2()
    
    # Sincronizar com histórico
    integration.sincronizar_com_historico(banco_simulado)
    
    # Verificar estado
    estado = integration.get_estado_completo()
    
    print("\nEstado após sincronização:")
    print(f"  Linha HORÁRIA:")
    print(f"    Posição absoluta: {estado['horario']['posicao_absoluta']:.0f}")
    print(f"    Forças: {estado['horario']['ultimas_forcas']}")
    
    print(f"\n  Linha ANTI-HORÁRIA:")
    print(f"    Posição absoluta: {estado['anti_horario']['posicao_absoluta']:.0f}")
    print(f"    Forças: {estado['anti_horario']['ultimas_forcas']}")
    
    # Processar nova jogada
    resultado = integration.processar_jogada(
        posicao_estator=5,
        direcao="horario",
        is_outlier=False
    )
    
    print(f"\nNova jogada processada (horário → 5):")
    print(f"  Próxima será: {resultado.direcao}")
    print(f"  Posição prevista: {resultado.posicao_prevista}")
    print(f"  Forças predominantes: {resultado.forcas_predominantes}")
    print(f"  Tendência: {resultado.tendencia}")
    
    print("\n✓ Teste de integração v2 concluído!")
