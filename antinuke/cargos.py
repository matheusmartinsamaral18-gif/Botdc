"""Anti-Nuke: criação, exclusão e edição de cargos."""
import time

import discord

from config import bot
from core.auditoria import pegar_executor
from core.permissoes import is_protegido
from core.logs import enviar_log
from core.raid_estado import get_raid, registrou
from backup.armazenamento import (
    carregar_backup_temp,
    salvar_backup_temp,
    snapshot_cargo,
)
from antinuke.punicao import punir, agendar_recuperacao


@bot.listen("on_guild_role_create")
async def on_guild_role_create(role):
    guild = role.guild
    estado = get_raid(guild.id)

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.role_create,
        role.id
    )

    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        if estado["ativo"]:
            estado["ultimo_ataque"] = time.time()
            agendar_recuperacao(guild)

        elif registrou("cargo_criar", executor, 2, 3):
            await punir(
                guild,
                executor,
                "Criou 2 cargos em 3 segundos"
            )

        return

    if executor and is_protegido(guild, executor):
        try:
            dados = carregar_backup_temp(guild.id)

            if not any(x.get("id") == role.id for x in dados["cargos"]):
                dados["cargos"].append(snapshot_cargo(role))
                salvar_backup_temp(guild.id, dados)

        except Exception as erro:
            print(f"Erro atualizando TEMP de cargo: {erro}")


@bot.listen("on_guild_role_delete")
async def on_guild_role_delete(role):
    guild = role.guild
    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.role_delete,
        role.id
    )

    estado = get_raid(guild.id)
    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        if estado["ativo"] or registrou("cargo_del", executor, 2, 3):
            estado["cargos_apagados"].append(role.name)
            await punir(
                guild,
                executor,
                "Deletou cargo / possível tentativa de nuke"
            )
            await enviar_log(
                guild,
                "🎭 Cargo excluído — restauração manual necessária",
                f"**Cargo:** {role.name} (`{role.id}`)\n"
                f"**Executor:** <@{executor}> (`{executor}`)\n"
                "**Ação:** invasor punido; nenhuma restauração automática foi executada.",
                cor=0xE74C3C
            )
        return

    if executor and is_protegido(guild, executor):
        try:
            dados = carregar_backup_temp(guild.id)
            dados["cargos"] = [
                x for x in dados["cargos"]
                if x.get("id") != role.id
            ]
            salvar_backup_temp(guild.id, dados)
        except Exception as erro:
            print(f"Erro removendo cargo do TEMP: {erro}")


@bot.listen("on_guild_role_update")
async def on_guild_role_update(antes, depois):
    mudou_permissoes = (
        antes.permissions.value != depois.permissions.value
    )

    if not mudou_permissoes:
        return

    executor = await pegar_executor(
        depois.guild,
        discord.AuditLogAction.role_update,
        depois.id
    )

    if executor and not is_protegido(depois.guild, executor):
        if (
            depois.permissions.administrator
            and not antes.permissions.administrator
        ):
            motivo = "Tentou dar ADM via cargo"
        else:
            motivo = "Alterou permissões de cargo"

        await enviar_log(
            depois.guild,
            "⚠️ Alteração de permissões de cargo",
            f"**Por:** <@{executor}> (`{executor}`)\n"
            f"**Cargo:** {depois.name}\n"
            f"**Ação:** {motivo}",
            cor=0xFFA500
        )

        await punir(depois.guild, executor, motivo)


async def setup(bot):
    pass
