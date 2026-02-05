import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from collections import deque
from scipy import stats
import json
from datetime import datetime
import os
import config

@dataclass
class RegistroCircular:
    """Registro de uma observação circular"""
    timestamp: datetime
    posicao_inicial: int
    posicao_parada: int
    angulo_inicial: float
    angulo_parada: float
    sentido: int  # 1 ou -1
    voltas_por_segundo: float
    forcas: List[float]
    variacao_forcas: List[float]
    jerk: List[float]
    energia: float
    tempo_ate_parada: float
    voltas_completas: int

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'posicao_inicial': self.posicao_inicial,
            'posicao_parada': self.posicao_parada,
            'angulo_inicial': self.angulo_inicial,
            'angulo_parada': self.angulo_parada,
            'sentido': self.sentido,
            'voltas_por_segundo': self.voltas_por_segundo,
            'forcas': self.forcas,
            'variacao_forcas': self.variacao_forcas,
            'jerk': self.jerk,
            'energia': self.energia,
            'tempo_ate_parada': self.tempo_ate_parada,
            'voltas_completas': self.voltas_completas
        }


class MemoriaCircularBidirecional:
    """
    Mantém históricos separados para rotação horária e anti-horária
    Cada direção tem sua própria linha de aprendizado
    """

    def __init__(self, capacidade_maxima: int = 1000):
        self.capacidade = capacidade_maxima

        # Linhas separadas por sentido
        self.linha_horaria = deque(maxlen=capacidade_maxima)      # sentido = 1
        self.linha_antihoraria = deque(maxlen=capacidade_maxima)  # sentido = -1

        # Estatísticas por sentido
        self.stats_horaria = self._criar_estrutura_stats()
        self.stats_antihoraria = self._criar_estrutura_stats()

        # Matrizes de transição aprendidas (posicao_inicial -> posicao_parada)
        self.matriz_transicao_horaria = np.zeros((37, 37))
        self.matriz_transicao_antihoraria = np.zeros((37, 37))

        # Contadores para cada transição
        self.contador_horaria = np.zeros((37, 37))
        self.contador_antihoraria = np.zeros((37, 37))

        # Padrões de força por região circular
        self.padroes_forca_horaria = {i: [] for i in range(37)}
        self.padroes_forca_antihoraria = {i: [] for i in range(37)}


    def _criar_estrutura_stats(self) -> dict:
        """Estrutura para armazenar estatísticas de cada sentido"""
        return {
            'total_observacoes': 0,
            'energia_media': 0.0,
            'energia_std': 0.0,
            'tempo_parada_medio': 0.0,
            'voltas_medias': 0.0,
            'forca_media_global': 0.0,
            'variacao_forca_media': 0.0,
            'jerk_medio_global': 0.0,
            # Distribuição de paradas por posição
            'distribuicao_paradas': np.zeros(37),
            # Velocidades típicas
            'velocidades_comuns': []
        }


    def adicionar_observacao(self, registro: RegistroCircular):
        """Adiciona observação na linha apropriada"""

        # Selecionar linha correta
        if registro.sentido == 1:
            linha = self.linha_horaria
            stats = self.stats_horaria
            matriz = self.matriz_transicao_horaria
            contador = self.contador_horaria
            padroes = self.padroes_forca_horaria
        else:
            linha = self.linha_antihoraria
            stats = self.stats_antihoraria
            matriz = self.matriz_transicao_antihoraria
            contador = self.contador_antihoraria
            padroes = self.padroes_forca_antihoraria

        # Adicionar à linha
        linha.append(registro)

        # Atualizar matriz de transição
        pos_i = registro.posicao_inicial
        pos_f = registro.posicao_parada
        contador[pos_i][pos_f] += 1

        # Recalcular probabilidades
        if contador[pos_i].sum() > 0:
            matriz[pos_i] = contador[pos_i] / contador[pos_i].sum()

        # Atualizar padrões de força por região
        padroes[pos_i].append({
            'forcas': registro.forcas,
            'resultado': pos_f,
            'energia': registro.energia
        })

        # Atualizar estatísticas
        self._atualizar_estatisticas(linha, stats)


    def _atualizar_estatisticas(self, linha: deque, stats: dict):
        """Recalcula estatísticas da linha"""
        if len(linha) == 0:
            return

        stats['total_observacoes'] = len(linha)

        energias = [r.energia for r in linha]
        stats['energia_media'] = np.mean(energias)
        stats['energia_std'] = np.std(energias)

        tempos = [r.tempo_ate_parada for r in linha]
        stats['tempo_parada_medio'] = np.mean(tempos)

        voltas = [r.voltas_completas for r in linha]
        stats['voltas_medias'] = np.mean(voltas)

        # Força global
        todas_forcas = []
        todas_variacoes = []
        todos_jerks = []
        for r in linha:
            todas_forcas.extend(r.forcas)
            todas_variacoes.extend(r.variacao_forcas)
            todos_jerks.extend(r.jerk)

        stats['forca_media_global'] = np.mean(todas_forcas) if todas_forcas else 0
        stats['variacao_forca_media'] = np.mean(todas_variacoes) if todas_variacoes else 0
        stats['jerk_medio_global'] = np.mean(todos_jerks) if todos_jerks else 0

        # Distribuição de paradas
        stats['distribuicao_paradas'] = np.zeros(37)
        for r in linha:
            stats['distribuicao_paradas'][r.posicao_parada] += 1

        # Normalizar
        total = stats['distribuicao_paradas'].sum()
        if total > 0:
            stats['distribuicao_paradas'] /= total

        # Velocidades
        stats['velocidades_comuns'] = [r.voltas_por_segundo for r in linha]


    def buscar_padroes_similares(self, 
                                 posicao_inicial: int,
                                 sentido: int,
                                 forcas_atuais: List[float],
                                 top_n: int = 10,
                                 vps_atual: float = 0.0) -> List[RegistroCircular]:
        """
        Busca os N registros mais similares na linha apropriada
        usando distância euclidiana nas forças + VPS (MELHORADO)
        """
        linha = self.linha_horaria if sentido == 1 else self.linha_antihoraria

        if len(linha) == 0:
            return []

        # Filtrar por posição inicial próxima (±3 posições)
        candidatos = [r for r in linha 
                     if self._distancia_circular(r.posicao_inicial, posicao_inicial) <= 3]

        if len(candidatos) == 0:
            candidatos = list(linha)

        # Calcular similaridade baseada em forças + VPS
        forcas_array = np.array(forcas_atuais)
        similaridades = []
        
        # Peso do VPS na distância total (normalizado)
        PESO_VPS = 2.0  # Cada 1 rot/s de diferença = 2 unidades de distância

        for registro in candidatos:
            # Garantir que temos o mesmo número de forças para comparação
            # Se tamanhos diferentes, truncar para o menor
            min_len = min(len(forcas_array), len(registro.forcas))
            if min_len == 0: continue
            
            f_atual = forcas_array[:min_len]
            f_reg = np.array(registro.forcas[:min_len])
            
            # Distância euclidiana nas forças
            dist_forcas = np.linalg.norm(f_atual - f_reg)
            
            # NOVO: Distância no VPS (se disponível)
            dist_vps = 0.0
            if vps_atual > 0 and registro.voltas_por_segundo > 0:
                dist_vps = abs(vps_atual - registro.voltas_por_segundo) * PESO_VPS
            
            # Distância total combinada
            distancia_total = dist_forcas + dist_vps
            
            similaridades.append((distancia_total, registro))

        # Ordenar por similaridade (menor distância = mais similar)
        similaridades.sort(key=lambda x: x[0])

        # Retornar top N
        return [reg for _, reg in similaridades[:top_n]]


    def _distancia_circular(self, pos1: int, pos2: int) -> int:
        """Distância mínima no círculo"""
        diff = abs(pos1 - pos2)
        return min(diff, 37 - diff)


    def obter_probabilidades_empiricas(self, 
                                      posicao_inicial: int,
                                      sentido: int,
                                      janela: int = 7) -> dict:
        """
        Retorna probabilidades empíricas baseadas no histórico
        para a janela gravitacional
        """
        matriz = (self.matriz_transicao_horaria if sentido == 1 
                 else self.matriz_transicao_antihoraria)

        stats = (self.stats_horaria if sentido == 1 
                else self.stats_antihoraria)

        # Probabilidades da matriz de transição
        probs_linha = matriz[posicao_inicial]

        # Criar janela ao redor da posição mais provável
        if probs_linha.sum() > 0:
            pos_mais_provavel = np.argmax(probs_linha)
        else:
            pos_mais_provavel = posicao_inicial

        offset = janela // 2
        posicoes_janela = [(pos_mais_provavel + i) % 37 
                          for i in range(-offset, offset + 1)]

        # Extrair probabilidades
        probs_janela = [probs_linha[p] for p in posicoes_janela]

        # Se não há histórico, usar distribuição uniforme
        if sum(probs_janela) == 0:
            probs_janela = [1.0/janela] * janela
        else:
            # Normalizar
            soma = sum(probs_janela)
            probs_janela = [p/soma for p in probs_janela]

        return {
            'posicoes': posicoes_janela,
            'probabilidades': probs_janela,
            'fonte': 'empirica',
            'observacoes_totais': stats['total_observacoes'],
            'distribuicao_global': stats['distribuicao_paradas'].tolist()
        }


    def analisar_contexto_forcas(self,
                                posicao_inicial: int,
                                sentido: int,
                                forcas_atuais: List[float]) -> dict:
        """
        Analisa contexto de forças comparando com histórico
        """
        padroes = (self.padroes_forca_horaria if sentido == 1 
                  else self.padroes_forca_antihoraria)

        if posicao_inicial not in padroes or len(padroes[posicao_inicial]) == 0:
            return {'contexto': 'sem_historico', 'confianca': 0}

        historico = padroes[posicao_inicial]
        forcas_array = np.array(forcas_atuais)

        # Encontrar os 5 padrões mais similares
        similaridades = []
        for padrao in historico:
            min_len = min(len(forcas_array), len(padrao['forcas']))
            if min_len == 0: continue
            
            f_atual = forcas_array[:min_len]
            f_padrao = np.array(padrao['forcas'][:min_len])
            
            distancia = np.linalg.norm(f_atual - f_padrao)
            similaridades.append({
                'distancia': distancia,
                'resultado': padrao['resultado'],
                'energia': padrao['energia']
            })

        similaridades.sort(key=lambda x: x['distancia'])
        top5 = similaridades[:5]

        # Posição mais frequente nos top 5
        resultados = [s['resultado'] for s in top5]
        if resultados:
            posicao_frequente = max(set(resultados), key=resultados.count)
            frequencia = resultados.count(posicao_frequente) / len(resultados)
        else:
            posicao_frequente = None
            frequencia = 0

        return {
            'contexto': 'padrao_identificado',
            'posicao_sugerida': posicao_frequente,
            'confianca': frequencia,
            'padroes_similares': len(top5),
            'energia_media_similar': np.mean([s['energia'] for s in top5]) if top5 else 0,
            'distancia_media': np.mean([s['distancia'] for s in top5]) if top5 else 0
        }


    def obter_estatisticas_linha(self, sentido: int) -> dict:
        """Retorna estatísticas completas de uma linha"""
        return self.stats_horaria.copy() if sentido == 1 else self.stats_antihoraria.copy()


    def exportar_historico(self, arquivo: str):
        """Exporta todo o histórico para arquivo JSON"""
        dados = {
            'linha_horaria': [r.to_dict() for r in self.linha_horaria],
            'linha_antihoraria': [r.to_dict() for r in self.linha_antihoraria],
            'stats_horaria': self._serializar_stats(self.stats_horaria),
            'stats_antihoraria': self._serializar_stats(self.stats_antihoraria),
            'matriz_transicao_horaria': self.matriz_transicao_horaria.tolist(),
            'matriz_transicao_antihoraria': self.matriz_transicao_antihoraria.tolist()
        }

        with open(arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)


    def _serializar_stats(self, stats: dict) -> dict:
        """Converte numpy arrays para listas para JSON"""
        stats_copy = stats.copy()
        stats_copy['distribuicao_paradas'] = stats_copy['distribuicao_paradas'].tolist()
        return stats_copy


    def importar_historico(self, arquivo: str):
        """Importa histórico de arquivo JSON"""
        if not os.path.exists(arquivo):
            print(f"Arquivo não encontrado para importar: {arquivo}")
            return
            
        with open(arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)

        # Reconstruir linhas
        self.linha_horaria.clear()
        for reg_dict in dados['linha_horaria']:
            reg_dict['timestamp'] = datetime.fromisoformat(reg_dict['timestamp'])
            self.linha_horaria.append(RegistroCircular(**reg_dict))

        self.linha_antihoraria.clear()
        for reg_dict in dados['linha_antihoraria']:
            reg_dict['timestamp'] = datetime.fromisoformat(reg_dict['timestamp'])
            self.linha_antihoraria.append(RegistroCircular(**reg_dict))

        # Restaurar matrizes
        self.matriz_transicao_horaria = np.array(dados['matriz_transicao_horaria'])
        self.matriz_transicao_antihoraria = np.array(dados['matriz_transicao_antihoraria'])

        # Recomputar estatísticas
        self._atualizar_estatisticas(self.linha_horaria, self.stats_horaria)
        self._atualizar_estatisticas(self.linha_antihoraria, self.stats_antihoraria)


# ============================================================================
# FILTRO DE KALMAN INTEGRADO COM MEMÓRIA BIDIRECIONAL
# ============================================================================

class FiltroKalmanCircularComMemoria:
    """
    Filtro de Kalman circular que aprende com histórico bidirecional
    """

    def __init__(self, num_posicoes: int = 37, janela_gravitacional: int = 7):
        self.num_posicoes = num_posicoes
        self.janela_gravitacional = janela_gravitacional
        self.angulo_por_posicao = 2 * np.pi / num_posicoes

        # Memória bidirecional
        self.memoria = MemoriaCircularBidirecional()

        # Estados do filtro (um para cada sentido)
        self.estado_horario = self._criar_estado_inicial()
        self.estado_antihorario = self._criar_estado_inicial()

        # Parâmetros do filtro
        self.Q = np.eye(3) * 0.1  # Ruído do processo
        self.R_theta = 0.5
        self.R_omega = 1.0


    def sincronizar_memoria(self, dados_sistema: list):
        """
        Reconstrói completamente a memória do Kalman a partir do banco de dados principal.
        Garante fonte única de verdade e RECALCULA os vetores de contexto (força, jerk)
        para habilitar o reconhecimento de padrões e estatísticas.
        """
        # 1. Limpar memória atual
        self.memoria = MemoriaCircularBidirecional()
        self.memoria.linha_horaria.clear()
        self.memoria.linha_antihoraria.clear()
        
        # Buffers para reconstruir o contexto progressivo de cada sentido
        # Armazena apenas os valores simples (float) para montar os vetores
        buffer_horario_forcas = []
        buffer_antihorario_forcas = []
        
        # Variável para rastrear a posição anterior globalmente
        ult_pos_global = None
        
        # Vamos iterar cronologicamente (do mais antigo para o mais novo)
        # O banco dados_sistema vem ordenado: [0]=Mais Recente ... [N]=Mais Antigo
        # Portanto, reversed(dados_sistema) nos dá a ordem cronológica correta.
        
        for jogada in reversed(dados_sistema):
             # Dados básicos da jogada
             atual_pos = jogada.get('numero')
             direcao = jogada.get('direcao')
             distancia = jogada.get('distancia') # Força aplicada nesta jogada
             ts = jogada.get('timestamp')
             
             # Se a jogada não tem posição ou direção definida, apenas atualizamos a referência e pulamos
             if atual_pos is None or not direcao:
                 ult_pos_global = atual_pos
                 continue
                 
             # Definir sentido e selecionar o buffer correto
             sentido = 1 if direcao == 'horario' else -1
             buffer_atual = buffer_horario_forcas if sentido == 1 else buffer_antihorario_forcas
             
             # Se temos distância válida, adicionar ao buffer
             if distancia:
                 buffer_atual.append(distancia)
                 # Manter buffer num tamanho razoável para não crescer indefinidamente, 
                 # mas mantendo histórico suficiente para os vetores (ex: ultimos 15)
                 # Porém, precisamos do histórico acumulado para esta jogada.
             
             # POSIÇÃO INICIAL: É a posição final da jogada ANTERIOR (globalmente)
             # Se for a primeira jogada do banco, assumimos 0 ou a própria posição (cold start)
             pos_inicial = ult_pos_global if ult_pos_global is not None else 0
             
             # Se temos dados suficientes para criar um registro
             # (Pelo menos uma força para registrar)
             if distancia:
                 # --- RECONSTRUIR VETORES DE CONTEXTO ---
                 # O registro precisa das últimas N forças *no momento daquela jogada*
                 # Pegamos as últimas 12 do buffer (incluindo a atual)
                 ctx_forcas = buffer_atual[-12:]
                 
                 # Calcular variações (derivada 1)
                 ctx_variacoes = []
                 if len(ctx_forcas) > 1:
                     for k in range(len(ctx_forcas) - 1):
                         v = ctx_forcas[k+1] - ctx_forcas[k] # Simples diferença. Para circular seria mais complexo se fosse ângulo.
                         # Se fosse força circular real, OK. Aqui assumimos magnitude.
                         ctx_variacoes.append(v)
                 else:
                     ctx_variacoes = [0.0]
                     
                 # Calcular Jerk (derivada 2)
                 ctx_jerks = []
                 if len(ctx_variacoes) > 1:
                     for k in range(len(ctx_variacoes) - 1):
                         j = ctx_variacoes[k+1] - ctx_variacoes[k]
                         ctx_jerks.append(j)
                 else:
                     ctx_jerks = [0.0]
                 
                 # VPS
                 vps = jogada.get('voltas_por_segundo')
                 if vps is None: vps = 0.0
                 
                 # Criar Registro Rico
                 reg = RegistroCircular(
                    timestamp=ts if ts else datetime.now(),
                    posicao_inicial=pos_inicial,
                    posicao_parada=atual_pos,
                    angulo_inicial=self._posicao_para_angulo(pos_inicial),
                    angulo_parada=self._posicao_para_angulo(atual_pos),
                    sentido=sentido,
                    voltas_por_segundo=vps,
                    forcas=list(ctx_forcas),     # Cópia do vetor histórico atual
                    variacao_forcas=ctx_variacoes,
                    jerk=ctx_jerks,
                    energia=0.0, # Pode ser calculado se necessário: 0.5 * (vps*2pi)^2
                    tempo_ate_parada=0.0,
                    voltas_completas=0
                 )
                 
                 self.memoria.adicionar_observacao(reg)
             
             # Atualizar referência global para a próxima iteração
             ult_pos_global = atual_pos
            
        print(f"[KALMAN] Memória Sincronizada: {len(self.memoria.linha_horaria)} H / {len(self.memoria.linha_antihoraria)} AH")


    def _criar_estado_inicial(self) -> dict:
        """Cria estrutura de estado do filtro"""
        return {
            'theta': 0.0,
            'omega': 0.0,
            'alpha': 0.0,
            'jerk': 0.0,
            'x': np.zeros(3),
            'P': np.eye(3) * 10
        }


    def _posicao_para_angulo(self, posicao: int) -> float:
        return (posicao % self.num_posicoes) * self.angulo_por_posicao


    def _angulo_para_posicao(self, theta: float) -> int:
        theta_norm = theta % (2 * np.pi)
        posicao = int(np.round(theta_norm / self.angulo_por_posicao))
        return posicao % self.num_posicoes


    def _diferenca_angular(self, theta1: float, theta2: float) -> float:
        diff = (theta2 - theta1) % (2 * np.pi)
        if diff > np.pi:
            diff -= 2 * np.pi
        return diff


    def prever_com_aprendizado(self,
                              posicao_inicial: int,
                              sentido_giro: int,
                              voltas_por_segundo: float,
                              forcas: List[float],
                              variacao_forcas: List[float],
                              jerk_list: List[float],
                              posicao_real_parada: Optional[int] = None) -> dict:
        """
        Orquestrador Principal (VERSÃO FUSÃO DE FORÇAS):
        1. Projeta Força Cinemática (Matemática).
        2. Projeta Força por Memória (Padrões Similares).
        3. Realiza FUSÃO DE FORÇAS para encontrar a 'Força Real Provável' (Sem ruído).
        4. Aplica a Força Final na Geometria da Roda.
        """
        
        # 1. Projeção Cinemática (Tendência + VPS + Jerk)
        # Retorna uma força escalar teórica baseada na física do momento
        # print("[DEBUG_K] 1. Calculando Cinemática...")
        prev_cinematica = self.prever_proxima_forca(
            sentido_giro, forcas, variacao_forcas, jerk_list, vps_atual=voltas_por_segundo
        )
        forca_cinematica = prev_cinematica['forca_prevista']
        confianca_cinematica = prev_cinematica['confianca']
        
        # 2. Projeção por Memória (Padrões)
        # ============================================================
        # [DESATIVADO] Baseado em análise de backtest que mostrou que
        # a memória PREJUDICA as previsões quando há mudança de lançador.
        # Taxa SEM memória: 21.1% vs COM memória: 15.8%
        # ============================================================
        USAR_MEMORIA_PADROES = False  # Flag para ativar/desativar memória
        
        forca_memoria = forca_cinematica  # Fallback
        peso_memoria = 0.0
        observacoes_count = 0
        
        if USAR_MEMORIA_PADROES:
            # Código de memória (desativado)
            padroes_similares = self.memoria.buscar_padroes_similares(
                posicao_inicial, sentido_giro, forcas, top_n=10, vps_atual=voltas_por_segundo
            )
            
            if padroes_similares:
                forcas_encontradas = []
                for reg in padroes_similares:
                    if reg and reg.forcas:
                        forcas_encontradas.append(reg.forcas[-1])
                
                if forcas_encontradas:
                    forca_memoria = sum(forcas_encontradas) / len(forcas_encontradas)
                    observacoes_count = len(forcas_encontradas)
                    peso_memoria = min(0.6, len(forcas_encontradas) * 0.1)
        
        # 3. FUSÃO DE FORÇAS (SIMPLIFICADA - SEM MEMÓRIA)
        # ============================================================
        # Agora usa 100% CINEMÁTICA (tendência + jerk + VPS)
        # Sem influência de dados históricos antigos
        # ============================================================
        
        # Como memória está desativada, usar 100% cinemática
        peso_cinematica_final = 1.0
        peso_memoria_final = 0.0
        
        print(f"[DEBUG_K] 3. Modo CINEMÁTICO PURO (memória desativada)")
        print(f"   Força Cinemática: {forca_cinematica:.2f} | Pesos: Cin=100% Mem=0%")
        
        forca_final_refinada = forca_cinematica  # 100% cinemática
        
        # 4. Aplicação Geométrica
        # Passamos a lista fake com a força refinada para o executor físico
        forcas_para_calculo = forcas[:-1] + [forca_final_refinada] if forcas else [forca_final_refinada]
        
        # print("[DEBUG_K] 4. Executando Goemetria...")
        
        # Selecionar estado correto
        estado_atual = self.estado_horario if sentido_giro == 1 else self.estado_antihorario
        
        resultado_kalman = self._executar_kalman(
            estado_atual, posicao_inicial, sentido_giro,
            voltas_por_segundo, forcas_para_calculo, variacao_forcas, jerk_list
        )
        posicao_final = resultado_kalman['posicao_kalman']

        # 5. Aprendizado (Retroalimentação se houver resultado real)
        if posicao_real_parada is not None:
             self._registrar_observacao(
                posicao_inicial, posicao_real_parada, sentido_giro,
                voltas_por_segundo, forcas, variacao_forcas, jerk_list, resultado_kalman
             )

        # 6. Preparar Retorno Rico
        stats_linha = self.memoria.obter_estatisticas_linha(sentido_giro)
        
        # Calcular confiança da fusão
        # Se as forças concordam, confiança sobe
        diff = abs(forca_cinematica - forca_memoria)
        conf_final = confianca_cinematica * 100
        if peso_memoria_final > 0.2:
             if diff < 1.0: conf_final += 15
             elif diff > 3.0: conf_final -= 15
             
        return {
            'posicao_prevista': posicao_final,
            'confianca': min(99.9, max(1.0, conf_final)),
            'forca_projetada_final': forca_final_refinada,
            'analise_gravitacional': {
                 'posicoes': [posicao_final], 'probabilidades': [], 'fonte': 'Fisica_Fusao_Forcas'
            },
            'componentes_fusao': {
                'kalman': {'posicao': float(f"{forca_cinematica:.2f}"), 'peso': peso_cinematica_final}, 
                'empirico': {'posicao': 0, 'peso': 0},
                'contexto': {'posicao': float(f"{forca_memoria:.2f}"), 'peso': peso_memoria_final}
            },
            'padroes_similares_encontrados': observacoes_count,
            'estatisticas_linha': stats_linha
        }




    def prever_proxima_forca(self, sentido_futuro: int, 
                           historico_forcas: list, 
                           historico_variacoes: list, 
                           historico_jerks: list,
                           vps_atual: float = 0.0) -> dict:
        """
        Estima a força escalar (distância) para a próxima jogada.
        Analisa a tendência linear recente, o Jerk (mudança de aceleração)
        E CRUZA COM O VPS (Velocidade) para ajustar a projeção.
        """
        if not historico_forcas:
             return {'forca_prevista': 15.0, 'confianca': 0.1, 'metodo': 'padrao_sem_dados'}
             
        # Fallback de VPS (Solicitação Usuário: Base média 0.9 se não informado)
        if vps_atual <= 0.001:
            vps_atual = 0.9

        # 1. Análise de Tendência Linear (Últimas 5 - MELHORADO de 3 para suavizar ruído)
        ultima_forca = historico_forcas[-1]
        tendencia = 0.0
        
        if len(historico_forcas) >= 3:
            # Média das variações recentes (usa até 5 se disponível)
            deltas = [historico_forcas[i] - historico_forcas[i-1] for i in range(1, len(historico_forcas))]
            janela_tendencia = min(5, len(deltas))  # MELHORADO: usa até 5 variações
            tendencia_bruta = np.mean(deltas[-janela_tendencia:]) 
            
            # AMORTECEDOR DE TENDÊNCIA (Evitar overshoot linear em freagens bruscas)
            # Se a tendência for cair > 5 casas, limita a -5.
            tendencia = max(-5.0, min(5.0, tendencia_bruta))
        
        # 2. Análise de Jerk (Ajuste fino) - PESO AUMENTADO de 0.5 para 0.6
        ajuste_jerk = 0.0
        if historico_jerks:
             media_jerk = np.mean(historico_jerks[-3:]) if len(historico_jerks) >= 3 else historico_jerks[-1]
             # Se Jerk positivo, a força está acelerando sua mudança -> projeta aumento
             ajuste_jerk = media_jerk * 0.6  # MELHORADO: peso 0.6 (era 0.5)
             
        # 3. Cruzamento com VPS (Velocidade) - Lógica Física CORRIGIDA
        # A Força (Distância) é geralmente proporcional ao VPS.
        
        # Se VPS > 1.5 voltas/s, é rápido. Impulsiona força.
        # Se VPS < 0.7 voltas/s, é lento. Reduz força.
        fator_velocidade = 1.0
        if vps_atual > 1.5:  # Rápido
             fator_velocidade = 1.05
        elif vps_atual < 0.7:  # Lento
             fator_velocidade = 0.95
        
        # CORREÇÃO DO BUG: ajuste_vps agora é calculado SEMPRE (estava dentro do elif)
        ajuste_vps = ultima_forca * (fator_velocidade - 1.0)

        # Projeção Final Cruzada
        forca_projetada = ultima_forca + tendencia + ajuste_jerk + ajuste_vps
        
        # Limites físicos (não pode ser negativa nem absurda > 37 casas de uma vez é raro, mas possível se for voltas)
        # Assumindo sistema de 0-37 casas.
        forca_projetada = max(1.0, min(37.0, forca_projetada))
        
        return {
            'forca_prevista': forca_projetada,
            'ultima_forca': ultima_forca,
            'tendencia_aplicada': tendencia,
            'ajuste_jerk': ajuste_jerk,
            'fator_vps': ajuste_vps,
            'confianca': 0.85 if len(historico_forcas) > 10 else 0.5,
            'metodo': 'analise_cinematica_cruzada'
        }



    def _executar_kalman(self, estado, posicao_inicial, sentido_giro, 
                        voltas_por_segundo, forcas, variacao_forcas, jerk_list) -> dict:
        """
        Executa o filtro de Kalman (Modelo Físico Dinâmico).
        Usa a Força Projetada e a Desaceleração média para estimar a parada
        CONSIDERANDO A GEOMETRIA REAL DA ROLETA.
        """
        
        # 1. Determinar a distância projetada (em casas ou voltas)
        # O input 'forcas' aqui já contém a força futura projetada na última posição
        if not forcas:
            distancia_estimada = 15.0
        else:
            distancia_estimada = forcas[-1]
            
        # 2. Refinamento por Variação (Desaceleração)
        fator_correcao = 1.0
        if variacao_forcas:
            media_var = np.mean(variacao_forcas)
            # Se a variação for muito negativa (desaceleração rápida), fator diminui
            fator_correcao = 1.0 + (media_var * 0.1) 
        
        distancia_final = distancia_estimada * fator_correcao
        casas_percorrer = distancia_final 
        
        # 3. Converter para Posição no Círculo (GEOMETRIA REAL DA RODA)
        # A aritmética +1 não significa vizinho na roleta. Precisa usar os índices.
        
        try:
            # Pegar índice do número inicial na roda
            if posicao_inicial in config.ROULETTE_WHEEL_ORDER:
                idx_inicial = config.ROULETTE_WHEEL_ORDER.index(posicao_inicial)
                
                # Calcular deslocamento de índices
                # Sentido 1 = Horário = Incrementa índice (na maioria das convenções)
                deslocamento = int(round(casas_percorrer)) * sentido_giro
                
                idx_final = (idx_inicial + deslocamento) % 37
                posicao_final_inteira = config.ROULETTE_WHEEL_ORDER[idx_final]
            else:
                # Fallback se número inválido
                posicao_final_inteira = (posicao_inicial + int(casas_percorrer * sentido_giro)) % 37
                
        except Exception as e:
            print(f"[KALMAN PHYSICS ERROR] Falha na geometria: {e}")
            posicao_final_inteira = (posicao_inicial + int(casas_percorrer * sentido_giro)) % 37
        
        # 4. Calcular Confiança do Modelo Físico
        confianca_modelo = 70.0
        if len(forcas) > 3:
            std_dev = np.std(forcas[-3:])
            if std_dev > 2.0: confianca_modelo -= 20 # Instável
            if std_dev < 0.5: confianca_modelo += 10 # Muito estável
            
        return {
            'posicao_kalman': posicao_final_inteira,
            'distancia_estimada': distancia_final,
            'confianca_kalman': min(95.0, max(10.0, confianca_modelo)),
            'energia': distancia_final # Proxy de energia
        }


    def _fusao_inteligente(self, resultado_kalman, probs_empiricas, 
                          contexto_forcas, padroes_similares) -> dict:
        """
        Combina previsão do Kalman com dados históricos.
        FLUXO DE CONFIANÇA:
        1. Peso Kalman: Baseado na física (40%)
        2. Peso Empírico: Baseado na frequência histórica da posição (30%)
        3. Peso Contexto: Baseado em padrões de força similares (30%)
        """

        # Pesos Base
        peso_kalman = 0.4
        peso_empirico = 0.3
        peso_contexto = 0.3

        # Ajuste dinâmico de pesos
        # Se temos MUITOS padrões similares, confiamos mais no contexto (Match Pattern)
        n_similares = len(padroes_similares)
        if n_similares >= 5:
            peso_contexto = 0.5
            peso_kalman = 0.3
            peso_empirico = 0.2
        elif n_similares == 0:
            peso_contexto = 0.0 # Sem padrão, ignora
            peso_kalman += 0.2
            peso_empirico += 0.1
            
        # Posições Sugeridas
        pos_k = resultado_kalman['posicao_kalman']
        
        # Empírico: Pega a mais provável da estatística pura
        if probs_empiricas['probabilidades']:
            idx_max = np.argmax(probs_empiricas['probabilidades'])
            pos_e = probs_empiricas['posicoes'][idx_max]
        else:
            pos_e = pos_k # Fallback
            
        # Contexto: Pura repetição de padrão
        pos_c = contexto_forcas.get('posicao_sugerida', pos_k)
        if pos_c is None: pos_c = pos_k

        # Votação (Soma de Pesos)
        votos = {}
        # Adiciona K
        votos[pos_k] = votos.get(pos_k, 0) + peso_kalman
        # Adiciona E
        votos[pos_e] = votos.get(pos_e, 0) + peso_empirico
        # Adiciona C
        if peso_contexto > 0:
            votos[pos_c] = votos.get(pos_c, 0) + peso_contexto
            
        # Vencedor
        posicao_final = max(votos.items(), key=lambda x: x[1])[0]
        confianca_final = votos[posicao_final] * 100
        
        # Logs de Debug da Confiança (serão visíveis se printados no caller)
        # print(f"   [FUSAO] K:{pos_k}({peso_kalman}) | E:{pos_e}({peso_empirico}) | C:{pos_c}({peso_contexto}) -> Vencedor: {posicao_final}")

        # Construir janela e retornar


        # Construir janela gravitacional ao redor da posição final
        offset = self.janela_gravitacional // 2
        janela = [(posicao_final + i) % 37 for i in range(-offset, offset + 1)]

        # Combinar probabilidades empíricas com von Mises
        probs_finais = self._combinar_distribuicoes(
            posicao_final,
            probs_empiricas,
            resultado_kalman['confianca_kalman']
        )

        return {
            'posicao_prevista': posicao_final,
            'confianca': min(100, confianca_final),
            'analise_gravitacional': {
                'posicoes': janela,
                'probabilidades': probs_finais,
                'posicao_mais_provavel': posicao_final,
                'fonte': 'fusao_hibrida'
            },
            'componentes_fusao': {
                'kalman': {'posicao': pos_k, 'peso': peso_kalman},
                'empirico': {'posicao': pos_e, 'peso': peso_empirico},
                'contexto': {'posicao': pos_c, 'peso': peso_contexto}
            },
            'padroes_similares_encontrados': len(padroes_similares),
            'contexto_forcas': contexto_forcas,
            'modelo': 'hibrido_kalman_ml'
        }


    def _combinar_distribuicoes(self, pos_central, probs_empiricas, confianca_kalman):
        """Combina distribuições empírica e teórica"""
        offset = self.janela_gravitacional // 2
        posicoes = [(pos_central + i) % 37 for i in range(-offset, offset + 1)]

        probs = []
        for pos in posicoes:
            # Probabilidade empírica
            if pos in probs_empiricas['posicoes']:
                idx = probs_empiricas['posicoes'].index(pos)
                prob_emp = probs_empiricas['probabilidades'][idx]
            else:
                prob_emp = 0.01

            # Probabilidade teórica (von Mises simplificada)
            distancia = self._distancia_circular(pos, pos_central)
            prob_teorica = np.exp(-distancia / 2)

            # Combinar
            alpha = 0.6 if probs_empiricas['observacoes_totais'] > 20 else 0.3
            prob_final = alpha * prob_emp + (1 - alpha) * prob_teorica
            probs.append(prob_final)

        # Normalizar
        soma = sum(probs)
        if soma > 0:
            probs = [p/soma for p in probs]

        return probs


    def _distancia_circular(self, pos1: int, pos2: int) -> int:
        diff = abs(pos1 - pos2)
        return min(diff, 37 - diff)


    def _registrar_observacao(self, pos_inicial, pos_parada, sentido,
                             voltas_por_segundo, forcas, variacao_forcas,
                             jerk_list, resultado_kalman):
        """Adiciona observação à memória"""

        registro = RegistroCircular(
            timestamp=datetime.now(),
            posicao_inicial=pos_inicial,
            posicao_parada=pos_parada,
            angulo_inicial=self._posicao_para_angulo(pos_inicial),
            angulo_parada=self._posicao_para_angulo(pos_parada),
            sentido=sentido,
            voltas_por_segundo=voltas_por_segundo,
            forcas=forcas,
            variacao_forcas=variacao_forcas,
            jerk=jerk_list,
            energia=resultado_kalman['energia'],
            tempo_ate_parada=0.0,  # seria calculado em sistema real
            voltas_completas=0
        )

        self.memoria.adicionar_observacao(registro)


    def salvar_memoria(self, arquivo: str = "memoria_circular.json"):
        """Salva memória em arquivo"""
        self.memoria.exportar_historico(arquivo)
        print(f"✅ Memória salva em: {arquivo}")


    def carregar_memoria(self, arquivo: str = "memoria_circular.json"):
        """Carrega memória de arquivo"""
        self.memoria.importar_historico(arquivo)
        print(f"✅ Memória carregada de: {arquivo}")


# ============================================================================
# EXEMPLO DE USO COM APRENDIZADO
# ============================================================================

def exemplo_sistema_completo():
    """Demonstração do sistema com memória bidirecional"""

    print("="*80)
    print("SISTEMA HÍBRIDO: KALMAN + APRENDIZADO BIDIRECIONAL")
    print("="*80)

    filtro = FiltroKalmanCircularComMemoria()

    # Simular várias rodadas para construir histórico
    print("\n🔄 Simulando 15 rodadas para construir memória...\n")

    for i in range(15):
        sentido = 1 if i % 2 == 0 else -1
        pos_inicial = (i * 3) % 37

        dados = {
            'posicao_inicial': pos_inicial,
            'sentido_giro': sentido,
            'voltas_por_segundo': 2.0 + np.random.uniform(-0.5, 0.5),
            'forcas': [10 - j*0.3 + np.random.uniform(-0.2, 0.2) for j in range(12)],
            'variacao_forcas': [-0.3 + np.random.uniform(-0.1, 0.1) for _ in range(12)],
            'jerk_list': [np.random.uniform(-0.1, 0.1) for _ in range(12)],
            'posicao_real_parada': (pos_inicial + sentido * 8) % 37  # simulado
        }

        resultado = filtro.prever_com_aprendizado(**dados)

        simbolo = "✅" if resultado.get('acerto', {}).get('acertou_exato', False) else "❌"
        print(f"Rodada {i+1:2d}: Sentido={'⟳' if sentido==1 else '⟲'} | "
              f"Previsto={resultado['posicao_prevista']:2d} | "
              f"Real={dados['posicao_real_parada']:2d} {simbolo}")

    # Agora fazer uma previsão com o modelo treinado
    print("\n" + "="*80)
    print("PREVISÃO COM MODELO TREINADO")
    print("="*80)

    dados_teste = {
        'posicao_inicial': 5,
        'sentido_giro': 1,
        'voltas_por_segundo': 2.5,
        'forcas': [10.2, 10.0, 9.8, 9.5, 9.2, 8.9, 8.6, 8.3, 8.0, 7.7, 7.4, 7.1],
        'variacao_forcas': [-0.2, -0.2, -0.3, -0.3, -0.3, -0.3, -0.3, -0.3, -0.3, -0.3, -0.3, -0.3],
        'jerk_list': [0.0, -0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    }

    resultado = filtro.prever_com_aprendizado(**dados_teste)

    print(f"\n📍 Posição inicial: {dados_teste['posicao_inicial']}")
    print(f"🔄 Sentido: Horário ⟳")

    print(f"\n🎯 PREVISÃO HÍBRIDA:")
    print(f"   Posição prevista: {resultado['posicao_prevista']}")
    print(f"   Confiança: {resultado['confianca']:.1f}%")

    print(f"\n🧩 COMPONENTES DA FUSÃO:")
    for nome, dados in resultado['componentes_fusao'].items():
        print(f"   {nome.capitalize():12s}: Pos {dados['posicao']:2d} (peso: {dados['peso']:.1f})")

    print(f"\n📊 PADRÕES ENCONTRADOS:")
    print(f"   Padrões similares: {resultado['padroes_similares_encontrados']}")
    print(f"   Contexto: {resultado['contexto_forcas']['contexto']}")
    if resultado['contexto_forcas']['contexto'] == 'padrao_identificado':
        print(f"   Confiança do contexto: {resultado['contexto_forcas']['confianca']*100:.1f}%")

    print(f"\n📈 ESTATÍSTICAS DA LINHA HORÁRIA:")
    stats = resultado['estatisticas_linha']
    print(f"   Total de observações: {stats['total_observacoes']}")
    print(f"   Energia média: {stats['energia_media']:.2f}")
    print(f"   Tempo médio de parada: {stats['tempo_parada_medio']:.2f}s")

    print(f"\n🌍 DISTRIBUIÇÃO GRAVITACIONAL:")
    analise = resultado['analise_gravitacional']
    for i, (pos, prob) in enumerate(zip(analise['posicoes'][:5], 
                                       analise['probabilidades'][:5])):
        print(f"   Posição {pos:2d}: {prob*100:5.1f}%")

    # Salvar memória
    filtro.salvar_memoria("memoria_rotacional.json")

    print("\n" + "="*80)


if __name__ == "__main__":
    exemplo_sistema_completo()
