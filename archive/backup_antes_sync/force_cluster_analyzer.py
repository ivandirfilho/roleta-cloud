"""
ANALISADOR DE CLUSTERS DE FORÇA X, Y, Z - BIDIRECIONAL
=======================================================
Sistema de identificação de 3 grupos de força por gravidade,
com análise de comportamento ISOLADO e previsão de destino por cluster.

IMPORTANTE: Análise SEPARADA para cada sentido (Horário e Anti-Horário)
porque o comportamento das forças é completamente diferente em cada sentido.

Autor: Sistema Kalman Avançado
Data: 2024-12
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from collections import Counter
import config


class ClusterForca:
    """Representa um cluster de forças (X, Y ou Z)"""
    
    def __init__(self, nome: str, centro: float, membros: List[float], sentido: str = ""):
        self.nome = nome  # 'X', 'Y' ou 'Z'
        self.centro = centro
        self.membros = membros
        self.count = len(membros)
        self.sentido = sentido  # 'horario' ou 'anti-horario'
        
        # Análise de comportamento ISOLADO
        self.tendencia = 0.0  # Tendência temporal DENTRO do cluster
        self.status = "➡️ Estável"  # "⬆️ Acelerando", "⬇️ Desacelerando", "➡️ Estável"
        
        # Previsão ISOLADA
        self.forca_prevista = centro  # Força prevista para este cluster
        self.destino = None  # Número da roleta previsto para este cluster
        self.regiao_destino = []  # Região de destino (7 números)
        
    def __repr__(self):
        s = "H" if self.sentido == "horario" else "AH"
        return f"Cluster {self.nome}({s}): centro={self.centro:.1f}, tendência={self.tendencia:+.1f}, destino={self.destino}"


class AnalisadorClustersBidirecional:
    """
    Analisa forças e identifica 3 clusters principais (X, Y, Z)
    SEPARADAMENTE para cada sentido (Horário e Anti-Horário).
    
    Cada sentido tem seus próprios:
    - Clusters X, Y, Z
    - Tendências isoladas
    - Destinos calculados
    - Regiões de saída
    """
    
    def __init__(self, raio_gravitacional: float = 3.5):
        """
        Args:
            raio_gravitacional: Raio para agrupar forças em um cluster (default ±3.5 = gravidade 7)
        """
        self.raio = raio_gravitacional
        
        # Clusters SEPARADOS por sentido
        self.clusters_horario: Dict[str, Optional[ClusterForca]] = {'X': None, 'Y': None, 'Z': None}
        self.clusters_anti_horario: Dict[str, Optional[ClusterForca]] = {'X': None, 'Y': None, 'Z': None}
        
        # Sequência SEPARADA por sentido
        self.sequencia_horario = []
        self.sequencia_anti_horario = []
        
        # Resultados SEPARADOS por sentido
        self.resultado_horario = None
        self.resultado_anti_horario = None
        
    def _identificar_clusters_sentido(self, forcas: List[float], sentido: str) -> Dict[str, Optional[ClusterForca]]:
        """
        Identifica os 3 clusters X, Y, Z das últimas 12 forças de UM sentido específico.
        """
        if not forcas or len(forcas) < 3:
            return {'X': None, 'Y': None, 'Z': None}
        
        # Usar últimas 12 forças
        forcas_analisar = forcas[-12:] if len(forcas) >= 12 else forcas[:]
        forcas_disponiveis = list(forcas_analisar)
        
        clusters_result = {}
        nomes_clusters = ['X', 'Y', 'Z']
        
        for nome in nomes_clusters:
            if len(forcas_disponiveis) < 2:
                clusters_result[nome] = None
                continue
                
            # Encontrar o maior cluster de gravidade 7
            melhor_centro = None
            melhor_membros = []
            
            for candidato in set(forcas_disponiveis):
                # Pegar todos dentro do raio
                membros = [f for f in forcas_disponiveis 
                          if abs(f - candidato) <= self.raio]
                
                if len(membros) > len(melhor_membros):
                    melhor_membros = membros
                    melhor_centro = np.mean(membros)
            
            if melhor_membros:
                cluster = ClusterForca(nome, melhor_centro, melhor_membros, sentido)
                clusters_result[nome] = cluster
                
                # Remover membros usados para próximo cluster
                for m in melhor_membros:
                    if m in forcas_disponiveis:
                        forcas_disponiveis.remove(m)
            else:
                clusters_result[nome] = None
        
        return clusters_result
    
    def identificar_clusters_bidirecionais(self, forcas_horario: List[float], 
                                           forcas_anti_horario: List[float]) -> Dict[str, Dict]:
        """
        Identifica clusters para AMBOS os sentidos.
        
        Args:
            forcas_horario: Lista de forças do sentido horário
            forcas_anti_horario: Lista de forças do sentido anti-horário
            
        Returns:
            Dict com 'horario' e 'anti_horario', cada um com seus clusters
        """
        self.clusters_horario = self._identificar_clusters_sentido(forcas_horario, "horario")
        self.clusters_anti_horario = self._identificar_clusters_sentido(forcas_anti_horario, "anti-horario")
        
        return {
            'horario': self.clusters_horario,
            'anti_horario': self.clusters_anti_horario
        }
    
    def _classificar_forca(self, forca: float, clusters: Dict[str, ClusterForca]) -> str:
        """Classifica uma força como X, Y, Z ou '?' para um conjunto de clusters."""
        if not any(clusters.values()):
            return '?'
        
        for nome in ['X', 'Y', 'Z']:
            cluster = clusters.get(nome)
            if cluster and abs(forca - cluster.centro) <= self.raio:
                return nome
        
        return '?'
    
    def gerar_sequencias_ui(self, forcas_horario: List[float], 
                           forcas_anti_horario: List[float], n: int = 6) -> Dict[str, List[str]]:
        """Gera sequências de classificações para exibir na UI, separadas por sentido."""
        
        # Horário
        forcas_h = forcas_horario[-n:] if len(forcas_horario) >= n else forcas_horario
        self.sequencia_horario = [self._classificar_forca(f, self.clusters_horario) for f in forcas_h]
        
        # Anti-horário
        forcas_ah = forcas_anti_horario[-n:] if len(forcas_anti_horario) >= n else forcas_anti_horario
        self.sequencia_anti_horario = [self._classificar_forca(f, self.clusters_anti_horario) for f in forcas_ah]
        
        return {
            'horario': self.sequencia_horario,
            'anti_horario': self.sequencia_anti_horario
        }
    
    def _analisar_tendencia_sentido(self, forcas: List[float], 
                                    clusters: Dict[str, ClusterForca]) -> Dict[str, ClusterForca]:
        """
        Analisa a tendência temporal ISOLADA de cada cluster para UM sentido.
        """
        if not clusters.get('X') or len(forcas) < 3:
            return clusters
        
        # Criar histórico temporal
        historico_temporal = []
        for i, forca in enumerate(forcas):
            cluster_id = self._classificar_forca(forca, clusters)
            historico_temporal.append((i, forca, cluster_id))
        
        # Para cada cluster, analisar tendência DENTRO dele
        for nome in ['X', 'Y', 'Z']:
            cluster = clusters.get(nome)
            if not cluster:
                continue
            
            # Pegar forças que pertencem a este cluster (em ordem temporal)
            forcas_do_cluster = [(idx, f) for idx, f, c in historico_temporal if c == nome]
            
            if len(forcas_do_cluster) >= 2:
                # Calcular variações DENTRO do cluster
                variacoes = []
                for i in range(1, len(forcas_do_cluster)):
                    delta = forcas_do_cluster[i][1] - forcas_do_cluster[i-1][1]
                    variacoes.append(delta)
                
                tendencia = np.mean(variacoes) if variacoes else 0.0
                
                # Limitar tendência para evitar overshooting
                tendencia = max(-3.0, min(3.0, tendencia))
                
                cluster.tendencia = tendencia
                cluster.forca_prevista = cluster.centro + tendencia
                
                # Status visual
                if tendencia > 0.3:
                    cluster.status = f"⬆️ +{tendencia:.1f}"
                elif tendencia < -0.3:
                    cluster.status = f"⬇️ {tendencia:.1f}"
                else:
                    cluster.status = "➡️ Estável"
            else:
                cluster.forca_prevista = cluster.centro
                cluster.status = "➡️ Estável"
        
        return clusters
    
    def analisar_tendencias_bidirecionais(self, forcas_horario: List[float],
                                           forcas_anti_horario: List[float]) -> Dict[str, Dict]:
        """
        Analisa tendências para AMBOS os sentidos.
        """
        self.clusters_horario = self._analisar_tendencia_sentido(forcas_horario, self.clusters_horario)
        self.clusters_anti_horario = self._analisar_tendencia_sentido(forcas_anti_horario, self.clusters_anti_horario)
        
        return {
            'horario': self.clusters_horario,
            'anti_horario': self.clusters_anti_horario
        }
    
    def _calcular_destinos_sentido(self, clusters: Dict[str, ClusterForca], 
                                   posicao_inicial: int, sentido: int,
                                   forcas_historico: List[float] = None) -> Dict[str, ClusterForca]:
        """
        Calcula o destino geométrico para cada cluster de UM sentido.
        
        NOVO MODELO (v2.0):
        - Base: Força média do cluster (85%)
        - Tendência: Calculada do histórico do cluster (7.5%)
        - Jerk: Taxa de mudança da tendência (5%)
        - VPS: Ajuste baseado em velocidade padrão (2.5%)
        
        Fórmula: força_final = (base * 0.85) + (tendência * 0.075) + (jerk * 0.05) + (vps * 0.025)
        """
        roda = config.ROULETTE_WHEEL_ORDER if hasattr(config, 'ROULETTE_WHEEL_ORDER') else list(range(37))
        n = len(roda)
        
        if posicao_inicial not in roda:
            posicao_inicial = 0
        
        idx_inicial = roda.index(posicao_inicial)
        
        # Pesos do novo modelo (v2.3)
        # Total: 35 + 50 + 15 + 0 = 100%
        PESO_BASE = 0.35        # 35% - Força média do cluster
        PESO_TENDENCIA = 0.50   # 50% - Variação da força (tendência)
        PESO_JERK = 0.15        # 15% - Variação da aceleração
        PESO_VPS = 0.0          # 0% - Desativado
        
        for nome in ['X', 'Y', 'Z']:
            cluster = clusters.get(nome)
            if not cluster:
                continue
            
            # Sentido em string para logs
            sentido_str = "horario" if sentido == 1 else "anti-horario"
            
            # 1. BASE: Força média do cluster (85%)
            forca_base = cluster.centro  # Já é a média dos membros
            
            # 2. TENDÊNCIA: Calcular a partir do histórico do cluster (7.5%)
            tendencia = 0.0
            forcas_cluster_count = 0
            if forcas_historico and len(forcas_historico) >= 3:
                # Filtrar forças que pertencem a este cluster (dentro do raio)
                forcas_cluster = [f for f in forcas_historico if abs(f - cluster.centro) <= self.raio]
                forcas_cluster_count = len(forcas_cluster)
                
                if len(forcas_cluster) >= 2:
                    # Calcular variações das forças do cluster
                    deltas = [forcas_cluster[i] - forcas_cluster[i-1] for i in range(1, len(forcas_cluster))]
                    if deltas:
                        tendencia_bruta = np.mean(deltas[-5:])  # Últimas 5 variações
                        tendencia = max(-15.0, min(15.0, tendencia_bruta))  # Limitar a ±15
            
            # 3. JERK: Taxa de mudança da tendência (5%)
            jerk = 0.0
            if forcas_historico and len(forcas_historico) >= 4:
                forcas_cluster = [f for f in forcas_historico if abs(f - cluster.centro) <= self.raio]
                if len(forcas_cluster) >= 3:
                    deltas = [forcas_cluster[i] - forcas_cluster[i-1] for i in range(1, len(forcas_cluster))]
                    if len(deltas) >= 2:
                        jerks = [deltas[i] - deltas[i-1] for i in range(1, len(deltas))]
                        if jerks:
                            jerk = np.mean(jerks[-3:])  # Últimos 3 jerks
            
            # 4. VPS: Ajuste baseado em velocidade padrão (2.5%)
            # Assumindo VPS médio de 1.0, ajuste neutro
            ajuste_vps = forca_base * 0.03  # Pequeno boost padrão
            
            # 5. CALCULAR FORÇA FINAL PONDERADA
            forca_final = (
                (forca_base * PESO_BASE) + 
                (tendencia * PESO_TENDENCIA * forca_base) +  # Tendência proporcional à base
                (jerk * PESO_JERK * forca_base) +            # Jerk proporcional à base
                (ajuste_vps * PESO_VPS)
            )
            
            # Normalizar para manter escala (soma dos pesos = 1.0 aprox)
            forca_final = forca_final / (PESO_BASE + PESO_TENDENCIA + PESO_JERK + PESO_VPS)
            
            # Limitar a valores físicos razoáveis
            forca_final = max(1.0, min(37.0, forca_final))
            
            # DEBUG: Mostrar fluxo completo
            print(f"[CLUSTER {nome}] Sentido: {sentido_str}")
            print(f"   Base (85%): {forca_base:.1f} | Membros cluster: {forcas_cluster_count}")
            print(f"   Tendência (7.5%): {tendencia:.2f} | Jerk (5%): {jerk:.2f} | VPS (2.5%): {ajuste_vps:.2f}")
            print(f"   FORÇA FINAL: {forca_final:.2f} casas")
            
            # Atualizar a força prevista do cluster
            cluster.forca_prevista = forca_final
            
            # Calcular deslocamento e destino
            deslocamento = int(round(forca_final)) * sentido
            idx_final = (idx_inicial + deslocamento) % n
            cluster.destino = roda[idx_final]
            print(f"   DESTINO: {cluster.destino} (deslocamento: {deslocamento} casas)")
        
        return clusters
    
    def _gerar_regioes_sentido(self, clusters: Dict[str, ClusterForca],
                               posicao_inicial: int, sentido: int,
                               gravidade: int = 7,
                               forcas_historico: List[float] = None) -> Dict[str, any]:
        """
        Gera 3 regiões de saída SEM sobreposição para UM sentido.
        """
        roda = config.ROULETTE_WHEEL_ORDER if hasattr(config, 'ROULETTE_WHEEL_ORDER') else list(range(37))
        n = len(roda)
        
        # Primeiro calcular destinos (agora com filtro ponderado v2.0)
        clusters = self._calcular_destinos_sentido(clusters, posicao_inicial, sentido, forcas_historico)
        
        def gerar_regiao_centrada(destino: int, tamanho: int, excluir: set) -> List[int]:
            """Gera região centrada em 'destino' com 'tamanho' números"""
            if destino not in roda:
                return []
            
            idx_centro = roda.index(destino)
            regiao = []
            
            # Adicionar centro se não excluído
            if destino not in excluir:
                regiao.append(destino)
            
            # Expandir para os lados
            offset = 1
            while len(regiao) < tamanho and offset < n // 2:
                # Esquerda
                idx_esq = (idx_centro - offset) % n
                pos_esq = roda[idx_esq]
                if pos_esq not in excluir and pos_esq not in regiao:
                    regiao.append(pos_esq)
                
                if len(regiao) >= tamanho:
                    break
                
                # Direita
                idx_dir = (idx_centro + offset) % n
                pos_dir = roda[idx_dir]
                if pos_dir not in excluir and pos_dir not in regiao:
                    regiao.append(pos_dir)
                
                offset += 1
            
            return regiao[:tamanho]
        
        # Região X (primeiro, sem exclusões)
        cluster_x = clusters.get('X')
        regiao_x = []
        destino_x = None
        if cluster_x and cluster_x.destino is not None:
            destino_x = cluster_x.destino
            regiao_x = gerar_regiao_centrada(destino_x, gravidade, set())
            cluster_x.regiao_destino = regiao_x
        
        # Região Y (excluindo região X)
        cluster_y = clusters.get('Y')
        regiao_y = []
        destino_y = None
        if cluster_y and cluster_y.destino is not None:
            destino_y = cluster_y.destino
            regiao_y = gerar_regiao_centrada(destino_y, gravidade, set(regiao_x))
            cluster_y.regiao_destino = regiao_y
        
        # Região Z (excluindo regiões X e Y)
        cluster_z = clusters.get('Z')
        regiao_z = []
        destino_z = None
        if cluster_z and cluster_z.destino is not None:
            destino_z = cluster_z.destino
            regiao_z = gerar_regiao_centrada(destino_z, gravidade, set(regiao_x) | set(regiao_y))
            cluster_z.regiao_destino = regiao_z
        
        # Total sem duplicatas
        todos = list(regiao_x)
        for num in regiao_y:
            if num not in todos:
                todos.append(num)
        for num in regiao_z:
            if num not in todos:
                todos.append(num)
        
        return {
            'cluster_x': {
                'forca_prevista': cluster_x.forca_prevista if cluster_x else None,
                'tendencia': cluster_x.tendencia if cluster_x else None,
                'status': cluster_x.status if cluster_x else 'N/A',
                'destino': destino_x,
                'regiao': regiao_x
            },
            'cluster_y': {
                'forca_prevista': cluster_y.forca_prevista if cluster_y else None,
                'tendencia': cluster_y.tendencia if cluster_y else None,
                'status': cluster_y.status if cluster_y else 'N/A',
                'destino': destino_y,
                'regiao': regiao_y
            },
            'cluster_z': {
                'forca_prevista': cluster_z.forca_prevista if cluster_z else None,
                'tendencia': cluster_z.tendencia if cluster_z else None,
                'status': cluster_z.status if cluster_z else 'N/A',
                'destino': destino_z,
                'regiao': regiao_z
            },
            'total': todos,
            'cobertura': len(todos),
            'percentual': (len(todos) / 37) * 100
        }
    
    def analisar_completo(self, forcas_horario: List[float], forcas_anti_horario: List[float],
                          posicao_inicial: int, sentido_futuro: str, gravidade: int = 7) -> Dict[str, any]:
        """
        Análise COMPLETA bidirecional:
        1. Identifica clusters para AMBOS os sentidos
        2. Analisa tendências para AMBOS os sentidos
        3. Gera regiões para AMBOS os sentidos
        4. Retorna resultado do sentido FUTURO (o que será jogado)
        
        Args:
            forcas_horario: Lista de forças do sentido horário
            forcas_anti_horario: Lista de forças do sentido anti-horário
            posicao_inicial: Número onde a bola parou (posição de partida)
            sentido_futuro: 'horario' ou 'anti-horario' (sentido da PRÓXIMA jogada)
            gravidade: Tamanho de cada região (default 7)
            
        Returns:
            Dict com resultados para AMBOS os sentidos e resultado principal do sentido futuro
        """
        # 1. Identificar clusters
        self.identificar_clusters_bidirecionais(forcas_horario, forcas_anti_horario)
        
        # 2. Gerar sequências
        self.gerar_sequencias_ui(forcas_horario, forcas_anti_horario)
        
        # 3. Analisar tendências
        self.analisar_tendencias_bidirecionais(forcas_horario, forcas_anti_horario)
        
        # 4. Gerar regiões para AMBOS os sentidos (com filtro ponderado v2.0)
        # Sentido horário: giro = +1
        self.resultado_horario = self._gerar_regioes_sentido(
            self.clusters_horario, posicao_inicial, 1, gravidade, forcas_horario
        )
        self.resultado_horario['sequencia'] = self.sequencia_horario
        
        # Sentido anti-horário: giro = -1
        self.resultado_anti_horario = self._gerar_regioes_sentido(
            self.clusters_anti_horario, posicao_inicial, -1, gravidade, forcas_anti_horario
        )
        self.resultado_anti_horario['sequencia'] = self.sequencia_anti_horario
        
        # 5. Determinar qual é o resultado principal (baseado no sentido futuro)
        if sentido_futuro == "horario":
            resultado_principal = self.resultado_horario
            clusters_principal = self.clusters_horario
        else:
            resultado_principal = self.resultado_anti_horario
            clusters_principal = self.clusters_anti_horario
        
        return {
            'horario': self.resultado_horario,
            'anti_horario': self.resultado_anti_horario,
            'principal': resultado_principal,
            'sentido_futuro': sentido_futuro,
            'clusters_principal': clusters_principal
        }
    
    # ========== MÉTODOS DE COMPATIBILIDADE ==========
    # (Para manter compatibilidade com código existente)
    
    def identificar_clusters(self, forcas: List[float]) -> Dict[str, Optional[ClusterForca]]:
        """Wrapper de compatibilidade - usa anti-horário por padrão"""
        return self._identificar_clusters_sentido(forcas, "anti-horario")
    
    def analisar_tendencia_isolada(self, forcas: List[float]) -> Dict[str, ClusterForca]:
        """Wrapper de compatibilidade"""
        clusters = self._identificar_clusters_sentido(forcas, "anti-horario")
        return self._analisar_tendencia_sentido(forcas, clusters)
    
    def gerar_regioes_saida_por_cluster(self, posicao_inicial: int, 
                                        sentido: int, 
                                        gravidade: int = 7) -> Dict[str, any]:
        """Wrapper de compatibilidade"""
        if sentido == 1:
            return self.resultado_horario if self.resultado_horario else {}
        else:
            return self.resultado_anti_horario if self.resultado_anti_horario else {}


# Alias para manter compatibilidade
AnalisadorClustersForca = AnalisadorClustersBidirecional


# ============================================================
# TESTES
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("TESTE: ANALISADOR DE CLUSTERS BIDIRECIONAL (H e AH)")
    print("=" * 70)
    
    analisador = AnalisadorClustersBidirecional(raio_gravitacional=3.5)
    
    # Forças de exemplo (simula histórico separado por sentido)
    forcas_horario = [15, 14, 16, 8, 9, 7, 8, 7, 15, 16, 14, 8]
    forcas_anti_horario = [22, 21, 23, 12, 11, 10, 22, 23, 11, 12, 10, 22]
    
    # Análise completa
    resultado = analisador.analisar_completo(
        forcas_horario=forcas_horario,
        forcas_anti_horario=forcas_anti_horario,
        posicao_inicial=22,
        sentido_futuro="anti-horario",
        gravidade=7
    )
    
    # Mostrar resultados HORÁRIO
    print("\n[SENTIDO HORÁRIO]")
    print("-" * 50)
    res_h = resultado['horario']
    print(f"  Sequência: {' → '.join(resultado['horario'].get('sequencia', []))}")
    print(f"  X: Força={res_h['cluster_x']['forca_prevista']:.1f} → {res_h['cluster_x']['destino']} ({res_h['cluster_x']['status']})")
    print(f"  Y: Força={res_h['cluster_y']['forca_prevista']:.1f} → {res_h['cluster_y']['destino']} ({res_h['cluster_y']['status']})")
    print(f"  Z: Força={res_h['cluster_z']['forca_prevista']:.1f if res_h['cluster_z']['forca_prevista'] else 'N/A'} → {res_h['cluster_z']['destino']} ({res_h['cluster_z']['status']})")
    print(f"  Total: {res_h['cobertura']} números ({res_h['percentual']:.1f}%)")
    
    # Mostrar resultados ANTI-HORÁRIO
    print("\n[SENTIDO ANTI-HORÁRIO]")
    print("-" * 50)
    res_ah = resultado['anti_horario']
    print(f"  Sequência: {' → '.join(resultado['anti_horario'].get('sequencia', []))}")
    print(f"  X: Força={res_ah['cluster_x']['forca_prevista']:.1f} → {res_ah['cluster_x']['destino']} ({res_ah['cluster_x']['status']})")
    print(f"  Y: Força={res_ah['cluster_y']['forca_prevista']:.1f} → {res_ah['cluster_y']['destino']} ({res_ah['cluster_y']['status']})")
    print(f"  Z: Força={res_ah['cluster_z']['forca_prevista']:.1f if res_ah['cluster_z']['forca_prevista'] else 'N/A'} → {res_ah['cluster_z']['destino']} ({res_ah['cluster_z']['status']})")
    print(f"  Total: {res_ah['cobertura']} números ({res_ah['percentual']:.1f}%)")
    
    # Mostrar resultado principal
    print("\n[RESULTADO PRINCIPAL - Sentido Futuro: " + resultado['sentido_futuro'].upper() + "]")
    print("=" * 50)
    res_p = resultado['principal']
    print(f"  Região X: {res_p['cluster_x']['regiao']}")
    print(f"  Região Y: {res_p['cluster_y']['regiao']}")
    print(f"  Região Z: {res_p['cluster_z']['regiao']}")
    print(f"  TOTAL: {res_p['cobertura']} números únicos")
