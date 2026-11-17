"""Backup contínuo das últimas mensagens de cada canal (com anexos)."""
import os
import re
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import tasks

from config import bot, MSG_POR_CANAL, INTERVALO_BACKUP_MSGS_MIN
from backup.armazenamento import carregar_backup, salvar_backup_bom

locks_backup_mensagens = defaultdict(asyncio.Lock)


def _nome_arquivo_seguro(nome):
    nome = os.path.basename(str(nome or "anexo"))
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", nome)
    return nome[:120] or "anexo"


async def _serializar_mensagem(mensagem):
    anexos = []
    pasta = os.path.join(
        "backup_anexos",
        str(mensagem.guild.id),
        str(mensagem.channel.id)
    )
    os.makedirs(pasta, exist_ok=True)

    for indice, anexo in enumerate(mensagem.attachments[:10]):
        nome_seguro = _nome_arquivo_seguro(anexo.filename)
        nome_local = f"{mensagem.id}_{indice}_{nome_seguro}"
        caminho = os.path.join(pasta, nome_local)

        # O arquivo só é baixado uma vez; os próximos ciclos reutilizam a cópia.
        limite_download = min(
            int(getattr(mensagem.guild, "filesize_limit", 25 * 1024 * 1024)),
            25 * 1024 * 1024
        )
        if not os.path.exists(caminho) and anexo.size <= limite_download:
            try:
                conteudo_arquivo = await anexo.read()
                with open(caminho, "wb") as arquivo_local:
                    arquivo_local.write(conteudo_arquivo)
            except Exception as erro:
                print(f"Não foi possível salvar anexo {anexo.filename}: {erro}")
                caminho = None
        elif not os.path.exists(caminho):
            caminho = None

        anexos.append({
            "filename": anexo.filename,
            "url": anexo.url,
            "content_type": anexo.content_type,
            "size": anexo.size,
            "local_path": caminho
        })

    embeds = []
    for embed in mensagem.embeds:
        try:
            embeds.append(embed.to_dict())
        except Exception:
            pass

    avatar = None
    try:
        avatar = mensagem.author.display_avatar.url
    except Exception:
        pass

    return {
        "id": mensagem.id,
        "author_id": mensagem.author.id,
        "author_name": str(mensagem.author),
        "author_display_name": getattr(mensagem.author, "display_name", str(mensagem.author)),
        "author_avatar": avatar,
        "author_is_bot": bool(mensagem.author.bot),
        "content": mensagem.content or "",
        "created_at": mensagem.created_at.isoformat(),
        "attachments": anexos,
        "embeds": embeds
    }


async def capturar_mensagens_canal(canal):
    if not isinstance(canal, discord.TextChannel):
        return []

    mensagens = []
    try:
        async for mensagem in canal.history(limit=MSG_POR_CANAL):
            mensagens.append(await _serializar_mensagem(mensagem))
        mensagens.reverse()
    except discord.Forbidden:
        print(f"Sem permissão para ler histórico em #{canal.name}.")
        return None
    except discord.HTTPException as erro:
        print(f"Erro lendo mensagens de #{canal.name}: {erro}")
        return None

    return mensagens[-MSG_POR_CANAL:]


async def salvar_backup_mensagens_guild(guild):
    total = 0

    for canal in list(guild.text_channels):
        try:
            mensagens_novas = await capturar_mensagens_canal(canal)
            if mensagens_novas is None:
                continue

            async with locks_backup_mensagens[guild.id]:
                dados = carregar_backup(guild.id)
                historico = dados.setdefault("mensagens", {})
                anteriores = historico.get(str(canal.id), {}).get("messages", [])
                por_id = {
                    str(m.get("id")): m
                    for m in (anteriores + mensagens_novas)
                    if m.get("id") is not None
                }
                mensagens_consolidadas = sorted(
                    por_id.values(),
                    key=lambda m: m.get("created_at", "")
                )[-MSG_POR_CANAL:]

                historico[str(canal.id)] = {
                    "channel_id": canal.id,
                    "channel_name": canal.name,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "messages": mensagens_consolidadas
                }
                salvar_backup_bom(guild.id, dados)

            total += len(mensagens_consolidadas)
            await asyncio.sleep(0.15)
        except Exception as erro:
            print(f"Erro no backup de mensagens de #{canal.name}: {erro}")

    print(f"💬 Backup de mensagens atualizado: {guild.name} ({total} mensagens).")
    return total


@tasks.loop(minutes=INTERVALO_BACKUP_MSGS_MIN)
async def backup_mensagens_loop():
    for guild in bot.guilds:
        try:
            await salvar_backup_mensagens_guild(guild)
        except Exception as erro:
            print(f"Erro no backup periódico de mensagens em {guild.name}: {erro}")


@backup_mensagens_loop.before_loop
async def antes_backup_mensagens():
    await bot.wait_until_ready()


def obter_mensagens_backup(guild_id, canal_id):
    dados = carregar_backup(guild_id)
    item = dados.get("mensagens", {}).get(str(canal_id), {})
    mensagens = item.get("messages", []) if isinstance(item, dict) else []
    return mensagens[-MSG_POR_CANAL:]


async def salvar_mensagem_individual(mensagem):
    if (
        mensagem.guild is None
        or not isinstance(mensagem.channel, discord.TextChannel)
        or mensagem.webhook_id is not None
        or (bot.user and mensagem.author.id == bot.user.id)
    ):
        return

    nova = await _serializar_mensagem(mensagem)
    async with locks_backup_mensagens[mensagem.guild.id]:
        dados = carregar_backup(mensagem.guild.id)
        historico = dados.setdefault("mensagens", {})
        chave = str(mensagem.channel.id)
        item = historico.get(chave, {})
        anteriores = item.get("messages", []) if isinstance(item, dict) else []

        por_id = {
            str(m.get("id")): m
            for m in (anteriores + [nova])
            if m.get("id") is not None
        }
        mensagens = sorted(
            por_id.values(),
            key=lambda m: m.get("created_at", "")
        )[-MSG_POR_CANAL:]

        historico[chave] = {
            "channel_id": mensagem.channel.id,
            "channel_name": mensagem.channel.name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "messages": mensagens
        }
        salvar_backup_bom(mensagem.guild.id, dados)


@bot.listen("on_message")
async def backup_mensagem_listener(message):
    try:
        await salvar_mensagem_individual(message)
    except Exception as erro:
        print(f"Erro salvando mensagem individual: {erro}")


async def setup(bot):
    if not backup_mensagens_loop.is_running():
        backup_mensagens_loop.start()
