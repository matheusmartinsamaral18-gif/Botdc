"""Canal exclusivo do dono, canal de logs e anti-spam."""
import time
from collections import defaultdict
from datetime import timedelta

import discord

from config import bot, LOGS_CHANNEL_ID, SOLO_DONO_CHANNEL_ID
from core.permissoes import is_protegido
from core.logs import enviar_log
from backup.mapa_canais import resolver_canal_configurado

msgs = defaultdict(list)


@bot.listen("on_message")
async def protecao_mensagens(message):
    if message.author.bot or message.guild is None:
        return

    # Comandos "!" e ".f" são tratados por outros módulos.
    if message.content.startswith("!") or message.content.strip().lower() == ".f":
        return

    # ----- canal exclusivo do dono -----
    canal_dono = resolver_canal_configurado(
        message.guild,
        SOLO_DONO_CHANNEL_ID
    )

    if canal_dono and message.channel.id == canal_dono.id:
        if not is_protegido(message.guild, message.author.id):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

        return

    # ----- canal de logs -----
    canal_logs = resolver_canal_configurado(
        message.guild,
        LOGS_CHANNEL_ID
    )

    if canal_logs and message.channel.id == canal_logs.id:
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        return

    # ----- anti-spam -----
    agora = time.time()

    chave = (
        message.guild.id,
        message.author.id
    )

    msgs[chave] = [
        t for t in msgs[chave]
        if agora - t < 3
    ]

    msgs[chave].append(agora)

    if len(msgs[chave]) >= 5:
        msgs[chave].clear()

        try:
            await message.author.timeout(
                timedelta(minutes=10),
                reason="Anti-Spam: 5 mensagens em 3 segundos"
            )

            await enviar_log(
                message.guild,
                "💬 Anti-Spam — Mute",
                f"**Usuário:** {message.author.mention} "
                f"(`{message.author.id}`)\n"
                f"**Canal:** {message.channel.mention}\n"
                "**Ação:** Timeout por 10 minutos",
                cor=0xFFA500
            )

        except discord.Forbidden:
            print(
                f"Sem permissão para aplicar timeout "
                f"em {message.author}."
            )

        except Exception as erro:
            print(f"Erro no anti-spam: {erro}")


async def setup(bot):
    pass
