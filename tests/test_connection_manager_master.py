"""Regressão do deadlock de MASTER no ConnectionManager (incidente 13/06).

Cenário do incidente: o MASTER (escuta) desconecta, o grace period de 10s
expira sem reconexão e, quando a escuta volta horas depois e envia REGISTER,
`update_device_id` não conseguia mais promovê-la a MASTER — ficava presa como
SLAVE para sempre. Como spins de SLAVE são descartados, o fluxo de decisões
parava (servidor "ligado" mas sem regiões/resultados).
"""
import asyncio
import time

from server.connection_manager import ConnectionManager


class FakeWS:
    """WebSocket mínimo: registra mensagens enviadas, no-op no close."""

    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)

    async def close(self, *args, **kwargs):
        pass


def _run(coro):
    return asyncio.run(coro)


def _cancel_grace(cm):
    task = cm._grace_period_task
    if task and not task.done():
        task.cancel()


def test_primeiro_dispositivo_vira_master():
    async def main():
        cm = ConnectionManager()
        conn = await cm.connect(FakeWS(), device_id=None)  # sem device_id => slave
        assert cm.get_role(conn) == "slave"
        await cm.update_device_id(conn, "dev-x")
        return cm, conn

    cm, conn = _run(main())
    assert cm.master_id == conn
    assert cm.get_role(conn) == "master"


def test_master_readquire_apos_grace_expirado():
    """O bug central: MASTER que volta após o grace period DEVE reassumir."""

    async def main():
        cm = ConnectionManager()
        # MASTER original assume e depois desconecta
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-x")
        assert cm.master_id == c1
        await cm.disconnect(c1)
        _cancel_grace(cm)
        # Simula grace period EXPIRADO (escuta voltou horas depois)
        cm.master_disconnect_time = time.time() - (cm.MASTER_GRACE_PERIOD + 100)
        assert cm.master_id is None and cm.last_master_device_id == "dev-x"
        # Escuta reconecta (sem device_id) e registra o mesmo device
        c2 = await cm.connect(FakeWS(), device_id=None)
        assert cm.get_role(c2) == "slave"
        await cm.update_device_id(c2, "dev-x")
        return cm, c2

    cm, c2 = _run(main())
    assert cm.master_id == c2, "escuta deveria reassumir MASTER após grace expirado"
    assert cm.get_role(c2) == "master"


def test_dispositivo_novo_apos_grace_expirado_vira_master():
    """Mesmo um device diferente assume se ninguém é MASTER e o grace expirou."""

    async def main():
        cm = ConnectionManager()
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-x")
        await cm.disconnect(c1)
        _cancel_grace(cm)
        cm.master_disconnect_time = time.time() - (cm.MASTER_GRACE_PERIOD + 100)
        c2 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c2, "dev-y")
        return cm, c2

    cm, c2 = _run(main())
    assert cm.master_id == c2
    assert cm.get_role(c2) == "master"


def test_mesmo_master_restaura_dentro_do_grace():
    async def main():
        cm = ConnectionManager()
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-x")
        await cm.disconnect(c1)
        _cancel_grace(cm)
        # dentro do grace (recém-desconectado)
        c2 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c2, "dev-x")
        _cancel_grace(cm)
        return cm, c2

    cm, c2 = _run(main())
    assert cm.master_id == c2
    assert cm.get_role(c2) == "master"


def test_outro_device_aguarda_durante_grace():
    """Device diferente DENTRO do grace permanece SLAVE (protege o MASTER original)."""

    async def main():
        cm = ConnectionManager()
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-x")
        await cm.disconnect(c1)
        _cancel_grace(cm)  # impede a promoção automática do grace para isolar o caso
        c2 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c2, "dev-y")
        return cm, c2

    cm, c2 = _run(main())
    assert cm.master_id is None, "ninguém deve assumir MASTER durante o grace de outro device"
    assert cm.get_role(c2) == "slave"
