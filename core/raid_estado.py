"""Estado compartilhado da raid (usado pelo anti-nuke e pelo backup)."""
import time
from collections import defaultdict

from config import JANELA_RAID

raid_state = {}
ja_banidos = {}
acoes = defaultdict(list)
canais_pendentes_por_executor = defaultdict(set)


def novo_estado_raid():
    return {
        "ativo": False,
        "raider_id": None,
        "raider_nome": "Desconhecido",
        "canais_apagados_ids": set(),
        "cargos_apagados": [],
        "timer": None,
        "ultimo_ataque": 0,
        "canais_raid_criados": set(),
        "canais_criados_pelo_bot": set(),
        "qtd_ataques": 0,
        "restaurando": False
    }


def get_raid(guild_id):
    if guild_id not in raid_state:
        raid_state[guild_id] = novo_estado_raid()

    return raid_state[guild_id]


def teve_raid_recente(guild_id, minutos=30):
    estado = get_raid(guild_id)

    if estado["ativo"]:
        return True

    if estado["ultimo_ataque"] == 0:
        return False

    return (
        time.time() - estado["ultimo_ataque"]
    ) < minutos * 60


def registrou(tipo, user_id, limite=2, janela=JANELA_RAID):
    agora = time.time()
    chave = (tipo, user_id)

    acoes[chave] = [
        t for t in acoes[chave]
        if agora - t < janela
    ]

    acoes[chave].append(agora)

    return len(acoes[chave]) >= limite
