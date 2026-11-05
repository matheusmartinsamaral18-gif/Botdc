import discord
from discord.ext import commands
import os, time
from collections import defaultdict
from datetime import timedelta

# ===== KEEP-ALIVE PRA RENDER NÃO DORMIR =====
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot online! 🛡️"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
# =============================================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== CONFIGURA =====
DONO_ID = 926223827590078504
ADM_CONFIANCA = []
LOGS_CHANNEL_ID = 1567711809396277318
# =====================

async def enviar_log(guild, titulo, descricao, cor=0xFF0000):
    try:
        canal = guild.get_channel(LOGS_CHANNEL_ID)
        if canal is None:
            canal = await bot.fetch_channel(LOGS_CHANNEL_ID)
        if canal:
            embed = discord.Embed(title=titulo, description=descricao, color=cor, timestamp=discord.utils.utcnow())
            embed.set_footer(text=f"Servidor: {guild.name}")
            await canal.send(embed=embed)
    except Exception as e:
        print(f"Erro log canal: {e}")
    try:
        dono = await bot.fetch_user(DONO_ID)
        await dono.send(f"{titulo}\n{descricao}")
    except: pass

def is_protegido(user_id):
    return user_id == DONO_ID or user_id in ADM_CONFIANCA

acoes = defaultdict(list)

def registrou(tipo, user_id, limite=2, janela=3):
    agora = time.time()
    chave = (tipo, user_id)
    acoes[chave].append(agora)
    acoes[chave] = [t for t in acoes[chave] if agora - t < janela]
    return len(acoes[chave]) >= limite

async def punir(guild, executor_id, motivo):
    if is_protegido(executor_id):
        return
    try:
        membro = await guild.fetch_member(executor_id)
        await membro.ban(reason=f"ANTI-NUKE: {motivo}")
        await enviar_log(guild, "🚨 ANTI-NUKE - Banido", f"**Usuário:** {membro} (`{membro.id}`)\n**Motivo:** {motivo}\n**Ação:** Banido automaticamente")
    except Exception as e:
        print(f"Erro punir: {e}")
        await enviar_log(guild, "⚠️ Falha ao punir", f"ID: `{executor_id}`\nMotivo: {motivo}\nErro: {e}", cor=0xFFA500)

async def pegar_executor(guild, action):
    try:
        async for entry in guild.audit_logs(limit=3, action=action):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() < 3:
                if entry.user.id != bot.user.id:
                    return entry.user.id
    except: pass
    return None

@bot.event
async def on_ready():
    print(f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP 3s")
    await bot.change_presence(activity=discord.Game(name="🛡️ Anti-Nuke + Backup"))

msgs = defaultdict(list)
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    if message.channel.id == LOGS_CHANNEL_ID:
        try: await message.delete()
        except: pass
        if message.content.startswith("!"):
            await bot.process_commands(message)
        return
    if is_protegido(message.author.id):
        await bot.process_commands(message); return
    agora = time.time()
    msgs[message.author.id].append(agora)
    msgs[message.author.id] = [t for t in msgs[message.author.id] if agora - t < 3]
    if len(msgs[message.author.id]) >= 5:
        msgs[message.author.id] = []
        try: await message.author.timeout(timedelta(minutes=10), reason="Spam")
        except: pass
        await enviar_log(message.guild, "💬 Anti-Spam - Mute", f"**Usuário:** {message.author.mention} (`{message.author.id}`)\n**Canal:** {message.channel.mention}\n**Ação:** Mutado por 10 minutos (5 msgs em 3s)", cor=0xFFA500)
        return
    await bot.process_commands(message)

@bot.event
async def on_member_ban(guild, user):
    ex = await pegar_executor(guild, discord.AuditLogAction.ban)
    if ex and registrou("ban", ex, 2, 3):
        await punir(guild, ex, "Baniu 2 em 3s")

@bot.event
async def on_member_remove(member):
    ex = await pegar_executor(member.guild, discord.AuditLogAction.kick)
    if ex and registrou("kick", ex, 2, 3):
        await punir(member.guild, ex, "Expulsou 2 em 3s")

@bot.event
async def on_guild_channel_create(channel):
    ex = await pegar_executor(channel.guild, discord.AuditLogAction.channel_create)
    if ex and registrou("canal_criar", ex, 2, 3):
        await punir(channel.guild, ex, "Criou 2 canais em 3s")

@bot.event
async def on_guild_channel_delete(channel):
    ex = await pegar_executor(channel.guild, discord.AuditLogAction.channel_delete)
    if ex and not is_protegido(ex) and ex != bot.user.id:
        try:
            guild = channel.guild
            categoria = channel.category
            overwrites = channel.overwrites
            if isinstance(channel, discord.TextChannel):
                novo = await guild.create_text_channel(name=channel.name, category=categoria, position=channel.position, topic=channel.topic, slowmode_delay=channel.slowmode_delay, nsfw=channel.nsfw, overwrites=overwrites, reason="BACKUP Anti-Nuke")
            elif isinstance(channel, discord.VoiceChannel):
                novo = await guild.create_voice_channel(name=channel.name, category=categoria, position=channel.position, bitrate=channel.bitrate, user_limit=channel.user_limit, overwrites=overwrites, reason="BACKUP Anti-Nuke")
            elif isinstance(channel, discord.CategoryChannel):
                novo = await guild.create_category(name=channel.name, position=channel.position, overwrites=overwrites, reason="BACKUP Anti-Nuke")
            else:
                novo = None
            if novo:
                print(f"♻️ BACKUP: Canal #{channel.name} recriado!")
                await enviar_log(guild, "♻️ Backup - Canal Recriado", f"**Canal:** #{channel.name}\n**Deletado por:** <@{ex}> (`{ex}`)\n**Ação:** Canal recriado automaticamente", cor=0x2ecc71)
        except Exception as e:
            print(f"Erro backup canal: {e}")
    if ex and registrou("canal_del", ex, 2, 3):
        await punir(channel.guild, ex, "Deletou 2 canais em 3s")

@bot.event
async def on_guild_channel_update(antes, depois):
    if antes.name != depois.name:
        ex = await pegar_executor(depois.guild, discord.AuditLogAction.channel_update)
        if ex and registrou("canal_rename", ex, 2, 3):
            await punir(depois.guild, ex, "Renomeou 2 canais em 3s")

@bot.event
async def on_guild_role_create(role):
    ex = await pegar_executor(role.guild, discord.AuditLogAction.role_create)
    if ex and registrou("cargo_criar", ex, 2, 3):
        await punir(role.guild, ex, "Criou 2 cargos em 3s")

@bot.event
async def on_guild_role_delete(role):
    ex = await pegar_executor(role.guild, discord.AuditLogAction.role_delete)
    if ex and not is_protegido(ex) and ex != bot.user.id and role.name != "@everyone":
        try:
            await role.guild.create_role(name=role.name, colour=role.colour, hoist=role.hoist, mentionable=role.mentionable, permissions=role.permissions, reason="BACKUP Anti-Nuke")
            print(f"♻️ BACKUP: Cargo {role.name} recriado!")
            await enviar_log(role.guild, "♻️ Backup - Cargo Recriado", f"**Cargo:** {role.name}\n**Deletado por:** <@{ex}> (`{ex}`)\n**Ação:** Cargo recriado automaticamente", cor=0x2ecc71)
        except Exception as e:
            print(f"Erro backup cargo: {e}")
    if ex and registrou("cargo_del", ex, 2, 3):
        await punir(role.guild, ex, "Deletou 2 cargos em 3s")

@bot.event
async def on_guild_role_update(antes, depois):
    if not antes.permissions.administrator and depois.permissions.administrator:
        ex = await pegar_executor(depois.guild, discord.AuditLogAction.role_update)
        if ex:
            await enviar_log(depois.guild, "⚠️ Tentativa de dar ADM", f"**Por:** <@{ex}> (`{ex}`)\n**Cargo:** {depois.name}\n**Ação:** Tentou dar ADM via cargo", cor=0xFFA500)
            await punir(depois.guild, ex, "Tentou dar ADM via cargo")

@bot.event
async def on_webhooks_update(channel):
    ex = await pegar_executor(channel.guild, discord.AuditLogAction.webhook_create)
    if ex and not is_protegido(ex):
        try:
            webs = await channel.webhooks()
            for w in webs:
                if w.user and w.user.id == ex: await w.delete()
        except: pass
        await punir(channel.guild, ex, "Criou webhook suspeito")

@bot.event
async def on_guild_emojis_update(guild, antes, depois):
    if len(depois) < len(antes):
        ex = await pegar_executor(guild, discord.AuditLogAction.emoji_delete)
        if ex and registrou("emoji", ex, 2, 3):
            await punir(guild, ex, "Deletou emojis")

@bot.event
async def on_guild_stickers_update(guild, antes, depois):
    if len(depois) < len(antes):
        ex = await pegar_executor(guild, discord.AuditLogAction.sticker_delete)
        if ex: await punir(guild, ex, "Deletou sticker")

@bot.event
async def on_raw_bulk_message_delete(payload):
    if len(payload.cached_messages) >= 5 and payload.guild_id:
        guild = bot.get_guild(payload.guild_id)
        ex = await pegar_executor(guild, discord.AuditLogAction.message_bulk_delete)
        if ex: await punir(guild, ex, "Apagou mensagens em massa")

@bot.event
async def on_guild_update(antes, depois):
    if antes.name != depois.name or antes.icon != depois.icon:
        ex = await pegar_executor(depois, discord.AuditLogAction.guild_update)
        if ex and not is_protegido(ex):
            try: await depois.edit(name=antes.name, icon=antes.icon)
            except: pass
            await enviar_log(depois, "🏷️ Nome/Ícone Alterado", f"**Por:** <@{ex}> (`{ex}`)\n**Ação:** Nome/ícone restaurado", cor=0xFFA500)
            await punir(depois, ex, "Tentou mudar nome/icone do server")

# ===== COMANDOS =====

@bot.command()
async def protecoes(ctx):
    embed = discord.Embed(title="🛡️ ANTI-NUKE | Proteções Ativas", description="O servidor está protegido 24h. Qualquer ataque é revertido e o autor é banido na hora.", color=0x5865F2)
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else bot.user.display_avatar.url)
    embed.add_field(name="⚔️ Anti-Nuke", value="> 🚫 Mass Ban — 2 bans em 3s\n> 🚫 Mass Kick — 2 kicks em 3s\n> 🚫 Dar ADM via cargo\n> 🚫 Criar webhook suspeito", inline=False)
    embed.add_field(name="♻️ Backup Automático", value="> 📁 Canais deletados são recriados\n> 🎭 Cargos deletados são recriados\n> 🏷️ Nome e ícone do servidor restaurados", inline=False)
    embed.add_field(name="🛠️ Anti-Raid / Moderação", value="> 💬 Anti-Spam — 5 msgs em 3s = mute 10min\n> 🧹 Anti-apagar mensagens em massa\n> ✏️ Anti-renomear canais em massa", inline=False)
    embed.add_field(name="🎨 Anti-Vandalismo", value="> 😀 Anti-deletar emojis\n> 🌟 Anti-deletar stickers\n> ➕ Anti-criar / deletar canais e cargos em massa", inline=False)
    embed.add_field(name="📌 Comandos", value="`!protecoes` — Ver este painel", inline=False)
    embed.set_footer(text=f"Servidor: {ctx.guild.name} • Protegido por {bot.user.name}", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)

keep_alive()
bot.run(os.getenv("TOKEN"))
