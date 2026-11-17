"""Comando !recursos (liberado para todos)."""
import discord

from config import bot


@bot.command(name="recursos")
async def recursos(ctx):
    embed = discord.Embed(
        title="🛡️ CENTRAL DE RECURSOS",
        description=(
            "Um sistema desenvolvido para oferecer mais segurança, "
            "organização e praticidade ao seu servidor Discord."
        ),
        color=0x5865F2
    )

    embed.set_thumbnail(
        url=(
            ctx.guild.icon.url
            if ctx.guild.icon
            else bot.user.display_avatar.url
        )
    )

    embed.add_field(
        name="🛡️ Proteção Anti-Nuke e Anti-Raid",
        value=(
            "> Proteção contra ataques, invasões e ações administrativas suspeitas.\n"
            "> Monitoramento de alterações e ações em massa.\n"
            "> Identificação de responsáveis e recuperação do servidor quando necessário."
        ),
        inline=False
    )

    embed.add_field(
        name="🎫 Sistema de Tickets",
        value=(
            "> Painel próprio para abertura de atendimentos.\n"
            "> Canais privados para conversar com a equipe.\n"
            "> Fechamento de tickets e geração de transcrições.\n"
            "> Alertas automáticos quando um atendimento fica sem resposta."
        ),
        inline=False
    )

    embed.add_field(
        name="📦 Backup e Restauração",
        value=(
            "> Salvamento automático da estrutura do servidor.\n"
            "> Backup de canais e cargos.\n"
            "> Recuperação da estrutura após ações destrutivas ou ataques."
        ),
        inline=False
    )

    embed.add_field(
        name="🚨 Sistema de Logs",
        value=(
            "> Registro de atividades suspeitas.\n"
            "> Identificação de responsáveis por alterações.\n"
            "> Notificações sobre ações importantes realizadas no servidor."
        ),
        inline=False
    )

    embed.add_field(
        name="💬 Proteção Anti-Spam",
        value=(
            "> Identificação de mensagens enviadas em excesso.\n"
            "> Aplicação automática de timeout em usuários que praticam spam."
        ),
        inline=False
    )

    embed.add_field(
        name="🧹 Gerenciamento e Limpeza",
        value=(
            "> Ferramentas para organização dos canais.\n"
            "> Limpeza de mensagens em grande quantidade.\n"
            "> Recriação de canais quando necessário."
        ),
        inline=False
    )

    embed.set_footer(
        text="Mais proteção, controle e organização. Tudo em um só bot.",
        icon_url=bot.user.display_avatar.url
    )

    await ctx.send(embed=embed)


async def setup(bot):
    pass
