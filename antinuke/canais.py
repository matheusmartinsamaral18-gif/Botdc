"""Anti-Nuke: criação, exclusão e edição de canais."""
import time

import discord

from config import bot
from core.auditoria import pegar_executor
from core.permissoes import is_protegido
from core.logs import enviar_log
from core.raid_estado import get_raid, registrou, canais_pendentes_por_executor
from backup.armazenamento import (
    atualizar_canal_no_backup_temp,
    remover_canal_do_backup_temp,
)
from antinuke.punicao import punir, agendar_recuperacao


@bot.listen("on_guild_channel_create")
async def on_guild_channel_create(channel):
    guild = channel.guild
    estado = get_raid(guild.id)

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_create,
        channel.id
    )

    if estado["restaurando"]:
        if executor is None:
            return

        if bot.user and executor == bot.user.id:
            return

        if is_protegido(guild, executor):
            return

        estado["canais_raid_criados"].add(channel.id)
        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)
        return

    if estado["ativo"]:
        if executor is not None:
            if bot.user and executor == bot.user.id:
                return

            if is_protegido(guild, executor):
                return

            canais_pendentes_por_executor[
                (guild.id, executor)
            ].add(channel.id)

        estado["canais_raid_criados"].add(channel.id)
        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)

        if executor is not None:
            await punir(
                guild,
                executor,
                "Criou canal durante raid ativa"
            )

        return

    if executor and not is_protegido(guild, executor):
        canais_pendentes_por_executor[
            (guild.id, executor)
        ].add(channel.id)

        if registrou("canal_criar", executor, 2, 3):
            await punir(
                guild,
                executor,
                "Criou 2 canais em 3 segundos"
            )

        return

    if executor and is_protegido(guild, executor):
        try:
            atualizar_canal_no_backup_temp(guild.id, channel)
        except Exception as erro:
            print(f"Erro atualizando TEMP: {erro}")


@bot.listen("on_guild_channel_delete")
async def on_guild_channel_delete(channel):
    guild = channel.guild
    estado = get_raid(guild.id)

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_delete,
        channel.id
    )

    # Nunca recria canais automaticamente. Apenas registra e pune.
    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        if estado["ativo"] or registrou("canal_del", executor, 2, 3):
            estado["canais_apagados_ids"].add(channel.id)
            await punir(
                guild,
                executor,
                "Deletou canal / possível tentativa de nuke"
            )
            await enviar_log(
                guild,
                "🗑️ Canal excluído — restauração manual necessária",
                f"**Canal:** #{channel.name} (`{channel.id}`)\n"
                f"**Executor:** <@{executor}> (`{executor}`)\n"
                "**Ação:** invasor punido; nenhuma restauração automática foi executada.",
                cor=0xE74C3C
            )
        return

    # Alterações legítimas feitas por pessoas protegidas atualizam o backup TEMP.
    if executor and is_protegido(guild, executor):
        try:
            remover_canal_do_backup_temp(guild.id, channel.id)
        except Exception as erro:
            print(f"Erro removendo canal do TEMP: {erro}")


@bot.listen("on_guild_channel_update")
async def on_guild_channel_update(antes, depois):
    guild = depois.guild

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_update,
        depois.id
    )

    if executor and not is_protegido(guild, executor):
        if registrou("canal_update", executor, 2, 3):
            await punir(
                guild,
                executor,
                "Alterou 2 canais em 3 segundos"
            )

        if get_raid(guild.id)["ativo"]:
            agendar_recuperacao(guild)

        return

    if executor and is_protegido(guild, executor):
        try:
            atualizar_canal_no_backup_temp(guild.id, depois)
        except Exception as erro:
            print(f"Erro atualizando TEMP de canal: {erro}")


async def setup(bot):
    pass
