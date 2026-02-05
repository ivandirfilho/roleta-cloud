# RoletaV11/strategies/microservice.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Set
from enum import Enum
import json
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1: CONSTANTES E CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

# Ordem física dos números na roleta europeia
ROULETTE_WHEEL_ORDER = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
]

# Configurações do Sanitizer
SANITIZER_CLUSTER_RADIUS = 5
SANITIZER_MIN_CLUSTER_SIZE = 2
SANITIZER_MAX_CLUSTERS = 3  # A, B, C

# ═══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1.5: ARITMÉTICA CIRCULAR PARA FORÇAS
# ═══════════════════════════════════════════════════════════════════════════════

WHEEL_SIZE_FORCA = 37  # Forças de 1 a 37 (circular)

# ═══════════════════════════════════════════════════════════════════════════════
# NOVO SISTEMA DE PREVISÃO - 4 MÓDULOS
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO 1: get_circular_multiplier - "O Físico"
# ═══════════════════════════════════════════════════════════════════════════════

def get_circular_multiplier(anterior: float, atual: float) -> float:
    """
    Calcula o multiplicador físico considerando a natureza circular da roda (1-37).
    """
    if anterior == 0:
        return 1.0  # Fallback para evitar divisão por zero
    
    # Multiplicador linear (sem considerar a volta)
    mult_linear = atual / anterior
    
    # Multiplicador considerando uma volta completa (+37)
    mult_volta = (atual + WHEEL_SIZE_FORCA) / anterior
    
    # Também considerar volta negativa (atual - 37)
    mult_volta_neg = (atual - WHEEL_SIZE_FORCA) / anterior if atual > WHEEL_SIZE_FORCA else float('inf')
    
    # Escolher o multiplicador mais próximo de 1.0 (menor esforço físico)
    candidatos = [mult_linear, mult_volta, mult_volta_neg]
    distancias = [abs(m - 1.0) for m in candidatos]
    melhor_idx = distancias.index(min(distancias))
    
    return candidatos[melhor_idx]


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO 2: classify_trend - "O Rotulador"
# ═══════════════════════════════════════════════════════════════════════════════

def classify_trend(multiplicador: float) -> str:
    """
    Transforma um multiplicador numérico em uma intenção/tendência.
    """
    if 0.98 <= multiplicador <= 1.02:
        return "ESTAVEL"
    elif multiplicador > 1.02:
        return "ACELERACAO"
    else:
        return "DESACELERACAO"


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO 3: arbitrate_trends - "O Tribunal"
# ═══════════════════════════════════════════════════════════════════════════════

# Threshold para detectar multiplicadores extremos (outliers de valor, não de tipo)
MULT_OUTLIER_THRESHOLD = 1.5  # Um mult é outlier se > 1.5x ou < 1/1.5 da mediana

def _pre_filter_extreme_multipliers(movimentos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Pré-filtro: Remove multiplicadores extremos ANTES do Tribunal votar.
    """
    if len(movimentos) < 3:
        return movimentos
    
    mults = [m['mult'] for m in movimentos]
    mediana = sorted(mults)[len(mults) // 2]
    
    # Evitar divisão por zero
    if mediana == 0:
        return movimentos
    
    # Marcar outliers extremos
    filtrado = []
    for mov in movimentos:
        ratio = mov['mult'] / mediana if mediana != 0 else 1.0
        
        # Se o multiplicador é > 1.5x a mediana ou < 1/1.5 da mediana, é extremo
        if ratio > MULT_OUTLIER_THRESHOLD or ratio < (1 / MULT_OUTLIER_THRESHOLD):
            mov['is_extreme_outlier'] = True
        else:
            mov['is_extreme_outlier'] = False
            filtrado.append(mov)
    
    # Se removemos demais, usar os 2 mais recentes não-extremos
    if len(filtrado) < 2:
        # Fallback: usar todos mas marcar os extremos
        return [m for m in movimentos if not m.get('is_extreme_outlier', False)] or movimentos
    
    return filtrado


def arbitrate_trends(lista_4_movimentos: List[Dict[str, Any]]) -> Tuple[List[float], str, int, List[Dict]]:
    """
    O Tribunal: Elimina ruído (outliers) e decide a tendência dominante.
    """
    if len(lista_4_movimentos) < 4:
        # Fallback: usar todos os multiplicadores disponíveis
        return [m['mult'] for m in lista_4_movimentos], "INDEFINIDO", 0, lista_4_movimentos
    
    # ─────────────────────────────────────────────────────────────────────
    # REGRA 0: PRÉ-FILTRO - Remover multiplicadores extremos
    # ─────────────────────────────────────────────────────────────────────
    movimentos_filtrados = _pre_filter_extreme_multipliers(lista_4_movimentos)
    extremos_removidos = len(lista_4_movimentos) - len(movimentos_filtrados)
    
    # Se todos foram filtrados, usar os 2 mais recentes da lista original
    if len(movimentos_filtrados) < 2:
        movimentos_filtrados = sorted(lista_4_movimentos, key=lambda m: m['index'], reverse=True)[:2]
        extremos_removidos = 2
    
    # Contar votos por tipo (usando lista filtrada)
    contagem = {"ACELERACAO": [], "DESACELERACAO": [], "ESTAVEL": []}
    for mov in movimentos_filtrados:
        tipo = mov['tipo']
        if tipo in contagem:
            contagem[tipo].append(mov)
    
    # Ordenar tipos por quantidade de votos (decrescente)
    tipos_ordenados = sorted(contagem.keys(), key=lambda t: len(contagem[t]), reverse=True)
    
    # ─────────────────────────────────────────────────────────────────────
    # REGRA 1: MAIORIA (um tipo tem ≥2 e é único líder)
    # ─────────────────────────────────────────────────────────────────────
    primeiro = tipos_ordenados[0]
    segundo = tipos_ordenados[1]
    
    if len(contagem[primeiro]) >= 2 and len(contagem[primeiro]) > len(contagem[segundo]):
        # Maioria clara - descartar os outros
        variacoes_vencedoras = contagem[primeiro]
        vencedores = [m['mult'] for m in variacoes_vencedoras]
        outliers = 4 - len(vencedores)
        return vencedores, primeiro, outliers, variacoes_vencedoras
    
    # ─────────────────────────────────────────────────────────────────────
    # REGRA 2: DESEMPATE (2 vs 2) - Recência decide
    # ─────────────────────────────────────────────────────────────────────
    if len(contagem[primeiro]) == 2 and len(contagem[segundo]) == 2:
        # Verificar qual grupo contém o movimento mais recente (index 3)
        primeiro_tem_recente = any(m['index'] == 3 for m in contagem[primeiro])
        segundo_tem_recente = any(m['index'] == 3 for m in contagem[segundo])
        
        if primeiro_tem_recente and not segundo_tem_recente:
            variacoes_vencedoras = contagem[primeiro]
            vencedores = [m['mult'] for m in variacoes_vencedoras]
            return vencedores, primeiro, 2, variacoes_vencedoras
        elif segundo_tem_recente and not primeiro_tem_recente:
            variacoes_vencedoras = contagem[segundo]
            vencedores = [m['mult'] for m in variacoes_vencedoras]
            return vencedores, segundo, 2, variacoes_vencedoras
        else:
            # Ambos têm elementos recentes, usar os 2 mais recentes
            variacoes_vencedoras = sorted(lista_4_movimentos, key=lambda m: m['index'], reverse=True)[:2]
            vencedores = [m['mult'] for m in variacoes_vencedoras]
            tendencia = variacoes_vencedoras[0]['tipo']  # Usar tendência do mais recente
            return vencedores, tendencia, 2, variacoes_vencedoras
    
    # ─────────────────────────────────────────────────────────────────────
    # REGRA 3: CAOS (nenhum grupo com 2 votos) - Usar últimos 2
    # ─────────────────────────────────────────────────────────────────────
    variacoes_vencedoras = sorted(lista_4_movimentos, key=lambda m: m['index'], reverse=True)[:2]
    vencedores = [m['mult'] for m in variacoes_vencedoras]
    tendencia = variacoes_vencedoras[0]['tipo']  # Usar tendência do mais recente
    return vencedores, tendencia, 2, variacoes_vencedoras


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO 4: predict_next - "O Executor"
# ═══════════════════════════════════════════════════════════════════════════════

def predict_next(ultima_forca: float, multiplicadores_vencedores: List[float]) -> int:
    """
    Calcula o número final da previsão.
    """
    if not multiplicadores_vencedores:
        return int(ultima_forca) if ultima_forca else 1
    
    # Calcular média dos multiplicadores vencedores
    media = sum(multiplicadores_vencedores) / len(multiplicadores_vencedores)
    
    # Aplicar à última força
    resultado_bruto = ultima_forca * media
    
    # Aplicar módulo 37 para garantir range 1-37
    # Fórmula: ((x - 1) % 37) + 1 garante que 37 permanece 37 e 38 vira 1
    final = int(((resultado_bruto - 1) % WHEEL_SIZE_FORCA) + 1)
    
    # Garantir que está no range
    if final < 1:
        final = 1
    elif final > WHEEL_SIZE_FORCA:
        final = WHEEL_SIZE_FORCA
    
    return final


# ═══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO PRINCIPAL: prever_proxima_forca_v2 - Orquestrador dos 4 Módulos
# ═══════════════════════════════════════════════════════════════════════════════

def prever_proxima_forca(forcas_5: List[float]) -> Dict[str, Any]:
    """
    Previsão de próxima força usando o novo sistema de 4 módulos.
    """
    # Garantir que temos ao menos 5 forças
    if len(forcas_5) < 5:
        # Fallback: retornar última força se não há dados suficientes
        ultima = forcas_5[0] if forcas_5 else 1
        return {
            'forca_prevista': int(ultima),
            'regime': 'DADOS_INSUFICIENTES',
            'outlier_idx': 0,
            'deltas': [],
            'detalhes': {'erro': f'Apenas {len(forcas_5)} forças disponíveis, necessário 5'}
        }
    
    # Inverter para ter F1=antigo, F5=recente (convenção do blueprint)
    # Entrada: [mais_recente, ..., mais_antigo] -> Saída: [antigo, ..., recente]
    F = list(reversed(forcas_5[:5]))  # F[0]=F1 (antigo), F[4]=F5 (recente)
    
    # ═══════════════════════════════════════════════════════════════════
    # PASSO 1: Calcular 4 multiplicadores circulares (Módulo 1)
    # ═══════════════════════════════════════════════════════════════════
    variacoes = []
    for i in range(4):
        anterior = F[i]
        atual = F[i + 1]
        mult = get_circular_multiplier(anterior, atual)
        variacoes.append({
            'mult': mult,
            'anterior': anterior,
            'atual': atual,
            'index': i  # 0=antigo, 3=recente
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # PASSO 2: Classificar cada variação (Módulo 2)
    # ═══════════════════════════════════════════════════════════════════
    for var in variacoes:
        var['tipo'] = classify_trend(var['mult'])
    
    # ═══════════════════════════════════════════════════════════════════
    # PASSO 3: Tribunal - Remover outliers (Módulo 3)
    # ═══════════════════════════════════════════════════════════════════
    multiplicadores_vencedores, tendencia, outliers_removidos, variacoes_vencedoras = arbitrate_trends(variacoes)
    
    # ═══════════════════════════════════════════════════════════════════
    # PASSO 4: Determinar a BASE correta para projeção
    # ═══════════════════════════════════════════════════════════════════
    variacao_mais_recente_sobreviveu = any(v.get('index') == 3 for v in variacoes_vencedoras)
    
    if variacao_mais_recente_sobreviveu:
        # F5 é válida - usar como base
        base_forca = F[4]  # F5
        base_info = "F5 (mais recente, válida)"
    else:
        # F5 é outlier - buscar última força válida
        indices_vencedores = [v.get('index', -1) for v in variacoes_vencedoras]
        if indices_vencedores:
            max_idx_vencedor = max(indices_vencedores)
            base_forca = F[max_idx_vencedor + 1]
            base_info = f"F{max_idx_vencedor + 2} (última válida, F5 era outlier)"
        else:
            # Nenhuma variação vencedora - usar mediana como fallback
            base_forca = sorted(F)[2]  # Mediana das 5 forças
            base_info = "mediana (nenhuma variação válida)"
    
    # ═══════════════════════════════════════════════════════════════════
    # PASSO 5: Calcular previsão final (Módulo 4)
    # ═══════════════════════════════════════════════════════════════════
    forca_prevista = predict_next(base_forca, multiplicadores_vencedores)
    
    # ═══════════════════════════════════════════════════════════════════
    # Montar resultado
    # ═══════════════════════════════════════════════════════════════════
    return {
        'forca_prevista': forca_prevista,
        'regime': tendencia,
        'outlier_idx': outliers_removidos,
        'deltas': multiplicadores_vencedores,
        'detalhes': {
            'forcas_entrada': F,
            'variacoes': [
                {
                    'de': v['anterior'],
                    'para': v['atual'],
                    'mult': round(v['mult'], 3),
                    'tipo': v['tipo'],
                    'vencedora': v in variacoes_vencedoras
                }
                for v in variacoes
            ],
            'tendencia_vencedora': tendencia,
            'multiplicadores_usados': [round(m, 3) for m in multiplicadores_vencedores],
            'media_aplicada': round(sum(multiplicadores_vencedores) / len(multiplicadores_vencedores), 3) if multiplicadores_vencedores else 0,
            'base_forca': base_forca,
            'base_info': base_info,
            'ultima_forca_original': F[4],
            'previsao_final': forca_prevista
        }
    }


# Funções de compatibilidade
def delta_circular(f_atual: int, f_anterior: int) -> int:
    """
    Mantida para compatibilidade. Calcula delta circular simples.
    """
    delta = f_atual - f_anterior
    if delta > WHEEL_SIZE_FORCA // 2:
        delta -= WHEEL_SIZE_FORCA
    elif delta < -WHEEL_SIZE_FORCA // 2:
        delta += WHEEL_SIZE_FORCA
    return delta


def normalizar_forca_circular(forca: float) -> int:
    """
    Mantida para compatibilidade. Normaliza força para range circular.
    """
    return int(round(forca)) % WHEEL_SIZE_FORCA


# ═══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 2: DATA TYPES (Estruturas de Dados)
# ═══════════════════════════════════════════════════════════════════════════════

class Sentido(Enum):
    """Direção do giro da roleta."""
    HORARIO = "horario"
    ANTIHORARIO = "antihorario"
    
    @classmethod
    def from_string(cls, value: str) -> 'Sentido':
        """Converte string para enum."""
        if value.lower() in ('horario', 'h', '1', 'cw', 'clockwise'):
            return cls.HORARIO
        return cls.ANTIHORARIO


@dataclass
class ClusterJerk:
    """Representa um cluster de Jerks identificado."""
    nome: str
    centro: float
    membros: List[float]
    indices: List[int]
    
    @property
    def tamanho(self) -> int:
        return len(self.membros)
    
    @property
    def densidade(self) -> float:
        if self.tamanho <= 1:
            return float(self.tamanho)
        
        dispersao = max(self.membros) - min(self.membros)
        if dispersao == 0:
            return float(self.tamanho) * 2
        
        return self.tamanho / dispersao
    
    def to_dict(self) -> dict:
        return {
            'nome': self.nome,
            'centro': self.centro,
            'membros': self.membros,
            'indices': self.indices,
            'tamanho': self.tamanho,
            'densidade': self.densidade
        }


@dataclass
class SanitizerOutput:
    """Saída do MS-01 Sanitizer."""
    # Dados purificados
    clean_forces: List[float]
    clean_accs: List[float]
    clean_jerks: List[float]
    
    # Crucial para MS-03: última força válida (mais recente)
    last_valid_force: float
    
    # Clusters identificados
    cluster_a: Optional[ClusterJerk] = None
    cluster_b: Optional[ClusterJerk] = None
    cluster_c: Optional[ClusterJerk] = None
    
    # Mapeamento de índices
    indices_forces_validos: List[int] = field(default_factory=list)
    indices_forces_outliers: List[int] = field(default_factory=list)
    indices_jerks_outliers: List[int] = field(default_factory=list)
    
    # Contexto
    sentido: str = ""
    
    # Métricas
    total_original: int = 12
    total_limpo: int = 0
    taxa_sobrevivencia: float = 0.0
    
    # Dados intermediários (para debug/análise)
    all_accs: List[float] = field(default_factory=list)
    all_jerks: List[float] = field(default_factory=list)
    
    def __post_init__(self):
        """Calcula métricas derivadas."""
        self.total_limpo = len(self.clean_forces)
        if self.total_original > 0:
            self.taxa_sobrevivencia = self.total_limpo / self.total_original
    
    @property
    def clusters_validos(self) -> List[ClusterJerk]:
        """Retorna lista de clusters válidos encontrados."""
        clusters = []
        if self.cluster_a:
            clusters.append(self.cluster_a)
        if self.cluster_b:
            clusters.append(self.cluster_b)
        if self.cluster_c:
            clusters.append(self.cluster_c)
        return clusters
    
    def to_dict(self) -> dict:
        """Serializa para dicionário."""
        return {
            'clean_forces': self.clean_forces,
            'clean_accs': self.clean_accs,
            'clean_jerks': self.clean_jerks,
            'last_valid_force': self.last_valid_force,
            'cluster_a': self.cluster_a.to_dict() if self.cluster_a else None,
            'cluster_b': self.cluster_b.to_dict() if self.cluster_b else None,
            'cluster_c': self.cluster_c.to_dict() if self.cluster_c else None,
            'indices_forces_validos': self.indices_forces_validos,
            'indices_forces_outliers': self.indices_forces_outliers,
            'indices_jerks_outliers': self.indices_jerks_outliers,
            'sentido': self.sentido,
            'total_original': self.total_original,
            'total_limpo': self.total_limpo,
            'taxa_sobrevivencia': self.taxa_sobrevivencia,
            'all_accs': self.all_accs,
            'all_jerks': self.all_jerks
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Exporta como JSON formatado."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 3: MS-01 SANITIZER - "A Refinaria"
# ═══════════════════════════════════════════════════════════════════════════════

class Sanitizer:
    """
    MS-01: The Sanitizer - Filtro de Ruído em Cascata
    """
    
    def __init__(self, 
                 cluster_radius: int = SANITIZER_CLUSTER_RADIUS,
                 min_cluster_size: int = SANITIZER_MIN_CLUSTER_SIZE,
                 max_clusters: int = SANITIZER_MAX_CLUSTERS):
        self.cluster_radius = cluster_radius
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
    
    def sanitize(self, raw_forces: List[float], sentido: str) -> SanitizerOutput:
        """
        Pipeline principal de sanitização.
        """
        
        # Validação básica
        if not raw_forces:
            return self._criar_output_vazio(sentido)
        
        total_original = len(raw_forces)
        
        # ETAPA 1: Calcular derivadas
        accs = self._calcular_aceleracoes(raw_forces)
        jerks = self._calcular_jerks(accs)
        
        # ETAPA 2: Clusterizar Jerks e encontrar os 3 maiores
        clusters, jerk_outlier_indices = self._clusterizar_jerks(jerks)
        
        # ETAPA 3: Mapear cascata (jerk outlier → forças contaminadas)
        force_indices_contaminados = self._mapear_cascata_jerk_para_force(
            jerk_outlier_indices, 
            total_original
        )
        
        # ETAPA 4: Criar listas limpas
        force_indices_validos = [
            i for i in range(total_original) 
            if i not in force_indices_contaminados
        ]
        
        clean_forces = [raw_forces[i] for i in force_indices_validos]
        
        # Acelerações limpas (precisamos reindexar baseado nas forças válidas)
        acc_indices_validos = self._mapear_indices_force_para_acc(
            force_indices_validos, 
            len(accs)
        )
        clean_accs = [accs[i] for i in acc_indices_validos]
        
        # Jerks limpos (dos clusters válidos)
        jerk_indices_validos = []
        for cluster in clusters:
            jerk_indices_validos.extend(cluster.indices)
        jerk_indices_validos = sorted(set(jerk_indices_validos))
        clean_jerks = [jerks[i] for i in jerk_indices_validos]
        
        # ETAPA 5: Determinar última força válida
        # A mais recente (índice 0) que sobreviveu ao filtro
        if clean_forces:
            last_valid_force = clean_forces[0]
        elif raw_forces:
            # Fallback: usar a original mais recente
            last_valid_force = raw_forces[0]
        else:
            last_valid_force = 0.0
        
        # ETAPA 6: Montar output
        output = SanitizerOutput(
            clean_forces=clean_forces,
            clean_accs=clean_accs,
            clean_jerks=clean_jerks,
            last_valid_force=last_valid_force,
            cluster_a=clusters[0] if len(clusters) > 0 else None,
            cluster_b=clusters[1] if len(clusters) > 1 else None,
            cluster_c=clusters[2] if len(clusters) > 2 else None,
            indices_forces_validos=force_indices_validos,
            indices_forces_outliers=list(force_indices_contaminados),
            indices_jerks_outliers=list(jerk_outlier_indices),
            sentido=sentido,
            total_original=total_original,
            all_accs=accs,
            all_jerks=jerks
        )
        
        return output
    
    def _calcular_aceleracoes(self, forces: List[float]) -> List[float]:
        """Calcula acelerações (derivada 1)."""
        if len(forces) < 2:
            return []
        return [forces[i] - forces[i + 1] for i in range(len(forces) - 1)]
    
    def _calcular_jerks(self, accs: List[float]) -> List[float]:
        """Calcula jerks (derivada 2)."""
        if len(accs) < 2:
            return []
        return [accs[i] - accs[i + 1] for i in range(len(accs) - 1)]
    
    def _clusterizar_jerks(self, jerks: List[float]) -> Tuple[List[ClusterJerk], Set[int]]:
        """Aplica algoritmo de clustering simplificado (vizinhança linear)."""
        if not jerks:
            return [], set()
        
        clusters = []
        visitados = set()
        
        jerk_indices = sorted(range(len(jerks)), key=lambda k: jerks[k])
        
        for i in jerk_indices:
            if i in visitados:
                continue
            
            valor_base = jerks[i]
            membros_indices = [i]
            visitados.add(i)
            
            # Expandir cluster (range 5)
            for j in jerk_indices:
                if j in visitados:
                    continue
                if abs(jerks[j] - valor_base) <= self.cluster_radius:
                    membros_indices.append(j)
                    visitados.add(j)
            
            if len(membros_indices) >= self.min_cluster_size:
                membros_valores = [jerks[idx] for idx in membros_indices]
                centro = sum(membros_valores) / len(membros_valores)
                clusters.append(ClusterJerk(
                    nome="",
                    centro=centro,
                    membros=membros_valores,
                    indices=membros_indices
                ))
        
        # Ordenar clusters por densidade (maior primeiro) e pegar top N
        clusters.sort(key=lambda c: c.densidade, reverse=True)
        clusters = clusters[:self.max_clusters]
        
        # Nomear clusters
        nomes = ["A", "B", "C"]
        indices_validos = set()
        for idx, cluster in enumerate(clusters):
            cluster.nome = nomes[idx] if idx < len(nomes) else f"C{idx}"
            indices_validos.update(cluster.indices)
        
        # Identificar outliers (índices que não estão em nenhum dos top clusters)
        todos_indices = set(range(len(jerks)))
        jerk_outlier_indices = todos_indices - indices_validos
        
        return clusters, jerk_outlier_indices
    
    def _mapear_cascata_jerk_para_force(self, jerk_outlier_indices: Set[int], total_forces: int) -> Set[int]:
        """
        Mapeia quais forças são contaminadas por um jerk outlier.
        
        Chain Rule:
        Jerk[k] outlier → afeta Acc[k] e Acc[k+1]
        Acc[k] afetado → afeta Force[k] e Force[k+1]
        
        Logo: Jerk[k] contamina Force[k], Force[k+1], Force[k+2]
        """
        force_contaminados = set()
        for jerk_idx in jerk_outlier_indices:
            # Jerk[i] deriva de Acc[i], Acc[i+1]
            # Acc[i] deriva de Force[i], Force[i+1]
            # Acc[i+1] deriva de Force[i+1], Force[i+2]
            
            # Portanto, Jerk[i] conecta Force[i], Force[i+1] e Force[i+2]
            force_contaminados.add(jerk_idx)
            force_contaminados.add(jerk_idx + 1)
            force_contaminados.add(jerk_idx + 2)
        
        # Filtrar índices fora do range
        return {idx for idx in force_contaminados if idx < total_forces}
    
    def _mapear_indices_force_para_acc(self, force_indices_validos: List[int], total_accs: int) -> List[int]:
        """
        Calcula quais acelerações são válidas se tivermos apenas algumas forças válidas.
        Acc[i] precisa de Force[i] E Force[i+1] para existir.
        """
        valid_forces_set = set(force_indices_validos)
        acc_indices_validos = []
        
        for i in range(total_accs):
            if i in valid_forces_set and (i + 1) in valid_forces_set:
                acc_indices_validos.append(i)
        
        return acc_indices_validos

    def _criar_output_vazio(self, sentido: str) -> SanitizerOutput:
        return SanitizerOutput(
            clean_forces=[], clean_accs=[], clean_jerks=[], last_valid_force=0.0, sentido=sentido
        )
