"""Tarefas automáticas dos tickets: alerta sem resposta e fechamento por inatividade."""
import time
import asyncio

import discord
from discord.ext import tasks

from config import (
    bot,
    TEMPO_ALERTA_TICKET,
    TEMPO_FECHAMENTO_INATIVIDADE_TICKET,
)
from tickets.dados import (
    ler_dados_ticket,
    atualizar_dados_ticket,
    obter_responsaveis_ticket,
    limpar_estado_tickets_orfaos,
)
from tickets.transcricao import fechar_ticket


async def notificar_responsaveis_ticket(canal, dados):
    guild = canal.guild

    responsaveis = obter_responsaveis_ticket(guild)

    mensagem = (
        "🎫 **Ticket aguardando atendimento**\n"
        f"Servidor: **{guild.name}**\n"
        f"Ticket: **{canal.name}**\n"
        f"Autor: <@{dados['owner_id']}>\n"
        f"Canal: {canal.mention}\n\n"
        "Este ticket está aberto há 30 minutos "
        "e ainda não recebeu resposta de um responsável."
    )

    enviados = 0

    for responsavel in responsaveis:
        try:
            await responsavel.send(mensagem)
            enviados += 1
            await asyncio.sleep(0.3)

        except Exception:
            pass

    return enviados


@tasks.loop(minutes=1)
async def verificar_tickets_sem_resposta():
    for guild in bot.guilds:
        for canal in list(guild.text_channels):
            try:
                dados = ler_dados_ticket(canal)
                if not dados["owner_id"]:
                    continue

                # O alerta depende sempre da última mensagem humana do canal.
                ultima_mensagem_humana = None
                async for mensagem in canal.history(limit=30):
                    if not mensagem.author.bot:
                        ultima_mensagem_humana = mensagem
                        break

                if ultima_mensagem_humana is None:
                    continue

                if ultima_mensagem_humana.author.id != dados["owner_id"]:
                    continue

                mensagem_id = str(ultima_mensagem_humana.id)
                if dados.get("ultimo_alerta_msg") == mensagem_id:
                    continue

                tempo_sem_resposta = (
                    discord.utils.utcnow() - ultima_mensagem_humana.created_at
                ).total_seconds()
                if tempo_sem_resposta < TEMPO_ALERTA_TICKET:
                    continue

                # Salva o ID antes de notificar para impedir alertas duplicados.
                atualizado = await atualizar_dados_ticket(
                    canal,
                    ultimo_alerta_msg=mensagem_id,
                    alertado=True
                )
                if not atualizado:
                    continue

                enviados = await notificar_responsaveis_ticket(canal, dados)

                try:
                    await canal.send(
                        content=(
                            f"<@{dados['owner_id']}> ⏰\n\n"
                            "Sua última mensagem está aguardando uma resposta "
                            "da equipe há **30 minutos**. Já avisamos os "
                            "administradores e responsáveis pelo atendimento."
                        ),
                        allowed_mentions=discord.AllowedMentions(users=True)
                    )
                except Exception as erro:
                    print(f"Erro avisando autor do ticket: {erro}")

                print(
                    f"⏰ Alerta de ticket enviado: {canal.name} "
                    f"| Responsáveis notificados: {enviados}"
                )

            except Exception as erro:
                print(f"Erro verificando ticket {canal.name}: {erro}")


@tasks.loop(minutes=1)
async def fechar_tickets_por_inatividade():
    """Fecha tickets que ficam 3 horas sem nenhuma nova mensagem."""
    agora = int(time.time())

    try:
        limpar_estado_tickets_orfaos()
    except Exception as erro:
        print(f"Erro limpando estado de tickets: {erro}")

    for guild in bot.guilds:
        for canal in list(guild.text_channels):
            try:
                dados = ler_dados_ticket(canal)
                if not dados["owner_id"]:
                    continue

                ultima_atividade = dados.get("ultima_atividade")

                # Compatibilidade com tickets antigos sem o campo de última atividade.
                if not ultima_atividade:
                    ultima_atividade = dados.get("aberto_em")
                    try:
                        async for mensagem in canal.history(limit=100):
                            if not mensagem.author.bot:
                                ultima_atividade = int(mensagem.created_at.timestamp())
                                break
                    except Exception as erro:
                        print(f"Erro lendo atividade antiga do ticket {canal.name}: {erro}")

                    if ultima_atividade:
                        await atualizar_dados_ticket(
                            canal,
                            ultima_atividade=ultima_atividade
                        )

                if not ultima_atividade:
                    continue

                if agora - ultima_atividade < TEMPO_FECHAMENTO_INATIVIDADE_TICKET:
                    continue

                aviso = (
                    "⏰ Este ticket foi encerrado automaticamente após "
                    "3 horas sem novas mensagens. A transcrição será enviada no privado."
                )
                try:
                    await canal.send(aviso)
                except Exception as erro:
                    print(f"Erro avisando fechamento por inatividade: {erro}")

                await asyncio.sleep(1)
                await fechar_ticket(canal, "Sistema automático (3 horas de inatividade)")

            except Exception as erro:
                print(f"Erro verificando inatividade do ticket {canal.name}: {erro}")


@fechar_tickets_por_inatividade.before_loop
async def antes_fechar_tickets_por_inatividade():
    await bot.wait_until_ready()


@verificar_tickets_sem_resposta.before_loop
async def antes_verificar_tickets():
    await bot.wait_until_ready()


async def setup(bot):
    if not verificar_tickets_sem_resposta.is_running():
        verificar_tickets_sem_resposta.start()

    if not fechar_tickets_por_inatividade.is_running():
        fechar_tickets_por_inatividade.start()
