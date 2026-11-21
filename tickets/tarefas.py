"""Tarefas automáticas dos tickets: alertas, controle da primeira mensagem e fechamento por inatividade."""
import time
import asyncio
from datetime import timedelta

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


async def autor_ja_enviou_mensagem(canal, dados):
    """
    Confere o histórico desde a abertura do ticket.
    Isso também protege contra reinícios do bot, quando o estado em memória
    ainda não tiver registrado a mensagem do autor.
    """
    owner_id = dados.get("owner_id")
    aberto_em = dados.get("aberto_em")

    if not owner_id or not aberto_em:
        return None

    try:
        async for mensagem in canal.history(limit=None, oldest_first=True):
            if mensagem.created_at.timestamp() < aberto_em:
                continue

            if mensagem.author.id == owner_id:
                return True

        return False

    except (discord.Forbidden, discord.HTTPException) as erro:
        print(f"Erro consultando mensagens do autor em {canal.name}: {erro}")
        return None


@tasks.loop(minutes=1)
async def verificar_primeira_mensagem_autor():
    """
    Novo sistema:
    - Após 30 minutos sem mensagem do autor, pede que ele explique o motivo.
    - Após 1 hora sem mensagem do autor, aplica timeout de 3 dias e fecha.
    """
    agora = int(time.time())

    for guild in bot.guilds:
        for canal in list(guild.text_channels):
            try:
                dados = ler_dados_ticket(canal)

                if not dados.get("owner_id"):
                    continue

                aberto_em = dados.get("aberto_em")
                if not aberto_em:
                    continue

                idade_ticket = agora - aberto_em
                if idade_ticket < 0:
                    continue

                # Se já existe registro positivo, não precisa consultar o histórico.
                autor_falou = bool(dados.get("autor_falou"))

                if not autor_falou:
                    resultado = await autor_ja_enviou_mensagem(canal, dados)

                    # None significa que não foi possível ler o histórico.
                    # Nesse caso, não pune nem envia aviso por segurança.
                    if resultado is None:
                        continue

                    if resultado:
                        await atualizar_dados_ticket(
                            canal,
                            autor_falou=True
                        )
                        autor_falou = True

                # Se o autor já falou, este novo sistema não faz mais nada.
                if autor_falou:
                    continue

                # Após 1 hora: timeout de 3 dias e fechamento do ticket.
                if idade_ticket >= 60 * 60:
                    if dados.get("punicao_abertura_processada"):
                        continue

                    # Marca antes das ações para impedir repetição em outra volta do loop.
                    await atualizar_dados_ticket(
                        canal,
                        punicao_abertura_processada=True
                    )

                    membro = guild.get_member(dados["owner_id"])
                    if membro is None:
                        try:
                            membro = await guild.fetch_member(dados["owner_id"])
                        except discord.NotFound:
                            membro = None
                        except discord.HTTPException as erro:
                            print(f"Erro buscando autor do ticket {canal.name}: {erro}")
                            # Não fecha sem conseguir confirmar o membro; tenta novamente.
                            await atualizar_dados_ticket(
                                canal,
                                punicao_abertura_processada=False
                            )
                            continue

                    timeout_aplicado = False
                    erro_timeout = None

                    if membro is not None:
                        try:
                            await membro.timeout(
                                timedelta(days=3),
                                reason="Abriu um ticket e não enviou nenhuma mensagem em 1 hora."
                            )
                            timeout_aplicado = True
                        except (discord.Forbidden, discord.HTTPException) as erro:
                            erro_timeout = erro
                            print(f"Não foi possível aplicar timeout no autor do ticket {canal.name}: {erro}")

                    try:
                        if timeout_aplicado:
                            await canal.send(
                                content=(
                                    f"<@{dados['owner_id']}> ⛔\n\n"
                                    "Seu ticket foi encerrado porque você não enviou nenhuma mensagem "
                                    "durante **1 hora** após a abertura. Foi aplicado um timeout de "
                                    "**3 dias** por inatividade no atendimento."
                                ),
                                allowed_mentions=discord.AllowedMentions(users=True)
                            )
                        elif membro is None:
                            await canal.send(
                                "⛔ O ticket será encerrado porque o autor não enviou nenhuma mensagem "
                                "durante **1 hora**. Não foi possível aplicar o timeout porque o usuário "
                                "não está mais no servidor."
                            )
                        else:
                            await canal.send(
                                "⛔ O ticket será encerrado porque o autor não enviou nenhuma mensagem "
                                "durante **1 hora**. Não consegui aplicar o timeout; verifique se o bot "
                                "tem a permissão **Moderar membros** e está acima do usuário na hierarquia."
                            )
                    except discord.HTTPException as erro:
                        print(f"Erro enviando aviso de encerramento por ausência de mensagem: {erro}")

                    await asyncio.sleep(1)
                    await fechar_ticket(
                        canal,
                        "Sistema automático (1 hora sem mensagem do autor)"
                    )
                    continue

                # Após 30 minutos: envia um único aviso ao autor.
                if idade_ticket >= 30 * 60 and not dados.get("aviso_abertura_enviado"):
                    try:
                        await canal.send(
                            content=(
                                f"<@{dados['owner_id']}> 👋\n\n"
                                "Percebemos que você abriu este ticket, mas ainda não enviou nenhuma "
                                "mensagem explicando o que precisa. Para que nossa equipe possa ajudar, "
                                "conte aqui o motivo do contato.\n\n"
                                "⏳ **Atenção:** se nenhuma mensagem for enviada até completar 1 hora "
                                "da abertura, o ticket será encerrado automaticamente e poderá ser "
                                "aplicado um timeout de 3 dias."
                            ),
                            allowed_mentions=discord.AllowedMentions(users=True)
                        )

                        await atualizar_dados_ticket(
                            canal,
                            aviso_abertura_enviado=True
                        )

                        print(f"⏰ Aviso de primeira mensagem enviado: {canal.name}")

                    except discord.HTTPException as erro:
                        print(f"Erro enviando aviso de primeira mensagem em {canal.name}: {erro}")

            except Exception as erro:
                print(f"Erro verificando primeira mensagem do ticket {canal.name}: {erro}")


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


@verificar_primeira_mensagem_autor.before_loop
async def antes_verificar_primeira_mensagem_autor():
    await bot.wait_until_ready()


@fechar_tickets_por_inatividade.before_loop
async def antes_fechar_tickets_por_inatividade():
    await bot.wait_until_ready()


@verificar_tickets_sem_resposta.before_loop
async def antes_verificar_tickets():
    await bot.wait_until_ready()


async def setup(bot):
    if not verificar_primeira_mensagem_autor.is_running():
        verificar_primeira_mensagem_autor.start()

    if not verificar_tickets_sem_resposta.is_running():
        verificar_tickets_sem_resposta.start()

    if not fechar_tickets_por_inatividade.is_running():
        fechar_tickets_por_inatividade.start()
