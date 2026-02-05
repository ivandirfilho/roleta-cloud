"""
Sistema Preditivo de Forças - Filtro de Kalman

Implementa o Filtro de Kalman para estimação e predição de posição,
velocidade e aceleração do sistema.
"""

import json
import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass

from force_predictor_db import EstadoKalman


@dataclass
class KalmanState:
    """Estado do Filtro de Kalman em formato de arrays."""
    x: np.ndarray  # Estado [posição, velocidade, aceleração]
    P: np.ndarray  # Matriz de covariância (3x3)


class KalmanFilter:
    """
    Filtro de Kalman para predição de movimento.
    
    Modelo de Aceleração Constante (CA):
    - Estado: [posição, velocidade, aceleração]
    - Observação: posição
    """
    
    def __init__(
        self,
        ruido_processo: float = 1.0,
        ruido_medicao: float = 1.0,
        dt_default: float = 1.0
    ):
        """
        Args:
            ruido_processo: Variância do ruído do processo (Q)
            ruido_medicao: Variância do ruído de medição (R)
            dt_default: Intervalo de tempo padrão entre medições
        """
        self.ruido_processo = ruido_processo
        self.ruido_medicao = ruido_medicao
        self.dt_default = dt_default
        
        # Estado inicial
        self.x = np.zeros(3)  # [posição, velocidade, aceleração]
        self.P = np.diag([1.0, 10.0, 10.0])  # Covariância inicial
        
        # Matriz de observação (só observamos posição)
        self.H = np.array([[1.0, 0.0, 0.0]])
        
        # Ruído de medição
        self.R = np.array([[ruido_medicao]])
    
    def _criar_matriz_transicao(self, dt: float) -> np.ndarray:
        """
        Cria matriz de transição F para o modelo CA.
        
        x(t+dt) = F * x(t)
        
        posição(t+dt) = posição + velocidade*dt + 0.5*aceleração*dt²
        velocidade(t+dt) = velocidade + aceleração*dt
        aceleração(t+dt) = aceleração (constante)
        """
        return np.array([
            [1, dt, 0.5 * dt**2],
            [0, 1,  dt],
            [0, 0,  1]
        ])
    
    def _criar_matriz_ruido_processo(self, dt: float) -> np.ndarray:
        """
        Cria matriz de ruído do processo Q.
        
        Modelo de "jerk" como ruído branco.
        """
        dt2 = dt**2
        dt3 = dt**3
        dt4 = dt**4
        
        q = self.ruido_processo
        
        return q * np.array([
            [dt4/4, dt3/2, dt2/2],
            [dt3/2, dt2,   dt],
            [dt2/2, dt,    1]
        ])
    
    def inicializar(self, posicao: float, velocidade: float = 0.0, aceleracao: float = 0.0):
        """
        Inicializa o estado do filtro.
        
        Args:
            posicao: Posição inicial (absoluta)
            velocidade: Velocidade inicial (partes/seg)
            aceleracao: Aceleração inicial (partes/seg²)
        """
        self.x = np.array([posicao, velocidade, aceleracao])
        self.P = np.diag([1.0, 10.0, 10.0])
    
    def predict(self, dt: Optional[float] = None) -> np.ndarray:
        """
        Etapa de predição (Predict).
        
        Projeta o estado para o próximo instante de tempo.
        
        Args:
            dt: Intervalo de tempo (segundos)
            
        Returns:
            Estado predito [posição, velocidade, aceleração]
        """
        if dt is None:
            dt = self.dt_default
        
        F = self._criar_matriz_transicao(dt)
        Q = self._criar_matriz_ruido_processo(dt)
        
        # Projetar estado
        x_pred = F @ self.x
        
        # Projetar covariância
        P_pred = F @ self.P @ F.T + Q
        
        # Atualizar estado interno (predição)
        self.x = x_pred
        self.P = P_pred
        
        return x_pred.copy()
    
    def update(self, z: float) -> np.ndarray:
        """
        Etapa de atualização (Update/Correction).
        
        Corrige o estado com base na observação.
        
        Args:
            z: Observação (posição medida)
            
        Returns:
            Estado corrigido [posição, velocidade, aceleração]
        """
        # Inovação (erro de predição)
        y = z - self.H @ self.x
        
        # Covariância da inovação
        S = self.H @ self.P @ self.H.T + self.R
        
        # Ganho de Kalman
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Corrigir estado
        self.x = self.x + (K @ y).flatten()
        
        # Corrigir covariância
        I = np.eye(3)
        self.P = (I - K @ self.H) @ self.P
        
        return self.x.copy()
    
    def predict_and_update(self, z: float, dt: Optional[float] = None) -> np.ndarray:
        """
        Executa predict + update em uma única chamada.
        
        Args:
            z: Observação (posição medida)
            dt: Intervalo de tempo
            
        Returns:
            Estado atualizado
        """
        self.predict(dt)
        return self.update(z)
    
    def prever_futuro(self, horizonte: float = 1.0) -> float:
        """
        Prevê a posição em um horizonte futuro.
        
        Não altera o estado interno.
        
        Args:
            horizonte: Tempo futuro em segundos
            
        Returns:
            Posição prevista (absoluta)
        """
        F = self._criar_matriz_transicao(horizonte)
        x_futuro = F @ self.x
        return x_futuro[0]  # Posição
    
    def get_state(self) -> KalmanState:
        """Retorna o estado atual."""
        return KalmanState(x=self.x.copy(), P=self.P.copy())
    
    def set_state(self, state: KalmanState):
        """Define o estado."""
        self.x = state.x.copy()
        self.P = state.P.copy()
    
    def get_confianca(self) -> float:
        """
        Calcula a confiança da predição (0-1).
        
        Baseado na variância da posição (P[0,0]).
        Quanto menor a variância, maior a confiança.
        """
        variancia_posicao = self.P[0, 0]
        
        # Mapear variância para confiança
        # variância 0 → confiança 1
        # variância alta → confiança baixa
        confianca = 1.0 / (1.0 + variancia_posicao)
        
        return min(max(confianca, 0.0), 1.0)
    
    @property
    def posicao(self) -> float:
        return self.x[0]
    
    @property
    def velocidade(self) -> float:
        return self.x[1]
    
    @property
    def aceleracao(self) -> float:
        return self.x[2]
    
    # --------------------------------------------------------------------------
    # Persistência (para salvar/carregar do banco)
    # --------------------------------------------------------------------------
    
    def to_estado_kalman(self) -> EstadoKalman:
        """Converte para objeto EstadoKalman do banco de dados."""
        return EstadoKalman(
            id=1,
            posicao_estimada=float(self.x[0]),
            velocidade_estimada=float(self.x[1]),
            aceleracao_estimada=float(self.x[2]),
            matriz_P=json.dumps(self.P.tolist()),
            atualizado_em=0
        )
    
    def from_estado_kalman(self, estado: EstadoKalman):
        """Carrega estado do objeto EstadoKalman."""
        self.x = np.array([
            estado.posicao_estimada,
            estado.velocidade_estimada,
            estado.aceleracao_estimada
        ])
        self.P = np.array(json.loads(estado.matriz_P))


# ==============================================================================
# TESTE
# ==============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TESTE DO FILTRO DE KALMAN")
    print("=" * 60)
    
    # Simular movimento de um eixo
    # Posição inicial: 10, velocidade: 5 partes/seg, aceleração: 2 partes/seg²
    
    kf = KalmanFilter(ruido_processo=0.5, ruido_medicao=2.0, dt_default=1.0)
    kf.inicializar(posicao=10, velocidade=0, aceleracao=0)
    
    print(f"\nEstado inicial:")
    print(f"  Posição: {kf.posicao:.2f}")
    print(f"  Velocidade: {kf.velocidade:.2f}")
    print(f"  Aceleração: {kf.aceleracao:.2f}")
    
    # Simular observações (com ruído)
    observacoes = [15, 22, 30, 40, 52, 65, 80, 97, 115, 135]
    
    print(f"\n--- SIMULAÇÃO ---")
    for i, obs in enumerate(observacoes):
        estado = kf.predict_and_update(obs, dt=1.0)
        previsao = kf.prever_futuro(1.0)
        confianca = kf.get_confianca()
        
        print(f"\nt={i+1}: Observado={obs}")
        print(f"  Estado: pos={estado[0]:.1f}, vel={estado[1]:.1f}, acel={estado[2]:.1f}")
        print(f"  Previsão (t+1): {previsao:.1f}")
        print(f"  Confiança: {confianca:.2%}")
    
    # Testar persistência
    print(f"\n--- TESTE DE PERSISTÊNCIA ---")
    estado_db = kf.to_estado_kalman()
    print(f"Salvo: pos={estado_db.posicao_estimada:.1f}, P={estado_db.matriz_P[:30]}...")
    
    # Criar novo filtro e carregar
    kf2 = KalmanFilter()
    kf2.from_estado_kalman(estado_db)
    print(f"Carregado: pos={kf2.posicao:.1f}, vel={kf2.velocidade:.1f}")
    
    print("\n" + "=" * 60)
    print("✓ Teste concluído!")
