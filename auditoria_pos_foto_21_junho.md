# 🔍 Auditoria pós-foto — estrutura do pipeline `foto → dados` (21/jun)

> **Data:** 21/06/2026 · **Escopo:** meta-auditoria da análise anterior (`foto_roleta_junho.md`) + verificação **estrutural** do pipeline de visão, agora que ele está **deployado há poucos dias**.
> **Pergunta do dono:** *"estruturalmente o sistema está rodando tudo ok?"* (cobertura baixa é esperada por ser recente — o foco é **encanamento correto**, não volume de dado).
> **Método:** MCPs `graphify` (estrutura) + `filesystem` (código) + `sequential-thinking` (verdito) + `memory` (checkpoint) + **SSH read-only no DB de produção AO VIVO** (`root@187.45.181.75`, `decisions.db`, 8831 linhas, HEAD `58d5528`).

---

## 1. Sumário executivo (TL;DR)

✅ **SIM — estruturalmente o sistema está rodando OK.** O encanamento `foto → OCR → dados → DB` está **íntegro e provado em produção**: escritor único → SQLite SoT → 41 colunas certas → `spin_force`/`spin_direction` 100% → loop de visão **vivo** (89 linhas `vision_source='vision'`, última 21/06 20:56) gravando `dealer + provider + wheel_model + confidence` na **mesma linha** da jogada.

⚠️ Foram encontrados **3 bugs estruturais de qualidade de dado** (que **não** se auto-corrigem com o tempo) — **todos corrigidos e testados** nesta auditoria (suíte: **615 passed**).

🧠 Também corrijo **3 imprecisões da minha própria análise anterior** (meta-auditoria) — a mais importante: a alegação de "modelo não normalizado em produção" estava **desatualizada** (já funciona; a fragmentação é **legado** pré-deploy).

---

## 2. Meta-auditoria: erros na análise anterior (honestidade intelectual)

| # | Afirmação anterior (`foto_roleta_junho.md` / sessão) | Correção (verificada no código + DB ao vivo) |
|---|---|---|
| **E-1** | *"Linhas de visão com `spin_force=0/1` sugerem mis-associação da foto."* | **FALSO.** `update_last_vision` (sqlite_repo.py:561-577) só grava `dealer/wheel_model/provider/vision_*` — **nunca toca `spin_force`**. A força vem do `novo_resultado` que criou a linha. Força 0/1 é apenas a força real (ou não-capturada) daquele giro, **independente da foto**. |
| **E-2** | *"`_norm_model` não está efetivo em produção (modelo fragmentado)."* | **DESATUALIZADO.** O split por dia prova: **19/06** = `Roleta aoVivo`(60 cru) = **legado** (pré-deploy de `_norm_model`, que entrou em `58d5528`); **21/06** = só `Roleta ao Vivo`(19) ✅ **já canonizado**. A canonização **funciona hoje** (via env `SDA_VISION_MODEL_ALIASES`, presente no container). A fragmentação é **histórica**, não bug ativo — embora a *dependência exclusiva do env* seja uma fragilidade (→ BUG-3). |
| **E-3** | *Enquadramento de "cobertura ~1% / n<30 por dealer" como **BLOQUEADOR**.* | **REENQUADRADO.** Sistema deployado há dias e operado de forma intermitente → cobertura baixa é **ramp-up esperado**, não defeito estrutural. O dado **acumula sozinho** com o uso (ver §6). |

> A preocupação de "associação racy" (foto cola na `MAX(id)`) **existe** mas é de **baixo impacto**: o dealer é estável por vários giros, então errar o dealer por ±1 linha raramente muda o agrupamento; e a **força não é afetada** (E-1). Tratada como *hardening* futuro, não bug crítico.

---

## 3. Veredito estrutural — o encanamento está íntegro

Confirmado no **código** e no **DB de produção ao vivo**:

| Camada | Evidência | Status |
|---|---|---|
| Produtor → Engine | `handle_new_result` lê `data.get('dealer'/'provider'/'wheel_model')` (message_handler.py:407-414) | ✅ |
| Escritor único → SoT | `save_decision` grava tudo numa linha (sqlite_repo.py:389-448); 41 colunas | ✅ |
| Força / sentido | `spin_force` 8251/8831 (93%) · `spin_direction` 8831/8831 (100%) | ✅ |
| Loop de visão | `handle_foto_frame → update_last_vision` (message_handler.py:1253-1320) | ✅ vivo |
| Persistência de visão | 89 linhas `vision_source='vision'` (77 em 19/06, 12 em 21/06; última 20:56) | ✅ |
| **Vínculo dealer×modelo×provider×força** | `GROUP BY dealer,wheel_model,provider,spin_direction → AVG(spin_force)` retorna linhas reais (ex.: `STEFANY · evolution · Roleta ao Vivo · força=20 · conf 0.97`) | ✅ **já existe** |

**Conclusão:** o objetivo de "vincular dealer/modelo/provedor à força para estratégia por dealer" é **estruturalmente realizado** — tudo já chega na mesma linha e a query funciona. O que falta é **maturação operacional** (volume + higiene), não arquitetura.

---

## 4. Bugs estruturais encontrados (ativos, não se auto-corrigem) — **CORRIGIDOS**

### 🐞 BUG-1 — `provider` poluído com `host:*` (analytics vazando)
- **Sintoma (DB ao vivo):** `provider` = `host:www.googletagmanager.com`, `host:...doubleclick.net`, `host:www.youtube.com`, `host:www.instagram.com` — **~2100 linhas**; ainda ocorrendo **em 21/06 (22 linhas)**. Só `evolution`(1450) era limpo.
- **Causa-raiz (cliente):** `extension/deal_capture.js:24` → `PROVIDER_FALLBACK = provider || \`host:${HOST}\``. Em frames de analytics o `HOST` é o domínio do tracker, que vaza como "provider".
- **Correção aplicada (server-side, defesa em profundidade):** validador Pydantic em `SpinInput` (`models/input.py`) que **recupera a marca pelo domínio** (`evo-games → evolution`) e **descarta** `host:*` não-reconhecido (→ `None`), em vez de poluir o agrupamento. Ponto único de ingestão, vale para DOM **e** visão.

### 🐞 BUG-2 — falso-positivo: OCR captura o **próprio dashboard**
- **Sintoma (DB ao vivo, 21/06):** 2 linhas com `wheel_model='Roleta Cloud'` e 1 vision-row com `provider='host:www.roleta.xma-ia.com'` — o OCR pegou a **aba do dashboard** (`Roleta Cloud` casa a keyword `roleta`) em vez da mesa do cassino.
- **Correção aplicada (`server/vision_ocr.py`):** reject-list `_SELF_TOKENS` (`roleta cloud`, `xma-ia`, `escuta beat`) + helper `_is_self`; em `_parse_fields`, `wheel_model`/`dealer` que casam a identidade do próprio app são **descartados antes** da inferência de provider.

### 🐞 BUG-3 — canonização de `wheel_model` **dependente exclusivamente do env** (fragilidade)
- **Sintoma:** `_norm_model` só funde as variantes de OCR (`Roleta aoVivo`/`Roleta ao Vivo`/`RoletaaoVivo`) **se** `SDA_VISION_MODEL_ALIASES` estiver setado. **Sem o env**, o fallback `.title()` é sensível a espaço → **3 saídas distintas** para o mesmo rótulo (provado empiricamente). Hoje funciona porque o container tem o env, mas é silenciosamente frágil (env perdido ou mesa nova → re-fragmenta).
- **Correção aplicada (`server/vision_ocr.py`):** `_DEFAULT_MODEL_ALIASES` **embutido** (`roletaaovivo → Roleta ao Vivo`), mesclado em `_model_aliases()` com o env **sobrepondo** os defaults. Agora as variantes colapsam **mesmo sem env**; operadores ainda customizam por env.

---

## 5. Correções — arquivos e testes

| Arquivo | Mudança | 
|---|---|
| `models/input.py` | `_PROVIDER_BRAND_KEYWORDS` + `@field_validator('provider')` (BUG-1) |
| `server/vision_ocr.py` | `_DEFAULT_MODEL_ALIASES` + merge em `_model_aliases` (BUG-3); `_SELF_TOKENS`/`_is_self` + reject em `_parse_fields` (BUG-2) |
| `tests/test_vision_ocr.py` | +`test_model_merges_variants_without_env`, +`test_parse_fields_rejects_self_dashboard`; `test_model_normalized_title_case_and_whitespace` ajustado p/ label genérico |
| `tests/test_vision_features.py` | +`test_spininput_sanitizes_provider_host_fallback` |

**Validação:** `python -m pytest -q` → **615 passed, 9 skipped, 1 xfailed** (0 falhas). Suíte focada (`test_vision_ocr` + `test_vision_features`): **26 passed**.

---

## 6. O que é **ramp-up esperado** (NÃO é bug)

- **Cobertura de visão ~1%** (89/8831) e **n por dealer 8-22** (< limiar `n≥30` do `dealer_offset`): consequência direta de o sistema ser **recente** e a Escuta ser ligada de forma intermitente. **Acumula sozinho** com o uso normal — nenhum código a corrigir.
- **`dealer='unknown'` em 99%**: idem — só é preenchido nos giros em que uma foto aterrissa. Acelerável (ver §7), mas não é defeito estrutural.

---

## 7. Recomendações remanescentes (documentadas, **não** aplicadas)

Itens fora do escopo "bug estrutural seguro" — exigem deploy/aprovação ou são client-side:

1. **(Cliente) Tratar a raiz do BUG-1** em `extension/deal_capture.js:24`: não usar `host:${HOST}` em frames de analytics (exige reload da extensão no Chrome; sem e2e local). O guard server-side já neutraliza o sintoma no DB.
2. **(Maior ROI — dado) `dealer` fill-forward temporal:** propagar o dealer OCR'd pelos giros do `session_id` por ordem de tempo, **cortando na troca** (sessões têm 2 dealers, ex.: `ANNA,LEVI`). Levaria a cobertura de dealer de ~1% à maioria **sem mais fotos** (sessão `84f121e8`: 12 com + 232 sem).
3. **(Limpeza única, prod-write → requer aprovação)** backfill das ~62 linhas legado de `wheel_model`:
   ```sql
   UPDATE decisions SET wheel_model='Roleta ao Vivo'
   WHERE wheel_model IN ('Roleta aoVivo','RoletaaoVivo');
   ```
4. **(Hardening) Associação atômica:** fundir `vision_*` no **próximo `novo_resultado`** (como o comentário `message_handler.py:1257` já prevê) em vez do `update MAX(id)`.
5. **(Consumidor) Só então** `dealer_force_profile`/`wheel_offset`, gated por `n≥30` + `confidence`, medido pelo template `decision_dna` (lift estimado vs realizado) antes de confiar.

---

## 8. Como validar / próximo passo
- ✅ Local: `python -m pytest -q` (615 passed).
- 🚀 **Deploy** das correções (não executado — é prod-write): subir `58d5528+correções` pelo fluxo de deploy padrão; o guard de provider e o reject de auto-captura passam a valer no próximo giro; a canonização fica robusta a env ausente.

> **Resumo de 1 linha:** estruturalmente o pipeline `foto→dados` está **íntegro e provado em produção**; os 3 problemas eram de **higiene de dado** (provider sujo, auto-captura, canonização frágil) — **corrigidos e testados** — e a baixa cobertura é apenas **ramp-up** de um sistema recém-implantado.
