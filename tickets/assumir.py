"""Assumir ticket e atualização da mensagem principal do ticket."""
import time
import asyncio

import discord

from config import bot
from tickets.dados import (
    ler_dados_ticket,
    atualizar_dados_ticket,
    eh_responsavel_ticket,
)


async def atualizar_mensagem_controle(canal):
    """
    Atualiza a mensagem principal do ticket: mostra o responsável e
    remove o botão "Assumir ticket" enquanto o ticket está assumido.
    """
    # Import aqui dentro para evitar import circular com botoes.py
    from tickets.botoes import TicketCloseView

    try:
        dados = ler_dados_ticket(canal)
        mensagem = None
        mid = dados.get("msg_controle_id")

        if mid:
            try:
                mensagem = await canal.fetch_message(int(mid))
            except discord.NotFound:
                mensagem = None

        if mensagem is None:
            async for m in canal.history(limit=15, oldest_first=True):
                if (
                    bot.user
                    and m.author.id == bot.user.id
                    and m.embeds
                    and (m.embeds[0].title or "").startswith("🎫 Atendimento")
                ):
                    mensagem = m
                    await atualizar_dados_ticket(
                        canal,
                        msg_controle_id=m.id
                    )
                    break

        if mensagem is None:
            return

        assumido = dados.get("assumido_por")
        embed = mensagem.embeds[0].copy() if mensagem.embeds else None

        if embed is not None:
            for i, campo in enumerate(list(embed.fields)):
                if campo.name == "🙋 Responsável":
                    embed.remove_field(i)
                    break

            if assumido:
                embed.add_field(
                    name="🙋 Responsável",
                    value=f"<@{assumido}>",
                    inline=False
                )

        await mensagem.edit(
            embed=embed,
            view=TicketCloseView(assumido=bool(assumido))
        )

    except Exception as erro:
        print(f"Erro atualizando mensagem do ticket: {erro}")


async def anunciar_assuncao(canal, texto):
    try:
        await canal.send(
            texto,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    except Exception as erro:
        print(f"Erro anunciando responsável: {erro}")

    await atualizar_mensagem_controle(canal)


async def processar_assumir(interaction):
    canal = interaction.channel
    guild = interaction.guild

    if guild is None or not isinstance(canal, discord.TextChannel):
        return

    dados = ler_dados_ticket(canal)

    if not dados["owner_id"]:
        await interaction.response.send_message(
            "Este canal não é um ticket válido.", ephemeral=True
        )
        return

    if not eh_responsavel_ticket(guild, interaction.user):
        await interaction.response.send_message(
            "Apenas a equipe de atendimento pode assumir tickets.",
            ephemeral=True
        )
        return

    anterior = dados.get("assumido_por")

    if anterior == interaction.user.id:
        await interaction.response.send_message(
            "Você já está responsável por este ticket.", ephemeral=True
        )
        return

    # Reconhece a interação na hora, antes de qualquer outra coisa.
    await interaction.response.defer(ephemeral=True)

    await atualizar_dados_ticket(
        canal,
        assumido_por=interaction.user.id,
        respondido=True,
        ultima_atividade=int(time.time())
    )

    if anterior:
        texto = (
            f"🔄 {interaction.user.mention} assumiu este atendimento "
            f"no lugar de <@{anterior}>!"
        )
    else:
        texto = f"🙋 {interaction.user.mention} assumiu este atendimento!"

    await interaction.followup.send(
        "Você assumiu este atendimento.", ephemeral=True
    )

    asyncio.create_task(anunciar_assuncao(canal, texto))
