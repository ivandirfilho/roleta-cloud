"""Workers para Roleta Cloud — processos auxiliares fora do app principal.

Cada worker neste pacote roda como container/processo separado.

- cdc_worker: consome `shared.outbox` no PG e replica em `cw|ccw.spins_vectors`.
"""
