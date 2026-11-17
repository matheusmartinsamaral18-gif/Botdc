"""Anti-Nuke: banimentos e expulsões em massa."""
import discord

from config import bot
from core.auditoria import pegar_executor
from core.raid_estado import registrou
from antinuke.punicao import punir


@bot.listen("on_member_ban")
async def on_member_ban(guild, user):
    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.ban,
        user.id
    )

    if executor and registrou("ban", executor, 2, 3):
        await punir(
            guild,
            executor,
            "Baniu 2 membros em 3 segundos"
        )


@bot.listen("on_member_remove")
async def on_member_remove(member):
    executor = await pegar_executor(
        member.guild,
        discord.AuditLogAction.kick,
        member.id
    )

    if executor and registrou("kick", executor, 2, 3):
        await punir(
            member.guild,
            executor,
            "Expulsou 2 membros em 3 segundos"
        )


async def setup(bot):
    pass
