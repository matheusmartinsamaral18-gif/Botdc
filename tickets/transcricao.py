"""Transcrição (arquivo .txt) e fechamento do ticket."""
import io
import time
from datetime import datetime, timezone

import discord

from config import bot
from tickets.dados import ler_dados_ticket


async def gerar_transcricao(canal, fechado_por=None):
    dados = ler_dados_ticket(canal)
    mensagens = []

    async for mensagem in canal.history(limit=None, oldest_first=True):
        data = mensagem.created_at.strftime("%d/%m/%Y às %H:%M:%S UTC")
        conteudo = mensagem.content or ""

        if mensagem.embeds:
            conteudo += "\n[Mensagem contém embed]"

        if mensagem.attachments:
            conteudo += "\nANEXOS:\n" + "\n".join(
                f"- {anexo.filename}: {anexo.url}"
                for anexo in mensagem.attachments
            )

        if mensagem.stickers:
            conteudo += "\n[Sticker enviado]"

        if not conteudo.strip():
            conteudo = "[Mensagem sem texto]"

        mensagens.append(
            f"{'─' * 72}\n"
            f"MENSAGEM {len(mensagens) + 1:03d}\n"
            f"Data: {data}\n"
            f"Autor: {mensagem.author}\n"
            f"ID do autor: {mensagem.author.id}\n"
            f"{'─' * 72}\n"
            f"{conteudo}\n"
        )

    inicio = dados.get("aberto_em")
    if inicio:
        data_inicio = datetime.fromtimestamp(inicio, timezone.utc)
        duracao = max(0, int(time.time() - inicio))
        horas, resto = divmod(duracao, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo_aberto = f"{horas}h {minutos}min {segundos}s"
        data_formatada = data_inicio.strftime("%d/%m/%Y às %H:%M:%S UTC")
    else:
        tempo_aberto = "Não registrado"
        data_formatada = "Não registrado"

    numero = dados.get('numero') or 'Não registrado'
    solicitante = f"ID {dados['owner_id']}" if dados.get('owner_id') else "Não registrado"
    encerramento = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M:%S UTC")
    responsavel = str(fechado_por) if fechado_por is not None else "Não registrado"

    cabecalho = (
        "╔══════════════════════════════════════════════════════════════════════╗\n"
        "                         HISTÓRICO DE ATENDIMENTO\n"
        "╚══════════════════════════════════════════════════════════════════════╝\n\n"
        f"SERVIDOR: {canal.guild.name}\n"
        f"CANAL: #{canal.name}\n"
        f"PROTOCOLO: #{numero}\n"
        f"SOLICITANTE: {solicitante}\n"
        f"ABERTO EM: {data_formatada}\n"
        f"TEMPO DE ATENDIMENTO: {tempo_aberto}\n"
        f"ENCERRADO EM: {encerramento}\n"
        f"ENCERRADO POR: {responsavel}\n"
        f"TOTAL DE MENSAGENS: {len(mensagens)}\n\n"
        f"{'=' * 72}\n"
        "                         CONVERSA DO TICKET\n"
        f"{'=' * 72}\n\n"
    )

    conteudo_final = cabecalho + ("\n".join(mensagens) if mensagens else "Nenhuma mensagem foi registrada neste ticket.\n")
    arquivo = io.BytesIO(conteudo_final.encode("utf-8"))
    return discord.File(arquivo, filename=f"historico-atendimento-{dados.get('numero') or 'ticket'}.txt")


async def fechar_ticket(canal, fechado_por):
    if not isinstance(canal, discord.TextChannel):
        return False

    dados = ler_dados_ticket(canal)
    guild = canal.guild
    if dados["owner_id"] is None:
        return False

    arquivo = None
    try:
        arquivo = await gerar_transcricao(canal, fechado_por)
    except Exception as erro:
        print(f"Erro gerando transcrição: {erro}")

    # Evita enviar duas mensagens caso o solicitante também seja o dono do servidor.
    destinatarios = {guild.owner_id, dados["owner_id"]}
    destinatarios.discard(None)

    for user_id in destinatarios:
        try:
            usuario = await bot.fetch_user(user_id)
            eh_solicitante = user_id == dados["owner_id"]
            embed = discord.Embed(
                title=("✅ Atendimento finalizado" if eh_solicitante else "📋 Relatório de atendimento encerrado"),
                description=(
                    "Seu atendimento foi encerrado. O histórico completo da conversa está anexado."
                    if eh_solicitante else
                    "Um ticket foi encerrado no servidor. Confira os dados e o histórico da conversa em anexo."
                ),
                color=0x2ECC71,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="🌐 Servidor", value=guild.name, inline=False)
            embed.add_field(name="🎫 Ticket", value=f"`#{dados.get('numero') or 'Sem número'}` • `#{canal.name}`", inline=True)
            embed.add_field(name="👤 Solicitante", value=f"<@{dados['owner_id']}>\n`{dados['owner_id']}`", inline=True)
            embed.add_field(name="🔒 Encerrado por", value=str(fechado_por), inline=False)
            embed.add_field(
                name="📎 Histórico da conversa",
                value="Arquivo TXT anexado com as mensagens, datas, autores e anexos do atendimento." if arquivo else "Não foi possível gerar o arquivo de histórico.",
                inline=False
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Central de Atendimento • Relatório automático")

            if arquivo:
                arquivo.fp.seek(0)
                await usuario.send(embed=embed, file=discord.File(arquivo.fp, filename=arquivo.filename))
            else:
                await usuario.send(embed=embed)
        except Exception as erro:
            print(f"Não foi possível enviar relatório para {user_id}: {erro}")

    try:
        await canal.delete(reason=f"Ticket fechado por {fechado_por}")
        return True
    except Exception as erro:
        print(f"Erro excluindo ticket: {erro}")
        return False
