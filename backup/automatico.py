"""Backup automático da estrutura (canais/cargos) a cada 30 minutos."""
import os

from discord.ext import tasks

from config import bot
from core.raid_estado import teve_raid_recente
from backup.armazenamento import (
    backup_bom_path,
    backup_temp_path,
    carregar_backup,
    salvar_backup_bom,
    salvar_backup_temp,
    tirar_foto_guild,
)
from backup.mensagens import salvar_backup_mensagens_guild


@tasks.loop(minutes=30)
async def sync_backup_loop():
    for guild in bot.guilds:
        try:
            if teve_raid_recente(guild.id, 30):
                print(f"⏸️ Sync pulado em {guild.name}: raid recente.")
                continue

            foto = tirar_foto_guild(guild)

            salvar_backup_temp(guild.id, foto)
            salvar_backup_bom(guild.id, foto)

            print(f"🔄 Backup atualizado: {guild.name}")

        except Exception as erro:
            print(f"Erro sync backup {guild.name}: {erro}")


@sync_backup_loop.before_loop
async def antes_sync():
    await bot.wait_until_ready()


@bot.listen("on_ready")
async def backup_inicial():
    for guild in bot.guilds:
        try:
            if not os.path.exists(backup_bom_path(guild.id)):
                foto = tirar_foto_guild(guild)

                salvar_backup_bom(guild.id, foto)
                salvar_backup_temp(guild.id, foto)

                print(f"📸 Backup inicial criado: {guild.name}")

            elif not os.path.exists(backup_temp_path(guild.id)):
                salvar_backup_temp(
                    guild.id,
                    tirar_foto_guild(guild)
                )

                print(f"📂 Backup TEMP criado: {guild.name}")

            else:
                print(f"📂 Backup BOM carregado: {guild.name}")

        except Exception as erro:
            print(f"Erro backup inicial {guild.name}: {erro}")

    # Na primeira inicialização, cria também o histórico inicial de mensagens.
    for guild in bot.guilds:
        try:
            if not carregar_backup(guild.id).get("mensagens"):
                await salvar_backup_mensagens_guild(guild)
        except Exception as erro:
            print(f"Erro no backup inicial de mensagens ({guild.name}): {erro}")


@bot.listen("on_guild_join")
async def backup_novo_servidor(guild):
    try:
        foto = tirar_foto_guild(guild)

        salvar_backup_bom(guild.id, foto)
        salvar_backup_temp(guild.id, foto)
        await salvar_backup_mensagens_guild(guild)

        print(f"📸 Novo servidor, backup criado: {guild.name}")

    except Exception as erro:
        print(f"Erro criando backup do novo servidor: {erro}")


async def setup(bot):
    if not sync_backup_loop.is_running():
        sync_backup_loop.start()
