# Roleta Cloud - Connection Manager

import asyncio
import json
import time
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set
from websockets.server import WebSocketServerProtocol
import uuid

logger = logging.getLogger(__name__)

@dataclass
class ConnectionInfo:
    """Informações de uma conexão WebSocket."""
    id: str                    # connection_id (efêmero)
    device_id: str             # 🆕 Persistente no cliente
    websocket: WebSocketServerProtocol
    role: str                  # "master" | "slave"
    connected_at: float        # timestamp
    last_activity: float = 0.0


class ConnectionManager:
    """Gerencia conexões WebSocket e roles (Master/Slave)."""

    def __init__(self):
        self.connections: Dict[str, ConnectionInfo] = {}
        self.master_id: Optional[str] = None
        self.master_device_id: Optional[str] = None       # 🆕 ID do dispositivo MASTER
        self.last_master_device_id: Optional[str] = None  # 🆕 Para reconexão no grace period
        self.master_lock = asyncio.Lock()
        self.master_disconnect_time: Optional[float] = None
        self._grace_period_task: Optional[asyncio.Task] = None  # 🔧 BUG-007: cancelável
        self.MASTER_GRACE_PERIOD = 10  # 🆕 Aumentado para 10s para estabilidade
        self.MAX_CONNECTIONS = 50  # Limite de conexões simultâneas

    @property
    def active_connections_set(self) -> Set[WebSocketServerProtocol]:
        """Retorna set de websockets para compatibilidade."""
        return {c.websocket for c in self.connections.values()}

    async def connect(self, websocket: WebSocketServerProtocol, device_id: str = None) -> str:
        """
        Registra uma nova conexão e atribui role com lógica de reconexão inteligente.
        Retorna o ID da conexão.
        """
        conn_id = str(uuid.uuid4())[:8]

        async with self.master_lock:
            # Verificar limite de conexões
            if len(self.connections) >= self.MAX_CONNECTIONS:
                logger.warning(f"⚠️ Limite de conexões atingido ({self.MAX_CONNECTIONS}). Rejeitando {device_id or 'unknown'}.")
                await websocket.close(1013, "Servidor lotado")
                return ""

            # CASO 1: Reconexão do MASTER (mesmo device_id dentro do grace period)
            is_master_reconnecting = (
                device_id and 
                device_id == self.last_master_device_id and
                self.master_disconnect_time is not None and
                (time.time() - self.master_disconnect_time) < self.MASTER_GRACE_PERIOD
            )

            if is_master_reconnecting:
                # Restaurar como MASTER
                self.master_id = conn_id
                self.master_device_id = device_id
                self.master_disconnect_time = None
                # 🔧 BUG-007: cancelar grace period pendente
                if self._grace_period_task and not self._grace_period_task.done():
                    self._grace_period_task.cancel()
                    self._grace_period_task = None
                role = "master"
                logger.info(f"👑 MASTER {device_id} reconectou - role restaurado")
            
            # CASO 2: Novo dispositivo conectando (ou device diferente do MASTER atual)
            # Se for um novo dispositivo ou o MASTER atual for diferente
            elif device_id and device_id not in self._get_active_device_ids():
                # Proteção do Master Atual: Novas conexões entram como SLAVE se já existe master
                if self.master_id and self.master_id in self.connections:
                     role = "slave"
                     logger.info(f"🛡️ Master ativo protegido. {device_id} entra como SLAVE.")
                else:
                     role = "master"
                     self.master_id = conn_id
                     self.master_device_id = device_id
                     self.master_disconnect_time = None
                     # 🔧 TASK-01: cancelar grace period pendente para evitar duplo master
                     if self._grace_period_task and not self._grace_period_task.done():
                         self._grace_period_task.cancel()
                         self._grace_period_task = None
                     logger.info(f"👑 Novo MASTER atribuído (sem master prévio): {device_id}")
            
            # CASO 3: Dispositivo que já é SLAVE reconectando ou sem device_id
            else:
                role = "slave"
                logger.info(f"📱 Conexão SLAVE: {device_id or 'sem device_id'}")

            # Registrar a conexão
            self.connections[conn_id] = ConnectionInfo(
                id=conn_id,
                device_id=device_id or "unknown",
                websocket=websocket,
                role=role,
                connected_at=time.time(),
                last_activity=time.time()
            )

        # Notificar nova conexão sobre seu role
        await websocket.send(json.dumps({
            "type": "role_assigned",
            "role": role,
            "connection_id": conn_id
        }))

        return conn_id

    def _get_active_device_ids(self) -> Set[str]:
        """Retorna set de device_ids ativos (excluindo unknown)."""
        return {c.device_id for c in self.connections.values() if c.device_id != "unknown"}

    async def _demote_master(self, reason: str):
        """Rebaixa o MASTER atual para SLAVE."""
        if self.master_id and self.master_id in self.connections:
            old_master = self.connections[self.master_id]
            old_master.role = "slave"
            try:
                await old_master.websocket.send(json.dumps({
                    "type": "role_changed",
                    "role": "slave",
                    "reason": reason
                }))
                logger.info(f"👑→📱 {self.master_id} rebaixado para SLAVE: {reason}")
            except Exception as e:
                logger.warning(f"Erro ao notificar rebaixamento de {self.master_id}: {e}")

    async def disconnect(self, conn_id: str):
        """
        Remove uma conexão e gerencia promoção de MASTER se necessário.
        """
        async with self.master_lock:
            if conn_id not in self.connections:
                return

            info = self.connections[conn_id]
            del self.connections[conn_id]

            if conn_id == self.master_id:
                logger.info(f"👑 MASTER {info.device_id} ({conn_id}) desconectou - iniciando grace period de {self.MASTER_GRACE_PERIOD}s")
                self.master_disconnect_time = time.time()
                self.last_master_device_id = info.device_id
                self.master_id = None
                self.master_device_id = None

                # Grace period dentro do lock para evitar race condition
                if self._grace_period_task and not self._grace_period_task.done():
                    self._grace_period_task.cancel()
                self._grace_period_task = asyncio.create_task(self.handle_grace_period())

    async def handle_grace_period(self):
        """Aguarda grace period e promove novo MASTER se necessário."""
        try:
            await asyncio.sleep(self.MASTER_GRACE_PERIOD)
        except asyncio.CancelledError:
            logger.info("⏱️ Grace period cancelado — MASTER reconectou")
            return

        async with self.master_lock:
            # Verificar se ainda precisa promover (pode ter reconectado)
            if self.master_id is None and self.connections:
                # Promover último SLAVE (mais recente = LIFO)
                slaves = sorted(
                    self.connections.values(),
                    key=lambda c: c.connected_at,
                    reverse=True
                )

                if slaves:
                    new_master = slaves[0]
                    new_master.role = "master"
                    self.master_id = new_master.id
                    self.master_disconnect_time = None

                    try:
                        await new_master.websocket.send(json.dumps({
                            "type": "role_changed",
                            "role": "master",
                            "reason": "MASTER anterior desconectou"
                        }))
                        logger.info(f"📱→👑 {new_master.id} promovido a MASTER")
                    except Exception as e:
                        logger.warning(f"Erro ao notificar promoção de MASTER: {e}")

    async def force_master(self, conn_id: str):
        """Força uma conexão a virar MASTER."""
        async with self.master_lock:
            if conn_id not in self.connections:
                return
            
            # Rebaixar atual se houver e for diferente
            if self.master_id and self.master_id != conn_id:
                await self._demote_master("Outro dispositivo forçou MASTER")
            
            # Promover novo
            new_master = self.connections[conn_id]
            new_master.role = "master"
            self.master_id = conn_id
            self.master_device_id = new_master.device_id
            
            try:
                await new_master.websocket.send(json.dumps({
                    "type": "role_changed",
                    "role": "master",
                    "reason": "Você assumiu o controle"
                }))
                logger.info(f"🎯 {conn_id} forçou MASTER")
            except Exception as e:
                logger.error(f"Erro ao notificar promoção de {conn_id}: {e}")

    async def update_device_id(self, conn_id: str, device_id: str):
        """
        Atualiza o device_id de uma conexão existente e reavalia roles.
        Chamado quando mensagem 'register' é recebida.
        """
        async with self.master_lock:
            if conn_id not in self.connections:
                return

            info = self.connections[conn_id]
            info.device_id = device_id
            logger.info(f"📝 Device ID atualizado para {conn_id}: {device_id}")

            # Se ainda não tem MASTER, decidir se este registro assume o papel.
            if self.master_id is None:
                within_grace = (
                    self.master_disconnect_time is not None and
                    (time.time() - self.master_disconnect_time) < self.MASTER_GRACE_PERIOD
                )
                is_master_reconnecting = (
                    self.last_master_device_id and
                    device_id == self.last_master_device_id and
                    within_grace
                )

                # Outro dispositivo (≠ último MASTER) DENTRO do grace period: permanece
                # SLAVE para dar chance ao MASTER original reconectar. handle_grace_period
                # promove o SLAVE mais recente quando o grace expira.
                if within_grace and not is_master_reconnecting:
                    logger.info(
                        f"⏳ {device_id} aguarda grace period do MASTER anterior — permanece SLAVE"
                    )
                else:
                    # Assume MASTER quando: (a) é o MASTER reconectando no grace period,
                    # (b) nunca houve MASTER, ou (c) 🔧 BUGFIX: o grace period já expirou e
                    # ninguém é MASTER. Sem o caso (c), um MASTER que voltava após >10s
                    # (ex.: aba fechada por horas) ficava preso como SLAVE para sempre —
                    # deadlock que derrubava o fluxo de spins (incidente 13/06).
                    info.role = "master"
                    self.master_id = conn_id
                    self.master_device_id = device_id
                    self.master_disconnect_time = None
                    if self._grace_period_task and not self._grace_period_task.done():
                        self._grace_period_task.cancel()
                        self._grace_period_task = None

                    if is_master_reconnecting:
                        reason = "MASTER reconectou (grace period)"
                    elif not self.last_master_device_id:
                        reason = "Primeiro dispositivo registrado"
                    else:
                        reason = "MASTER assumido após grace period expirado"

                    try:
                        await info.websocket.send(json.dumps({
                            "type": "role_assigned",
                            "role": "master",
                            "reason": reason
                        }))
                    except Exception:
                        pass
                    logger.info(f"👑 Novo MASTER assumiu após registro: {device_id} ({reason})")

    def get_role(self, conn_id: str) -> str:
        """Retorna o role de uma conexão."""
        if conn_id in self.connections:
            return self.connections[conn_id].role
        return "unknown"

    def update_activity(self, conn_id: str):
        """Atualiza timestamp de última atividade."""
        if conn_id in self.connections:
            self.connections[conn_id].last_activity = time.time()

    async def broadcast(self, message: str, exclude_disconnected: bool = True):
        """Envia mensagem para todas as conexões em paralelo."""
        conns = list(self.connections.values())
        if not conns:
            return

        async def _safe_send(conn):
            try:
                await conn.websocket.send(message)
                return None
            except Exception:
                return conn.id

        results = await asyncio.gather(*[_safe_send(c) for c in conns], return_exceptions=True)
        disconnected = {r for r in results if isinstance(r, str)}

        if exclude_disconnected:
            for conn_id in disconnected:
                await self.disconnect(conn_id)

connection_manager = ConnectionManager()
