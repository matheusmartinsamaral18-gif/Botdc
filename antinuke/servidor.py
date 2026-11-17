"""Anti-Nuke: webhooks, emojis, stickers, limpeza em massa e nome/ícone."""
import discord

from config import bot
from core.auditoria import pegar_executor
from core.permissoes import is_protegido
from core.logs import enviar_log
from core.raid_estado import registrou
from antinuke.punicao import punir


@bot.listen("on_webhooks_update")
async def on_webhooks_update(channel):
    guild = channel.guild

    # Ignora o evento disparado pela criação de webhook feita pelo próprio bot.
    try:
        webhooks_atuais = await channel.webhooks()
        agora = discord.utils.utcnow()
        if any(
            webhook.user and bot.user and webhook.user.id == bot.user.id
            and (agora - webhook.created_at).total_seconds() < 20
            for webhook in webhooks_atuais
        ):
            return
    except Exception:
        pass

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.webhook_create
    )

    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        try:
            webhooks = await channel.webhooks()

            for webhook in webhooks:
                if webhook.user and webhook.user.id == executor:
                    await webhook.delete(
                        reason="Anti-Nuke: webhook suspeito"
                    )

        except Exception as erro:
            print(f"Erro removendo webhook: {erro}")

        await punir(
            guild,
            executor,
            "Criou webhook suspeito"
        )


@bot.listen("on_guild_emojis_update")
async def on_guild_emojis_update(guild, antes, depois):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild,
            discord.AuditLogAction.emoji_delete
        )

        if (
            executor
            and not is_protegido(guild, executor)
            and registrou("emoji", executor, 2, 3)
        ):
            await punir(
                guild,
                executor,
                "Deletou emojis em massa"
            )


@bot.listen("on_guild_stickers_update")
async def on_guild_stickers_update(guild, antes, depois):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild,
            discord.AuditLogAction.sticker_delete
        )

        if executor and not is_protegido(guild, executor):
            await punir(
                guild,
                executor,
                "Deletou sticker"
            )


@bot.listen("on_raw_bulk_message_delete")
async def on_raw_bulk_message_delete(payload):
    if payload.guild_id is None:
        return

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.message_bulk_delete
    )

    if executor and not is_protegido(guild, executor):
        await punir(
            guild,
            executor,
            "Apagou mensagens em massa"
        )


@bot.listen("on_guild_update")
async def on_guild_update(antes, depois):
    mudou_nome = antes.name != depois.name
    mudou_icone = antes.icon != depois.icon

    if not mudou_nome and not mudou_icone:
        return

    executor = await pegar_executor(
        depois,
        discord.AuditLogAction.guild_update
    )

    if not executor or is_protegido(depois, executor):
        return

    alteracoes = []
    if mudou_nome:
        alteracoes.append(f"nome: `{antes.name}` → `{depois.name}`")
    if mudou_icone:
        alteracoes.append("ícone do servidor")

    await enviar_log(
        depois,
        "🏷️ Nome/ícone do servidor alterado",
        f"**Executor:** <@{executor}> (`{executor}`)\n"
        f"**Alterações:** {', '.join(alteracoes)}\n"
        "**Ação:** invasor punido. A reversão é manual.",
        cor=0xE74C3C
    )

    await punir(
        depois,
        executor,
        "Tentou mudar nome/ícone do servidor"
    )


async def setup(bot):
    pass
