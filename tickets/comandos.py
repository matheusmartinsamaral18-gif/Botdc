"""Comando !ticket painel #canal + registro dos botões persistentes."""
import discord

from config import bot
from tickets.botoes import TicketPanelView, TicketCloseView


@bot.group(
    name="ticket",
    invoke_without_command=True
)
async def ticket(ctx):
    await ctx.send(
        "Use: `!ticket painel #canal`",
        delete_after=5
    )


@ticket.command(name="painel")
async def ticket_painel(ctx, canal: discord.TextChannel):
    if ctx.author.id != ctx.guild.owner_id:
        return

    embed = discord.Embed(
        title="🎫 SUPORTE • THEUSSYT COMMUNITY",
        description=(
            "Precisa de ajuda? Fale com a nossa staff.\n\n"
            "✅ **Faça**\n"
            "> Explique seu problema com detalhes\n"
            "> Envie prints ou vídeos se tiver\n"
            "> Aguarde a resposta com paciência\n\n"
            "❌ **Evite**\n"
            "> Abrir ticket sem motivo\n"
            "> Marcar a staff várias vezes\n\n"
            "📋 Ao fechar, você recebe a transcrição no privado\n"
            "🔒 Só você e a equipe veem o ticket"
        ),
        color=0x5865F2
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_footer(
        text=f"{ctx.guild.name} • Sistema de Tickets"
    )

    try:
        await canal.send(
            embed=embed,
            view=TicketPanelView()
        )

        await ctx.send(
            f"✅ Painel de tickets publicado em {canal.mention}.",
            delete_after=5
        )

    except discord.Forbidden:
        await ctx.send(
            "❌ Não tenho permissão para enviar mensagens nesse canal.",
            delete_after=5
        )

    except Exception as erro:
        print(f"Erro publicando painel: {erro}")

        await ctx.send(
            "❌ Não foi possível publicar o painel.",
            delete_after=5
        )


async def setup(bot):
    # Botões persistentes: continuam funcionando depois de reiniciar o bot.
    bot.add_view(TicketPanelView())
    bot.add_view(TicketCloseView())
