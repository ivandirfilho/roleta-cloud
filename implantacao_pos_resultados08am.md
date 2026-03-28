# Implantacao Pos Resultados 08AM - Plano de Gestao de Banca

> **Data:** 28/Mar/2026
> **Base:** `resultados_08am_dia28.md` - Sessao `session_1774696285001`
> **Status:** PRE-IMPLANTACAO (documento de estudo)
> **Foco:** Gestao de banca a cada jogada - melhor martingale por situacao

---

## 1. Diagnostico do Problema

### 1.1 O Que a Sessao Revelou

Na sessao das 08AM (29 apostas, 14 hits, 15 misses):

| Metrica | Valor | Problema |
|---------|:-----:|---------|
| Hit rate global | 48.3% | Abaixo do esperado (56.8%) |
| Gale maximo usado | G1 | **Nunca escalou** em 29 apostas |
| P&L com G1 fixo | -R$105 | Perda de R$105 |
| P&L simulado (Anti-MG) | +R$27 a +R$69 | **Oportunidade perdida** |
| Streak maximo (global) | 6 hits | Nao capitalizado pelo gale |

### 1.2 Por Que o SmartGale v4 Travou em G1

O fluxo atual em `core/engine.py` linhas 99-106:

`
bet_c4_rate = self.game_state.get_bet_c4_rate()
mg = self.game_state.target_martingale
mg.get_gale(score=result.score, c4_rate=bet_c4_rate)
`

**3 fatores travaram o gale:**

1. **Regra 4 (c4_rate < 0.25 = forca G1):** 40% das apostas tinham c4_rate <= 0.25, bloqueando escalacao
2. **Regra 2 (streak por direcao):** Cada `MartingaleState` (CW e CCW) tracka streaks separadamente. A alternancia H/AH reseta o streak da direcao antes de atingir 2
3. **Regra 1 (score 3-4 = teto G2):** Com scores entre 3-4, o maximo possivel era G2 mesmo sem as outras travas

**Resultado:** O SmartGale v4 funciona como um `Always G1` na pratica.

### 1.3 Insight Central da Simulacao

`
  MARTINGALE CLASSICO (dobrar na derrota):    -R$162  PIOR
  ALWAYS G1 (atual):                          -R$105  BASE
  ANTI-MARTINGALE (dobrar na vitoria):        +R$27   MELHOR
  STREAK COMBINADO (escalar em streaks):      +R$69   MELHOR GERAL
`

**Principio:** Quando hit rate < 50%, escalar em derrotas AMPLIFICA perdas. Escalar em vitorias CAPITALIZA clusters de acerto.

---

## 2. O Que Vale a Pena Implantar

### Decisao: Foco em Gestao de Banca

Nossas tecnicas NAO incluem pausa de direcao. A acuracia e responsabilidade da estrategia (SDA-21 + Triple Rate). O martingale deve EXCLUSIVAMENTE gerenciar quanto apostar em cada jogada, independente da direcao.

### 2.1 TASK-MG-01: Adicionar Streak Tracker Global ao MartingaleState

**O que:** Novo campo `global_consecutive_hits` no `MartingaleState` que monitora hits consecutivos de AMBAS as direcoes combinadas.

**Por que vale a pena:**
- Na sessao, houve streak global de 6 hits (#15-20) que gerou +R$135 extra na simulacao S6
- O streak per-direction nunca passou de 2 em CW (por alternancia H/AH)
- Sem esse tracker, o sistema nunca detecta sequencias cross-direction

**Arquivo:** `state/game.py`

**Codigo atual (linhas 33-35):**
`python
level: int = 1
consecutive_hits: int = 0
total_bets: int = 0
`

**Codigo proposto:**
`python
level: int = 1
consecutive_hits: int = 0       # Streak per-direction (mantido)
global_consecutive_hits: int = 0 # Streak cross-direction (NOVO)
total_bets: int = 0
`

**Impacto em update() (linha 74) - adicionar parametro global_hit:**
`python
def update(self, hit: bool, global_hit: bool = None) -> Dict[str, Any]:
    level_before = self.level
    self.total_bets += 1
    
    if hit:
        self.consecutive_hits += 1
    else:
        self.consecutive_hits = 0
        self.level = 1
    
    # Global streak (cross-direction)
    if global_hit is not None:
        if global_hit:
            self.global_consecutive_hits += 1
        else:
            self.global_consecutive_hits = 0
`

**Impacto em engine.py (linhas 53-83):**
- O `engine.py` chama `martingale_cw.update(hit_result)` ou `martingale_ccw.update(hit_result)`
- Precisamos passar `global_hit=hit_result` para AMBOS os martingales

**Risco:** BAIXO - campo aditivo, nao muda comportamento existente ate TASK-MG-02 ativar

**Simulacao:** S6 (Streak Combinado) gerou +R$69 vs -R$105 do atual = **+R$174 de melhoria**

---

### 2.2 TASK-MG-02: Reformular get_gale() para Anti-Martingale com Take-Profit

**O que:** Inverter a logica de escalacao - subir apos VITORIAS (nao derrotas), com reset em G3 hit (take-profit).

**Por que vale a pena:**
- O martingale classico (dobrar na derrota) gerou -R$162 na simulacao - PIOR resultado
- O anti-martingale com take-profit gerou +R$27 - UNICA estrategia lucrativa com logica simples
- O principio e matematicamente solido: quando hit rate < 50%, amplificar ganhos > amplificar perdas

**Arquivo:** `state/game.py` - metodo `get_gale()` (linhas 52-72)

**Logica atual:**
`
Score ceiling -> c4 advisor -> Streak per-direction -> Escalacao
Se 2+ hits consecutivos PER-DIRECTION -> sobe 1
Se miss -> volta G1
`

**Logica proposta (SmartGale v5):**
`
1. BASE: Anti-Martingale
   - Hit -> sobe 1 nivel (G1->G2->G3)
   - Miss -> reset G1 imediatamente
   
2. TAKE-PROFIT:
   - Hit em G3 -> lock profit, reset G1
   - Evita exposicao prolongada no nivel maximo
   
3. TRACKER DECISOR:
   - Usa global_consecutive_hits (de TASK-MG-01) como trigger primario
   - 2 hits globais consecutivos -> libera G2
   - 3+ hits globais consecutivos -> libera G3
   
4. FILTRO DE SEGURANCA:
   - Score ceiling mantido (Regra 1)
   - c4_rate threshold AJUSTADO: 0.25 -> 0.15 (menos restritivo)
`

**Codigo proposto para get_gale:**
`python
def get_gale(self, score: int = 3, c4_rate: float = 0.5) -> int:
    """SmartGale v5: Anti-Martingale com Take-Profit."""
    # Regra 1 - Teto por Score (mantida)
    if score <= 2:
        max_gale = 1
    elif score <= 4:
        max_gale = 2
    else:
        max_gale = 3
    
    # Regra 4 - C4 advisor (threshold ajustado)
    if c4_rate < 0.15:
        max_gale = 1
    
    # NOVO: Anti-Martingale com streak global
    streak = self.global_consecutive_hits
    
    if streak >= 3:
        desired = 3  # Libera G3 em streaks fortes
    elif streak >= 2:
        desired = 2  # Libera G2 apos 2 hits
    else:
        desired = 1  # Sem streak = G1 (conservador)
    
    self.level = min(desired, max_gale)
    return self.level
`

**Impacto em update() - Take-Profit:**
`python
if hit:
    self.consecutive_hits += 1
    # TAKE-PROFIT: G3 + HIT -> reset para preservar lucro
    if level_before == 3:
        self.level = 1
        self.consecutive_hits = 0
        transition = "TAKE-PROFIT: G3 HIT -> lock, reset G1"
else:
    self.consecutive_hits = 0
    self.level = 1  # Reset imediato no miss (mantido)
`

**Analise de risco detalhada:**
| Cenario | SmartGale v4 (atual) | SmartGale v5 (proposto) |
|---------|:--------------------:|:----------------------:|
| 3 misses seguidos | -R$63 (3 x G1) | -R$63 (3 x G1) - IGUAL |
| 3 hits seguidos | +R$45 (3 x G1) | +R$60 (G1+G2+G3) - MELHOR |
| Hit-Miss alternado | -R$18 (G1+G1) | -R$18 (G1+G1) - IGUAL |
| 6 hits seguidos | +R$90 (6 x G1) | +R$180 (G1+G2+G3+take+G1+G2) - MELHOR |
| Miss apos G3 | impossivel (nunca sobe) | -R$21 (reset G1) - SEGURO |

**Simulacao nesta sessao:** +R$27 (S3 puro) a +R$69 (S6 com streak global)

---

### 2.3 TASK-MG-03: Ajustar c4_rate Threshold (0.25 -> 0.15)

**O que:** Reduzir o threshold do Gale Advisor de 0.25 para 0.15.

**Por que vale a pena:**
- Com threshold 0.25, **40% das apostas** foram forcadas a G1 nesta sessao
- Muitas dessas bloquearam escalacoes em direcoes que estavam performando bem
- O threshold 0.15 so bloquearia em situacoes de performance realmente catastrofica (< 15% hit rate nas ultimas 4)
- Na sessao, NENHUMA aposta teve c4_rate < 0.15, entao o filtro teria sido transparente

**Arquivo:** `state/game.py` - metodo `get_gale()` (linha 61)

**Atual:** `if c4_rate < 0.25: max_gale = 1`
**Proposto:** `if c4_rate < 0.15: max_gale = 1`

**Risco:** BAIXO - o threshold continua existindo como rede de seguranca, apenas menos agressivo.

**Analise na sessao:**
- Com 0.25: 12/30 apostas bloqueadas (40%)
- Com 0.15: 0/30 apostas bloqueadas (0%)
- Isso significa que o threshold 0.25 estava **suprimindo** a escalacao sem justificativa real

---

### 2.4 TASK-MG-04: Sincronizar global_hit Entre Ambos Martingales

**O que:** Quando um resultado chega (hit ou miss), ambos `martingale_cw` e `martingale_ccw` devem receber o `global_hit` para manter o `global_consecutive_hits` sincronizado.

**Por que vale a pena:**
- O streak global e o principal driver da escalacao no SmartGale v5
- Se apenas um martingale recebe o global_hit, o outro fica com streak global desatualizado
- Isso causaria escalacao incorreta quando a direcao alvo muda

**Arquivo:** `core/engine.py` - secao de resultado (linhas 53-83)

**Fluxo atual:**
`python
if bet_direction in ("cw", "horario"):
    martingale_info = self.game_state.martingale_cw.update(hit_result)
else:
    martingale_info = self.game_state.martingale_ccw.update(hit_result)
`

**Fluxo proposto:**
`python
if bet_direction in ("cw", "horario"):
    martingale_info = self.game_state.martingale_cw.update(hit_result, global_hit=hit_result)
    self.game_state.martingale_ccw.sync_global(hit_result)
else:
    martingale_info = self.game_state.martingale_ccw.update(hit_result, global_hit=hit_result)
    self.game_state.martingale_cw.sync_global(hit_result)
`

**Novo metodo sync_global() em MartingaleState:**
`python
def sync_global(self, global_hit: bool):
    """Sincroniza streak global sem alterar estado local."""
    if global_hit:
        self.global_consecutive_hits += 1
    else:
        self.global_consecutive_hits = 0
`

**Risco:** BAIXO - metodo isolado, nao toca em level/consecutive_hits local.

---

### 2.5 TASK-MG-05: Atualizar to_dict/from_dict para Persistir global_streak

**O que:** Garantir que `global_consecutive_hits` seja salvo e restaurado no `state.json`.

**Arquivo:** `state/game.py` - metodos `to_dict()` e `from_dict()` (linhas 103-116)

**Proposto - adicionar ao to_dict:**
`python
"global_consecutive_hits": self.global_consecutive_hits,
`

**Proposto - adicionar ao from_dict:**
`python
obj.global_consecutive_hits = data.get("global_consecutive_hits", 0)
`

**Risco:** MINIMO - retrocompativel (default 0 se campo nao existir).

---

### 2.6 TASK-MG-06: Testes Unitarios para SmartGale v5

**O que:** Novos testes cobrindo anti-martingale, take-profit, global streak e sincronizacao.

| ID | Teste | Cenario |
|:--:|-------|---------|
| T1 | `test_anti_mg_hit_escalation` | 3 hits seguidos -> G1, G2, G3 |
| T2 | `test_anti_mg_miss_reset` | Hit G2, miss -> volta G1 |
| T3 | `test_take_profit_g3_hit` | Hit em G3 -> reset G1 |
| T4 | `test_global_streak_cross_direction` | CW hit + CCW hit = global 2 |
| T5 | `test_c4_threshold_015` | c4=0.20 nao bloqueia (antes bloqueava) |
| T6 | `test_c4_threshold_015_blocks` | c4=0.10 bloqueia -> G1 |
| T7 | `test_sync_global_independent` | sync_global nao muda level local |
| T8 | `test_to_dict_from_dict_global` | Persistencia do global_consecutive_hits |
| T9 | `test_session_replay` | Replay dos 29 resultados reais = P&L esperado |

**Arquivo:** `tests/test_smartgale_v5.py` (novo)

**Risco:** NENHUM - testes nao alteram producao.

---

### 2.7 TASK-MG-07: Atualizar Manutenabilidade ISO

**O que:** Documentar SmartGale v5 na `Manutenabilidade_iso.md`.

**Secoes a atualizar:**
- PARTE II (Arquitetura): Adicionar descricao do SmartGale v5
- PARTE IV (Bugs): Registrar BUG-MG-01 e BUG-MG-02 como resolvidos
- PARTE IV (Melhorias): Registrar MEL-MG-01/02/03
- Matriz de qualidade: Atualizar eficiencia/confiabilidade

---

## 3. O Que NAO Vale a Pena Implantar Agora

### 3.1 Pausa de Direcao (MEL-MG-03 do documento de resultados)
**Descartado.** Nossas tecnicas nao incluem pausa. A acuracia por direcao e responsabilidade da estrategia SDA-21, nao do martingale. O martingale cuida EXCLUSIVAMENTE de quanto apostar.

### 3.2 Window-Based Gale (S9)
**Descartado.** Gerou -R$129 na simulacao. O lag de 5 apostas faz o sistema escalar APOS o streak (tarde demais) e manter o nivel alto quando o streak acaba.

### 3.3 D'Alembert / Fibonacci (S4, S5)
**Descartado.** Ambos geraram perdas piores que Always G1. A progressao gradual nao se adapta rapido o suficiente aos clusters de resultado.

### 3.4 Performance-Threshold Global (S8)
**Descartado por ora.** Embora melhor que G1 fixo (-R$90 vs -R$105), o hit rate acumulado e muito lento para reagir. Pode ser revisitado como complemento futuro.

---

## 4. Analise de Conflitos com Sessao Atual

### 4.1 Compatibilidade com Sessao em Andamento

| Aspecto | Impacto | Mitigacao |
|---------|---------|-----------|
| `state.json` | Novo campo `global_consecutive_hits` | Default 0 se ausente (retrocompativel) |
| Banco de dados | Nenhuma mudanca de schema | Zero conflito |
| `gale_windows` | Formato inalterado | Janelas existentes continuam validas |
| `window_plays` | Formato inalterado | Plays existentes continuam validos |
| Performance lists | Inalteradas | c4_rate continua vindo de `performance_bet` |

**Veredicto:** A implantacao NAO requer reset de sessao. O novo SmartGale v5 inicia com `global_consecutive_hits=0` e converge naturalmente apos 2-3 jogadas.

### 4.2 Sequencia Segura de Deploy

`
1. Merge do codigo (TASK-MG-01 a 05)
2. Rodar testes locais (67 existentes + 9 novos = 76)
3. git push
4. SSH no servidor: git pull && docker compose down && docker compose build --no-cache && docker compose up -d
5. Container sobe com state.json existente
6. global_consecutive_hits inicia em 0 (default)
7. Apos primeira jogada, sistema opera em SmartGale v5
`

**Tempo de indisponibilidade:** ~30 segundos (rebuild + restart).

---

## 5. Ordem de Implantacao

| Ordem | Task | Dependencia | Risco | Arquivos |
|:-----:|:----:|:-----------:|:-----:|:---------|
| 1 | TASK-MG-01 | Nenhuma | Baixo | `state/game.py` |
| 2 | TASK-MG-05 | TASK-MG-01 | Minimo | `state/game.py` |
| 3 | TASK-MG-03 | Nenhuma | Baixo | `state/game.py` |
| 4 | TASK-MG-02 | TASK-MG-01 | Medio | `state/game.py` |
| 5 | TASK-MG-04 | TASK-MG-01 | Baixo | `core/engine.py` |
| 6 | TASK-MG-06 | Todas acima | Nenhum | `tests/test_smartgale_v5.py` |
| 7 | TASK-MG-07 | Todas acima | Nenhum | `Manutenabilidade_iso.md` |

**Total de arquivos modificados:** 3 (`state/game.py`, `core/engine.py`, `Manutenabilidade_iso.md`)
**Arquivo novo:** 1 (`tests/test_smartgale_v5.py`)

---

## 6. Resumo Executivo

### Problema
O SmartGale v4 esta travado em G1 (R$21) em 100% das apostas devido a combinacao de c4_rate < 0.25 + streak separado por direcao + alternancia H/AH. Resultado: -R$105 na sessao.

### Solucao
Evoluir para **SmartGale v5** com:
1. **Anti-Martingale:** Escalar em vitorias (nao derrotas)
2. **Streak Global:** Tracker cross-direction para detectar sequencias reais
3. **Take-Profit:** Reset apos G3+HIT para preservar lucro
4. **c4 Ajustado:** Threshold 0.15 (menos restritivo)

### Resultado Esperado
| Metrica | SmartGale v4 | SmartGale v5 |
|---------|:------------:|:------------:|
| P&L nesta sessao | -R$105 | +R$27 a +R$69 |
| Escalacao ativa | 0% das apostas | Streaks de 2+ |
| Risco maximo | R$21/aposta | R$63/aposta (G3) |
| Protecao em miss | G1 sempre | G1 reset imediato |
| Take-profit | Nao existe | G3 HIT = lock |

### Premissa
> **O martingale NAO decide SE apostar. Ele decide QUANTO apostar.** A decisao de apostar ou nao e da estrategia (SDA-21 + Triple Rate). O martingale gerencia a banca a cada jogada, capitalizando momentos de acerto e protegendo em momentos de erro.

### Proximos Passos
1. Aprovar este plano
2. Executar TASK-MG-01 a 07
3. Rodar sessao de teste em producao
4. Analisar resultados com SmartGale v5
5. Iterar se necessario

---

> **Documento de pre-implantacao** - Aguardando aprovacao
> **Nao foram feitas alteracoes no software**
