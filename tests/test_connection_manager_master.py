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


def test_grace_period_nao_promove_conexao_sem_register():
    """Incidente 04/08: dashboard (sem REGISTER, device 'unknown') NÃO pode ser
    promovido pelo grace period; a escuta registrada deve ser a promovida."""

    async def main():
        cm = ConnectionManager()
        cm.MASTER_GRACE_PERIOD = 0.05
        # Escuta assume MASTER
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-escuta")
        # Dashboard passivo conecta DEPOIS (mais recente no LIFO) e nunca registra
        dash = await cm.connect(FakeWS(), device_id=None)
        # Outra escuta registrada, mais antiga que o dashboard
        await asyncio.sleep(0)
        # MASTER cai; grace expira e promove
        await cm.disconnect(c1)
        await asyncio.sleep(0.2)
        return cm, dash

    cm, dash = _run(main())
    assert cm.master_id is None, "dashboard 'unknown' não pode virar MASTER"
    assert cm.get_role(dash) == "slave"


def test_grace_period_promove_registrado_ignorando_dashboard_mais_recente():
    async def main():
        cm = ConnectionManager()
        cm.MASTER_GRACE_PERIOD = 0.05
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-escuta-1")
        c2 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c2, "dev-escuta-2")
        dash = await cm.connect(FakeWS(), device_id=None)  # mais recente, sem register
        await cm.disconnect(c1)
        await asyncio.sleep(0.2)
        return cm, c2, dash

    cm, c2, dash = _run(main())
    assert cm.master_id == c2, "a escuta registrada (não o dashboard) deve ser promovida"
    assert cm.get_role(dash) == "slave"


def test_register_destrona_master_passivo_sem_register():
    """Incidente 04/08 (produção): um MASTER passivo ('unknown') não pode
    bloquear a escuta que envia REGISTER — ela deve destronar e assumir."""

    async def main():
        cm = ConnectionManager()
        # Dashboard já é MASTER (estado corrompido pré-fix)
        dash = await cm.connect(FakeWS(), device_id=None)
        cm.master_id = dash
        cm.connections[dash].role = "master"
        # Escuta conecta e registra
        esc = await cm.connect(FakeWS(), device_id=None)
        assert cm.get_role(esc) == "slave"
        await cm.update_device_id(esc, "dev-escuta")
        return cm, dash, esc

    cm, dash, esc = _run(main())
    assert cm.master_id == esc, "escuta registrada deve destronar o master passivo"
    assert cm.get_role(esc) == "master"
    assert cm.get_role(dash) == "slave"


def test_register_nao_destrona_master_registrado():
    """Proteção do master real continua: device registrado NÃO destrona outro registrado."""

    async def main():
        cm = ConnectionManager()
        c1 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c1, "dev-escuta-1")
        c2 = await cm.connect(FakeWS(), device_id=None)
        await cm.update_device_id(c2, "dev-escuta-2")
        return cm, c1, c2

    cm, c1, c2 = _run(main())
    assert cm.master_id == c1, "master registrado permanece protegido"
    assert cm.get_role(c2) == "slave"
