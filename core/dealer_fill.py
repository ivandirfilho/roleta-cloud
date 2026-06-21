"""Vision (auditoria_pos_foto 21/06) — fill-forward do dealer, lógica PURA.

O dealer é estável por vários giros (um turno dura ~20-30min). Quando um giro
chega sem dealer (DOM não casou e a foto/OCR ainda não aterrissou), propaga-se o
ÚLTIMO dealer real conhecido da MESMA sessão. Corta automaticamente na troca: um
dealer real novo substitui o anterior; uma sessão nova invalida o estado.

Esta é a lógica PURA (sem estado, sem I/O), testável isoladamente. O estado por
sessão vive no MessageHandler (server/message_handler.py), que chama estas
funções. É METADATA — nunca toca nenhuma decisão de aposta.

Auditoria: auditoria_pos_foto_21_junho.md §7.2 (maior ROI de cobertura).
"""
from __future__ import annotations

from typing import Optional

UNKNOWN = "unknown"


def is_real_dealer(dealer: Optional[str]) -> bool:
    """True se `dealer` é um nome real (não vazio, não 'unknown')."""
    return bool(dealer) and str(dealer).strip().lower() != UNKNOWN


def resolve_dealer(
    raw_dealer: Optional[str],
    last_known: Optional[str],
    enabled: bool,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve o dealer de um giro e atualiza o 'último conhecido'.

    Args:
        raw_dealer: dealer que veio no giro (DOM/visão), pode ser None/'unknown'.
        last_known: último dealer REAL visto nesta sessão (ou None).
        enabled: flag SDA_DEALER_FILL_FORWARD.

    Returns:
        (dealer_a_usar, novo_last_known)
        - Se `raw_dealer` é real: usa-o e ele vira o novo last_known (corta na troca).
        - Se `raw_dealer` não é real e enabled e há last_known: propaga last_known.
        - Senão: devolve `raw_dealer` como veio (None/'unknown'), last_known intacto.

    A função é idempotente e nunca levanta.
    """
    if is_real_dealer(raw_dealer):
        canonical = str(raw_dealer).strip()
        return canonical, canonical
    if enabled and is_real_dealer(last_known):
        return last_known, last_known
    return raw_dealer, last_known
