# RoletaV11/domain/logic.py

import logging
import numpy as np
import statistics
from typing import List, Tuple, Dict, Optional, Set

from core import config

class RouletteLogic: 
    """Contém toda a lógica pura e utilitários para análise da roleta.""" 

    def __init__(self): 
        """Inicializa a classe de lógica, pré-calculando as micro-regiões.""" 
        self.ROULETTE_WHEEL_ORDER: List[int] = config.ROULETTE_WHEEL_ORDER 
        self.wheel_size: int = len(self.ROULETTE_WHEEL_ORDER) 
        self.micro_regions: Dict[int, List[int]] = self._gerar_definicoes_micro_regiões() 

    # --- MÉTODOS PÚBLICOS DE CÁLCULO ---

    def calcular_distancia_giro(self, num_anterior: int, num_atual: int, direcao: str) -> Optional[int]:
        """Calcula a distância percorrida em 'casas'.""" 
        try: 
            if num_anterior == num_atual: 
                return self.wheel_size

            idx_anterior = self.ROULETTE_WHEEL_ORDER.index(num_anterior) 
            idx_atual = self.ROULETTE_WHEEL_ORDER.index(num_atual) 
            
            if direcao == 'anti-horario': 
                return (idx_anterior - idx_atual + self.wheel_size) % self.wheel_size 
            elif direcao == 'horario': 
                return (idx_atual - idx_anterior + self.wheel_size) % self.wheel_size 
            else:
                logging.warning(f"Direção de giro inválida recebida: '{direcao}'.")
                return None
        except (ValueError, TypeError): 
            logging.warning(f"Número inválido encontrado ao calcular distância: {num_anterior} ou {num_atual}.")
            return None

    def calcular_centro_alvo(self, num_anterior: int, forca: int, direcao_alvo: str) -> int:
        """Calcula o número central de uma aposta a partir de um número de partida."""
        try:
            _, _, idx_anterior = self._get_wheel_context(num_anterior)
            if idx_anterior == -1: return num_anterior
            
            idx_calculado = (idx_anterior + forca) % self.wheel_size if direcao_alvo == 'horario' else (idx_anterior - forca + self.wheel_size) % self.wheel_size

            return self._get_number_from_index(idx_calculado)
        except (ValueError, TypeError):
            return num_anterior

    def get_roulette_region(self, center_number: int, num_neighbors: int) -> List[int]:
        """Calcula uma lista de números na roleta com base em um número central e vizinhos."""
        try:
            center_index = self.ROULETTE_WHEEL_ORDER.index(center_number)
        except (ValueError, TypeError):
            return []
            
        region = []
        for i in range(-num_neighbors, num_neighbors + 1):
            neighbor_index = (center_index + i + self.wheel_size) % self.wheel_size
            region.append(self.ROULETTE_WHEEL_ORDER[neighbor_index])
            
        return region

    def get_roulette_region_visual(self, center_number: int, num_neighbors: int) -> str:
        """Cria a representação visual de uma aposta."""
        try:
            center_index = self.ROULETTE_WHEEL_ORDER.index(center_number)
        except (ValueError, TypeError):
            return f"[{center_number}]"

        region_parts = []
        for i in range(-num_neighbors, num_neighbors + 1):
            neighbor_index = (center_index + i + self.wheel_size) % self.wheel_size
            number = self.ROULETTE_WHEEL_ORDER[neighbor_index]
            
            if i == 0:
                region_parts.append(f"[{number}]")
            else:
                region_parts.append(str(number))
        
        return " ".join(region_parts)
    
    # --- MÉTODOS DE ANÁLISE DE FORÇA (LÓGICA CIRCULAR) ---

    def calcular_distancia_circular_forca(self, f1: int, f2: int) -> int: 
        """Calcula a distância circular mais curta entre duas FORÇAS no universo de 1 a 37.""" 
        universo = self.wheel_size 
        dist_linear = abs(f1 - f2) 
        return min(dist_linear, universo - dist_linear) 

    def identificar_forcas_em_cesta(self, forcas_disponiveis: Set[int], centro_forca: int, vizinhos: int) -> Set[int]:
        """Identifica e retorna as FORÇAS dentro de uma cesta circular."""
        cesta_forcas = set()
        raio = vizinhos // 2 
        for f in forcas_disponiveis:
            if self.calcular_distancia_circular_forca(f, centro_forca) <= raio:
                cesta_forcas.add(f)
        return cesta_forcas

    # --- ARSENAL DO ORÁCULO: MÉTODOS DE ANÁLISE GEOMÉTRICA DO DNA ---

    def _calcular_indice_tendencia(self, forcas: tuple) -> float:
        """Mede a força e direção do momentum. Retorna de -1.0 a +1.0."""
        if len(forcas) < 2: return 0.0
        try:
            x = np.arange(len(forcas))
            y = np.array(forcas)
            slope, _ = np.polyfit(x, y, 1)
            return np.clip(slope / 18.0, -1.0, 1.0)
        except (np.linalg.LinAlgError, ValueError):
            return 0.0

    def _calcular_indice_volatilidade(self, forcas: tuple) -> float:
        """Mede o caos e a dispersão. Retorna de 0.0 a 1.0."""
        if len(forcas) < 2: return 0.0
        std_dev = np.std(forcas)
        return np.clip(std_dev / 11.0, 0.0, 1.0)

    def _calcular_indice_oscilacao(self, forcas: tuple) -> float:
        """Mede o 'zigue-zague' do sinal. Retorna de 0.0 a 1.0."""
        if len(forcas) < 3: return 0.0
        diffs = np.diff(forcas)
        sign_changes = np.diff(np.sign(diffs)) != 0
        return np.sum(sign_changes) / (len(forcas) - 2)

    def gerar_perfil_geometrico_dna(self, forcas: tuple) -> dict:
        """Orquestra a análise geométrica, retornando o perfil completo do DNA."""
        if not isinstance(forcas, tuple): forcas = tuple(forcas)
        
        return {
            'tendencia': self._calcular_indice_tendencia(forcas),
            'volatilidade': self._calcular_indice_volatilidade(forcas),
            'oscilacao': self._calcular_indice_oscilacao(forcas)
        }
    
    # --- MÉTODOS HELPER ---

    def _calcular_distancia_entre_numeros(self, num1: int, num2: int) -> int: 
        try: 
            idx1 = self.ROULETTE_WHEEL_ORDER.index(num1); idx2 = self.ROULETTE_WHEEL_ORDER.index(num2); dist = abs(idx1 - idx2) 
            return min(dist, self.wheel_size - dist) 
        except (ValueError, TypeError): return self.wheel_size 

    def _gerar_definicoes_micro_regiões(self) -> Dict[int, List[int]]: 
        micro_regioes = {0: [0]} 
        for key_number in config.NUMEROS_CHAVE_MICRO_REGIOES: 
            try: 
                key_index = self.ROULETTE_WHEEL_ORDER.index(key_number) 
                neighbor_anti_horario = self.ROULETTE_WHEEL_ORDER[(key_index - 1 + self.wheel_size) % self.wheel_size] 
                neighbor_horario = self.ROULETTE_WHEEL_ORDER[(key_index + 1) % self.wheel_size] 
                micro_regioes[key_number] = sorted([neighbor_anti_horario, key_number, neighbor_horario]) 
            except ValueError: pass
        return micro_regioes 

    def _get_wheel_context(self, number: int) -> tuple[int, int, int]: 
        try: 
            return number, self.wheel_size, self.ROULETTE_WHEEL_ORDER.index(number) 
        except (ValueError, TypeError): return number, self.wheel_size, -1 

    def _get_number_from_index(self, index: int) -> int: 
        return self.ROULETTE_WHEEL_ORDER[index % self.wheel_size]
