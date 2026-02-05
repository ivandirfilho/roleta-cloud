# strategies.py

"""
Módulo de Estratégias de Aposta para o Roleta Metaverso Pro.

v17.2 (CORREÇÃO CRÍTICA):
- Corrigido o bug fundamental de leitura do histórico.
- Todas as estratégias agora leem o histórico a partir do final (o mais recente)
  usando `historico[-1]` e `...[-N:]` em vez de `historico[0]` e `...[:N]`.
- Isso corrige o bug das "Forças-Alvo" travadas.

v17.1 (ECA+2):
Implementado o filtro de "Score Mínimo para Aposta" na SDA.
A estratégia agora recebe o limiar (1-6) da UI via ContextoAnalise
e só retorna (True, ...) se o score de captura for atingido.
"""

from abc import ABC, abstractmethod
import statistics
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
import numpy as np
import threading
import time
import math
import random
from scipy.stats import skew, kurtosis
from scipy.fft import rfft
import pywt
from statsmodels.tsa.arima.model import ARIMA
from typing import List, Dict, Tuple, Optional, Any, Set
from datetime import datetime
from itertools import combinations
from functools import lru_cache
from annoy import AnnoyIndex


from domain.logic import RouletteLogic
from core import config
from database.persistence import DataPersistence

@dataclass
class ContextoAnalise:
    """Objeto de Transferência de Dados para o contexto da análise."""
    modo_leitura_forca: str = "sentido_oposto"
    vitoria_anterior: Optional[bool] = None
    # [ECA+2] Adicionado o filtro de score vindo da UI
    sda_min_cluster_score: int = field(default_factory=lambda: config.SDA_MIN_CLUSTER_SCORE_PARA_APOSTAR)
    # [NOVA] Filtros separados para cada variação
    sda_min_cluster_score_7: int = field(default_factory=lambda: config.SDA_MIN_CLUSTER_SCORE_PARA_APOSTAR)
    sda_min_cluster_score_9: int = field(default_factory=lambda: config.SDA_MIN_CLUSTER_SCORE_PARA_APOSTAR)
    sda_min_cluster_score_11: int = field(default_factory=lambda: config.SDA_MIN_CLUSTER_SCORE_PARA_APOSTAR)
    sda_min_cluster_score_17: int = field(default_factory=lambda: config.SDA_MIN_CLUSTER_SCORE_PARA_APOSTAR)
    # [NOVA] Flag para ativar/desativar SDA Espelho independente de filtros
    usar_sda_espelho: bool = False

class EstrategiaBase(ABC):
    """Classe base para todas as estratégias de aposta."""
    def __init__(self, nome: str, descricao: str, logic_module: RouletteLogic):
        self.nome = nome
        self.descricao = descricao
        self.logic = logic_module

    @abstractmethod
    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        """O método principal de análise."""
        pass
    
    def get_state(self) -> dict: return {}
    def reset_from_saved_state(self, state: dict): pass

# ============== ESTRATÉGIAS LEGADAS (LÓGICA RESTAURADA) ==============
# [Classes EstrategiaPelaForca, EstrategiaInerciaPreditiva, 
# EstrategiaRessonanciaPolinomial, EstrategiaHibridaAdaptativa, 
# EstrategiaHibridaAdaptativaAMPLA, EstrategiaSinergiaPreditiva
# ... permanecem inalteradas aqui ...]

class EstrategiaPelaForca(EstrategiaBase):
    """Implementação puramente lógica da estratégia 'Pela Força'."""
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(
            nome="Pela Força",
            descricao="Analisa as forças recentes de um sentido para prever 2 regiões de aposta.",
            logic_module=logic_module
        )

    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        if len(historico) < 3: return (False, [], {})
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        jogada_recente = historico[-1]
        direcao_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        
        # Este método já usava reversed(), então estava pegando os dados recentes corretamente.
        forcas_cronologicas = [j['distancia'] for j in reversed(historico) if j.get('direcao') == direcao_alvo and j.get('distancia')]
        
        if len(forcas_cronologicas) < 2: return (False, [], {})
        
        cestas = self.logic._encontrar_melhores_cestas(forcas_cronologicas[:config.FORCA_HISTORICO_FORCAS_ANALISADAS]) # Pega os N mais recentes
        if len(cestas) < 2: return (False, [], {})
        
        cesta_a, cesta_b = cestas[0], cestas[1]
        alvo_a_bruto = round(statistics.median(cesta_a)); alvo_b = round(statistics.median(cesta_b))
        
        penultima_forca, ultima_forca = forcas_cronologicas[1], forcas_cronologicas[0] # Invertido porque forcas_cronologicas está revertido
        
        if ultima_forca not in cesta_a and ultima_forca in cesta_b:
            alvo_a_bruto, alvo_b = alvo_b, alvo_a_bruto
            
        ajuste = round(abs(ultima_forca - penultima_forca) / config.FORCA_FATOR_AJUSTE_DINAMICO)
        alvo_a_final = alvo_a_bruto - ajuste if ultima_forca < penultima_forca else alvo_a_bruto + ajuste
        alvo_a_final = max(1, min(self.logic.wheel_size, alvo_a_final))
        alvo_b = max(1, min(self.logic.wheel_size, alvo_b))
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        num_anterior = jogada_recente.get('numero')
        num_central_a = self.logic.calcular_centro_alvo(num_anterior, alvo_a_final, direcao_alvo)
        num_central_b = self.logic.calcular_centro_alvo(num_anterior, alvo_b, direcao_alvo)
        
        numeros_finais, centros = self.logic._handle_region_overlap(num_central_a, num_central_b, config.FORCA_VIZINHOS_APOSTA)
        num_vizinhos = config.FORCA_VIZINHOS_APOSTA
        visual_regions = [self.logic.get_roulette_region_visual(c, num_vizinhos) for c in centros]
        detalhes = {
            "centros": centros,
            "vizinhos_utilizados": f"{num_vizinhos}L",
            "regiao_visual_sugerida": " / ".join(visual_regions)
        }
        return (True, sorted(list(numeros_finais)), detalhes)

class EstrategiaInerciaPreditiva(EstrategiaBase):
    """Implementação puramente lógica da estratégia 'Inércia Preditiva'."""
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(
            nome="Inércia Preditiva",
            descricao="Encontra o cluster mais denso de forças para prever 1 região de aposta.",
            logic_module=logic_module
        )

    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        if len(historico) < 6: return False, [], {}

        # [CORREÇÃO v17.2] Usar o item mais recente
        jogada_recente = historico[-1]
        direcao_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        
        # [CORREÇÃO v17.2] Pegar as 6 forças mais recentes
        forcas_alvo = [j['distancia'] for j in historico if j.get('direcao') == direcao_alvo and j.get('distancia')][-6:]
        
        if len(forcas_alvo) < config.INERCIA_MIN_FORCAS_NO_CLUSTER:
            return False, [], {}
            
        forca_alvo_calculada = self.logic._encontrar_melhor_cluster_de_forca(forcas_alvo, config.INERCIA_TAMANHO_CESTA_CLUSTER, config.INERCIA_MIN_FORCAS_NO_CLUSTER)
        if forca_alvo_calculada is None: return False, [], {}
        
        forca_final = round(forca_alvo_calculada)
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        num_anterior = jogada_recente.get('numero')
        num_central_final = self.logic.calcular_centro_alvo(num_anterior, forca_final, direcao_alvo)
        
        numeros_finais_aposta = self.logic.get_roulette_region(num_central_final, config.INERCIA_VIZINHOS_APOSTA)
        num_vizinhos = config.INERCIA_VIZINHOS_APOSTA
        visual_region = self.logic.get_roulette_region_visual(num_central_final, num_vizinhos)
        detalhes = {
            "numero_central_sugerido": num_central_final,
            "vizinhos_utilizados": f"{num_vizinhos}L",
            "regiao_visual_sugerida": visual_region
        }
        return True, sorted(list(numeros_finais_aposta)), detalhes

class EstrategiaRessonanciaPolinomial(EstrategiaBase):
    """Estratégia adaptativa que combina previsão de tendência com uma âncora estatística."""
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(nome="Ressonância Polinomial", descricao="Sintetiza tendência com um centro gravitacional de forças.", logic_module=logic_module)
        self.memoria_forca: List[int] = []
        self.nivel_de_confianca: float = 0.5
    def get_state(self): return {"nivel_de_confianca": self.nivel_de_confianca}
    def reset_from_saved_state(self, state: dict): self.nivel_de_confianca = state.get("nivel_de_confianca", 0.5)
    def _atualizar_confianca(self, vitoria_anterior: Optional[bool]):
        if vitoria_anterior is True: self.nivel_de_confianca += config.MRA_FATOR_CONFIANCA_VITORIA
        elif vitoria_anterior is False: self.nivel_de_confianca += config.MRA_FATOR_CONFIANCA_DERROTA
        self.nivel_de_confianca = max(0.0, min(1.0, self.nivel_de_confianca))
        
    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        if len(historico) < 6: return False, [], {}
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        jogada_recente = historico[-1]
        
        self._atualizar_confianca(contexto.vitoria_anterior)
        
        direcao_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        
        # [CORREÇÃO v17.2] Pegar as 12 forças mais recentes
        self.memoria_forca = [j['distancia'] for j in historico if j.get('direcao') == direcao_alvo and j.get('distancia')][-12:]
        
        if len(self.memoria_forca) < 4: return False, [], {}
        
        y = np.array(list(reversed(self.memoria_forca))); x = np.arange(len(y))
        try: forca_exploracao = np.poly1d(np.polyfit(x, y, 2))(len(y))
        except: forca_exploracao = self.memoria_forca[0]
        
        # [CORREÇÃO v17.2] Pegar as 6 mais recentes da memória
        forcas_grav = self.memoria_forca[-6:]
        
        if forcas_grav and (cluster_mean := self.logic._encontrar_melhor_cluster_de_forca(forcas_grav, config.INERCIA_TAMANHO_CESTA_CLUSTER, 1)) is not None: forca_gravitacional = cluster_mean
        else: forca_gravitacional = statistics.median(forcas_grav) if forcas_grav else 18.0
        
        forca_final = (forca_exploracao * self.nivel_de_confianca) + (forca_gravitacional * (1 - self.nivel_de_confianca))
        forca_final_arredondada = round(max(1, min(self.logic.wheel_size, forca_final)))
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        num_anterior = jogada_recente.get('numero')
        num_central_sugerido = self.logic.calcular_centro_alvo(num_anterior, forca_final_arredondada, direcao_alvo)
        
        numeros_finais_aposta = self.logic.get_roulette_region(num_central_sugerido, config.MRA_VIZINHOS_APOSTA)
        num_vizinhos = config.MRA_VIZINHOS_APOSTA
        visual_region = self.logic.get_roulette_region_visual(num_central_sugerido, num_vizinhos)
        detalhes = {"numero_central_sugerido": num_central_sugerido, "vizinhos_utilizados": f"{num_vizinhos}L", "regiao_visual_sugerida": visual_region}
        return True, sorted(list(numeros_finais_aposta)), detalhes

class EstrategiaHibridaAdaptativa(EstrategiaBase):
    """Estratégia que usa um 'Cérebro' para diagnosticar o estado do jogo."""
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(nome="Híbrida Adaptativa", descricao="Alterna caça a padrões e modo de sobrevivência, 3 alvos.", logic_module=logic_module)
        
    def _motor_cacador_de_padroes(self, forcas: List[int]) -> List[int]:
        forcas_com_indices = list(enumerate(forcas)); indices_consumidos = set(); forcas_finais = []
        for _ in range(3):
            if len(indices_consumidos) >= len(forcas_com_indices): break
            forcas_disponiveis = [f for f in forcas_com_indices if f[0] not in indices_consumidos]
            if not forcas_disponiveis: break
            if clusters_encontrados := self.logic._encontrar_multiplos_clusters(forcas_disponiveis, 5, 2):
                cluster_dominante_tuplas = clusters_encontrados[0]
                media_cluster = statistics.mean([item[1] for item in cluster_dominante_tuplas])
                forcas_finais.append(round(media_cluster))
                indices_consumidos.update({item[0] for item in cluster_dominante_tuplas})
            else:
                primeira_forca_disponivel = forcas_disponiveis[0]
                forcas_finais.append(round(primeira_forca_disponivel[1]))
                indices_consumidos.add(primeira_forca_disponivel[0])
        if len(forcas_finais) < 3:
            for fallback_candidato in (f for f in forcas_com_indices if f[0] not in indices_consumidos):
                if len(forcas_finais) >= 3: break
                forcas_finais.append(round(fallback_candidato[1]))
        alvos_unicos = list(dict.fromkeys(forcas_finais))
        while len(alvos_unicos) < 3:
            for numero_candidato in self.logic.ROULETTE_WHEEL_ORDER:
                if len(alvos_unicos) >= 3: break
                if numero_candidato not in alvos_unicos: alvos_unicos.append(numero_candidato)
        return alvos_unicos[:3]
        
    def _motor_ancora_de_sobrevivencia(self, forcas_alvo: List[int], forcas_opostas: List[int]) -> List[int]:
        sonda1_forca = forcas_alvo[0] if forcas_alvo else 18
        sonda2_forca = forcas_opostas[0] if forcas_opostas else sonda1_forca
        sonda3_forca = forcas_alvo[1] if len(forcas_alvo) > 1 else sonda1_forca
        return [round(sonda1_forca), round(sonda2_forca), round(sonda3_forca)]
        
    def _aplicar_deconflito_hierarquico(self, centros_candidatos: List[int], forcas: List[int], direcao_alvo: str) -> List[int]:
        centros_finais, regioes_ocupadas = [], set()
        num_vizinhos = config.HIBRIDA_VIZINHOS_APOSTA
        if len(forcas) < 2: return centros_candidatos
        vetor_momentum = forcas[0] - forcas[1]
        direcao_busca = (1 if vetor_momentum > 0 else -1) if direcao_alvo == 'horario' else (-1 if vetor_momentum > 0 else 1)
        for centro_cand in centros_candidatos:
            centro_a_testar = centro_cand
            if centro_a_testar in centros_finais: centro_a_testar = self.logic._get_number_from_index(self.logic.ROULETTE_WHEEL_ORDER.index(centro_a_testar) + 1)
            if not regioes_ocupadas.intersection(self.logic.get_roulette_region(centro_a_testar, num_vizinhos)):
                centros_finais.append(centro_a_testar); regioes_ocupadas.update(self.logic.get_roulette_region(centro_a_testar, num_vizinhos)); continue
            idx_inicial = self.logic.ROULETTE_WHEEL_ORDER.index(centro_a_testar); busca_sucedida = False
            for j in range(1, self.logic.wheel_size):
                idx_teste = (idx_inicial + (j * direcao_busca) + self.logic.wheel_size) % self.logic.wheel_size
                centro_teste = self.logic._get_number_from_index(idx_teste)
                if not regioes_ocupadas.intersection(self.logic.get_roulette_region(centro_teste, num_vizinhos)):
                    centros_finais.append(centro_teste); regioes_ocupadas.update(self.logic.get_roulette_region(centro_teste, num_vizinhos)); busca_sucedida = True; break
            if not busca_sucedida:
                for fallback in self.logic.ROULETTE_WHEEL_ORDER:
                    if not regioes_ocupadas.intersection(self.logic.get_roulette_region(fallback, num_vizinhos)):
                        centros_finais.append(fallback); regioes_ocupadas.update(self.logic.get_roulette_region(fallback, num_vizinhos)); break
        return centros_finais
        
    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        if len(historico) < 6: return False, [], {}
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        jogada_recente = historico[-1]
        
        # [CORREÇÃO v17.2] Pegar as 6 forças globais mais recentes
        forcas_globais = [j['distancia'] for j in historico if j.get('distancia')][-6:]
        
        if len(forcas_globais) < 6: return False, [], {}
        
        direcao_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        
        if self.logic._calcular_indice_convergencia(forcas_globais) <= config.HIBRIDA_LIMITE_CAOS_CONVERGENCE:
            forcas_alvo_brutas = self._motor_cacador_de_padroes(forcas_globais)
        else:
            # [CORREÇÃO v17.2] Pegar as 2 forças alvo mais recentes
            forcas_alvo = [j['distancia'] for j in historico if j['direcao'] == direcao_alvo and j.get('distancia')][-2:]
            # [CORREÇÃO v17.2] Pegar a força oposta mais recente
            forcas_opostas = [j['distancia'] for j in historico if j['direcao'] != direcao_alvo and j.get('distancia')][-1:]
            forcas_alvo_brutas = self._motor_ancora_de_sobrevivencia(forcas_alvo, forcas_opostas)
            
        # [CORREÇÃO v17.2] Usar o item mais recente
        num_anterior = jogada_recente.get('numero')
        centros_candidatos = [self.logic.calcular_centro_alvo(num_anterior, f, direcao_alvo) for f in forcas_alvo_brutas]
        
        # [CORREÇÃO v17.2] Passa as forças globais (que são as mais recentes)
        centros_finais = self._aplicar_deconflito_hierarquico(centros_candidatos, forcas_globais, direcao_alvo)
        
        numeros_finais_aposta = set().union(*(self.logic.get_roulette_region(c, config.HIBRIDA_VIZINHOS_APOSTA) for c in centros_finais))
        num_vizinhos = config.HIBRIDA_VIZINHOS_APOSTA
        visual_regions = [self.logic.get_roulette_region_visual(c, num_vizinhos) for c in centros_finais]
        detalhes = {
            "Centros Finais": centros_finais, "vizinhos_utilizados": f"{num_vizinhos}L",
            "regiao_visual_sugerida": " / ".join(visual_regions)
        }
        return True, sorted(list(numeros_finais_aposta)), detalhes

class EstrategiaHibridaAdaptativaAMPLA(EstrategiaHibridaAdaptativa):
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(logic_module)
        self.nome="Híbrida Adaptativa AMPLA"; self.descricao="Versão da Híbrida com 7 números por alvo."
    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        # A lógica de `analisar` da classe pai (EstrategiaHibridaAdaptativa) já foi corrigida.
        # Esta função chama `super().analisar`, então ela usará a lógica corrigida.
        is_valid, _, details = super().analisar(historico, contexto)
        if not is_valid: return False, [], details
        
        centros_finais = details.get("Centros Finais", [])
        if not centros_finais: return False, [], details
        
        numeros_finais_aposta = set().union(*(self.logic.get_roulette_region(c, config.HIBRIDA_AMPLA_VIZINHOS_APOSTA) for c in centros_finais))
        num_vizinhos = config.HIBRIDA_AMPLA_VIZINHOS_APOSTA
        visual_regions = [self.logic.get_roulette_region_visual(c, num_vizinhos) for c in centros_finais]
        details["vizinhos_utilizados"] = f"{num_vizinhos}L"
        details["regiao_visual_sugerida"] = " / ".join(visual_regions)
        return True, sorted(list(numeros_finais_aposta)), details

class EstrategiaSinergiaPreditiva(EstrategiaBase):
    """
    REESCRITA: Caça Seletiva Sequencial. Seleciona 4 centros com lógica de
    exclusão de cluster por gravidade. Garante 18 números distintos.
    """
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(nome="Sinergia Preditiva", descricao="Caça Seletiva Sequencial com clusters de exclusão e 4 alvos otimizados.", logic_module=logic_module)
        
    def _calcular_centro_e_excluir_cesta(self, forca_candidata: int, forcas_disponiveis: Set[int], gravidade: int) -> Tuple[Optional[int], Set[int], Optional[Set[int]]]:
        """
        Calcula o centro (a própria força), identifica a cesta e retorna 
        a força e as forças excluídas.
        """
        if forca_candidata not in forcas_disponiveis:
            return None, forcas_disponiveis, None
            
        centro_forca = forca_candidata
        forcas_excluidas = self.logic.identificar_forcas_em_cesta(forcas_disponiveis, centro_forca, gravidade)
        
        # O novo conjunto de forças disponíveis (exclui o centro e a cesta)
        novas_disponiveis = forcas_disponiveis - forcas_excluidas
        
        return centro_forca, novas_disponiveis, forcas_excluidas
        
    def _resolver_deconflito_regional_18_numeros(self, centros_candidatos: List[int], num_anterior: int, direcao_alvo: str) -> List[int]:
        """
        Aplica o deconflito regional forçado: 3 centros com 2 vizinhos, 1 centro com 1 vizinho.
        """
        centros_finais, regioes_ocupadas = [], set()
        
        # As prioridades são 5 vizinhos para C1, C2, C3 e 3 vizinhos para C4.
        vizinhos = [config.ESP_VIZINHOS_APOSTA] * 3 + [1] 
        
        for i, forca_bruta in enumerate(centros_candidatos):
            if len(centros_finais) >= 4:
                break
                
            num_vizinhos = vizinhos[i]
            
            # Converte a Força para Número Central
            centro_num_candidato = self.logic.calcular_centro_alvo(num_anterior, forca_bruta, direcao_alvo)
            
            # --- Lógica de Deconflito (Busca pelo número mais próximo que não se sobreponha) ---
            
            if i == 0:
                # O primeiro centro sempre é aceito
                centros_finais.append(centro_num_candidato)
                regioes_ocupadas.update(self.logic.get_roulette_region(centro_num_candidato, num_vizinhos))
                continue
            
            # Busca sequencial ao redor do centro candidato (até 36 passos, garantindo que a busca circular cubra o círculo)
            for offset in range(0, self.logic.wheel_size):
                
                # Testa na direção horária
                idx_h = (self.logic.ROULETTE_WHEEL_ORDER.index(centro_num_candidato) + offset) % self.logic.wheel_size
                # [FIX CRÍTICO APLICADO] Corrigido o erro de digitação
                num_teste_h = self.logic.ROULETTE_WHEEL_ORDER[idx_h] 
                regiao_teste_h = self.logic.get_roulette_region(num_teste_h, num_vizinhos)
                
                if not regioes_ocupadas.intersection(regiao_teste_h):
                    centros_finais.append(num_teste_h)
                    regioes_ocupadas.update(regiao_teste_h)
                    break
                    
                # Testa na direção anti-horária (apenas se offset > 0 para evitar duplicação)
                if offset > 0:
                    idx_ah = (self.logic.ROULETTE_WHEEL_ORDER.index(centro_num_candidato) - offset + self.logic.wheel_size) % self.logic.wheel_size
                    # [FIX CRÍTICO APLICADO] Corrigido o erro de digitação
                    num_teste_ah = self.logic.ROULETTE_WHEEL_ORDER[idx_ah] 
                    regiao_teste_ah = self.logic.get_roulette_region(num_teste_ah, num_vizinhos)
                    
                    if not regioes_ocupadas.intersection(regiao_teste_ah):
                        centros_finais.append(num_teste_ah)
                        regioes_ocupadas.update(regiao_teste_ah)
                        break
            
            # Fallback forçado caso a busca circular não encontre 
            else:
                 # Se a busca falhar, simplesmente adiciona o centro candidato original e ignora a sobreposição (para não quebrar a aposta de 4 centros)
                 if centro_num_candidato not in centros_finais:
                     centros_finais.append(centro_num_candidato)
                     regioes_ocupadas.update(self.logic.get_roulette_region(centro_num_candidato, num_vizinhos))


        return centros_finais

    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        if len(historico) < 6: return False, [], {} # Requer pelo menos 6 giros para Força 1 a Força 6
        
        # [CORREÇÃO v17.2] Usar o item mais recente
        jogada_recente = historico[-1]
        d_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        num_anterior = jogada_recente.get('numero')
        
        # [CORREÇÃO v17.2] Pegar as 6 forças mais recentes
        forcas_alvo_raw = [j['distancia'] for j in historico if j['direcao'] == d_alvo and j.get('distancia', 0) > 0][-6:]
        
        if len(forcas_alvo_raw) < 6: return False, [], {}
        
        # F1 é o mais recente, F6 é o mais antigo (A lista já está cronológica, então F1 é o [-1])
        # A lógica original desta estratégia esperava F1..F6, onde F1 é o mais recente.
        # Invertemos a lista para F1 ser o índice 0.
        forcas_alvo_raw.reverse() # Agora F1 = [0], F6 = [5]
        
        f_raw = {i+1: forcas_alvo_raw[i] for i in range(6)}
        
        # Conjunto de todas as forças disponíveis (para exclusão)
        forcas_disponiveis: Set[int] = set(f_raw.values())
        centros_de_forca_candidatos = []
        
        # --- LÓGICA DA CAÇA SELETIVA SEQUENCIAL ---
        
        # 1. VETOR 1 (Prioridade: F1)
        forca_c1 = f_raw[1]
        c1, forcas_disponiveis, _ = self._calcular_centro_e_excluir_cesta(forca_c1, forcas_disponiveis, gravidade=5)
        if c1 is not None: centros_de_forca_candidatos.append(c1)
        
        # 2. VETOR 2 (Prioridade: F2)
        forca_c2 = f_raw[2]
        c2, forcas_disponiveis, _ = self._calcular_centro_e_excluir_cesta(forca_c2, forcas_disponiveis, gravidade=5)
        if c2 is not None: centros_de_forca_candidatos.append(c2)
        
        # 3. VETOR 3 (Prioridade: F3)
        forca_c3 = f_raw[3]
        c3, forcas_disponiveis, _ = self._calcular_centro_e_excluir_cesta(forca_c3, forcas_disponiveis, gravidade=5)
        if c3 is not None: centros_de_forca_candidatos.append(c3)

        # 4. VETOR 4 (SMART FALLBACK: F4 -> F5 -> F6 -> ALEATÓRIO)
        c4 = None
        for forca_key in [4, 5, 6]:
            forca_cand = f_raw[forca_key]
            if forca_cand in forcas_disponiveis:
                # O Vetor 4 é o centro (força) que ainda não foi excluído
                c4 = forca_cand
                break
        
        if c4 is None:
            # Fallback para Força Aleatória (entre 1 e 37), último recurso
            c4 = random.randint(1, self.logic.wheel_size)
        
        centros_de_forca_candidatos.append(c4)
        
        # --- FASE CRÍTICA: GARANTIA DE 4 CENTROS E PREENCHIMENTO ---
        # Garantia de contrato (Deve sempre haver 4 centros)
        if len(centros_de_forca_candidatos) < 4:
            # Esta seção só deve ser executada se houver um erro lógico grave acima,
            # mas o código acima (V1, V2, V3, V4) garante a lista de 4 centros de força bruta.
            median_force = round(statistics.median(forcas_alvo_raw)) # Usa a lista invertida
            while len(centros_de_forca_candidatos) < 4:
                 centros_de_forca_candidatos.append(median_force)
        
        # O Deconflito processa os primeiros 4.
        centros_de_forca_candidatos = centros_de_forca_candidatos[:4]

        # --- FASE FINAL: DECONFLITO REGIONAL E CONVERSÃO ---
        
        # Aplica o deconflito regional 3x5 + 1x3
        centros_finais_numeros = self._resolver_deconflito_regional_18_numeros(
            centros_de_forca_candidatos, num_anterior, d_alvo
        )
        
        # Geração dos Números Finais
        numeros = set()
        num_vizinhos_grande = config.ESP_VIZINHOS_APOSTA # 2 vizinhos
        num_vizinhos_pequeno = 1 # 1 vizinho
        
        if len(centros_finais_numeros) >= 3:
            for c in centros_finais_numeros[:3]:
                numeros.update(self.logic.get_roulette_region(c, num_vizinhos_grande))
        if len(centros_finais_numeros) >= 4:
            numeros.update(self.logic.get_roulette_region(centros_finais_numeros[3], num_vizinhos_pequeno))

        # Geração da Região Visual para UI
        visual_regions = []
        for i, c in enumerate(centros_finais_numeros):
            v = num_vizinhos_pequeno if i == 3 else num_vizinhos_grande
            visual_regions.append(self.logic.get_roulette_region_visual(c, v))

        detalhes = {
            "centros_finais_otimizados": centros_finais_numeros, 
            "vizinhos_utilizados": f"3x{num_vizinhos_grande}L + 1x{num_vizinhos_pequeno}L",
            "regiao_visual_sugerida": " / ".join(visual_regions)
        }
        return True, sorted(list(numeros)), detalhes

# ============== SDA v17.1 (CLUSTER DE FORÇA 17 com FILTRO) ==============

class EstrategiaSinergiaDirecionalAvancada(EstrategiaBase):
    """
    SDA v17.1 - Análise de Cluster de Força com 4 Variações Internas.
    MODIFICADO: Quando usada como estratégia principal, executa 4 variações (SDA-7, SDA-9, SDA-11, SDA-17)
    e seleciona automaticamente a melhor baseado em ROI.
    """
    def __init__(self, logic_module: RouletteLogic, persistence_module: DataPersistence, 
                 raio_gravidade: int = None, num_vizinhos: int = None, _eh_variacao_interna: bool = False):
        """
        Inicializa a estratégia SDA.
        
        Se raio_gravidade e num_vizinhos forem None, cria 4 variações internas.
        Se forem fornecidos, cria uma variação única (para uso interno).
        """
        self.persistence = persistence_module
        
        # Determinar se é estratégia principal ou variação interna
        self.eh_estrategia_principal = not _eh_variacao_interna and raio_gravidade is None and num_vizinhos is None
        
        if self.eh_estrategia_principal:
            # Estratégia principal: criar 3 variações internas
            nome_strategia = "Sinergia Direcional Avançada"
            total_numeros = "7, 9, 11"
            descricao = f"4 variações (SDA-7, SDA-9, SDA-11, SDA-17) com seleção automática por ROI das últimas {config.SDA_SELECAO_ROI_JANELA} jogadas."
        else:
            # Variação interna: usar parâmetros fornecidos
            nome_strategia = f"SDA-{num_vizinhos*2 + 1}" if num_vizinhos else "SDA"
            total_numeros = num_vizinhos*2 + 1 if num_vizinhos else "N/A"
            descricao = f"Busca o Cluster de Força (1-37) que mais captura as {config.SDA_FORCAS_ANALISADAS} forças alvo. Raio={raio_gravidade}, Vizinhos={num_vizinhos}."
        
        super().__init__(
            nome=nome_strategia,
            descricao=descricao,
            logic_module=logic_module
        )
        
        # Parâmetros próprios desta variação (se for variação interna)
        self.raio_gravidade = raio_gravidade or config.SDA_VIZINHOS_APOSTA
        self.num_vizinhos = num_vizinhos or config.SDA_VIZINHOS_APOSTA
        
        # Calcular força gravitacional média baseada no número de vizinhos
        if num_vizinhos:
            self.forca_gravitacional_media = num_vizinhos*2 + 1
        else:
            self.forca_gravitacional_media = config.SDA_FORCA_DEFAULT
        
        if self.eh_estrategia_principal:
            # Criar as 4 variações internas
            self.variacoes_internas = {}
            for nome_var, config_var in config.SDA_VARIACOES_CONFIG.items():
                self.variacoes_internas[nome_var] = EstrategiaSinergiaDirecionalAvancada(
                    logic_module,
                    persistence_module,
                    raio_gravidade=config_var["raio_gravidade"],
                    num_vizinhos=config_var["num_vizinhos"],
                    _eh_variacao_interna=True
                )
                # Atribuir nome correto às variações
                self.variacoes_internas[nome_var].nome = nome_var
            
            # Criar instância da SDA Espelho (importação será feita após a definição da classe)
            # Será inicializada no método analisar se necessário
            self.estrategia_espelho = None
            
            # Criar instância da SDA Gêmea (importação será feita após a definição da classe)
            # Será inicializada no método analisar se necessário
            self.estrategia_gemea = None
            
            # Placares principais de cada estratégia (atualizado quando estratégia é eleita e aposta)
            self.performance_principal = {
                nome_var: {
                    "historico_gatilhos": [],
                    "roi_historico": [],
                    "roi_medio_12": 0.0,
                    "total_ganhos": 0.0,
                    "total_gastos": 0.0,
                    "acertos": 0,
                    "erros": 0
                }
                for nome_var in self.variacoes_internas.keys()
            }
            # Adicionar SDA-Espelho ao performance_principal
            self.performance_principal["SDA-Espelho"] = {
                "historico_gatilhos": [],
                "roi_historico": [],
                "roi_medio_12": 0.0,
                "total_ganhos": 0.0,
                "total_gastos": 0.0,
                "acertos": 0,
                "erros": 0
            }
            
            # Armazenar última análise de cada variação
            self.ultimas_analises_internas = {}
            # Armazenar última estratégia eleita
            self.ultima_estrategia_eleita = None
            print(f"{nome_strategia} inicializada com 4 variações internas (SDA-7, SDA-9, SDA-11, SDA-17) e SDA Espelho.")
        else:
            self.variacoes_internas = {}
            self.ultimas_analises_internas = {}
            self.performance_principal = {}
            self.ultima_estrategia_eleita = None
            print(f"{nome_strategia} inicializada (raio_gravidade={raio_gravidade}, num_vizinhos={num_vizinhos}, total={total_numeros} números).")

    def _formatar_detalhes_ui_cluster_forca(self, 
                                           forcas_alvo: List[int], 
                                           nucleo_aposta: int, 
                                           melhor_forca: int, 
                                           score_vencedor: int, 
                                           top_5_scores: List[Tuple[int, int]],
                                           num_vizinhos: int) -> Dict[str, Any]:
        """Helper para formatar o dicionário de detalhes para a UI."""
        
        visual_region = self.logic.get_roulette_region_visual(nucleo_aposta, num_vizinhos)
        
        # Estrutura: (nome_vetor, nucleo_central, score_captura)
        # [CORREÇÃO ECA+1] O score total é agora dinâmico
        vetores_eleitos_detalhes = [
            (f"CLUSTER (Score: {score_vencedor}/{config.SDA_FORCAS_ANALISADAS})", nucleo_aposta, float(score_vencedor))
        ]
        
        return {
            "forcas_de_entrada": forcas_alvo,
            "vetores_eleitos_detalhes": vetores_eleitos_detalhes,
            "centros_finais": [nucleo_aposta], # Lista com 1 centro
            "score_confianca": float(score_vencedor), # Score de captura
            "forca_resultante_cluster": melhor_forca,  # NOVO: Força escolhida pelo cluster vencedor
            "roi_preditivo": 0.0, # N/A
            "vizinhos_utilizados": f"{num_vizinhos}L (Total {num_vizinhos*2 + 1}n)",
            "regiao_visual_sugerida": visual_region,
            "detalhes_eleicao": { 
                "modo": f"SDA (Cluster de Força {num_vizinhos*2 + 1})", 
                "protagonista": f"Força {melhor_forca}",
                "scores": top_5_scores # Mostra os 5 melhores clusters
            }
        }

    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        """
        Implementação da lógica de "Cluster de Força" com filtro.
        MODIFICADO: Se for a estratégia principal, executa as 4 variações internas e SDA Espelho.
        """
        
        # NOVO: Se for a estratégia principal, executar as 4 variações e SDA Espelho
        if self.eh_estrategia_principal and self.variacoes_internas:
            return self._analisar_com_variacoes(historico, contexto)
        
        # Comportamento original para variações individuais
        return self._analisar_variacao_unica(historico, contexto)
    
    def _analisar_com_variacoes(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        """
        Executa as 4 variações internas e SDA Espelho, cada uma usando seu filtro configurado na UI.
        Eleger a melhor estratégia baseado no ROI PRINCIPAL.
        """
        resultados = {}
        
        # Executar análise de cada variação uma única vez com seu filtro da UI
        for nome_var, estrategia in self.variacoes_internas.items():
            # Executar análise com o filtro específico desta variação (vindo do contexto)
            deve_apostar, numeros, detalhes = estrategia._analisar_variacao_unica(historico, contexto)
            
            resultados[nome_var] = {
                "deve_apostar": deve_apostar,
                "numeros": numeros,
                "detalhes": detalhes,
                "custo": len(numeros) * config.CUSTO_POR_NUMERO_BASE if numeros else 0
            }
            
            # Armazenar última análise para atualização de performance
            self.ultimas_analises_internas[nome_var] = resultados[nome_var]
        
        # Executar análise da SDA Espelho (SEMPRE, para cálculo de ROI)
        # Inicializar SDA Espelho se necessário (lazy initialization para evitar import circular)
        if self.estrategia_espelho is None:
            # Importação local para evitar erro de NameError (classe definida depois)
            from strategies import EstrategiaSinergiaDirecionalAvancadaEspelho
            self.estrategia_espelho = EstrategiaSinergiaDirecionalAvancadaEspelho(self.logic)
        
        # SEMPRE executa análise (para cálculo de ROI)
        deve_apostar_espelho, numeros_espelho, detalhes_espelho = self.estrategia_espelho.analisar(historico, contexto)
        
        # Mas só adiciona aos resultados se o botão estiver ativo
        if contexto.usar_sda_espelho:
            resultados["SDA-Espelho"] = {
                "deve_apostar": deve_apostar_espelho,
                "numeros": numeros_espelho,
                "detalhes": detalhes_espelho,
                "custo": len(numeros_espelho) * config.CUSTO_POR_NUMERO_BASE if numeros_espelho else 0
            }
        else:
            # Adiciona mesmo assim para exibição e cálculo de ROI, mas com deve_apostar=False
            resultados["SDA-Espelho"] = {
                "deve_apostar": False,  # Não pode apostar se botão desativado
                "numeros": numeros_espelho,
                "detalhes": detalhes_espelho,
                "custo": len(numeros_espelho) * config.CUSTO_POR_NUMERO_BASE if numeros_espelho else 0
            }
        
        # Atualizar performance_principal com dados da SDA Espelho (sempre)
        if "SDA-Espelho" not in self.performance_principal:
            self.performance_principal["SDA-Espelho"] = {
                "historico_gatilhos": [],
                "roi_historico": [],
                "roi_medio_12": 0.0,
                "total_ganhos": 0.0,
                "total_gastos": 0.0,
                "acertos": 0,
                "erros": 0
            }
        
        # Sincronizar ROI da SDA Espelho com performance_principal (sempre)
        self.performance_principal["SDA-Espelho"]["roi_medio_12"] = self.estrategia_espelho.performance_espelho["roi_medio_12"]
        
        # ========== SDA GÊMEA (NOVO) ==========
        # Executar análise da SDA Gêmea (SEMPRE, para exibição na UI)
        if self.estrategia_gemea is None:
            from strategies import EstrategiaSDAGemea
            self.estrategia_gemea = EstrategiaSDAGemea(self.logic)
        
        deve_apostar_gemea, numeros_gemea, detalhes_gemea = self.estrategia_gemea.analisar(historico, contexto)
        
        # Armazenar resultado da SDA Gêmea para exibição na UI
        resultados["SDA-Gêmea"] = {
            "deve_apostar": deve_apostar_gemea,
            "numeros": numeros_gemea,
            "detalhes": detalhes_gemea,
            "custo": len(numeros_gemea) * config.CUSTO_POR_NUMERO_BASE if numeros_gemea else 0
        }
        
        # Escolher melhor estratégia baseado no ROI PRINCIPAL (incluindo SDA-Espelho)
        melhor_estrategia = None
        melhor_roi_principal = float('-inf')
        todas_estrategias = list(self.variacoes_internas.keys())
        if "SDA-Espelho" in resultados:
            todas_estrategias.append("SDA-Espelho")
        
        for nome_var in todas_estrategias:
            roi_principal = self.performance_principal.get(nome_var, {}).get("roi_medio_12", 0.0)
            if roi_principal > melhor_roi_principal:
                melhor_roi_principal = roi_principal
                melhor_estrategia = nome_var
        
        # Se não há histórico suficiente, usar primeira estratégia como padrão
        if not melhor_estrategia:
            melhor_estrategia = list(self.variacoes_internas.keys())[0] if self.variacoes_internas else "SDA-11"
        
        melhor_resultado = resultados.get(melhor_estrategia, {})
        
        # Armazenar qual estratégia foi eleita para atualização de performance
        self.ultima_estrategia_eleita = melhor_estrategia
        
        # Retornar resultado da melhor estratégia
        if melhor_resultado and melhor_resultado.get("deve_apostar"):
            detalhes_melhor = melhor_resultado["detalhes"]
            return (
                True,
                melhor_resultado["numeros"],
                {
                    **detalhes_melhor,
                    "variacoes": resultados,
                    "melhor_selecionada": melhor_estrategia,
                    "centros_finais": detalhes_melhor.get("centros_finais", []),
                    "roi_estrategias_principais": {
                        var: self.performance_principal.get(var, {}).get("roi_medio_12", 0.0)
                        for var in list(self.variacoes_internas.keys()) + (["SDA-Espelho"] if "SDA-Espelho" in resultados else [])
                    },
                    "forcas_de_entrada": detalhes_melhor.get("forcas_de_entrada", []),
                    # Detalhes da SDA Gêmea para exibição na UI
                    "sda_gemea": resultados.get("SDA-Gêmea", {}).get("detalhes", {})
                }
            )
        
        # Se nenhuma deve apostar, ainda assim eleger melhor estratégia baseado em ROI principal
        forcas_alvo = []
        centros_melhor = []
        
        if resultados:
            # Tentar pegar forças e centros da melhor estratégia
            if melhor_resultado:
                forcas_alvo = melhor_resultado.get("detalhes", {}).get("forcas_de_entrada", [])
                centros_melhor = melhor_resultado.get("detalhes", {}).get("centros_finais", [])
            
            # Se não encontrou, tentar pegar de qualquer resultado
            if not forcas_alvo:
                for var_resultado in resultados.values():
                    forcas = var_resultado.get("detalhes", {}).get("forcas_de_entrada", [])
                    if forcas:
                        forcas_alvo = forcas
                        if not centros_melhor:
                            centros_melhor = var_resultado.get("detalhes", {}).get("centros_finais", [])
                        break
        
        return False, [], {
            "variacoes": resultados,
            "melhor_selecionada": melhor_estrategia,
            "forcas_de_entrada": forcas_alvo,
            "centros_finais": centros_melhor,
            "roi_estrategias_principais": {
                var: self.performance_principal.get(var, {}).get("roi_medio_12", 0.0)
                for var in list(self.variacoes_internas.keys()) + (["SDA-Espelho"] if "SDA-Espelho" in resultados else [])
            },
            "mensagem": "Nenhuma estratégia atende aos critérios",
            # Detalhes da SDA Gêmea para exibição na UI
            "sda_gemea": resultados.get("SDA-Gêmea", {}).get("detalhes", {})
        }
    
    def _analisar_variacao_unica(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        """
        Implementação da lógica de "Cluster de Força" para uma variação única.
        """
        
        # --- FASE 1: Coleta e Validação de Dados ---
        
        if len(historico) < config.SDA_FORCAS_ANALISADAS: 
            return False, [], {}
        
        # CONVENÇÃO: historico[0] = mais recente
        jogada_recente = historico[0]
        direcao_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        
        # Coleta forças da direção alvo (historico já está ordenado com mais recente primeiro)
        forcas_disponiveis = [j['distancia'] for j in historico if j.get('direcao') == direcao_alvo and j.get('distancia', 0) > 0]
        # Pega as primeiras N forças (que são as mais recentes)
        forcas_alvo = forcas_disponiveis[:config.SDA_FORCAS_ANALISADAS]
        
        if len(forcas_alvo) < config.SDA_FORCAS_ANALISADAS:
            detalhes_falha = self._formatar_detalhes_ui_cluster_forca(forcas_alvo, 0, 0, 0, [], self.num_vizinhos)
            detalhes_falha['regiao_visual_sugerida'] = f"(Forças insuficientes: {len(forcas_alvo)}/{config.SDA_FORCAS_ANALISADAS})"
            detalhes_falha['centros_finais'] = []
            detalhes_falha['raio_gravidade_usado'] = self.raio_gravidade
            detalhes_falha['forca_gravitacional_media'] = self.forca_gravitacional_media
            detalhes_falha['num_vizinhos'] = self.num_vizinhos
            return False, [], detalhes_falha
            
        num_anterior = jogada_recente.get('numero')

        # --- FASE 2: Análise de Cluster de Força ---
        
        # MODIFICADO: Usa self.raio_gravidade ao invés de config
        raio_gravidade = self.raio_gravidade
        scores_cluster = []
        
        for centro_forca_candidato in range(1, self.logic.wheel_size + 1):
            score_atual = 0
            for f in forcas_alvo:
                dist = self.logic.calcular_distancia_circular_forca(centro_forca_candidato, f)
                if dist <= raio_gravidade:
                    score_atual += 1
            scores_cluster.append((centro_forca_candidato, score_atual))

        # --- FASE 3: Eleição do Vetor Vencedor ---
        
        if not scores_cluster:
            return False, [], {}

        # Ordenar por score (decrescente)
        scores_cluster.sort(key=lambda x: x[1], reverse=True)
        
        # Obter o score máximo
        score_maximo = scores_cluster[0][1]
        
        # Filtrar apenas forças com score máximo
        forcas_com_score_maximo = [(f, score) for f, score in scores_cluster if score == score_maximo]
        
        # Se houver apenas uma força com score máximo, usar ela
        if len(forcas_com_score_maximo) == 1:
            melhor_forca_central = forcas_com_score_maximo[0][0]
            score_vencedor = score_maximo
        else:
            # DESEMPATE: escolher a força que minimiza a soma das distâncias às forças-alvo
            melhor_forca_central = None
            menor_soma_distancias = float('inf')
            
            for forca_candidata, score in forcas_com_score_maximo:
                # Calcular soma das distâncias desta força candidata a todas as forças-alvo
                soma_distancias = 0
                for forca_alvo in forcas_alvo:
                    dist = self.logic.calcular_distancia_circular_forca(forca_candidata, forca_alvo)
                    soma_distancias += dist
                
                # Se esta força tem menor soma de distâncias, ela é a melhor
                if soma_distancias < menor_soma_distancias:
                    menor_soma_distancias = soma_distancias
                    melhor_forca_central = forca_candidata
            
            score_vencedor = score_maximo
        
        # Manter top_5_scores como estava
        top_5_scores = [(f[0], f[1]) for f in scores_cluster[:5]]

        # --- FASE 4: APLICAÇÃO DO FILTRO DE GATILHO ---
        
        # Pega o limiar do usuário vindo da UI baseado na variação
        # Determina qual filtro usar baseado no nome da variação (SDA-7, SDA-9, SDA-11, SDA-17)
        if self.nome == "SDA-7":
            min_score_necessario = contexto.sda_min_cluster_score_7
        elif self.nome == "SDA-9":
            min_score_necessario = contexto.sda_min_cluster_score_9
        elif self.nome == "SDA-11":
            min_score_necessario = contexto.sda_min_cluster_score_11
        elif self.nome == "SDA-17":
            min_score_necessario = contexto.sda_min_cluster_score_17
        else:
            # Fallback para compatibilidade com código antigo
            min_score_necessario = contexto.sda_min_cluster_score
        
        # --- FASE 4: Cálculo da Aposta (SEMPRE calcula, mesmo se não deve apostar) ---
        # MODIFICADO: Sempre calcula os números para poder calcular ROI simulado no painel principal
        
        # MODIFICADO: Usa self.num_vizinhos ao invés de config
        nucleo_aposta_final = self.logic.calcular_centro_alvo(
            num_anterior, 
            melhor_forca_central,
            direcao_alvo
        )
        
        # MODIFICADO: Usa self.num_vizinhos para gerar números de aposta
        numeros_finais = self.logic.get_roulette_region(nucleo_aposta_final, self.num_vizinhos)
        
        # --- FASE 5: Aplicação do Filtro de Gatilho ---
        deve_apostar = score_vencedor >= min_score_necessario
        
        # Formata os detalhes para a UI (sempre, mesmo se não deve apostar)
        detalhes_ui = self._formatar_detalhes_ui_cluster_forca(
            forcas_alvo,
            nucleo_aposta_final,
            melhor_forca_central,
            score_vencedor,
            top_5_scores,
            self.num_vizinhos
        )
        
        # Adiciona informações sobre configuração usada
        detalhes_ui['raio_gravidade_usado'] = self.raio_gravidade
        detalhes_ui['forca_gravitacional_media'] = self.forca_gravitacional_media
        detalhes_ui['num_vizinhos'] = self.num_vizinhos
        
        # Se não deve apostar, adiciona mensagem de filtro mas retorna os números mesmo assim
        if not deve_apostar:
            detalhes_ui['regiao_visual_sugerida'] = f"(FILTRADO: Score {score_vencedor} < {min_score_necessario})"
        
        return deve_apostar, sorted(list(numeros_finais)), detalhes_ui
    
    def atualizar_performance_principal(self, numero_sorteado: int, numeros_apostados: List[int], ganho: float, custo: float):
        """
        Atualiza o performance principal (por estratégia) para todas as 4 variações.
        """
        if not hasattr(self, 'ultimas_analises_internas') or not self.ultimas_analises_internas:
            return
        
        # Atualizar placar PRINCIPAL para TODAS as 4 estratégias
        for nome_var, resultado in self.ultimas_analises_internas.items():
            numeros_sugeridos = resultado.get("numeros", [])
            
            if not numeros_sugeridos:
                continue
            
            # Inicializar performance principal se não existir
            if nome_var not in self.performance_principal:
                self.performance_principal[nome_var] = {
                    "historico_gatilhos": [],
                    "roi_historico": [],
                    "roi_medio_12": 0.0,
                    "total_ganhos": 0.0,
                    "total_gastos": 0.0,
                    "acertos": 0,
                    "erros": 0
                }
            
            # Obter performance principal da estratégia
            perf_principal = self.performance_principal[nome_var]
            
            # Verificar se acertou o número sorteado
            acertou = numero_sorteado in numeros_sugeridos
            custo_var = len(numeros_sugeridos) * config.CUSTO_POR_NUMERO_BASE
            
            # Atualizar histórico principal
            hist_principal = perf_principal["historico_gatilhos"]
            hist_principal.insert(0, acertou)
            if len(hist_principal) > config.SDA_SELECAO_ROI_JANELA:
                hist_principal.pop()
            
            # Calcular ROI principal
            if acertou and custo_var > 0:
                ganho_var = (custo_var / len(numeros_sugeridos)) * config.PAYOUT_FACTOR
                roi_var = ganho_var - custo_var
                perf_principal["total_ganhos"] += ganho_var
                perf_principal["acertos"] += 1
            else:
                roi_var = -custo_var
                perf_principal["erros"] += 1
            
            perf_principal["total_gastos"] += custo_var
            
            # Atualizar ROI histórico principal
            roi_hist_principal = perf_principal["roi_historico"]
            roi_hist_principal.insert(0, roi_var)
            if len(roi_hist_principal) > config.SDA_SELECAO_ROI_JANELA:
                roi_hist_principal.pop()
            
            # Calcular ROI médio das últimas 12 (principal)
            if roi_hist_principal:
                perf_principal["roi_medio_12"] = sum(roi_hist_principal) / len(roi_hist_principal)
            else:
                perf_principal["roi_medio_12"] = 0.0


    # --- MÉTODOS DO ORÁCULO QUÂNTICO (Mantidos para Data Lake) ---
    
    def _reconstruir_indice_ann(self):
        # Este método não é usado pela nova lógica, mas pode ser chamado
        # por rotinas de manutenção.
        print("SDA v17.1: Reconstrução ANN ignorada (lógica SACA desativada).")

    def _executar_logica_saca(self, dna: tuple, num_anterior: int, direcao_alvo: str) -> tuple:
        raise NotImplementedError("SDA v17.1 não usa _executar_logica_saca")

    def _gerar_impressao_digital_dna(self, dna: tuple) -> List[float]:
        # Este método ainda pode ser chamado por 'managers.py' para o Data Lake.
        # É importante que ele continue funcional.
        try:
            dna_arr = np.array(dna, dtype=float)
            if dna_arr.size == 0:
                return [0.0] * 7
            features = [
                np.mean(dna_arr), np.std(dna_arr), skew(dna_arr), kurtosis(dna_arr),
                self._hurst_exponent_calc(dna_arr), self._shannon_entropy(dna_arr),
                self._recurrence_determinism(dna_arr)
            ]
            return [np.nan_to_num(f, nan=0.0, posinf=0.0, neginf=0.0) for f in features]
        except Exception:
            return [0.0] * 7
    
    @lru_cache(maxsize=config.SDA_VECTOR_CACHE_SIZE)
    def _calcular_todos_vetores(self, forcas: tuple) -> Dict[str, int]:
        # Este método ainda é chamado por 'managers.py' para o Data Lake.
        # É importante que ele continue funcional.
        if not hasattr(self, 'ARSENAL_VETORES'):
             # Fallback caso a classe tenha sido modificada e o arsenal removido
             self.ARSENAL_VETORES = ['V_REVERSION'] # Garante que não quebre
             
        if not forcas: return {v: config.SDA_FORCA_DEFAULT for v in self.ARSENAL_VETORES}
        
        # Definição do arsenal (necessário para o Data Lake)
        self.ARSENAL_VETORES = [
            'V_CONST', 'V_ALTER', 'V_PROG', 'V_WAVE', 'V_ACCEL', 
            'V_CLUSTER', 'V_EXPAND', 'V_PHASE', 'V_REVERSION',
            'V_SPECTRAL_PEAK', 'V_WAVELET_DECOMP', 'V_HURST_EXPONENT',
            'V_MARKOV_CHAIN', 'V_PHASE_SPACE', 'V_KALMAN_FILTER',
            'V_ENTROPIC_FORCE', 'V_QUANTUM_TUNNEL', 'V_PARTICLE_SWARM',
            'V_RECURRENCE_PLOT'
        ]
        
        resultados = {}
        for v in self.ARSENAL_VETORES:
            try:
                calc_func = getattr(self, f"_{v.lower()}_calc")
                resultados[v] = self._normalizar_forca(calc_func(forcas))
            except (AttributeError, TypeError):
                resultados[v] = config.SDA_FORCA_DEFAULT
        return resultados

    def _normalizar_forca(self, valor: float) -> int:
        return max(config.SDA_FORCA_MIN, min(config.SDA_FORCA_MAX, int(round(valor))))

    # ============== ARSENAL DE 19 VETORES (Mantido para Data Lake) ==============
    def _v_const_calc(self, f: tuple) -> float: return np.average(f, weights=np.array(config.SDA_MEMORY_WEIGHTS[:len(f)]))
    def _v_alter_calc(self, f: tuple) -> float: return f[0] - (f[0]-f[1]) if len(f)>1 else f[0]
    def _v_prog_calc(self, f: tuple) -> float:
        if len(f) < 2: return f[0]
        y = np.array(list(reversed(f))); x = np.arange(len(y))
        try: return np.poly1d(np.polyfit(x, y, 1))(len(y))
        except (np.linalg.LinAlgError, ValueError): return f[0]
    def _v_wave_calc(self, f: tuple) -> float: return f[2] if len(f)>2 else f[0]
    def _v_accel_calc(self, f: tuple) -> float:
        if len(f) < 3: return f[0]
        v1 = f[0]-f[1]; v2 = f[1]-f[2]; a = v1-v2
        return f[0] + v1 + a
    def _v_cluster_calc(self, f: tuple) -> float: return self.logic._encontrar_melhor_cluster_de_forca(list(f), 7, 2) or np.median(f)
    def _v_expand_calc(self, f: tuple) -> float:
        if len(f) < 4: return f[0]
        r_new = np.ptp(f[:2]); r_old = np.ptp(f[2:4])
        if r_new > r_old: return f[0] + (f[0] - np.mean(f[:2]))
        return np.mean(f[:2])
    def _v_phase_calc(self, f: tuple) -> float: return f[3] if len(f)>3 else f[0]
    def _v_reversion_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        m = np.mean(f)
        if len(f) > 1 and abs(f[0] - m) > 1.5 * np.std(f): return m
        return f[0]
    def _v_spectral_peak_calc(self, f: tuple) -> float:
        if not f or np.std(f) < 1: return np.mean(f) if f else config.SDA_FORCA_DEFAULT
        yf = rfft(np.array(f)); 
        if len(yf) < 2: return np.mean(f)
        idx = np.argmax(np.abs(yf[1:])) + 1
        return f[len(f) - (len(f)//idx)] if idx>0 and (len(f)//idx) < len(f) else f[0]
    def _v_wavelet_decomp_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        try:
            cA, cD = pywt.dwt(f, 'db1'); return cA[-1] + (cA[-1] - cA[-2]) if len(cA) > 1 else cA[-1]
        except ValueError: return np.mean(f)
        except NameError: return np.mean(f) 
    def _hurst_exponent_calc(self, f: np.ndarray) -> float:
        epsilon = 1e-9
        if len(f) < 6: return 0.5
        lags = range(2, 6)
        tau = [np.sqrt(np.std(np.subtract(f[lag:], f[:-lag]))) for lag in lags]
        tau_safe = [t if t > 0 else epsilon for t in tau]
        poly = np.polyfit(np.log(lags), np.log(tau_safe), 1)
        return poly[0]
    def _v_hurst_exponent_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        h = self._hurst_exponent_calc(np.array(f))
        if h > 0.55 and len(f) > 1: return f[0] + (f[0] - f[1])
        if h < 0.45 and len(f) > 1: return f[0] - (f[0] - f[1])
        return f[0]
    def _v_markov_chain_calc(self, f: tuple) -> float:
        if len(f) < 2: return f[0] if f else config.SDA_FORCA_DEFAULT
        states = np.digitize(f, bins=[12, 25]); trans = list(zip(states, states[1:])); last_state = states[0]
        counts = {s: {s_n: 0 for s_n in range(4)} for s in range(4)}
        for s1, s2 in trans: counts[s2][s1] += 1
        total_from_last = sum(counts[last_state].values())
        if total_from_last == 0: return config.SDA_FORCA_DEFAULT
        probs = {s_n: c / total_from_last for s_n, c in counts[last_state].items()}
        next_state = max(probs, key=probs.get); return [6, 18, 30][next_state]
    def _v_phase_space_calc(self, f: tuple) -> float:
        if len(f) < 4: return f[0] if f else config.SDA_FORCA_DEFAULT
        p1=(f[1],f[0]); p2=(f[2],f[1]); p3=(f[3],f[2]); v1 = (p1[0]-p2[0], p1[1]-p2[1]); v2 = (p2[0]-p3[0], p2[1]-p3[1])
        next_x = p1[0] + v1[0] + (v1[0]-v2[0]); return next_x
    def _v_kalman_filter_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        try:
            kf = KalmanFilter(f[-1]); return kf.process(reversed(f[:-1]))
        except NameError:
            return np.mean(f) 
    def _v_entropic_force_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        ent = self._shannon_entropy(np.array(f))
        if ent < 2.0: return config.SDA_FORCA_DEFAULT
        return np.average(f, weights=config.SDA_MEMORY_WEIGHTS[:len(f)])
    def _v_quantum_tunnel_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        m, s = np.mean(f), np.std(f)
        if s < 1: return m
        if f[0] > m + 1.8*s: return m - s
        if f[0] < m - 1.8*s: return m + s
        return f[0]
    def _v_particle_swarm_calc(self, f: tuple) -> float: 
        if not f: return config.SDA_FORCA_DEFAULT
        return np.median(sorted(f)[:4])
    def _v_recurrence_plot_calc(self, f: tuple) -> float:
        if not f: return config.SDA_FORCA_DEFAULT
        det = self._recurrence_determinism(np.array(f))
        if det > 0.4: return self._v_prog_calc(f)
        return self._v_reversion_calc(f)
    def _shannon_entropy(self, f: np.ndarray) -> float:
        if f.size == 0: return 0.0
        _, counts = np.unique(f, return_counts=True); probs = counts / len(f)
        if probs.size == 0: return 0.0
        return -np.sum(probs * np.log2(probs + 1e-9))
    def _recurrence_determinism(self, f: np.ndarray) -> float:
        if f.size == 0: return 0.0
        s = np.std(f)
        if s < 1e-6: return 1.0
        radius = s * 0.5
        rec_matrix = np.array([[1 if np.abs(i-j) < radius else 0 for j in f] for i in f])
        diag_sum = sum(np.trace(rec_matrix, offset=k) for k in range(1, len(f)))
        total_points = np.sum(rec_matrix); return diag_sum / total_points if total_points > 0 else 0


# ============== SDA GÊMEA (2 Regiões de 9 números cada) ==============

class EstrategiaSDAGemea(EstrategiaBase):
    """
    SDA Gêmea - Encontra 2 centros que maximizam a captura das 6 últimas forças.
    
    Cada centro tem gravidade 9 (4 vizinhos de cada lado = 9 números por região).
    Total: 18 números (se não houver sobreposição).
    
    Algoritmo:
    1. Encontra o 1º centro (C1) que captura o MÁXIMO de forças das 6
    2. Remove as forças capturadas por C1
    3. Encontra o 2º centro (C2) que captura o máximo das forças RESTANTES
    
    O cálculo respeita a natureza CIRCULAR do espaço de forças (1-37, onde 37 e 1 são vizinhos).
    """
    
    WHEEL_SIZE_FORCA = 37  # Forças vão de 1 a 37
    GRAVIDADE = 4  # 4 vizinhos de cada lado = 9 números por região
    
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(
            nome="SDA-Gêmea",
            descricao="2 regiões de 9 números cada (gravidade 4), maximizando captura das 6 últimas forças",
            logic_module=logic_module
        )
        
        # Performance
        self.performance_gemea = {
            "historico_gatilhos": [],
            "roi_historico": [],
            "roi_medio_12": 0.0,
            "total_ganhos": 0.0,
            "total_gastos": 0.0,
            "acertos": 0,
            "erros": 0
        }
        
        # Última análise para atualização de performance
        self.ultima_analise_gemea = None
        
        # Limiar para detectar outliers (margem de 30% sobre gravidade 9)
        self.LIMIAR_OUTLIER = 6
    
    def _calcular_variacao_circular(self, forca_anterior: int, forca_atual: int) -> int:
        """
        Calcula a variação entre duas forças considerando o espaço circular (1-37).
        Retorna o caminho mais curto com sinal:
        - Positivo = força aumentando (acelerando)
        - Negativo = força diminuindo (desacelerando)
        """
        diff_linear = forca_atual - forca_anterior
        
        # Calcular as duas possíveis distâncias circulares
        if diff_linear > 0:
            dist_positivo = diff_linear
            dist_negativo = diff_linear - self.WHEEL_SIZE_FORCA
        else:
            dist_negativo = diff_linear
            dist_positivo = diff_linear + self.WHEEL_SIZE_FORCA
        
        # Retornar o caminho mais curto
        if abs(dist_positivo) <= abs(dist_negativo):
            return dist_positivo
        else:
            return dist_negativo
    
    def _calcular_variacoes(self, forcas: List[int]) -> List[int]:
        """
        Calcula as variações entre forças consecutivas.
        
        Args:
            forcas: [F1, F2, F3, F4, F5, F6] onde F1 é a mais recente
            
        Returns:
            [V1, V2, V3, V4, V5] onde V1 = F2→F1
        """
        variacoes = []
        for i in range(len(forcas) - 1):
            # V[i] = F[i+1] → F[i] (força anterior para atual)
            variacao = self._calcular_variacao_circular(forcas[i + 1], forcas[i])
            variacoes.append(variacao)
        return variacoes
    
    def _detectar_e_remover_outliers(self, forcas: List[int], limiar: int = None) -> Tuple[List[int], List[int], List[int]]:
        """
        Detecta e remove forças outliers baseado nas variações.
        
        Uma variação > limiar indica que uma das forças é anômala.
        A força mais distante da mediana das forças é considerada o outlier.
        
        Args:
            forcas: Lista das forças [F1 mais recente, ..., F6 mais antiga]
            limiar: Limite absoluto para considerar variação anômala (default: 6)
        
        Returns:
            (forcas_filtradas, variacoes, indices_removidos)
        """
        if limiar is None:
            limiar = self.LIMIAR_OUTLIER
        
        if len(forcas) < 2:
            return forcas, [], []
        
        # Calcular variações
        variacoes = self._calcular_variacoes(forcas)
        
        # Calcular mediana das forças (considerando espaço circular)
        # Para simplificar, usamos média aritmética como aproximação
        media_forcas = sum(forcas) / len(forcas)
        
        # Identificar outliers
        indices_para_remover = set()
        
        for i, variacao in enumerate(variacoes):
            if abs(variacao) > limiar:
                # V[i] conecta F[i+1] → F[i]
                # Determinar qual força é o outlier
                f_anterior = forcas[i + 1]  # Força mais antiga
                f_atual = forcas[i]          # Força mais recente
                
                # Qual está mais longe da média?
                dist_anterior = self._calcular_distancia_circular_forca(f_anterior, int(media_forcas))
                dist_atual = self._calcular_distancia_circular_forca(f_atual, int(media_forcas))
                
                if dist_anterior > dist_atual:
                    indices_para_remover.add(i + 1)  # F[i+1] é outlier
                else:
                    indices_para_remover.add(i)      # F[i] é outlier
        
        # Remover outliers
        forcas_filtradas = [f for idx, f in enumerate(forcas) if idx not in indices_para_remover]
        
        # Garantir que sobrem pelo menos 3 forças
        if len(forcas_filtradas) < 3:
            # Se muitas formas foram removidas, usar forças originais
            return forcas, variacoes, []
        
        return forcas_filtradas, variacoes, sorted(list(indices_para_remover))
    
    def _calcular_distancia_circular_forca(self, f1: int, f2: int) -> int:
        """
        Calcula a distância mais curta entre duas forças no espaço circular (1-37).
        
        Exemplo:
        - dist(37, 1) = 1 (não 36!)
        - dist(1, 37) = 1
        - dist(20, 25) = 5
        """
        diff = abs(f1 - f2)
        return min(diff, self.WHEEL_SIZE_FORCA - diff)
    
    def _calcular_score_cluster(self, centro_candidato: int, forcas: List[int]) -> Tuple[int, List[int]]:
        """
        Calcula quantas forças estão dentro do raio de gravidade de um centro candidato.
        
        Args:
            centro_candidato: Força central candidata (1-37)
            forcas: Lista de forças a verificar
            
        Returns:
            (score, forcas_capturadas): Número de forças capturadas e quais foram
        """
        forcas_capturadas = []
        for forca in forcas:
            distancia = self._calcular_distancia_circular_forca(centro_candidato, forca)
            if distancia <= self.GRAVIDADE:
                forcas_capturadas.append(forca)
        return len(forcas_capturadas), forcas_capturadas
    
    def _encontrar_melhor_centro(self, forcas_disponiveis: List[int]) -> Tuple[int, int, List[int]]:
        """
        Encontra o centro que captura o máximo de forças disponíveis.
        
        Args:
            forcas_disponiveis: Lista de forças ainda disponíveis para captura
            
        Returns:
            (melhor_centro, score, forcas_capturadas)
        """
        melhor_centro = None
        melhor_score = -1
        melhores_capturadas = []
        
        # Testar cada força possível (1 a 37) como centro
        for centro_candidato in range(1, self.WHEEL_SIZE_FORCA + 1):
            score, capturadas = self._calcular_score_cluster(centro_candidato, forcas_disponiveis)
            
            if score > melhor_score:
                melhor_score = score
                melhor_centro = centro_candidato
                melhores_capturadas = capturadas
            elif score == melhor_score and melhor_centro is not None:
                # Em caso de empate, preferir centro mais próximo da média das forças
                media_forcas = sum(forcas_disponiveis) / len(forcas_disponiveis) if forcas_disponiveis else 18
                dist_atual = self._calcular_distancia_circular_forca(centro_candidato, int(media_forcas))
                dist_melhor = self._calcular_distancia_circular_forca(melhor_centro, int(media_forcas))
                if dist_atual < dist_melhor:
                    melhor_centro = centro_candidato
                    melhores_capturadas = capturadas
        
        return melhor_centro or 18, melhor_score, melhores_capturadas
    
    # ========== CLUSTER DE VARIAÇÕES ==========
    GRAVIDADE_VARIACAO = 3  # 3 vizinhos de cada lado = 7 valores no cluster (gravidade 6)
    
    def _calcular_score_cluster_variacao(self, centro_candidato: int, variacoes: List[int]) -> Tuple[int, List[int]]:
        """
        Calcula quantas variações estão dentro do raio de gravidade de um centro candidato.
        Variações vão de -18 a +18.
        
        Args:
            centro_candidato: Variação central candidata (-18 a +18)
            variacoes: Lista de variações a verificar
            
        Returns:
            (score, variacoes_capturadas)
        """
        variacoes_capturadas = []
        for variacao in variacoes:
            # Distância simples (variações são lineares, não circulares)
            distancia = abs(centro_candidato - variacao)
            if distancia <= self.GRAVIDADE_VARIACAO:
                variacoes_capturadas.append(variacao)
        return len(variacoes_capturadas), variacoes_capturadas
    
    def _encontrar_melhor_centro_variacao(self, variacoes_disponiveis: List[int]) -> Tuple[int, int, List[int]]:
        """
        Encontra o centro que captura o máximo de variações disponíveis.
        
        Args:
            variacoes_disponiveis: Lista de variações ainda disponíveis para captura
            
        Returns:
            (melhor_centro, score, variacoes_capturadas)
        """
        if not variacoes_disponiveis:
            return 0, 0, []
        
        melhor_centro = None
        melhor_score = -1
        melhores_capturadas = []
        
        # Testar cada variação possível (-18 a +18) como centro
        for centro_candidato in range(-18, 19):
            score, capturadas = self._calcular_score_cluster_variacao(centro_candidato, variacoes_disponiveis)
            
            if score > melhor_score:
                melhor_score = score
                melhor_centro = centro_candidato
                melhores_capturadas = capturadas
            elif score == melhor_score and melhor_centro is not None:
                # Em caso de empate, preferir centro mais próximo de 0 (neutro)
                if abs(centro_candidato) < abs(melhor_centro):
                    melhor_centro = centro_candidato
                    melhores_capturadas = capturadas
        
        return melhor_centro if melhor_centro is not None else 0, melhor_score, melhores_capturadas
    
    def _aplicar_variacao_circular(self, forca: int, variacao: int) -> int:
        """
        Aplica uma variação a uma força, respeitando o espaço circular (1-37).
        
        Args:
            forca: Força original (1-37)
            variacao: Variação a aplicar (-18 a +18)
            
        Returns:
            Nova força ajustada (1-37)
        """
        nova_forca = forca + variacao
        
        # Ajustar para espaço circular 1-37
        while nova_forca < 1:
            nova_forca += self.WHEEL_SIZE_FORCA
        while nova_forca > self.WHEEL_SIZE_FORCA:
            nova_forca -= self.WHEEL_SIZE_FORCA
        
        return nova_forca
    
    def _buscar_regiao_proxima_sem_conflito(self, centro_original: int, regioes_ocupadas: set, num_vizinhos: int) -> int:
        """
        Busca circular expandindo a partir do centro original.
        Retorna o centro mais próximo sem sobreposição para garantir 18 números distintos.
        
        Args:
            centro_original: Número central original
            regioes_ocupadas: Set de números já ocupados pela primeira região
            num_vizinhos: Quantidade de vizinhos de cada lado
            
        Returns:
            Número central da região sem conflito
        """
        try:
            idx_original = self.logic.ROULETTE_WHEEL_ORDER.index(centro_original)
        except (ValueError, TypeError):
            return centro_original
        
        # Busca expandindo em ambas as direções simultaneamente
        for offset in range(1, self.logic.wheel_size):
            # Testa horário
            idx_h = (idx_original + offset) % self.logic.wheel_size
            num_h = self.logic.ROULETTE_WHEEL_ORDER[idx_h]
            regiao_h = set(self.logic.get_roulette_region(num_h, num_vizinhos))
            if not regioes_ocupadas.intersection(regiao_h):
                return num_h
            
            # Testa anti-horário
            idx_ah = (idx_original - offset + self.logic.wheel_size) % self.logic.wheel_size
            num_ah = self.logic.ROULETTE_WHEEL_ORDER[idx_ah]
            regiao_ah = set(self.logic.get_roulette_region(num_ah, num_vizinhos))
            if not regioes_ocupadas.intersection(regiao_ah):
                return num_ah
        
        # Fallback: retorna o original (aceita sobreposição mínima)
        return centro_original

    
    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        """
        Análise principal da SDA Gêmea.
        
        LÓGICA DE DIREÇÃO:
        1. Verifica o sentido da ÚLTIMA jogada (direcao da jogada[-1])
        2. Presume que a PRÓXIMA jogada é no sentido CONTRÁRIO
        3. Coleta as forças do sentido da PRÓXIMA jogada
        4. Aplica a força a partir da CASA ATUAL (número da jogada[-1])
        
        ALGORITMO:
        1. Detectar outliers nas forças usando variações
        2. Encontrar C1 e C2 (clusters de forças)
        3. Encontrar VC1 e VC2 (clusters de variações)
        4. Ajustar: C1_final = C1 + VC1, C2_final = C2 + VC2
        5. Converter para números na roleta física
        6. Retornar 2 regiões de 9 números cada
        """
        if len(historico) < 6:
            return False, [], {"erro": "Histórico insuficiente (mínimo 6 jogadas)"}
        
        # ========== DETERMINAR DIREÇÃO DA PRÓXIMA JOGADA ==========
        # Regra: A próxima jogada é SEMPRE no sentido CONTRÁRIO da anterior
        # CONVENÇÃO: historico[0] = mais recente
        jogada_recente = historico[0]
        direcao_ultima_jogada = jogada_recente.get('direcao')
        
        # Sentido da PRÓXIMA jogada (oposto ao da última)
        direcao_proxima_jogada = 'anti-horario' if direcao_ultima_jogada == 'horario' else 'horario'
        
        # Casa atual (de onde a bola vai partir)
        numero_casa_atual = jogada_recente.get('numero')
        
        # ========== COLETAR FORÇAS DO SENTIDO DA PRÓXIMA JOGADA ==========
        # Usamos as forças históricas do mesmo sentido que a próxima jogada
        # CONVENÇÃO: historico já está ordenado com mais recente primeiro
        forcas_alvo = [
            j['distancia'] for j in historico 
            if j.get('direcao') == direcao_proxima_jogada and j.get('distancia') is not None
        ][:6]  # Pega as primeiras 6 (mais recentes)
        
        if len(forcas_alvo) < 6:
            return False, [], {"erro": f"Insuficiente forças na direção {direcao_proxima_jogada} (encontradas: {len(forcas_alvo)})"}
        
        # ========== NOVO: Detectar e remover outliers ==========
        # forcas_alvo já está [F1 mais recente, ..., F6 mais antiga]
        forcas_ordenadas = forcas_alvo
        
        # Aplicar detecção de outliers
        forcas_filtradas, variacoes, indices_removidos = self._detectar_e_remover_outliers(forcas_ordenadas)
        
        # ========== PASSO 1: Encontrar o 1º centro (C1) ==========
        c1_forca, c1_score, c1_capturadas = self._encontrar_melhor_centro(forcas_filtradas)
        
        # ========== PASSO 2: Remover forças capturadas por C1 ==========
        forcas_restantes = [f for f in forcas_filtradas if f not in c1_capturadas]
        
        # ========== PASSO 3: Encontrar o 2º centro (C2) ==========
        if forcas_restantes:
            c2_forca, c2_score, c2_capturadas = self._encontrar_melhor_centro(forcas_restantes)
        else:
            # Se não sobrou nenhuma força, usar uma posição oposta ao C1
            c2_forca = ((c1_forca - 1 + self.WHEEL_SIZE_FORCA // 2) % self.WHEEL_SIZE_FORCA) + 1
            c2_score = 0
            c2_capturadas = []
        
        # ========== PASSO 4: CLUSTER DE VARIAÇÕES (NOVO) ==========
        # Encontrar VC1 e VC2 usando as 5 variações
        if variacoes:
            # VC1: Cluster que captura mais variações
            vc1_centro, vc1_score, vc1_capturadas = self._encontrar_melhor_centro_variacao(variacoes)
            
            # Remover variações capturadas por VC1
            variacoes_restantes = [v for v in variacoes if v not in vc1_capturadas]
            
            # VC2: Cluster das variações restantes
            if variacoes_restantes:
                vc2_centro, vc2_score, vc2_capturadas = self._encontrar_melhor_centro_variacao(variacoes_restantes)
            else:
                # Se não sobrou, usar variação oposta
                vc2_centro = -vc1_centro if vc1_centro != 0 else 0
                vc2_score = 0
                vc2_capturadas = []
        else:
            vc1_centro, vc1_score, vc1_capturadas = 0, 0, []
            vc2_centro, vc2_score, vc2_capturadas = 0, 0, []
        
        # ========== PASSO 5: AJUSTAR C1 e C2 com VC1 e VC2 ==========
        c1_forca_ajustada = self._aplicar_variacao_circular(c1_forca, vc1_centro)
        c2_forca_ajustada = self._aplicar_variacao_circular(c2_forca, vc2_centro)
        
        # ========== PASSO 6: Converter forças AJUSTADAS para números na roleta ==========
        # A força é aplicada a partir da CASA ATUAL no sentido da PRÓXIMA JOGADA
        c1_numero = self.logic.calcular_centro_alvo(numero_casa_atual, c1_forca_ajustada, direcao_proxima_jogada)
        c2_numero = self.logic.calcular_centro_alvo(numero_casa_atual, c2_forca_ajustada, direcao_proxima_jogada)
        
        # ========== PASSO 7: Gerar região de C1 (9 números) ==========
        regiao_c1 = set(self.logic.get_roulette_region(c1_numero, self.GRAVIDADE))
        
        # ========== PASSO 8: Verificar sobreposição e resolver ==========
        # Se C2 sobrepõe C1, mover C2 para a região mais próxima sem conflito
        regiao_c2_original = set(self.logic.get_roulette_region(c2_numero, self.GRAVIDADE))
        
        if regiao_c1.intersection(regiao_c2_original):
            # Há sobreposição! Buscar região mais próxima sem conflito
            c2_numero_original = c2_numero
            c2_numero = self._buscar_regiao_proxima_sem_conflito(c2_numero, regiao_c1, self.GRAVIDADE)
            regiao_c2 = set(self.logic.get_roulette_region(c2_numero, self.GRAVIDADE))
            c2_foi_movido = True
        else:
            regiao_c2 = regiao_c2_original
            c2_foi_movido = False
            c2_numero_original = c2_numero
        
        # Resultado final: 18 números distintos (9 + 9)
        numeros_finais = regiao_c1.union(regiao_c2)
        
        # Visual das regiões
        visual_c1 = self.logic.get_roulette_region_visual(c1_numero, self.GRAVIDADE)
        visual_c2 = self.logic.get_roulette_region_visual(c2_numero, self.GRAVIDADE)
        
        # Calcular score total
        score_total = c1_score + c2_score
        
        # Detalhes para UI
        detalhes = {
            "forcas_de_entrada": forcas_alvo,
            "forcas_ordenadas": forcas_ordenadas,  # [F1 mais recente, ..., F6 mais antiga]
            "variacoes": variacoes,                 # [V1, V2, V3, V4, V5]
            "outliers_removidos": indices_removidos,
            "forcas_filtradas": forcas_filtradas,   # Forças após remover outliers
            # Informações de direção
            "direcao_ultima_jogada": direcao_ultima_jogada,
            "direcao_proxima_jogada": direcao_proxima_jogada,
            "numero_casa_atual": numero_casa_atual,
            # Cluster de Variações
            "cluster_variacao_1": {
                "centro": vc1_centro,
                "score": vc1_score,
                "variacoes_capturadas": vc1_capturadas
            },
            "cluster_variacao_2": {
                "centro": vc2_centro,
                "score": vc2_score,
                "variacoes_capturadas": vc2_capturadas
            },
            # Centro 1
            "centro_1": {
                "forca_original": c1_forca,
                "variacao_aplicada": vc1_centro,
                "forca_ajustada": c1_forca_ajustada,
                "numero": c1_numero,
                "score": c1_score,
                "forcas_capturadas": c1_capturadas,
                "regiao_visual": visual_c1
            },
            # Centro 2 (com resolução de sobreposição se necessário)
            "centro_2": {
                "forca_original": c2_forca,
                "variacao_aplicada": vc2_centro,
                "forca_ajustada": c2_forca_ajustada,
                "numero_original": c2_numero_original,
                "numero": c2_numero,
                "foi_movido": c2_foi_movido,
                "score": c2_score,
                "forcas_capturadas": c2_capturadas,
                "regiao_visual": visual_c2
            },
            "score_total": score_total,
            "centros_finais": [c1_numero, c2_numero],
            "total_numeros": len(numeros_finais),
            "vizinhos_utilizados": f"{self.GRAVIDADE}L × 2 regiões (18 números distintos)",
            "regiao_visual_sugerida": f"{visual_c1} | {visual_c2}"
        }
        
        # Armazenar para atualização de performance
        self.ultima_analise_gemea = {
            "numeros": sorted(list(numeros_finais)),
            "detalhes": detalhes
        }
        print(f"[SDA Gêmea] Análise concluída: {len(numeros_finais)} números sugeridos, Centros: {c1_numero}, {c2_numero}")
        
        return True, sorted(list(numeros_finais)), detalhes
    
    def atualizar_performance_gemea(self, numero_sorteado: int, numeros_apostados: List[int], ganho: float, custo: float):
        """
        Atualiza a performance da SDA Gêmea após o resultado.
        Similar a atualizar_performance_espelho.
        """
        if not self.ultima_analise_gemea:
            return
        
        numeros_sugeridos = self.ultima_analise_gemea.get("numeros", [])
        
        if not numeros_sugeridos:
            return
        
        # Verificar se acertou o número sorteado
        acertou = numero_sorteado in numeros_sugeridos
        custo_gemea = len(numeros_sugeridos) * config.CUSTO_POR_NUMERO_BASE
        
        # Atualizar histórico (insert no início para manter mais recentes primeiro)
        hist_gemea = self.performance_gemea["historico_gatilhos"]
        hist_gemea.insert(0, acertou)
        if len(hist_gemea) > config.SDA_SELECAO_ROI_JANELA:
            hist_gemea.pop()
        
        # Calcular ROI
        if acertou and custo_gemea > 0:
            ganho_gemea = (custo_gemea / len(numeros_sugeridos)) * config.PAYOUT_FACTOR
            roi_gemea = ganho_gemea - custo_gemea
            self.performance_gemea["total_ganhos"] += ganho_gemea
            self.performance_gemea["acertos"] += 1
        else:
            roi_gemea = -custo_gemea
            self.performance_gemea["erros"] += 1
        
        self.performance_gemea["total_gastos"] += custo_gemea
        
        # Atualizar ROI histórico
        roi_hist_gemea = self.performance_gemea["roi_historico"]
        roi_hist_gemea.insert(0, roi_gemea)
        if len(roi_hist_gemea) > config.SDA_SELECAO_ROI_JANELA:
            roi_hist_gemea.pop()
        
        # Calcular ROI médio das últimas 12
        if roi_hist_gemea:
            self.performance_gemea["roi_medio_12"] = sum(roi_hist_gemea) / len(roi_hist_gemea)
        else:
            self.performance_gemea["roi_medio_12"] = 0.0
    
    def get_state(self) -> dict:
        return {
            "performance_gemea": self.performance_gemea
        }
    
    def reset_from_saved_state(self, state: dict):
        if "performance_gemea" in state:
            self.performance_gemea = state["performance_gemea"]


class EstrategiaSinergiaDirecionalAvancadaEspelho(EstrategiaBase):
    """
    SDA Espelho - Usa as últimas 4 forças para gerar 4 regiões de 3 números cada.
    Total: 12 números únicos com resolução automática de sobreposições.
    """
    def __init__(self, logic_module: RouletteLogic):
        super().__init__(
            nome="SDA-Espelho",
            descricao="4 números centrais com 1 vizinho de cada lado (total 12 números) usando as últimas 4 forças",
            logic_module=logic_module
        )
        # Estrutura de performance própria
        self.performance_espelho = {
            "historico_gatilhos": [],
            "roi_historico": [],
            "roi_medio_12": 0.0,
            "total_ganhos": 0.0,
            "total_gastos": 0.0,
            "acertos": 0,
            "erros": 0
        }
        # Armazenar última análise para atualização de performance
        self.ultima_analise_espelho = None

    def _buscar_regiao_proxima_sem_conflito(self, centro_original: int, regioes_ocupadas: set, num_vizinhos: int) -> int:
        """
        Busca circular expandindo a partir do centro original.
        Retorna o centro mais próximo sem sobreposição.
        """
        try:
            idx_original = self.logic.ROULETTE_WHEEL_ORDER.index(centro_original)
        except (ValueError, TypeError):
            return centro_original
        
        # Busca expandindo em ambas as direções simultaneamente
        for offset in range(1, self.logic.wheel_size):
            # Testa horário
            idx_h = (idx_original + offset) % self.logic.wheel_size
            num_h = self.logic.ROULETTE_WHEEL_ORDER[idx_h]
            regiao_h = set(self.logic.get_roulette_region(num_h, num_vizinhos))
            if not regioes_ocupadas.intersection(regiao_h):
                return num_h
            
            # Testa anti-horário
            idx_ah = (idx_original - offset + self.logic.wheel_size) % self.logic.wheel_size
            num_ah = self.logic.ROULETTE_WHEEL_ORDER[idx_ah]
            regiao_ah = set(self.logic.get_roulette_region(num_ah, num_vizinhos))
            if not regioes_ocupadas.intersection(regiao_ah):
                return num_ah
        
        # Fallback: retorna o original (aceita sobreposição mínima)
        return centro_original

    def _resolver_deconflito_espelho(self, centros_candidatos: List[int], num_anterior: int, direcao_alvo: str) -> List[int]:
        """
        Resolve sobreposições procurando a região mais próxima sem conflito.
        Mantém F1 como prioridade absoluta.
        """
        centros_finais = []
        regioes_ocupadas = set()
        num_vizinhos = config.SDA_ESPELHO_VIZINHOS_APOSTA
        
        # F1 sempre é aceito (prioridade)
        if centros_candidatos:
            centro_f1 = centros_candidatos[0]
            centros_finais.append(centro_f1)
            regioes_ocupadas.update(self.logic.get_roulette_region(centro_f1, num_vizinhos))
        
        # Processar F2, F3, F4
        for i, centro_candidato in enumerate(centros_candidatos[1:], start=1):
            regiao_candidata = set(self.logic.get_roulette_region(centro_candidato, num_vizinhos))
            
            # Se não há sobreposição, aceita o centro original
            if not regioes_ocupadas.intersection(regiao_candidata):
                centros_finais.append(centro_candidato)
                regioes_ocupadas.update(regiao_candidata)
                continue
            
            # Busca circular: encontrar região mais próxima sem sobreposição
            centro_encontrado = self._buscar_regiao_proxima_sem_conflito(
                centro_candidato, regioes_ocupadas, num_vizinhos
            )
            centros_finais.append(centro_encontrado)
            regioes_ocupadas.update(self.logic.get_roulette_region(centro_encontrado, num_vizinhos))
        
        return centros_finais

    def analisar(self, historico: list[dict], contexto: ContextoAnalise) -> tuple[bool, list[int], dict]:
        """
        Implementação da lógica SDA Espelho.
        Usa as últimas 4 forças para gerar 4 regiões de 3 números cada.
        """
        # --- FASE 1: Coleta e Validação de Dados ---
        if len(historico) < config.SDA_ESPELHO_TOTAL_FORCAS:
            return False, [], {}
        
        # CONVENÇÃO: historico[0] = mais recente
        jogada_recente = historico[0]
        direcao_alvo = 'anti-horario' if jogada_recente.get('direcao') == 'horario' else 'horario'
        
        # Coleta forças da direção alvo (historico já está ordenado com mais recente primeiro)
        forcas_disponiveis = [j['distancia'] for j in historico if j.get('direcao') == direcao_alvo and j.get('distancia', 0) > 0]
        # Pega as primeiras N forças (que são as mais recentes) - já estão [F1, F2, F3, F4]
        forcas_alvo = forcas_disponiveis[:config.SDA_ESPELHO_TOTAL_FORCAS]
        
        if len(forcas_alvo) < config.SDA_ESPELHO_TOTAL_FORCAS:
            return False, [], {}
        
        num_anterior = jogada_recente.get('numero')
        
        # --- FASE 2: Cálculo dos 4 centros candidatos ---
        # Todas as forças são aplicadas a partir do mesmo ponto: num_anterior (último número sorteado)
        centros_candidatos = []
        for forca in forcas_alvo:  # F1, F2, F3, F4 (F1 é o mais recente)
            # Aplicar força a partir de num_anterior no sentido direcao_alvo
            centro = self.logic.calcular_centro_alvo(num_anterior, forca, direcao_alvo)
            centros_candidatos.append(centro)
        
        # --- FASE 3: Resolução de sobreposições ---
        centros_finais = self._resolver_deconflito_espelho(centros_candidatos, num_anterior, direcao_alvo)
        
        # --- FASE 4: Geração dos números finais ---
        numeros_finais = set()
        num_vizinhos = config.SDA_ESPELHO_VIZINHOS_APOSTA
        
        for centro in centros_finais:
            numeros_finais.update(self.logic.get_roulette_region(centro, num_vizinhos))
        
        # --- FASE 5: Formatação de detalhes para UI ---
        regioes_visuais = []
        for centro in centros_finais:
            regiao_visual = self.logic.get_roulette_region_visual(centro, num_vizinhos)
            regioes_visuais.append(regiao_visual)
        
        sobreposicoes_resolvidas = len(centros_candidatos) != len(set(centros_finais))
        
        detalhes = {
            "forcas_de_entrada": forcas_alvo,  # [F1, F2, F3, F4]
            "centros_candidatos_originais": centros_candidatos,
            "centros_finais": centros_finais,
            "regioes_visuais": regioes_visuais,
            "descricao": "4 números centrais com 1 vizinho de cada lado",
            "total_numeros": len(numeros_finais),
            "sobreposicoes_resolvidas": sobreposicoes_resolvidas,
            "roi_medio_12": self.performance_espelho["roi_medio_12"],
            "vizinhos_utilizados": f"1L (Total 3n por região)",
            "regiao_visual_sugerida": " / ".join(regioes_visuais)
        }
        
        # Armazenar última análise para atualização de performance
        self.ultima_analise_espelho = {
            "deve_apostar": True,  # SDA Espelho sempre pode apostar se flag estiver ativo
            "numeros": sorted(list(numeros_finais)),
            "detalhes": detalhes
        }
        
        # SDA Espelho só deve apostar se o flag estiver ativo
        deve_apostar = contexto.usar_sda_espelho and len(numeros_finais) > 0
        
        return deve_apostar, sorted(list(numeros_finais)), detalhes

    def atualizar_performance_espelho(self, numero_sorteado: int, numeros_apostados: List[int], ganho: float, custo: float):
        """
        Atualiza o performance da SDA Espelho.
        Similar a atualizar_performance_principal da SDA principal.
        """
        if not self.ultima_analise_espelho:
            return
        
        numeros_sugeridos = self.ultima_analise_espelho.get("numeros", [])
        
        if not numeros_sugeridos:
            return
        
        # Verificar se acertou o número sorteado
        acertou = numero_sorteado in numeros_sugeridos
        custo_espelho = len(numeros_sugeridos) * config.CUSTO_POR_NUMERO_BASE
        
        # Atualizar histórico
        hist_espelho = self.performance_espelho["historico_gatilhos"]
        hist_espelho.insert(0, acertou)
        if len(hist_espelho) > config.SDA_SELECAO_ROI_JANELA:
            hist_espelho.pop()
        
        # Calcular ROI
        if acertou and custo_espelho > 0:
            ganho_espelho = (custo_espelho / len(numeros_sugeridos)) * config.PAYOUT_FACTOR
            roi_espelho = ganho_espelho - custo_espelho
            self.performance_espelho["total_ganhos"] += ganho_espelho
            self.performance_espelho["acertos"] += 1
        else:
            roi_espelho = -custo_espelho
            self.performance_espelho["erros"] += 1
        
        self.performance_espelho["total_gastos"] += custo_espelho
        
        # Atualizar ROI histórico
        roi_hist_espelho = self.performance_espelho["roi_historico"]
        roi_hist_espelho.insert(0, roi_espelho)
        if len(roi_hist_espelho) > config.SDA_SELECAO_ROI_JANELA:
            roi_hist_espelho.pop()
        
        # Calcular ROI médio das últimas 12
        if roi_hist_espelho:
            self.performance_espelho["roi_medio_12"] = sum(roi_hist_espelho) / len(roi_hist_espelho)
        else:
            self.performance_espelho["roi_medio_12"] = 0.0

class KalmanFilter:
    def __init__(self, x0, P=1.0, R=4.0, Q=0.1): self.x=float(x0); self.P=float(P); self.R=float(R); self.Q=float(Q)
    def process(self, Z):
        for z_val in Z:
            z = float(z_val)
            self.P += self.Q
            K = self.P / (self.P + self.R)
            self.x += K * (z - self.x)
            self.P *= (1.0 - K)
        return self.x