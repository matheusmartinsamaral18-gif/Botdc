"""
Controle dos comandos com "!":
- apaga a mensagem do comando
- só o dono do servidor pode usar (exceto !recursos)
Obs.: só pode existir UM on_message com @bot.event; os outros sistemas
usam @bot.listen("on_message") e funcionam em paralelo.
"""
import discord

from config import bot


@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    if not message.content.startswith("!"):
        return

    ctx = await bot.get_context(message)

    try:
        await message.delete()
    except discord.HTTPException:
        pass

    if ctx.command is None:
        return

    if ctx.command.qualified_name == "recursos":
        await bot.invoke(ctx)
        return

    if message.author.id != message.guild.owner_id:
        return

    await bot.invoke(ctx)


async def setup(bot):
    pass
