"""Eventos de mensagem dentro dos tickets: atividade, responsável e comando .f"""
import time
import asyncio

import discord

from config import bot
from tickets.dados import (
    ler_dados_ticket,
    atualizar_dados_ticket,
    eh_responsavel_ticket,
)
from tickets.assumir import anunciar_assuncao
from tickets.transcricao import fechar_ticket


@bot.listen("on_message")
async def ticket_on_message(message):
    if message.author.bot or message.guild is None:
        return

    dados_ticket = ler_dados_ticket(message.channel)

    # Se não for canal de ticket, este módulo não faz nada.
    if not dados_ticket["owner_id"]:
        return

    # ----- atualiza atividade (prazo de 3 horas) -----
    await atualizar_dados_ticket(
        message.channel,
        ultima_atividade=int(time.time())
    )

    # ----- identifica resposta de responsável -----
    dados_ticket = ler_dados_ticket(message.channel)

    if eh_responsavel_ticket(message.guild, message.author):
        alteracoes = {"respondido": True}

        # Se ninguém assumiu manualmente, o primeiro responsável que
        # responder passa a ser o responsável automaticamente.
        if not dados_ticket.get("assumido_por"):
            alteracoes["assumido_por"] = message.author.id
            await atualizar_dados_ticket(message.channel, **alteracoes)
            asyncio.create_task(
                anunciar_assuncao(
                    message.channel,
                    f"🙋 {message.author.mention} assumiu este atendimento!"
                )
            )
        elif not dados_ticket["respondido"]:
            await atualizar_dados_ticket(message.channel, **alteracoes)

    # ----- comando .f para fechar ticket (somente responsáveis) -----
    if message.content.strip().lower() == ".f":
        if not eh_responsavel_ticket(message.guild, message.author):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        await message.channel.send(
            f"🔒 Ticket fechado por {message.author.mention}. "
            "Estou enviando a transcrição no privado..."
        )

        await asyncio.sleep(2)

        await fechar_ticket(
            message.channel,
            message.author
        )


async def setup(bot):
    pass
