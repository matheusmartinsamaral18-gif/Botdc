"""Logs enviados por DM somente para o dono do bot (MEU_ID)."""
import discord

from config import bot, MEU_ID


async def enviar_log_simples(guild, titulo, descricao, cor=0xFF0000):
    try:
        embed = discord.Embed(
            title=titulo,
            description=descricao,
            color=cor,
            timestamp=discord.utils.utcnow()
        )

        if guild:
            embed.add_field(
                name="🌐 Servidor",
                value=(
                    f"**{guild.name}**\n"
                    f"ID: `{guild.id}`"
                ),
                inline=False
            )

            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.set_footer(
                text="Sistema Anti-Nuke • Relatório privado"
            )

        usuario = await bot.fetch_user(MEU_ID)
        await usuario.send(embed=embed)

    except discord.Forbidden:
        print(
            "Não foi possível enviar o log: "
            "ative as mensagens privadas do bot."
        )

    except Exception as erro:
        print(f"Erro enviando log privado para MEU_ID: {erro}")


async def enviar_log(guild, titulo, descricao, cor=0xFF0000):
    await enviar_log_simples(guild, titulo, descricao, cor)
