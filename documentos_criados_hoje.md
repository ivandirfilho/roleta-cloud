# Documentos Criados em 28/03/2026

> **Data:** 28/Mar/2026
> **Total de documentos criados:** 7
> **Commits do dia:** 3 (`c2b1cf3`, `950473c`, `33f0e18`)

---

## Lista de Documentos

### 1. `resolucao_bugs_28_03.md`
- **Criado em:** ~06:57
- **Commit:** `c2b1cf3`
- **Conteúdo:** Levantamento de 12 bugs e 11 melhorias identificados a partir do `estado_pos_refatoracao.md`. Cada item contém descrição, arquivo afetado, linhas, severidade e proposta de correção. Inclui análise do fluxo de dados estratégico antes/depois do git de refatoração do dia 27/03.

### 2. `implantação_da_resolucao_bugs_28.md`
- **Criado em:** ~07:10
- **Commit:** `c2b1cf3`
- **Conteúdo:** Plano de implantação com todas as tasks necessárias do `resolucao_bugs_28_03.md`. Transformou cada bug/melhoria em task executável com código antes/depois. Serviu como guia para o commit `c2b1cf3` que corrigiu 12 bugs + 11 melhorias.

### 3. `resposta_a_sugestão_28_03.md`
- **Criado em:** ~07:47
- **Commit:** `950473c`
- **Conteúdo:** Análise completa (517 linhas) das 4 sessões do Jules (agente Google) que enviaram sugestões via ZIP. Para cada sessão, documenta: o que Jules propôs, diff vs código atual, conflitos com nossas correções, e veredicto (aceitar/rejeitar parcialmente). Tabela de conflitos e auditoria final.

### 4. `tasks_aplicacoes_apos_resposta.md`
- **Criado em:** ~07:58
- **Commit:** `950473c`
- **Conteúdo:** 4 tasks aprovadas extraídas da resposta ao Jules + 1 task de documentação. Cada task com código antes/depois exato, simulação de impacto, auditoria de bugs e referência à Manutenabilidade ISO. Serviu como guia para o commit `950473c`.

### 5. `resultados_08am_dia28.md`
- **Criado em:** ~09:07 | **Atualizado:** ~12:15
- **Commit:** `33f0e18`
- **Conteúdo:** Análise completa da sessão das 08AM (789 linhas). Inclui:
  - Tabela decisão-por-decisão (42 decisions)
  - Análise por direção (CW 33.3% vs CCW 66.7%)
  - Análise de gale windows (8 janelas)
  - Validação do pipeline de dados
  - **Seção 10: Análise de Martingale** — simulação de 10 estratégias com os 29 resultados reais, ranking comparativo, bugs/melhorias identificados, recomendação do Hybrid Anti-Martingale

### 6. `implantacao_pos_resultados08am.md`
- **Criado em:** ~11:55
- **Commit:** `33f0e18`
- **Conteúdo:** Plano de implantação do SmartGale v5 (430 linhas). 7 tasks (MG-01 a MG-07) com código proposto, análise de risco, ordem de implantação, análise de conflitos com sessão atual. Documento de pré-aprovação que foi aprovado e executado no mesmo dia.

### 7. `documentos_criados_hoje.md` ← (este documento)
- **Criado em:** ~16:42
- **Conteúdo:** Resumo de todos os documentos criados no dia 28/03.

---

## Documento Atualizado (não criado)

### `Manutenabilidade_iso.md`
- **Atualizado em:** commits `950473c` e `33f0e18`
- **Alterações:** Adicionados BUG-POST-008, BUG-MG-001/002, MEL-ISO-011/012/013, MEL-MG-001/002/003, atualização da matriz ISO e footer.

---

## O que significa "G1 S0 GS0" no Frontend

No frontend, ao lado do nome "Gale", aparece a string do **gale_display** do SmartGale v5:

```
G1 S0 GS0
│  │   │
│  │   └── GS = Global Streak (hits consecutivos GLOBAIS, ambas direções)
│  │        0 = nenhum hit consecutivo global no momento
│  │
│  └── S = Streak local (hits consecutivos NA DIREÇÃO atual)
│       0 = nenhum hit consecutivo nesta direção
│
└── G = Gale Level (nível atual de aposta)
     1 = G1 (R$21 = R$1 × 21 números)
     2 = G2 (R$42 = R$2 × 21 números)
     3 = G3 (R$63 = R$3 × 21 números)
```

### Exemplos práticos:

| Display | Significado |
|---------|------------|
| `G1 S0 GS0` | Nível 1, sem streak local, sem streak global — aposta mínima R$21 |
| `G1 S1 GS1` | Nível 1, 1 hit local, 1 hit global — ainda em G1 (precisa GS≥2 para subir) |
| `G2 S1 GS2` | Nível 2, 1 hit local, 2 hits globais — escalou para G2 (R$42) |
| `G3 S2 GS3` | Nível 3, 2 hits locais, 3 hits globais — nível máximo R$63 |
| `G1 S0 GS0` | Após miss — reset imediato para G1 |
| `G1 S0 GS5` | Após take-profit (G3+HIT) — resetou G1 mas global continua |

### Como o SmartGale v5 usa esses valores:

1. **GS (Global Streak)** é o principal driver de escalação:
   - GS < 2 → G1 (conservador)
   - GS ≥ 2 → G2 liberado
   - GS ≥ 3 → G3 liberado

2. **S (Streak local)** é informativo — mostra o streak na direção específica

3. **G (Gale Level)** é o resultado final após aplicar:
   - Teto por score SDA (score 3-4 → max G2, score 5+ → max G3)
   - Filtro c4_rate (< 0.15 → força G1)
   - Limitação pelo global streak

### Diferença do SmartGale v4 (anterior):

| | SmartGale v4 | SmartGale v5 (atual) |
|---|---|---|
| Display | `G1 S0` | `G1 S0 GS0` |
| Escalação baseada em | Streak LOCAL por direção | Streak GLOBAL cross-direction |
| c4_rate threshold | < 0.25 (bloqueava 40%) | < 0.15 (menos restritivo) |
| Take-profit | Não existia | G3+HIT → reset G1 |
| Na sessão 08AM | Ficou G1 100% do tempo | Escalaria nos streaks de 2+ |

---

> **Documento gerado em:** 28/Mar/2026 16:42
