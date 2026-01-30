# Roleta Cloud - Connection Manager

import asyncio
import json
import time
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set, List
from websockets.server import WebSocketServerProtocol
import uuid

logger = logging.getLogger(__name__)

@dataclass
class ConnectionInfo:
    """Informações de uma conexão WebSocket."""
    id: str
    websocket: WebSocketServerProtocol
    role: str  # "master" | "slave"
    connected_at: float  # timestamp
    last_activity: float = 0.0


class ConnectionManager:
    """Gerencia conexões WebSocket e roles (Master/Slave)."""

    def __init__(self):
        self.connections: Dict[str, ConnectionInfo] = {}
        self.master_id: Optional[str] = None
        self.master_lock = asyncio.Lock()
        self.master_disconnect_time: Optional[float] = None
        self.MASTER_GRACE_PERIOD = 5  # Segundos

    @property
    def active_connections_set(self) -> Set[WebSocketServerProtocol]:
        """Retorna set de websockets para compatibilidade."""
        return {c.websocket for c in self.connections.values()}

    async def connect(self, websocket: WebSocketServerProtocol) -> str:
        """
        Registra uma nova conexão e atribui role.
        Retorna o ID da conexão.
        """
        conn_id = str(uuid.uuid4())[:8]

        async with self.master_lock:
            # Nova conexão SEMPRE vira MASTER
            if self.master_id and self.master_id in self.connections:
                # Rebaixar MASTER atual para SLAVE
                old_master = self.connections[self.master_id]
                old_master.role = "slave"
                try:
                    await old_master.websocket.send(json.dumps({
                        "type": "role_changed",
                        "role": "slave",
                        "reason": "Novo dispositivo conectou"
                    }))
                    logger.info(f"👑→📱 {self.master_id} rebaixado para SLAVE")
                except:
                    pass  # Conexão pode ter fechado

            # Nova conexão é MASTER
            self.master_id = conn_id
            self.master_disconnect_time = None  # Cancelar grace period se houver

            self.connections[conn_id] = ConnectionInfo(
                id=conn_id,
                websocket=websocket,
                role="master",
                connected_at=time.time(),
                last_activity=time.time()
            )

        # Notificar nova conexão sobre seu role
        await websocket.send(json.dumps({
            "type": "role_assigned",
            "role": "master",
            "connection_id": conn_id
        }))
        logger.info(f"👑 {conn_id} atribuído como MASTER")

        return conn_id

    async def disconnect(self, conn_id: str):
        """
        Remove uma conexão e gerencia promoção de MASTER se necessário.
        """
        async with self.master_lock:
            if conn_id in self.connections:
                del self.connections[conn_id]

            if conn_id == self.master_id:
                logger.info(f"👑 MASTER {conn_id} desconectou - iniciando grace period de {self.MASTER_GRACE_PERIOD}s")
                self.master_disconnect_time = time.time()
                self.master_id = None

        # Grace period (fora do lock)
        if self.master_disconnect_time:
            await self.handle_grace_period()

    async def handle_grace_period(self):
        """Aguarda grace period e promove novo MASTER se necessário."""
        await asyncio.sleep(self.MASTER_GRACE_PERIOD)

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
                    except:
                        pass

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
        """Envia mensagem para todas as conexões."""
        disconnected = set()
        for conn in self.connections.values():
            try:
                await conn.websocket.send(message)
            except:
                disconnected.add(conn.id)

        if exclude_disconnected:
            for conn_id in disconnected:
                await self.disconnect(conn_id)

connection_manager = ConnectionManager()
