# Próximos Passos — 10/06 (Plano Revisado)

## Objetivo deste plano
Refazer o plano com foco total em **estrutura de software**, **eficiência operacional** e **validação da estratégia para gerar lucro**.

> **Escopo deliberado:** neste momento, **segurança fica fora do plano de execução**.  
> A prioridade é fazer a operação funcionar bem, com previsibilidade e resultado.

---

## 1) O que motivou a revisão

O plano anterior acertou no diagnóstico técnico (CI quebrado, migrations pendentes, captura DEAL incompleta, backup frágil), mas misturou frentes demais ao mesmo tempo.  
Para ganhar velocidade real, precisamos concentrar em três pilares:

1. **Confiabilidade funcional do core** (pipeline de decisão sem quebra)
2. **Qualidade dos dados estratégicos** (captura correta para alimentar modelo)
3. **Ciclo rápido de validação de lucro** (medir, comparar, decidir rápido)

Sem isso, qualquer melhoria paralela vira custo com pouco retorno.

---

## 2) Princípios do plano revisado

1. **Primeiro funcionar, depois otimizar**  
   Corrigir fluxo crítico ponta a ponta antes de novas features.

2. **Toda entrega deve aumentar capacidade de medir lucro**  
   Se não melhora decisão, qualidade de dado ou medição de resultado, não entra agora.

3. **Reduzir variabilidade operacional**  
   Menos passos manuais e menos “depende do operador”.

4. **Curto ciclo de experimento**  
   Implementar -> medir em produção -> ajustar em janela curta.

5. **Segurança explicitamente adiada**  
   Não entra no ciclo atual, salvo se bloquear execução da estratégia.

---

## 3) Plano de execução (revisado)

### Fase A — Estabilizar a estrutura que impacta lucro (Dia 1 e 2)

1. **Corrigir pipeline de schema de forma definitiva (CI + deploy)**
   - Implementar `alembic upgrade head` no CI e no fluxo de deploy.
   - Eliminar drift entre código e banco.
   - **Por quê:** sem schema consistente, os testes e o worker falham de forma intermitente e atrasam qualquer evolução estratégica.

2. **Padronizar checklist de deploy funcional**
   - Checklist único: pull, build, migrate, smoke-test, health.
   - **Por quê:** evita regressão operacional e reduz tempo de recuperação.

3. **Confirmar processamento fim a fim da decisão**
   - Validar ingestão -> decisão -> outbox -> consumo worker -> métricas.
   - **Por quê:** lucro só existe se o ciclo de decisão estiver íntegro.

---

### Fase B — Resolver qualidade de dado estratégico (Dia 3 e 4)

1. **Fechar captura DEAL (dealer/table/round) em produção real**
   - Validar com sessão assistida e logs por evento.
   - **Por quê:** hoje o modelo perde contexto importante; sem esse dado, calibração e análise de performance ficam cegas.

2. **Criar rotina curta de validação de integridade de dados**
   - Contagem diária de nulos e cobertura mínima por campo-chave.
   - **Por quê:** impede degradar qualidade de entrada sem perceber.

3. **Atualizar modelo/artefato apenas com dados válidos**
   - Regerar artefato estratégico quando cobertura mínima for atingida.
   - **Por quê:** melhora consistência da recomendação e evita treinar em lixo.

---

### Fase C — Validar eficiência e lucro da estratégia (Semana 2)

1. **Definir experimento controlado CW/CCW com baseline**
   - Comparar estratégia atual vs baseline em janela fixa.
   - **Por quê:** decisão de evolução deve ser por evidência, não percepção.

2. **Publicar painel mínimo de eficiência estratégica**
   - KPIs: hit rate, ROI por janela, drawdown, tempo de reação, cobertura de dados.
   - **Por quê:** acelera decisão de continuar, ajustar ou reverter estratégia.

3. **Aplicar regra de gate para promoção de estratégia**
   - Só sobe de estágio se bater metas mínimas por período.
   - **Por quê:** evita escalar versão que “parece boa”, mas não sustenta lucro.

---

## 4) Métricas de sucesso deste ciclo

- **Estabilidade operacional**
  - CI verde e sem falha de schema
  - Deploy com migração sem intervenção manual

- **Qualidade de dados**
  - Queda expressiva de `dealer/table/round` ausentes
  - Cobertura mínima de campos estratégicos definida e monitorada

- **Eficiência/Lucro**
  - KPI de ROI por janela com tendência positiva consistente
  - Redução de drawdown nas mesmas condições de jogo

---

## 5) O que não entra agora (intencionalmente)

- Hardening de SSH/firewall/fail2ban
- Rotação de segredos e revisão de superfícies de ataque
- Aprofundamento de políticas de segurança

Esses itens ficam para o ciclo seguinte, após estabilização e validação de eficiência/lucro.

---

## 6) Resumo executivo

Plano revisado = **menos frentes paralelas, mais foco no que move resultado**:

1. Estrutura funcional previsível (CI/deploy/schema/fluxo)
2. Dado estratégico confiável (DEAL + integridade)
3. Validação objetiva de lucro (experimento + KPI + gates)

Com isso, o software passa a operar com base em evidência e velocidade de iteração — exatamente o necessário para evoluir eficiência antes de abrir o próximo ciclo (segurança).
