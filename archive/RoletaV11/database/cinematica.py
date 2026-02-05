# RoletaV11/database/cinematica.py

from dataclasses import dataclass, field
from typing import List, Dict
import json
import os
from datetime import datetime

# Constantes
MAX_ITEMS = 45  # Máximo de itens em cada série

@dataclass
class SeriesCinematica:
    """Representa uma série cinemática (forças, acelerações ou jerks)."""
    nome: str
    sentido: str  # 'horario' ou 'antihorario'
    tipo: str     # 'forca', 'aceleracao' ou 'jerk'
    dados: List[float] = field(default_factory=list)
    max_items: int = MAX_ITEMS
    ultima_atualizacao: str = ""
    
    def adicionar(self, valor: float) -> None:
        """Adiciona um novo valor NO INÍCIO da série."""
        self.dados.insert(0, valor)
        if len(self.dados) > self.max_items:
            self.dados.pop()
        self.ultima_atualizacao = datetime.now().isoformat()
    
    def obter_ultimos(self, n: int) -> List[float]:
        return self.dados[:n]
    
    def obter_todos(self) -> List[float]:
        return self.dados.copy()
    
    def tamanho(self) -> int:
        return len(self.dados)
    
    def to_dict(self) -> Dict:
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
        return cls(
            nome=data.get('nome', ''),
            sentido=data.get('sentido', ''),
            tipo=data.get('tipo', ''),
            dados=data.get('dados', []),
            max_items=data.get('max_items', MAX_ITEMS),
            ultima_atualizacao=data.get('ultima_atualizacao', '')
        )


class CinematicaDB:
    """Gerencia 6 séries temporais separadas por sentido (Horária/Anti-horária)."""
    
    ARQUIVO_PERSISTENCIA = "cinematica_db.json"
    
    def __init__(self, caminho_arquivo: str = None):
        self.caminho = caminho_arquivo or self.ARQUIVO_PERSISTENCIA
        
        self.forcas_horario = SeriesCinematica("forcas_horario", "horario", "forca")
        self.forcas_antihorario = SeriesCinematica("forcas_antihorario", "antihorario", "forca")
        self.aceleracoes_horario = SeriesCinematica("aceleracoes_horario", "horario", "aceleracao")
        self.aceleracoes_antihorario = SeriesCinematica("aceleracoes_antihorario", "antihorario", "aceleracao")
        self.jerks_horario = SeriesCinematica("jerks_horario", "horario", "jerk")
        self.jerks_antihorario = SeriesCinematica("jerks_antihorario", "antihorario", "jerk")
        
        self._carregar()
        print(f"[CinematicaDB] Banco de dados cinemático inicializado.")
    
    def adicionar_jogada(self, forca: float, sentido: str) -> Dict:
        sentido_norm = 'antihorario' if 'anti' in sentido.lower() else 'horario'
        
        if sentido_norm == 'horario':
            serie_forcas = self.forcas_horario
            serie_accs = self.aceleracoes_horario
            serie_jerks = self.jerks_horario
        else:
            serie_forcas = self.forcas_antihorario
            serie_accs = self.aceleracoes_antihorario
            serie_jerks = self.jerks_antihorario
        
        forca_anterior = serie_forcas.dados[0] if serie_forcas.dados else None
        acc_anterior = serie_accs.dados[0] if serie_accs.dados else None
        
        serie_forcas.adicionar(float(forca))
        
        nova_acc = None
        if forca_anterior is not None:
            nova_acc = float(forca) - forca_anterior
            serie_accs.adicionar(nova_acc)
        
        novo_jerk = None
        if nova_acc is not None and acc_anterior is not None:
            novo_jerk = nova_acc - acc_anterior
            serie_jerks.adicionar(novo_jerk)
        
        self._salvar()
        
        return {
            'sentido': sentido_norm,
            'forca': forca,
            'aceleracao': nova_acc,
            'jerk': novo_jerk
        }
    
    def obter_series(self, sentido: str) -> Dict[str, List[float]]:
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
    
    def sincronizar_com_banco_completo(self, banco_de_dados_completo: List[Dict]) -> None:
        if not banco_de_dados_completo: return
        
        # Limpar
        self.forcas_horario.dados.clear()
        self.forcas_antihorario.dados.clear()
        self.aceleracoes_horario.dados.clear()
        self.aceleracoes_antihorario.dados.clear()
        self.jerks_horario.dados.clear()
        self.jerks_antihorario.dados.clear()
        
        forcas_h = []
        forcas_ah = []
        
        for jogada in banco_de_dados_completo:
            if jogada.get('is_outlier', False): continue
            forca = jogada.get('distancia')
            if forca is None: continue
            
            direcao = jogada.get('direcao', '')
            if direcao == 'horario':
                forcas_h.append(float(forca))
            elif direcao in ('antihorario', 'anti-horario'):
                forcas_ah.append(float(forca))
        
        self.forcas_horario.dados = forcas_h[:MAX_ITEMS]
        self.forcas_antihorario.dados = forcas_ah[:MAX_ITEMS]
        
        self._recalcular_derivadas()
        self._salvar()
        print(f"[CinematicaDB] Sincronização concluída!")
    
    def _recalcular_derivadas(self) -> None:
        for (serie_f, serie_acc, serie_jerk) in [
            (self.forcas_horario, self.aceleracoes_horario, self.jerks_horario),
            (self.forcas_antihorario, self.aceleracoes_antihorario, self.jerks_antihorario)
        ]:
            forcas = serie_f.dados
            accs = [forcas[i] - forcas[i+1] for i in range(len(forcas)-1)]
            serie_acc.dados = accs[:MAX_ITEMS]
            
            jerks = [accs[i] - accs[i+1] for i in range(len(accs)-1)]
            serie_jerk.dados = jerks[:MAX_ITEMS]

    def _salvar(self) -> None:
        try:
            dados = {
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
        if not os.path.exists(self.caminho): return
        try:
            with open(self.caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            series = dados.get('series', {})
            
            if 'forcas_horario' in series: self.forcas_horario = SeriesCinematica.from_dict(series['forcas_horario'])
            if 'forcas_antihorario' in series: self.forcas_antihorario = SeriesCinematica.from_dict(series['forcas_antihorario'])
            if 'aceleracoes_horario' in series: self.aceleracoes_horario = SeriesCinematica.from_dict(series['aceleracoes_horario'])
            if 'aceleracoes_antihorario' in series: self.aceleracoes_antihorario = SeriesCinematica.from_dict(series['aceleracoes_antihorario'])
            if 'jerks_horario' in series: self.jerks_horario = SeriesCinematica.from_dict(series['jerks_horario'])
            if 'jerks_antihorario' in series: self.jerks_antihorario = SeriesCinematica.from_dict(series['jerks_antihorario'])

        except Exception as e:
            print(f"[CinematicaDB] Erro ao carregar: {e}")
