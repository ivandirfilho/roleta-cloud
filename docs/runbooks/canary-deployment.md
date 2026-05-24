# S13 — Canary Deployment (estrategias novas)

## Objetivo

Habilitar uma estrategia nova (ex: `cold_regions`, `shadow_predictor`) para
um percentual `pct` de decisoes via `shared.feature_flags.pct`, comparar
KPIs vs grupo controle e promover/abortar.

## Mecanica

Cada feature flag em `shared.feature_flags` tem:
- `enabled` (bool) — kill switch global.
- `pct` (int 0..100) — % de decisoes que usam a versao nova.

Decisao por chamada:
```python
import hashlib
def in_canary(decision_id: int, pct: int) -> bool:
    if pct <= 0: return False
    if pct >= 100: return True
    h = int(hashlib.sha1(str(decision_id).encode()).hexdigest(), 16)
    return (h % 100) < pct
```

Hash determinstico garante que mesmo `decision_id` sempre cai no mesmo bucket
(reproducibilidade em replays).

## Gates de promocao

Para promover de `pct=N` para `pct=N+M`, todos os seguintes devem ser true
nas ultimas 24h:

| Metrica                    | Limite                       |
|---------------------------|------------------------------|
| win_rate_canary           | >= win_rate_control - 2pp    |
| latencia_p95_canary       | <= latencia_p95_control + 10ms |
| erros_5xx_canary          | <= 0.1%                      |
| divergencia_shadow_avg    | <= 15% (so para shadow)      |

## Sequencia tipica

1. `UPDATE shared.feature_flags SET enabled=true, pct=5 WHERE name='X';`
2. Aguardar 1h, validar gates.
3. Subir para 25, 50, 100 com intervalos de >=1h.
4. Se gate falhar: `UPDATE ... SET enabled=false;` (rollback instantaneo).

## Auditoria

Cada decisao escreve em `shared.outbox`:
```json
{"event_type": "canary_eval", "flag": "X", "in_canary": true, "decision_id": 123}
```
Permite reproduzir grupos depois.
