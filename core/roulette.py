"""
Roleta Cloud - Core
====================

Este módulo contém a representação da REALIDADE FÍSICA da roleta europeia.
Ele é IMUTÁVEL e representa fatos absolutos sobre o jogo.

O Core não contém estratégias, UI, ou lógica de negócio.
Apenas cálculos matemáticos puros sobre a roleta.

Autor: Roleta Cloud Team
Versão: 1.0.0
"""

from typing import List, Set, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """Direção de rotação da roleta"""
    CLOCKWISE = "horario"          # Sentido horário
    COUNTERCLOCKWISE = "anti-horario"  # Sentido anti-horário
    
    @classmethod
    def opposite(cls, direction: 'Direction') -> 'Direction':
        """Retorna a direção oposta"""
        if direction == cls.CLOCKWISE:
            return cls.COUNTERCLOCKWISE
        return cls.CLOCKWISE
    
    @classmethod
    def from_string(cls, s: str) -> 'Direction':
        """Converte string para Direction"""
        if s in ("horario", "clockwise", "cw"):
            return cls.CLOCKWISE
        return cls.COUNTERCLOCKWISE


class Color(Enum):
    """Cores dos números da roleta"""
    RED = "vermelho"
    BLACK = "preto"
    GREEN = "verde"


@dataclass(frozen=True)
class RouletteNumber:
    """Representa um número da roleta com todas suas propriedades"""
    value: int
    position: int  # Posição física na roda (0-36)
    color: Color
    
    def __str__(self):
        return f"{self.value}"
    
    def __repr__(self):
        return f"RouletteNumber({self.value}, pos={self.position}, {self.color.value})"


class RouletteCore:
    """
    Núcleo imutável da roleta europeia.
    
    Representa a REALIDADE FÍSICA da roleta:
    - 37 casas (0-36)
    - Formato circular
    - Sequência física dos números
    - Direções de rotação
    
    TODOS os cálculos são baseados na geometria circular.
    """
    
    # ========== CONSTANTES FÍSICAS (IMUTÁVEIS) ==========
    
    # Ordem dos números na roda física (sentido horário, começando do 0)
    WHEEL_SEQUENCE: List[int] = [
        0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 
        11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 
        22, 18, 29, 7, 28, 12, 35, 3, 26
    ]
    
    # Total de casas
    TOTAL_SLOTS: int = 37
    
    # Conjuntos de cores
    RED_NUMBERS: Set[int] = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    BLACK_NUMBERS: Set[int] = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
    GREEN_NUMBERS: Set[int] = {0}
    
    # Mapeamento número -> posição (calculado uma vez)
    _position_map: dict = None
    
    def __init__(self):
        """Inicializa os mapeamentos internos"""
        if RouletteCore._position_map is None:
            RouletteCore._position_map = {
                num: idx for idx, num in enumerate(self.WHEEL_SEQUENCE)
            }
    
    # ========== MÉTODOS DE CONSULTA ==========
    
    def get_position(self, number: int) -> int:
        """
        Retorna a posição física de um número na roda.
        
        Args:
            number: Número da roleta (0-36)
            
        Returns:
            Posição na roda (0-36)
        """
        if number < 0 or number > 36:
            raise ValueError(f"Número inválido: {number}. Deve ser 0-36.")
        return self._position_map[number]
    
    def get_number_at_position(self, position: int) -> int:
        """
        Retorna o número em uma posição física da roda.
        
        Args:
            position: Posição na roda (0-36)
            
        Returns:
            Número da roleta
        """
        position = position % self.TOTAL_SLOTS
        return self.WHEEL_SEQUENCE[position]
    
    def get_color(self, number: int) -> Color:
        """Retorna a cor de um número"""
        if number in self.GREEN_NUMBERS:
            return Color.GREEN
        if number in self.RED_NUMBERS:
            return Color.RED
        return Color.BLACK
    
    def get_roulette_number(self, number: int) -> RouletteNumber:
        """Retorna objeto RouletteNumber com todas as propriedades"""
        return RouletteNumber(
            value=number,
            position=self.get_position(number),
            color=self.get_color(number)
        )
    
    # ========== CÁLCULOS CIRCULARES ==========
    
    def calculate_distance(
        self, 
        from_number: int, 
        to_number: int, 
        direction: Direction
    ) -> int:
        """
        Calcula a distância circular entre dois números.
        
        A distância é medida em "casas" na roda física.
        
        Args:
            from_number: Número de origem
            to_number: Número de destino
            direction: Direção da contagem
            
        Returns:
            Distância em casas (1-36)
        """
        from_pos = self.get_position(from_number)
        to_pos = self.get_position(to_number)
        
        if direction == Direction.CLOCKWISE:
            # Sentido horário: to - from (com wrap-around)
            distance = (to_pos - from_pos) % self.TOTAL_SLOTS
        else:
            # Sentido anti-horário: from - to (com wrap-around)
            distance = (from_pos - to_pos) % self.TOTAL_SLOTS
        
        # Distância 0 significa mesmo número, mas se são diferentes, é 37 (volta completa)
        if distance == 0 and from_number != to_number:
            distance = self.TOTAL_SLOTS
            
        return distance
    
    def calculate_force(self, from_number: int, to_number: int) -> Tuple[int, Direction]:
        """
        Calcula a "força" entre dois números.
        
        Força é a menor distância entre os números, 
        junto com a direção dessa distância.
        
        Args:
            from_number: Número de origem
            to_number: Número de destino
            
        Returns:
            Tupla (força, direção)
        """
        dist_cw = self.calculate_distance(from_number, to_number, Direction.CLOCKWISE)
        dist_ccw = self.calculate_distance(from_number, to_number, Direction.COUNTERCLOCKWISE)
        
        if dist_cw <= dist_ccw:
            return dist_cw, Direction.CLOCKWISE
        return dist_ccw, Direction.COUNTERCLOCKWISE
    
    def calculate_target(
        self, 
        from_number: int, 
        force: int, 
        direction: Direction
    ) -> int:
        """
        Calcula o número alvo dado um número inicial, força e direção.
        
        Este é o cálculo INVERSO da força:
        Dado onde estou + quanto andar + pra onde = onde chego
        
        Args:
            from_number: Número de origem
            force: Quantidade de casas a percorrer
            direction: Direção do movimento
            
        Returns:
            Número de destino
        """
        from_pos = self.get_position(from_number)
        
        if direction == Direction.CLOCKWISE:
            target_pos = (from_pos + force) % self.TOTAL_SLOTS
        else:
            target_pos = (from_pos - force) % self.TOTAL_SLOTS
        
        return self.get_number_at_position(target_pos)
    
    # ========== REGIÕES E VIZINHOS ==========
    
    def get_neighbors(self, center: int, radius: int) -> List[int]:
        """
        Retorna os vizinhos de um número.
        
        Args:
            center: Número central
            radius: Quantidade de vizinhos de cada lado
            
        Returns:
            Lista de números (inclui o centro)
            Total: radius * 2 + 1 números
        """
        center_pos = self.get_position(center)
        neighbors = []
        
        for offset in range(-radius, radius + 1):
            pos = (center_pos + offset) % self.TOTAL_SLOTS
            neighbors.append(self.get_number_at_position(pos))
        
        return neighbors
    
    def get_region(self, center: int, radius: int) -> Set[int]:
        """
        Retorna região como conjunto (para operações de set).
        """
        return set(self.get_neighbors(center, radius))
    
    def get_visual_region(self, center: int, radius: int) -> str:
        """
        Retorna representação visual da região.
        Formato: "num1-CENTRO-numN"
        """
        neighbors = self.get_neighbors(center, radius)
        if len(neighbors) >= 3:
            return f"{neighbors[0]}─{center}─{neighbors[-1]}"
        return str(center)
    
    # ========== DISTÂNCIA CIRCULAR DE FORÇA ==========
    
    def calculate_force_distance(self, force1: int, force2: int) -> int:
        """
        Calcula distância circular entre duas forças.
        
        Forças vão de 1 a 37, e são circulares.
        
        Args:
            force1: Primeira força
            force2: Segunda força
            
        Returns:
            Menor distância circular entre as forças
        """
        diff = abs(force1 - force2)
        return min(diff, self.TOTAL_SLOTS - diff)
    
    def forces_in_gravity_well(
        self, 
        forces: List[int], 
        center: int, 
        radius: int
    ) -> List[int]:
        """
        Retorna forças que estão dentro de um "poço gravitacional".
        
        Args:
            forces: Lista de forças a verificar
            center: Centro do poço
            radius: Raio do poço
            
        Returns:
            Lista de forças dentro do raio
        """
        return [f for f in forces if self.calculate_force_distance(f, center) <= radius]
    
    # ========== UTILIDADES ==========
    
    def is_valid_number(self, number: int) -> bool:
        """Verifica se é um número válido de roleta"""
        return 0 <= number <= 36
    
    def all_numbers(self) -> List[int]:
        """Retorna todos os números da roleta em ordem da roda"""
        return self.WHEEL_SEQUENCE.copy()
    
    def __repr__(self):
        return f"RouletteCore(slots={self.TOTAL_SLOTS})"


# ========== INSTÂNCIA SINGLETON ==========

# Instância global para uso em todo o sistema
roulette = RouletteCore()


