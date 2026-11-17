"""Comandos: !atualizar (backup) e !restaurar."""
import discord

from config import bot
from core.raid_estado import get_raid
from backup.armazenamento import (
    carregar_backup,
    salvar_backup_bom,
    salvar_backup_temp,
    tirar_foto_guild,
)
from backup.mensagens import salvar_backup_mensagens_guild
from backup.restauracao import (
    construir_overwrites,
    criar_canal_backup,
    mapa_categorias_existentes,
    restaurar_mensagens_canal,
    restaurar_mensagens_todos_canais,
    ConfirmarRestauracaoTudoView,
)


@bot.command(
    name="atualizar",
    aliases=["atualizarbackup", "backup", "salvar"]
)
async def atualizar_backup(ctx, *, arg: str = ""):
    if ctx.author.id != ctx.guild.owner_id:
        return

    if ctx.invoked_with in ("backup", "salvar"):
        arg = "backup"

    if arg.strip().lower() not in ("backup", ""):
        await ctx.send(
            "Usa assim: `!atualizar backup`",
            delete_after=5
        )
        return

    estado = get_raid(ctx.guild.id)

    if estado["ativo"]:
        await ctx.send(
            "⚠️ Há uma raid em andamento. "
            "O backup BOM não será atualizado.",
            delete_after=8
        )
        return

    try:
        foto = tirar_foto_guild(ctx.guild)

        salvar_backup_bom(ctx.guild.id, foto)
        salvar_backup_temp(ctx.guild.id, foto)
        total_mensagens = await salvar_backup_mensagens_guild(ctx.guild)

        await ctx.send(
            f"✅ Backup atualizado! "
            f"**{len(foto['canais'])} canais**, "
            f"**{len(foto['cargos'])} cargos** e "
            f"**{total_mensagens} mensagens** salvos.",
            delete_after=8
        )

        print(
            f"✅ Backup atualizado por {ctx.author} "
            f"em {ctx.guild.name}"
        )

    except Exception as erro:
        await ctx.send(
            f"❌ Erro ao atualizar backup: {erro}",
            delete_after=8
        )


@bot.command(name="restaurar")
async def restaurar(ctx, *, argumento: str = ""):
    if ctx.guild is None or ctx.author.id != ctx.guild.owner_id:
        return

    argumento = (argumento or "").strip()
    normalizado = " ".join(argumento.lower().split())

    if normalizado in ("", "ajuda", "help"):
        await ctx.send(
            "**Comandos de restauração manual:**\n"
            "• `!restaurar tudo` — canais, cargos e mensagens (com confirmação)\n"
            "• `!restaurar canal #canal` — restaura a configuração do canal\n"
            "• `!restaurar msg deste canal` — mensagens do canal atual\n"
            "• `!restaurar msg de todos canais` — mensagens de todos os canais\n"
            "• `!restaurar msg do #canal` — mensagens de um canal específico"
        )
        return

    if normalizado == "tudo":
        view = ConfirmarRestauracaoTudoView(ctx.guild.id, ctx.author.id)
        await ctx.send(
            "⚠️ **Confirma a restauração do backup inteiro?**\n"
            "Isso recria cargos e canais ausentes e reenvia as mensagens salvas. "
            "Os canais e cargos atuais não serão apagados.",
            view=view
        )
        return

    if normalizado == "msg deste canal":
        qtd, erro = await restaurar_mensagens_canal(ctx.channel)
        await ctx.send(
            erro or f"✅ {qtd} mensagens reenviadas em {ctx.channel.mention}."
        )
        return

    if normalizado == "msg de todos canais":
        qtd, ignorados = await restaurar_mensagens_todos_canais(ctx.guild)
        await ctx.send(
            f"✅ **{qtd} mensagens** reenviadas. "
            f"Canais sem correspondência: **{ignorados}**."
        )
        return

    if normalizado.startswith("msg do "):
        canal = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        if canal is None:
            nome = argumento[7:].strip().lstrip("#")
            canal = discord.utils.get(ctx.guild.text_channels, name=nome)
        if not isinstance(canal, discord.TextChannel):
            await ctx.send("❌ Não encontrei esse canal. Use `!restaurar msg do #canal`.")
            return
        qtd, erro = await restaurar_mensagens_canal(canal)
        await ctx.send(
            erro or f"✅ {qtd} mensagens reenviadas em {canal.mention}."
        )
        return

    if normalizado.startswith("canal "):
        canal = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        nome = argumento[6:].strip().lstrip("#")
        if canal is None:
            canal = discord.utils.get(ctx.guild.text_channels, name=nome)
        backup = carregar_backup(ctx.guild.id)
        item = next(
            (x for x in backup.get("canais", [])
             if (canal and int(x.get("id", 0)) == canal.id)
             or x.get("name", "").lower() == nome.lower()),
            None
        )
        if item is None:
            await ctx.send("❌ Não encontrei esse canal no backup.")
            return

        if canal is None:
            mapa_categorias = mapa_categorias_existentes(ctx.guild, backup)
            mapa_cargos = {
                int(r.get("id", 0)): ctx.guild.get_role(int(r.get("id", 0)))
                for r in backup.get("cargos", [])
                if ctx.guild.get_role(int(r.get("id", 0))) is not None
            }
            try:
                novo = await criar_canal_backup(
                    ctx.guild, item, mapa_categorias, mapa_cargos
                )
                await ctx.send(f"✅ Canal recriado: {novo.mention}")
            except Exception as erro:
                await ctx.send(f"❌ Não foi possível recriar o canal: {erro}")
            return

        try:
            categoria = None
            categoria_id = item.get("category_id")
            if categoria_id:
                categoria = ctx.guild.get_channel(int(categoria_id))
                if not isinstance(categoria, discord.CategoryChannel):
                    categoria = next(
                        (c for c in ctx.guild.categories
                         if c.name == next(
                             (x.get("name") for x in backup.get("canais", [])
                              if x.get("id") == categoria_id),
                             None
                         )),
                        None
                    )
            overwrites = construir_overwrites(
                ctx.guild, item.get("overwrites", [])
            )
            kwargs = {
                "name": item.get("name", canal.name),
                "overwrites": overwrites,
                "reason": "Restauração manual da configuração do canal"
            }
            if isinstance(canal, discord.TextChannel):
                kwargs.update({
                    "topic": item.get("topic"),
                    "slowmode_delay": item.get("slowmode", 0),
                    "nsfw": item.get("nsfw", False),
                    "category": categoria
                })
            await canal.edit(**kwargs)
            await ctx.send(f"✅ Configuração do canal atualizada: {canal.mention}")
        except Exception as erro:
            await ctx.send(f"❌ Não foi possível restaurar o canal: {erro}")
        return

    await ctx.send("❌ Comando não reconhecido. Use `!restaurar` para ver as opções.")


async def setup(bot):
    pass
