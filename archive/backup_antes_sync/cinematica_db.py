"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    BANCO DE DADOS CINEMÁTICO - 6 SÉRIES                       ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  CONVENÇÃO DE ORDENAÇÃO:                                                      ║
║  ═══════════════════════                                                      ║
║                                                                               ║
║  • Índice 0 = MAIS RECENTE                                                    ║
║  • Índice -1 = MAIS ANTIGO                                                    ║
║                                                                               ║
║  Quando exibido como lista:                                                   ║
║  [RECENTE ←――――――――――――――――――――――――――――――――――――――――――――→ ANTIGO]              ║
║  [  F0   ,   F1   ,   F2   ,   ...   ,   F43  ,   F44  ]                      ║
║                                                                               ║
║  Quando exibido verticalmente (tabela):                                       ║
║  Linha 0 = MAIS RECENTE (topo)                                                ║
║  Linha N = MAIS ANTIGO (base)                                                 ║
║                                                                               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  SÉRIES DISPONÍVEIS (45 itens cada):                                          ║
║  ───────────────────────────────────                                          ║
║                                                                               ║
║  1. forcas_horario        - Últimas 45 forças do sentido HORÁRIO              ║
║  2. forcas_antihorario    - Últimas 45 forças do sentido ANTI-HORÁRIO         ║
║  3. aceleracoes_horario   - Últimas 45 acelerações do sentido HORÁRIO         ║
║  4. aceleracoes_antihorario - Últimas 45 acelerações do sentido ANTI-HORÁRIO  ║
║  5. jerks_horario         - Últimos 45 jerks do sentido HORÁRIO               ║
║  6. jerks_antihorario     - Últimos 45 jerks do sentido ANTI-HORÁRIO          ║
║                                                                               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  RELAÇÃO ENTRE AS GRANDEZAS:                                                  ║
║  ───────────────────────────                                                  ║
║                                                                               ║
║  Força[i] → Aceleração[i] = Força[i] - Força[i+1]                             ║
║                                                                               ║
║  Aceleração[i] → Jerk[i] = Aceleração[i] - Aceleração[i+1]                    ║
║                                                                               ║
║  Ou seja:                                                                     ║
║  - Para calcular Aceleração[0], precisamos de Força[0] e Força[1]             ║
║  - Para calcular Jerk[0], precisamos de Aceleração[0] e Aceleração[1]         ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import json
import os
from datetime import datetime


# Constantes
MAX_ITEMS = 45  # Máximo de itens em cada série


@dataclass
class SeriesCinematica:
    """
    Representa uma série cinemática (forças, acelerações ou jerks).
    
    CONVENÇÃO: índice 0 = mais recente, índice -1 = mais antigo
    """
    nome: str
    sentido: str  # 'horario' ou 'antihorario'
    tipo: str     # 'forca', 'aceleracao' ou 'jerk'
    dados: List[float] = field(default_factory=list)
    max_items: int = MAX_ITEMS
    ultima_atualizacao: str = ""
    
    def adicionar(self, valor: float) -> None:
        """
        Adiciona um novo valor NO INÍCIO da série (posição 0 = mais recente).
        Remove o item mais antigo se ultrapassar o limite.
        """
        self.dados.insert(0, valor)
        if len(self.dados) > self.max_items:
            self.dados.pop()  # Remove o mais antigo (final da lista)
        self.ultima_atualizacao = datetime.now().isoformat()
    
    def obter_ultimos(self, n: int) -> List[float]:
        """
        Retorna os últimos N valores (mais recentes primeiro).
        """
        return self.dados[:n]
    
    def obter_todos(self) -> List[float]:
        """
        Retorna todos os valores (mais recente primeiro).
        """
        return self.dados.copy()
    
    def tamanho(self) -> int:
        """Retorna a quantidade de itens na série."""
        return len(self.dados)
    
    def to_dict(self) -> Dict:
        """Converte para dicionário para serialização."""
        return {
            'nome': self.nome,
            'sentido': self.sentido,
            'tipo': self.tipo,
            'dados': self.dados,
            'max_items': self.max_items,
            'ultima_atualizacao': self.ultima_atualizacao
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SeriesCinematica':
        """Cria instância a partir de dicionário."""
        return cls(
            nome=data.get('nome', ''),
            sentido=data.get('sentido', ''),
            tipo=data.get('tipo', ''),
            dados=data.get('dados', []),
            max_items=data.get('max_items', MAX_ITEMS),
            ultima_atualizacao=data.get('ultima_atualizacao', '')
        )


class CinematicaDB:
    """
    ╔═══════════════════════════════════════════════════════════════════════════╗
    ║                    BANCO DE DADOS CINEMÁTICO                              ║
    ╠═══════════════════════════════════════════════════════════════════════════╣
    ║  Gerencia 6 séries temporais separadas por sentido:                       ║
    ║                                                                           ║
    ║  HORÁRIO:              │  ANTI-HORÁRIO:                                   ║
    ║  • forcas_horario      │  • forcas_antihorario                            ║
    ║  • aceleracoes_horario │  • aceleracoes_antihorario                       ║
    ║  • jerks_horario       │  • jerks_antihorario                             ║
    ║                                                                           ║
    ║  CONVENÇÃO: [0] = mais recente, [-1] = mais antigo                        ║
    ╚═══════════════════════════════════════════════════════════════════════════╝
    """
    
    ARQUIVO_PERSISTENCIA = "cinematica_db.json"
    
    def __init__(self, caminho_arquivo: str = None):
        """
        Inicializa o banco de dados cinemático.
        
        Args:
            caminho_arquivo: Caminho para o arquivo de persistência (opcional)
        """
        self.caminho = caminho_arquivo or self.ARQUIVO_PERSISTENCIA
        
        # Inicializar as 6 séries
        self.forcas_horario = SeriesCinematica(
            nome="forcas_horario",
            sentido="horario",
            tipo="forca"
        )
        self.forcas_antihorario = SeriesCinematica(
            nome="forcas_antihorario",
            sentido="antihorario",
            tipo="forca"
        )
        self.aceleracoes_horario = SeriesCinematica(
            nome="aceleracoes_horario",
            sentido="horario",
            tipo="aceleracao"
        )
        self.aceleracoes_antihorario = SeriesCinematica(
            nome="aceleracoes_antihorario",
            sentido="antihorario",
            tipo="aceleracao"
        )
        self.jerks_horario = SeriesCinematica(
            nome="jerks_horario",
            sentido="horario",
            tipo="jerk"
        )
        self.jerks_antihorario = SeriesCinematica(
            nome="jerks_antihorario",
            sentido="antihorario",
            tipo="jerk"
        )
        
        # Tentar carregar dados existentes
        self._carregar()
        
        print(f"[CinematicaDB] Banco de dados cinemático inicializado.")
        print(f"   📊 Forças H: {self.forcas_horario.tamanho()} | AH: {self.forcas_antihorario.tamanho()}")
        print(f"   📊 Acelerações H: {self.aceleracoes_horario.tamanho()} | AH: {self.aceleracoes_antihorario.tamanho()}")
        print(f"   📊 Jerks H: {self.jerks_horario.tamanho()} | AH: {self.jerks_antihorario.tamanho()}")
    
    def adicionar_jogada(self, forca: float, sentido: str) -> Dict:
        """
        Adiciona uma nova jogada e recalcula derivadas.
        
        Args:
            forca: Valor da força (distância)
            sentido: 'horario' ou 'antihorario' (aceita 'anti-horario' também)
        
        Returns:
            Dict com as novas acelerações e jerks calculados
        
        CONVENÇÃO: O novo valor é inserido na posição 0 (mais recente).
        """
        # Normalizar sentido
        sentido_norm = 'antihorario' if 'anti' in sentido.lower() else 'horario'
        
        # Selecionar séries corretas
        if sentido_norm == 'horario':
            serie_forcas = self.forcas_horario
            serie_accs = self.aceleracoes_horario
            serie_jerks = self.jerks_horario
        else:
            serie_forcas = self.forcas_antihorario
            serie_accs = self.aceleracoes_antihorario
            serie_jerks = self.jerks_antihorario
        
        # Guardar força anterior para calcular aceleração
        forca_anterior = serie_forcas.dados[0] if serie_forcas.dados else None
        acc_anterior = serie_accs.dados[0] if serie_accs.dados else None
        
        # Adicionar nova força
        serie_forcas.adicionar(float(forca))
        
        # Calcular nova aceleração (se temos força anterior)
        nova_acc = None
        if forca_anterior is not None:
            nova_acc = float(forca) - forca_anterior
            serie_accs.adicionar(nova_acc)
        
        # Calcular novo jerk (se temos aceleração anterior)
        novo_jerk = None
        if nova_acc is not None and acc_anterior is not None:
            novo_jerk = nova_acc - acc_anterior
            serie_jerks.adicionar(novo_jerk)
        
        # Salvar automaticamente
        self._salvar()
        
        return {
            'sentido': sentido_norm,
            'forca': forca,
            'aceleracao': nova_acc,
            'jerk': novo_jerk
        }
    
    def obter_series(self, sentido: str) -> Dict[str, List[float]]:
        """
        Obtém as 3 séries (forças, acelerações, jerks) para um sentido.
        
        CONVENÇÃO: [0] = mais recente, [-1] = mais antigo
        """
        sentido_norm = 'antihorario' if 'anti' in sentido.lower() else 'horario'
        
        if sentido_norm == 'horario':
            return {
                'forcas': self.forcas_horario.obter_todos(),
                'aceleracoes': self.aceleracoes_horario.obter_todos(),
                'jerks': self.jerks_horario.obter_todos()
            }
        else:
            return {
                'forcas': self.forcas_antihorario.obter_todos(),
                'aceleracoes': self.aceleracoes_antihorario.obter_todos(),
                'jerks': self.jerks_antihorario.obter_todos()
            }
    
    def obter_ultimas(self, sentido: str, n_forcas: int = 12, n_accs: int = 11, n_jerks: int = 10) -> Dict:
        """
        Obtém as últimas N grandezas para um sentido.
        
        Args:
            sentido: 'horario' ou 'antihorario'
            n_forcas: Quantidade de forças (padrão 12)
            n_accs: Quantidade de acelerações (padrão 11)
            n_jerks: Quantidade de jerks (padrão 10)
        
        Returns:
            Dict com as listas, CONVENÇÃO: [0] = mais recente
        """
        sentido_norm = 'antihorario' if 'anti' in sentido.lower() else 'horario'
        
        if sentido_norm == 'horario':
            return {
                'forcas': self.forcas_horario.obter_ultimos(n_forcas),
                'aceleracoes': self.aceleracoes_horario.obter_ultimos(n_accs),
                'jerks': self.jerks_horario.obter_ultimos(n_jerks)
            }
        else:
            return {
                'forcas': self.forcas_antihorario.obter_ultimos(n_forcas),
                'aceleracoes': self.aceleracoes_antihorario.obter_ultimos(n_accs),
                'jerks': self.jerks_antihorario.obter_ultimos(n_jerks)
            }
    
    def sincronizar_com_banco_completo(self, banco_de_dados_completo: List[Dict]) -> None:
        """
        Sincroniza o CinematicaDB com o banco_de_dados_completo existente.
        
        CONVENÇÃO: banco_de_dados_completo[0] = mais recente
        
        Esta função deve ser chamada na inicialização para popular as séries
        a partir dos dados históricos.
        """
        if not banco_de_dados_completo:
            print("[CinematicaDB] Banco completo vazio, nada a sincronizar.")
            return
        
        # Limpar séries atuais
        self.forcas_horario.dados.clear()
        self.forcas_antihorario.dados.clear()
        self.aceleracoes_horario.dados.clear()
        self.aceleracoes_antihorario.dados.clear()
        self.jerks_horario.dados.clear()
        self.jerks_antihorario.dados.clear()
        
        # Separar forças por sentido (manter ordem: [0] = mais recente)
        forcas_h = []
        forcas_ah = []
        
        for jogada in banco_de_dados_completo:
            if jogada.get('is_outlier', False):
                continue
            
            forca = jogada.get('distancia')
            if forca is None:
                continue
            
            direcao = jogada.get('direcao', '')
            
            if direcao == 'horario':
                forcas_h.append(float(forca))
            elif direcao in ('antihorario', 'anti-horario'):
                forcas_ah.append(float(forca))
        
        # Limitar a 45 e armazenar
        self.forcas_horario.dados = forcas_h[:MAX_ITEMS]
        self.forcas_antihorario.dados = forcas_ah[:MAX_ITEMS]
        
        # Calcular acelerações (acc[i] = forca[i] - forca[i+1])
        self._recalcular_derivadas()
        
        # Salvar
        self._salvar()
        
        print(f"[CinematicaDB] Sincronização concluída!")
        print(f"   📊 Forças H: {len(self.forcas_horario.dados)} | AH: {len(self.forcas_antihorario.dados)}")
        print(f"   📊 Acelerações H: {len(self.aceleracoes_horario.dados)} | AH: {len(self.aceleracoes_antihorario.dados)}")
        print(f"   📊 Jerks H: {len(self.jerks_horario.dados)} | AH: {len(self.jerks_antihorario.dados)}")
    
    def _recalcular_derivadas(self) -> None:
        """
        Recalcula todas as acelerações e jerks a partir das forças.
        
        Aceleração[i] = Força[i] - Força[i+1]
        Jerk[i] = Aceleração[i] - Aceleração[i+1]
        """
        # Horário
        forcas_h = self.forcas_horario.dados
        accs_h = []
        for i in range(len(forcas_h) - 1):
            accs_h.append(forcas_h[i] - forcas_h[i + 1])
        self.aceleracoes_horario.dados = accs_h[:MAX_ITEMS]
        
        jerks_h = []
        for i in range(len(accs_h) - 1):
            jerks_h.append(accs_h[i] - accs_h[i + 1])
        self.jerks_horario.dados = jerks_h[:MAX_ITEMS]
        
        # Anti-horário
        forcas_ah = self.forcas_antihorario.dados
        accs_ah = []
        for i in range(len(forcas_ah) - 1):
            accs_ah.append(forcas_ah[i] - forcas_ah[i + 1])
        self.aceleracoes_antihorario.dados = accs_ah[:MAX_ITEMS]
        
        jerks_ah = []
        for i in range(len(accs_ah) - 1):
            jerks_ah.append(accs_ah[i] - accs_ah[i + 1])
        self.jerks_antihorario.dados = jerks_ah[:MAX_ITEMS]
    
    def _salvar(self) -> None:
        """Salva os dados em arquivo JSON."""
        try:
            dados = {
                'instrucao': (
                    "CONVENÇÃO DE ORDENAÇÃO: "
                    "Índice 0 = MAIS RECENTE, Índice -1 = MAIS ANTIGO. "
                    "Quando exibido como lista: [RECENTE → ANTIGO]. "
                    "Quando exibido verticalmente: Linha 0 = MAIS RECENTE (topo)."
                ),
                'ultima_atualizacao': datetime.now().isoformat(),
                'series': {
                    'forcas_horario': self.forcas_horario.to_dict(),
                    'forcas_antihorario': self.forcas_antihorario.to_dict(),
                    'aceleracoes_horario': self.aceleracoes_horario.to_dict(),
                    'aceleracoes_antihorario': self.aceleracoes_antihorario.to_dict(),
                    'jerks_horario': self.jerks_horario.to_dict(),
                    'jerks_antihorario': self.jerks_antihorario.to_dict(),
                }
            }
            
            with open(self.caminho, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CinematicaDB] Erro ao salvar: {e}")
    
    def _carregar(self) -> None:
        """Carrega dados do arquivo JSON, se existir."""
        if not os.path.exists(self.caminho):
            return
        
        try:
            with open(self.caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            series = dados.get('series', {})
            
            if 'forcas_horario' in series:
                self.forcas_horario = SeriesCinematica.from_dict(series['forcas_horario'])
            if 'forcas_antihorario' in series:
                self.forcas_antihorario = SeriesCinematica.from_dict(series['forcas_antihorario'])
            if 'aceleracoes_horario' in series:
                self.aceleracoes_horario = SeriesCinematica.from_dict(series['aceleracoes_horario'])
            if 'aceleracoes_antihorario' in series:
                self.aceleracoes_antihorario = SeriesCinematica.from_dict(series['aceleracoes_antihorario'])
            if 'jerks_horario' in series:
                self.jerks_horario = SeriesCinematica.from_dict(series['jerks_horario'])
            if 'jerks_antihorario' in series:
                self.jerks_antihorario = SeriesCinematica.from_dict(series['jerks_antihorario'])
            
            print(f"[CinematicaDB] Dados carregados de '{self.caminho}'")
        except Exception as e:
            print(f"[CinematicaDB] Erro ao carregar: {e}")
    
    def imprimir_status(self) -> None:
        """Imprime o status atual de todas as séries."""
        print("\n" + "═"*70)
        print("  📊 CINEMATICA DB - STATUS")
        print("═"*70)
        print("  CONVENÇÃO: [0] = mais recente, [-1] = mais antigo")
        print("─"*70)
        
        print(f"\n  🔵 HORÁRIO:")
        print(f"     Forças ({len(self.forcas_horario.dados)}):      {self.forcas_horario.dados[:8]}...")
        print(f"     Acelerações ({len(self.aceleracoes_horario.dados)}): {self.aceleracoes_horario.dados[:8]}...")
        print(f"     Jerks ({len(self.jerks_horario.dados)}):        {self.jerks_horario.dados[:8]}...")
        
        print(f"\n  🔴 ANTI-HORÁRIO:")
        print(f"     Forças ({len(self.forcas_antihorario.dados)}):      {self.forcas_antihorario.dados[:8]}...")
        print(f"     Acelerações ({len(self.aceleracoes_antihorario.dados)}): {self.aceleracoes_antihorario.dados[:8]}...")
        print(f"     Jerks ({len(self.jerks_antihorario.dados)}):        {self.jerks_antihorario.dados[:8]}...")
        
        print("═"*70 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# EXEMPLO DE USO
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Testando CinematicaDB...")
    
    # Criar instância
    db = CinematicaDB()
    
    # Simular algumas jogadas
    jogadas_teste = [
        (15, 'horario'),
        (12, 'anti-horario'),
        (18, 'horario'),
        (14, 'anti-horario'),
        (20, 'horario'),
        (10, 'anti-horario'),
    ]
    
    for forca, sentido in jogadas_teste:
        resultado = db.adicionar_jogada(forca, sentido)
        print(f"Adicionado: Força={forca}, Sentido={sentido}")
        print(f"   → Acc={resultado['aceleracao']}, Jerk={resultado['jerk']}")
    
    # Imprimir status
    db.imprimir_status()
    
    # Testar obtenção
    dados_h = db.obter_ultimas('horario', n_forcas=3, n_accs=2, n_jerks=1)
    print(f"Últimas HORÁRIO: {dados_h}")
