import discord
from discord.ext import commands
import os, time
from collections import defaultdict
from datetime import timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== CONFIGURA =====
DONO_ID = 926223827590078504 # <-- COLOCA TEU ID AQUI
ADM_CONFIANCA = [] # IDs que NUNCA serão punidos
# =====================

def is_protegido(user_id):
    return user_id == DONO_ID or user_id in ADM_CONFIANCA

acoes = defaultdict(list)

def registrou(tipo, user_id, limite=3, janela=10):
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
        dono = await bot.fetch_user(DONO_ID)
        await dono.send(f"🚨 **ANTI-NUKE**\nServidor: {guild.name}\nBanido: {membro}\nMotivo: {motivo}")
    except Exception as e:
        print(f"Erro: {e}")

async def pegar_executor(guild, action):
    try:
        async for entry in guild.audit_logs(limit=1, action=action):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() < 5:
                return entry.user.id
    except:
        pass
    return None

@bot.event
async def on_ready():
    print(f"✅ ONLINE: {bot.user} | 15 PROTEÇÕES")
    await bot.change_presence(activity=discord.Game(name="🛡️ Protegendo sem atrapalhar"))

# ===== ANTI-SPAM + ANTI-EVERYONE (SEM BAN) =====
msgs = defaultdict(list)
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    if is_protegido(message.author.id):
        await bot.process_commands(message); return

    # 16. Anti-@everyone: SÓ APAGA, NÃO BANE
    if "@everyone" in message.content or "@here" in message.content:
        if not message.author.guild_permissions.administrator:
            await message.delete()
            await message.channel.send(f"{message.author.mention} ⚠️ Só ADM pode usar @everyone!", delete_after=3)
            return

    # Anti-spam: 5 msgs em 5s = mute 10 min (não é ban)
    agora = time.time()
    msgs[message.author.id].append(agora)
    msgs[message.author.id] = [t for t in msgs[message.author.id] if agora - t < 5]
    if len(msgs[message.author.id]) >= 5:
        msgs[message.author.id] = []
        try: await message.author.timeout(timedelta(minutes=10), reason="Spam")
        except: pass
        return
    await bot.process_commands(message)

@bot.event
async def on_member_ban(guild, user):
    ex = await pegar_executor(guild, discord.AuditLogAction.ban)
    if ex and registrou("ban", ex, 3, 10):
        await punir(guild, ex, "Baniu 3 em 10s")

@bot.event
async def on_member_remove(member):
    ex = await pegar_executor(member.guild, discord.AuditLogAction.kick)
    if ex and registrou("kick", ex, 3, 10):
        await punir(member.guild, ex, "Expulsou 3 em 10s")

@bot.event
async def on_guild_channel_create(channel):
    ex = await pegar_executor(channel.guild, discord.AuditLogAction.channel_create)
    if ex and registrou("canal_criar", ex, 3, 10):
        await punir(channel.guild, ex, "Criou 3 canais em 10s")

@bot.event
async def on_guild_channel_delete(channel):
    ex = await pegar_executor(channel.guild, discord.AuditLogAction.channel_delete)
    if ex and registrou("canal_del", ex, 3, 10):
        await punir(channel.guild, ex, "Deletou 3 canais em 10s")

@bot.event
async def on_guild_channel_update(antes, depois):
    if antes.name != depois.name:
        ex = await pegar_executor(depois.guild, discord.AuditLogAction.channel_update)
        if ex and registrou("canal_rename", ex, 3, 10):
            await punir(depois.guild, ex, "Renomeou 3 canais em 10s")

@bot.event
async def on_guild_role_create(role):
    ex = await pegar_executor(role.guild, discord.AuditLogAction.role_create)
    if ex and registrou("cargo_criar", ex, 3, 10):
        await punir(role.guild, ex, "Criou 3 cargos em 10s")

@bot.event
async def on_guild_role_delete(role):
    ex = await pegar_executor(role.guild, discord.AuditLogAction.role_delete)
    if ex and registrou("cargo_del", ex, 3, 10):
        await punir(role.guild, ex, "Deletou 3 cargos em 10s")

@bot.event
async def on_guild_role_update(antes, depois):
    if not antes.permissions.administrator and depois.permissions.administrator:
        ex = await pegar_executor(depois.guild, discord.AuditLogAction.role_update)
        if ex: await punir(depois.guild, ex, "Tentou dar ADM via cargo")

@bot.event
async def on_webhooks_update(channel):
    ex = await pegar_executor(channel.guild, discord.AuditLogAction.webhook_create)
    if ex and not is_protegido(ex):
        try:
            webs = await channel.webhooks()
            for w in webs:
                if w.user and w.user.id == ex: await w.delete()
        except: pass
        if registrou("webhook", ex, 2, 10):
            await punir(channel.guild, ex, "Criou webhooks suspeitos")

@bot.event
async def on_guild_emojis_update(guild, antes, depois):
    if len(depois) < len(antes) - 2:
        ex = await pegar_executor(guild, discord.AuditLogAction.emoji_delete)
        if ex: await punir(guild, ex, "Deletou vários emojis")

@bot.event
async def on_raw_bulk_message_delete(payload):
    if len(payload.cached_messages) >= 10 and payload.guild_id:
        guild = bot.get_guild(payload.guild_id)
        ex = await pegar_executor(guild, discord.AuditLogAction.message_bulk_delete)
        if ex: await punir(guild, ex, "Apagou muitas mensagens")

@bot.event
async def on_guild_update(antes, depois):
    if antes.name != depois.name or antes.icon != depois.icon:
        ex = await pegar_executor(depois, discord.AuditLogAction.guild_update)
        if ex and not is_protegido(ex):
            try: await depois.edit(name=antes.name, icon=antes.icon)
            except: pass
            await punir(depois, ex, "Tentou mudar nome/icone do server")

@bot.command()
@commands.has_permissions(administrator=True)
async def destravar(ctx):
    for c in ctx.guild.text_channels:
        await c.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("✅ Destravado!")

@bot.command()
async def protecoes(ctx):
    await ctx.send("🛡️ **15 Proteções:**\n1 Anti-Spam (só muta)\n2 Anti-@everyone (só apaga)\n3 Anti-Mass Ban\n4 Anti-Mass Kick\n5 Anti-Criar Canal\n6 Anti-Deletar Canal\n7 Anti-Renomear Canal\n8 Anti-Criar Cargo\n9 Anti-Deletar Cargo\n10 Anti-Dar ADM\n11 Anti-Webhook\n12 Anti-Deletar Emoji\n13 Anti-Apagar Mensagens\n14 Anti-Mudar Nome do Server\n15 Anti-Sticker / Anti-Emoji Spam")

bot.run(os.getenv("TOKEN"))
