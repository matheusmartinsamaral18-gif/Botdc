"""Dados dos tickets: contador, tópico do canal, estado salvo e quem é da equipe."""
import os
import json
import asyncio
from collections import defaultdict

from config import bot, ADM_CONFIANCA

# Locks para evitar dois tickets com o mesmo número.
locks_tickets = defaultdict(asyncio.Lock)


# ---------- contador ----------

def arquivo_contador_ticket(guild_id):
    return f"contador_tickets_{guild_id}.json"


def carregar_contador_ticket(guild_id):
    path = arquivo_contador_ticket(guild_id)

    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return int(dados.get("contador", 0))
    except Exception as erro:
        print(f"Erro lendo contador de tickets: {erro}")

    return 0


def salvar_contador_ticket(guild_id, numero):
    path = arquivo_contador_ticket(guild_id)
    temporario = path + ".tmp"

    try:
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump({"contador": numero}, f)

        os.replace(temporario, path)
        return True

    except Exception as erro:
        print(f"Erro salvando contador de tickets: {erro}")
        return False


async def proximo_numero_ticket(guild_id):
    async with locks_tickets[guild_id]:
        numero = carregar_contador_ticket(guild_id) + 1
        salvar_contador_ticket(guild_id, numero)
        return numero


# ---------- dados fixos (tópico do canal) ----------

def _ler_dados_topic(canal):
    """
    Lê os dados do ticket pelo topic.
    Também aceita o formato antigo ticket_owner:ID.
    """

    topic = getattr(canal, "topic", None) or ""

    dados = {
        "owner_id": None,
        "numero": None,
        "aberto_em": None,
        "alertado": False,
        "respondido": False,
        "assumido_por": None,
        "ultima_atividade": None,
        "ultimo_alerta_msg": None,
        "msg_controle_id": None
    }

    if not topic:
        return dados

    partes = topic.split("|")

    for parte in partes:
        if ":" not in parte:
            continue

        chave, valor = parte.split(":", 1)

        try:
            if chave == "ticket_owner":
                dados["owner_id"] = int(valor)

            elif chave == "ticket_numero":
                dados["numero"] = int(valor)

            elif chave == "ticket_aberto":
                dados["aberto_em"] = int(valor)

            elif chave == "ticket_alertado":
                dados["alertado"] = valor == "1"

            elif chave == "ticket_respondido":
                dados["respondido"] = valor == "1"

            elif chave == "ticket_assumido_por":
                dados["assumido_por"] = int(valor) if valor not in ("", "None", "0") else None

            elif chave == "ticket_ultima_atividade":
                dados["ultima_atividade"] = int(valor)

            elif chave == "ticket_ultimo_alerta_msg":
                dados["ultimo_alerta_msg"] = valor or None

        except (ValueError, TypeError):
            pass

    return dados


# ---------- estado dinâmico (arquivo + memória) ----------
# O Discord limita muito a edição de canais; por isso o que muda
# (assumido, atividade, alertas...) fica em arquivo, é instantâneo.

ARQUIVO_ESTADO_TICKETS = "estado_tickets.json"
CAMPOS_ESTADO_TICKET = (
    "alertado",
    "respondido",
    "assumido_por",
    "ultima_atividade",
    "ultimo_alerta_msg",
    "msg_controle_id"
)
estado_tickets = {}


def _carregar_estado_tickets():
    global estado_tickets

    try:
        if os.path.exists(ARQUIVO_ESTADO_TICKETS):
            with open(ARQUIVO_ESTADO_TICKETS, "r", encoding="utf-8") as f:
                dados = json.load(f)

            if isinstance(dados, dict):
                estado_tickets = dados

    except Exception as erro:
        print(f"Erro lendo estado dos tickets: {erro}")


def _salvar_estado_tickets():
    temporario = ARQUIVO_ESTADO_TICKETS + ".tmp"

    try:
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(estado_tickets, f, ensure_ascii=False)

        os.replace(temporario, ARQUIVO_ESTADO_TICKETS)
        return True

    except Exception as erro:
        print(f"Erro salvando estado dos tickets: {erro}")
        return False


def limpar_estado_tickets_orfaos():
    """Remove do arquivo o estado de tickets cujo canal não existe mais."""

    if not bot.guilds:
        return

    existentes = {
        str(canal.id)
        for guild in bot.guilds
        for canal in guild.channels
    }

    orfaos = [k for k in estado_tickets if k not in existentes]

    if orfaos:
        for chave in orfaos:
            estado_tickets.pop(chave, None)

        _salvar_estado_tickets()


_carregar_estado_tickets()


def ler_dados_ticket(canal):
    """Dados fixos vêm do tópico; dados que mudam vêm do estado salvo."""

    dados = _ler_dados_topic(canal)

    if dados["owner_id"]:
        extra = estado_tickets.get(str(canal.id))

        if extra:
            for campo in CAMPOS_ESTADO_TICKET:
                if campo in extra:
                    dados[campo] = extra[campo]

    return dados


async def atualizar_dados_ticket(canal, **alteracoes):
    try:
        item = estado_tickets.setdefault(str(canal.id), {})

        for chave, valor in alteracoes.items():
            if chave in CAMPOS_ESTADO_TICKET:
                item[chave] = valor

        return _salvar_estado_tickets()

    except Exception as erro:
        print(f"Erro atualizando dados do ticket: {erro}")
        return False


# ---------- equipe ----------

def eh_responsavel_ticket(guild, membro):
    if guild is None or membro is None:
        return False

    if membro.id == guild.owner_id:
        return True

    if membro.id in ADM_CONFIANCA:
        return True

    permissoes = membro.guild_permissions

    if permissoes.administrator or permissoes.manage_channels:
        return True

    return False


def obter_responsaveis_ticket(guild):
    responsaveis = {}

    dono = guild.get_member(guild.owner_id)

    if dono:
        responsaveis[dono.id] = dono

    for membro in guild.members:
        if eh_responsavel_ticket(guild, membro):
            responsaveis[membro.id] = membro

    for user_id in ADM_CONFIANCA:
        try:
            membro = guild.get_member(user_id)

            if membro:
                responsaveis[membro.id] = membro
        except Exception:
            pass

    return list(responsaveis.values())
