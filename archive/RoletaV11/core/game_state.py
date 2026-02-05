# RoletaV11/core/game_state.py

import threading
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

from core import config
from domain.logic import RouletteLogic
from database.persistence import DataPersistence
from database.cinematica import CinematicaDB
from database.microservico import MicroservicoDB, PrevisaoMicroservico
from strategies.legacy import ContextoAnalise
from strategies import (
    EstrategiaPelaForca,
    EstrategiaInerciaPreditiva,
    EstrategiaRessonanciaPolinomial,
    EstrategiaHibridaAdaptativa,
    EstrategiaHibridaAdaptativaAMPLA,
    EstrategiaSinergiaPreditiva,
    EstrategiaSinergiaDirecionalAvancada
)
from strategies.microservice import Sanitizer, prever_proxima_forca as prever_microservico

class GameStateManager:
    """
    Gerencia o estado global do jogo, histórico e orquestra estratégias.
    """
    def __init__(self, app_controller=None):
        self.app_controller = app_controller
        self.logic = RouletteLogic()
        self.persistence = DataPersistence()
        
        # Carregar configuração SDA (vetores) para persistência se necessário
        # Simplificação: Não carregar vetores antigos por enquanto
        self.persistence.sda_vetor_names = [] 
        
        self.cinematica_db = CinematicaDB()
        self.microservico_db = MicroservicoDB()
        self.sanitizer = Sanitizer() # Novo Microserviço Sanitizer
        
        # Histórico em memória
        self.historico_jogadas: List[dict] = []
        
        # Inicializar estratégias
        self._init_strategies()
        
        # Estado UI / Contexto
        self.contexto_analise = ContextoAnalise()
        
        # Variáveis de controle
        self.banca_inicial = config.BANCA_INICIAL
        self.banca_atual = config.BANCA_INICIAL
        self._lock = threading.Lock()
        
        # Carregar dados persistidos se houver
        self._load_state()

    def _init_strategies(self):
        """Inicializa as estratégias disponíveis."""
        self.estrategias = {
            "Pela Força": EstrategiaPelaForca(self.logic),
            "Inércia Preditiva": EstrategiaInerciaPreditiva(self.logic),
            "Ressonância Polinomial": EstrategiaRessonanciaPolinomial(self.logic),
            "Híbrida Adaptativa": EstrategiaHibridaAdaptativa(self.logic),
            "Híbrida Adaptativa AMPLA": EstrategiaHibridaAdaptativaAMPLA(self.logic),
            "Sinergia Preditiva": EstrategiaSinergiaPreditiva(self.logic),
            # SDA Principal (v17.1)
            "Sinergia Direcional Avançada": EstrategiaSinergiaDirecionalAvancada(self.logic, self.persistence)
        }
        self.estrategia_ativa_nome = "Sinergia Direcional Avançada" # Default

    def _load_state(self):
        """Carrega estado salvo."""
        data = self.persistence.load_data()
        if data:
            self.historico_jogadas = data.get('historico', [])
            self.banca_atual = data.get('banca', config.BANCA_INICIAL)
            # Restaurar estado das estratégias se necessário
            # ...
            print(f"Estado carregado: {len(self.historico_jogadas)} jogadas.")
            
            # Sincronizar CinematicaDB com histórico carregado se vazio
            if len(self.cinematica_db.forcas_horario.dados) == 0:
                self.cinematica_db.sincronizar_com_banco_completo(self.historico_jogadas)

    def processar_novo_numero(self, info_jogada):
        """
        Ponto de entrada principal para novos dados (Roleta ou Simulação).
        Thread-safe.
        """
        with self._lock:
            numero = info_jogada.numero
            direcao = info_jogada.direcao
            timestamp = datetime.now().isoformat()
            
            # 1. Atualizar histórico básico
            jogada_dict = {
                "numero": numero,
                "direcao": direcao,
                "timestamp": timestamp,
                "dealer": info_jogada.dealer,
                "stats": {}, # Placeholders
                "distancia": None
            }
            
            # Calcular distância se houver jogada anterior
            if self.historico_jogadas:
                ultimo = self.historico_jogadas[-1]
                dist = self.logic.calcular_distancia_giro(ultimo['numero'], numero, direcao)
                jogada_dict['distancia'] = dist
                
                # Atualizar CinematicaDB
                if dist is not None:
                    # Adicionar jogada e obter dados cinemáticos
                    dados_cine = self.cinematica_db.adicionar_jogada(dist, direcao)
                    # Enriquecer jogada_dict com dados cinemáticos
                    jogada_dict['stats']['forca'] = float(dist)
                    jogada_dict['stats']['aceleracao'] = dados_cine.get('aceleracao')
                    jogada_dict['stats']['jerk'] = dados_cine.get('jerk')
                    
                    # Logar performance no arquivo texto
                    self.persistence.write_to_log(f"{timestamp} | Num: {numero} | Dir: {direcao} | Força: {dist}")

            self.historico_jogadas.append(jogada_dict)
            
            # Persistir estado
            self.persistence.save_data({
                'historico': self.historico_jogadas,
                'banca': self.banca_atual
            })
            
            # 2. Atualizar Microserviço de Previsão (Pipeline)
            self._atualizar_microservico_pipeline(jogada_dict)
            
            # 3. Executar Estratégia Ativa
            resultado_analise = self._executar_estrategia_ativa()
            
            # 4. Notificar UI (via AppController)
            if self.app_controller:
                self.app_controller.atualizar_ui(
                    ultimo_numero=jogada_dict, 
                    resultado_analise=resultado_analise
                )

    def _atualizar_microservico_pipeline(self, jogada_atual):
        """
        Executa o pipeline do microserviço:
        1. Resolve a previsão pendente (do giro anterior)
        2. Gera nova previsão para o próximo giro
        """
        sentido_atual = jogada_atual['direcao'] # "horario" ou "anti-horario" (da jogada que ACABOU de acontecer)
        
        # A. Resolver Previsão Pendente
        # Se a jogada atual foi "horario", significa que a bola girou no sentido horário.
        # Devemos buscar se havia uma previsão feita para este sentido.
        norm_sentido = "horario" if "anti" not in sentido_atual else "antihorario"
        
        previsao_pendente = self.microservico_db.obter_ultima_previsao_pendente(norm_sentido)
        if previsao_pendente:
            # Temos uma previsão esperando resultado. O resultado é o número atual.
            resultado = self.microservico_db.atualizar_resultado(
                previsao_pendente.id, 
                jogada_atual['numero']
            )
            print(f"[Microserviço] Previsão {previsao_pendente.id} resolvida: Acerto={resultado['acertou']}")

        # B. Gerar Nova Previsão (para o PRÓXIMO giro)
        # Assumindo alternância de sentido ou mantendo lógica simples
        # Se acabou de girar Horário, o próximo PROVAVELMENTE será Anti-Horário (depende do dealer, mas padrão é alternar)
        proximo_sentido = "antihorario" if norm_sentido == "horario" else "horario"
        
        # Pegar histórico de forças desse próximo sentido para prever
        series = self.cinematica_db.obter_series(proximo_sentido)
        forcas_raw = series['forcas'] # Lista [recente, antigo...]
        
        if len(forcas_raw) >= 5:
            # Pipeline Sanitizer + Predictor
            sanitizer_out = self.sanitizer.sanitize(forcas_raw[:12], proximo_sentido)
            # Usar clean forces para prever
            previsao_out = prever_microservico(sanitizer_out.clean_forces[:5])
            
            forca_prevista = previsao_out['forca_prevista']
            
            # Calcular Região Alvo (baseada no número atual como ponto de partida)
            centro_alvo = self.logic.calcular_centro_alvo(
                jogada_atual['numero'], 
                forca_prevista, 
                'anti-horario' if proximo_sentido == 'antihorario' else 'horario'
            )
            
            # Região Vício (Rotina - 17 números - Raio 8)
            regiao_vicio = self.logic.get_roulette_region(centro_alvo, 8)
            
            # Gravar Nova Previsão no DB
            nova_prev = PrevisaoMicroservico(
                timestamp=datetime.now().isoformat(),
                sentido=proximo_sentido,
                posicao_partida=jogada_atual['numero'],
                forca_vicio=float(forca_prevista),
                centro_vicio=centro_alvo,
                regiao_vicio=json.dumps(regiao_vicio),
                taxa_sobrevivencia=sanitizer_out.taxa_sobrevivencia,
                last_valid_force=sanitizer_out.last_valid_force,
                regime=previsao_out['regime']
            )
            self.microservico_db.gravar_previsao(nova_prev)

    def _executar_estrategia_ativa(self):
        """Executa a estratégia selecionada."""
        if not self.estrategia_ativa_nome or self.estrategia_ativa_nome not in self.estrategias:
            return None
            
        estrategia = self.estrategias[self.estrategia_ativa_nome]
        
        # Passar histórico para estratégia 
        # (Nota: As estratégias legadas esperam lista de dicts com 'numero', 'direcao', 'distancia')
        # Nosso self.historico_jogadas já está nesse formato.
        
        deve_apostar, numeros, detalhes = estrategia.analisar(
            self.historico_jogadas, 
            self.contexto_analise
        )
        
        return {
            "estrategia": self.estrategia_ativa_nome,
            "deve_apostar": deve_apostar,
            "numeros": numeros,
            "detalhes": detalhes
        }
    
    def set_estrategia(self, nome: str):
        if nome in self.estrategias:
            self.estrategia_ativa_nome = nome
            print(f"Estratégia alterada para: {nome}")
