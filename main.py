import discord
from discord.ext import commands
import os, time, json, asyncio
from collections import defaultdict
from datetime import timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== CONFIGURA - NÃO MEXI =====
ADM_CONFIANCA = []
LOGS_CHANNEL_ID = 1567711809396277318
SOLO_DONO_CHANNEL_ID = 1567716695760703528
# DONO removido - agora pega automaticamente do servidor
# =====================

def get_dono_id(guild):
    if guild is None:
        return None
    # guild.owner_id já vem do Discord, sem precisar de ID fixo
    if guild.owner_id:
        return guild.owner_id
    if guild.owner:
        return guild.owner.id
    return None

def is_protegido(guild, user_id):
    if guild is not None and user_id == get_dono_id(guild):
        return True
    return user_id in ADM_CONFIANCA

# ===== 12. BACKUP POR SERVIDOR - ARQUIVO SEPARADO AUTOMATICO =====
def backup_path(guild_id):
    return f"backup_{guild_id}.json"

def carregar_backup(guild_id):
    try:
        if os.path.exists(backup_path(guild_id)):
            with open(backup_path(guild_id), "r", encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return {"canais": [], "cargos": []}

def salvar_backup(guild_id, dados):
    try:
        with open(backup_path(guild_id), "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erro salvar backup {guild_id}: {e}")

def snapshot_canal(ch):
    return {
        "id": ch.id, "name": ch.name, "type": str(ch.type),
        "position": ch.position,
        "category_id": ch.category_id,
        "topic": getattr(ch, "topic", None),
        "slowmode": getattr(ch, "slowmode_delay", 0),
        "nsfw": getattr(ch, "nsfw", False),
        "bitrate": getattr(ch, "bitrate", None),
        "user_limit": getattr(ch, "user_limit", None),
        # CORRIGIDO: Role não tem .type, usa is_role
        "overwrites": [{"id": k.id, "is_role": isinstance(k, discord.Role), "allow": v.pair()[0].value, "deny": v.pair()[1].value} for k, v in ch.overwrites.items()]
    }

def snapshot_cargo(r):
    return {
        "id": r.id, "name": r.name, "color": r.colour.value,
        "hoist": r.hoist, "mentionable": r.mentionable,
        "permissions": r.permissions.value, "position": r.position
    }

def tirar_foto_guild(guild):
    dados = {"canais": [], "cargos": []}
    for ch in guild.channels:
        dados["canais"].append(snapshot_canal(ch))
    for r in guild.roles:
        if r.name != "@everyone" and not r.managed and r.name != bot.user.name:
            dados["cargos"].append(snapshot_cargo(r))
    return dados

# ===== ESTADO DO RAID POR SERVIDOR =====
raid_state = {}
ja_banidos = set()
mensagens_processadas = set()

def get_raid(guild_id):
    if guild_id not in raid_state:
        raid_state[guild_id] = {"ativo": False, "raider_id": None, "raider_nome": "Desconhecido", "canais_apagados_ids": set(), "cargos_apagados": [], "timer": None, "ultimo_ataque": 0, "canais_raid_criados": set(), "qtd_ataques": 0}
    return raid_state[guild_id]

# ===== LOG UNICO - 10. SÓ 1 LOG NO FINAL =====
async def enviar_log_simples(guild, titulo, descricao, cor=0xFF0000):
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
    if "Raid finalizado" not in titulo and "Banido" not in titulo:
        try:
            dono_id = get_dono_id(guild)
            if dono_id:
                dono = await bot.fetch_user(dono_id)
                await dono.send(f"{titulo}\n{descricao}")
        except: pass

async def enviar_log(guild, titulo, descricao, cor=0xFF0000):
    await enviar_log_simples(guild, titulo, descricao, cor)

acoes = defaultdict(list)

def registrou(tipo, user_id, limite=2, janela=3):
    agora = time.time()
    chave = (tipo, user_id)
    acoes[chave].append(agora)
    acoes[chave] = [t for t in acoes[chave] if agora - t < janela]
    return len(acoes[chave]) >= limite

# ===== 1. BAN PRIMEIRO - RAPIDO, SEM ESPERAR =====
async def punir(guild, executor_id, motivo):
    if is_protegido(guild, executor_id):
        return False
    if executor_id in ja_banidos:
        return False
    ja_banidos.add(executor_id)
    try:
        membro = await guild.fetch_member(executor_id)
        nome = str(membro)
    except:
        nome = f"ID {executor_id}"
        try:
            user = await bot.fetch_user(executor_id)
            await guild.ban(user, reason=f"ANTI-NUKE: {motivo}")
            print(f"🚨 Ban por ID: {nome} - {motivo}")
            return True
        except Exception as e:
            if "Unknown" in str(e) or "404" in str(e) or "10007" in str(e):
                return False
            print(f"Erro punir (ignorado): {e}")
            return False
    try:
        await guild.ban(membro, reason=f"ANTI-NUKE: {motivo}")
        print(f"🚨 Banido rápido: {nome} - {motivo}")
        st = get_raid(guild.id)
        st["ativo"] = True
        st["raider_id"] = executor_id
        st["raider_nome"] = nome
        st["ultimo_ataque"] = time.time()
        st["qtd_ataques"] += 1
        agendar_recuperacao(guild)
        return True
    except Exception as e:
        if "Unknown" in str(e) or "404" in str(e) or "10007" in str(e) or "Missing Permissions" in str(e):
            return False
        print(f"Erro punir: {e}")
        return False

async def pegar_executor(guild, action):
    try:
        async for entry in guild.audit_logs(limit=3, action=action):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() < 3:
                if entry.user.id != bot.user.id:
                    return entry.user.id
    except: pass
    return None

# ===== 4 + 5 + 6 + 7. ESPERAR PARAR E RESTAURAR =====
def agendar_recuperacao(guild):
    st = get_raid(guild.id)
    if st["timer"] and not st["timer"].done():
        st["timer"].cancel()
    async def esperar_e_restaurar():
        try:
            await asyncio.sleep(15)
            await restaurar_tudo(guild)
        except asyncio.CancelledError:
            pass
    st["timer"] = asyncio.create_task(esperar_e_restaurar())

async def restaurar_tudo(guild):
    st = get_raid(guild.id)
    if not st["ativo"]:
        return
    print(f"♻️ Começando restauração em {guild.name}...")
    backup = carregar_backup(guild.id)
    canais_restaurados = 0
    canais_raid_apagados = 0
    cargos_restaurados = 0

    ids_backup = {c["id"] for c in backup["canais"]}
    for ch in list(guild.channels):
        if ch.id not in ids_backup and ch.id not in st["canais_apagados_ids"]:
            if ch.id in [LOGS_CHANNEL_ID, SOLO_DONO_CHANNEL_ID]:
                continue
            try:
                await ch.delete(reason="Anti-Nuke: Limpando canal de raid")
                canais_raid_apagados += 1
                await asyncio.sleep(0.3)
            except: pass

    canais_atuais_ids = {c.id for c in guild.channels}
    for cdata in sorted(backup["canais"], key=lambda x: x["position"]):
        if cdata["id"] not in canais_atuais_ids:
            try:
                categoria = guild.get_channel(cdata["category_id"]) if cdata["category_id"] else None
                overwrites = {}
                for ow in cdata["overwrites"]:
                    # CORRIGIDO: usa is_role, com fallback pra backup antigo
                    if "is_role" in ow:
                        alvo = guild.get_role(ow["id"]) if ow["is_role"] else guild.get_member(ow["id"])
                    else:
                        alvo = guild.get_role(ow["id"]) or guild.get_member(ow["id"])
                    if alvo:
                        overwrites[alvo] = discord.PermissionOverwrite.from_pair(discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"]))
                tipo = cdata["type"]
                if "text" in tipo:
                    await guild.create_text_channel(name=cdata["name"], category=categoria, position=cdata["position"], topic=cdata["topic"], slowmode_delay=cdata["slowmode"], nsfw=cdata["nsfw"], overwrites=overwrites, reason="Anti-Nuke Restore")
                elif "voice" in tipo:
                    await guild.create_voice_channel(name=cdata["name"], category=categoria, position=cdata["position"], bitrate=cdata["bitrate"] or 64000, user_limit=cdata["user_limit"] or 0, overwrites=overwrites, reason="Anti-Nuke Restore")
                elif "category" in tipo:
                    await guild.create_category(name=cdata["name"], position=cdata["position"], overwrites=overwrites, reason="Anti-Nuke Restore")
                canais_restaurados += 1
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"Erro restaurar canal {cdata['name']}: {e}")

    cargos_atuais = {r.name for r in guild.roles}
    for rdata in backup["cargos"]:
        if rdata["name"] not in cargos_atuais:
            try:
                await guild.create_role(name=rdata["name"], colour=discord.Colour(rdata["color"]), hoist=rdata["hoist"], mentionable=rdata["mentionable"], permissions=discord.Permissions(rdata["permissions"]), reason="Anti-Nuke Restore")
                cargos_restaurados += 1
                await asyncio.sleep(0.3)
            except: pass

    try:
        canal = guild.get_channel(LOGS_CHANNEL_ID)
        if canal:
            embed = discord.Embed(title="🛡️ Raid finalizado", description=f"**Raider:** {st['raider_nome']} (`{st['raider_id']}`)\n**Canais do raid apagados:** {canais_raid_apagados}\n**Canais restaurados:** {canais_restaurados}\n**Cargos restaurados:** {cargos_restaurados}\n**Tempo de espera:** 15s", color=0x2ecc71, timestamp=discord.utils.utcnow())
            embed.set_footer(text=f"Servidor: {guild.name}")
            await canal.send(embed=embed)
    except: pass

    raid_state[guild.id] = {"ativo": False, "raider_id": None, "raider_nome": "Desconhecido", "canais_apagados_ids": set(), "cargos_apagados": [], "timer": None, "ultimo_ataque": 0, "canais_raid_criados": set(), "qtd_ataques": 0}
    try:
        salvar_backup(guild.id, tirar_foto_guild(guild))
    except: pass
    print(f"✅ Restauração finalizada em {guild.name}")

@bot.event
async def on_ready():
    print(f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP 3s")
    await bot.change_presence(activity=discord.Game(name="🛡️ SYSTEM PROTECTING"))
    for guild in bot.guilds:
        try:
            if not os.path.exists(backup_path(guild.id)):
                salvar_backup(guild.id, tirar_foto_guild(guild))
                print(f"📸 Backup inicial criado: backup_{guild.id}.json - {guild.name}")
            else:
                print(f"📂 Backup carregado: {guild.name}")
        except Exception as e:
            print(f"Erro backup inicial {guild.name}: {e}")

@bot.event
async def on_guild_join(guild):
    try:
        salvar_backup(guild.id, tirar_foto_guild(guild))
        print(f"📸 Novo servidor, backup criado: {guild.name}")
    except: pass

msgs = defaultdict(list)
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    if message.id in mensagens_processadas:
        return
    mensagens_processadas.add(message.id)
    if len(mensagens_processadas) > 500:
        mensagens_processadas.clear()
        mensagens_processadas.add(message.id)

    if message.channel.id == SOLO_DONO_CHANNEL_ID:
        if message.author.id != get_dono_id(message.guild):
            try: await message.delete()
            except: pass
            return
        await bot.process_commands(message)
        return

    if message.channel.id == LOGS_CHANNEL_ID:
        try: await message.delete()
        except: pass
        if message.content.startswith("!"):
            await bot.process_commands(message)
        return

    if is_protegido(message.guild, message.author.id):
        await bot.process_commands(message)
        return

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
    guild = channel.guild
    st = get_raid(guild.id)
    if st["ativo"]:
        st["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)
        return
    try:
        dados = carregar_backup(guild.id)
        if not any(c["id"] == channel.id for c in dados["canais"]):
            dados["canais"].append(snapshot_canal(channel))
            salvar_backup(guild.id, dados)
    except: pass
    ex = await pegar_executor(guild, discord.AuditLogAction.channel_create)
    if ex and registrou("canal_criar", ex, 2, 3):
        await punir(guild, ex, "Criou 2 canais em 3s")

@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    st = get_raid(guild.id)
    if st["ativo"]:
        st["ultimo_ataque"] = time.time()
        st["canais_apagados_ids"].add(channel.id)
        agendar_recuperacao(guild)
        ex2 = await pegar_executor(guild, discord.AuditLogAction.channel_delete)
        if ex2 and registrou("canal_del", ex2, 2, 3):
            await punir(guild, ex2, "Deletou 2 canais em 3s")
        return

    ex = await pegar_executor(guild, discord.AuditLogAction.channel_delete)
    try:
        dados = carregar_backup(guild.id)
        dados["canais"] = [c for c in dados["canais"] if c["id"] != channel.id]
        salvar_backup(guild.id, dados)
    except: pass

    if ex and not is_protegido(guild, ex) and ex != bot.user.id:
        try:
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
        await punir(guild, ex, "Deletou 2 canais em 3s")

@bot.event
async def on_guild_channel_update(antes, depois):
    if antes.name != depois.name:
        ex = await pegar_executor(depois.guild, discord.AuditLogAction.channel_update)
        if ex and registrou("canal_rename", ex, 2, 3):
            await punir(depois.guild, ex, "Renomeou 2 canais em 3s")
    else:
        st = get_raid(depois.guild.id)
        if not st["ativo"]:
            try:
                dados = carregar_backup(depois.guild.id)
                for i, c in enumerate(dados["canais"]):
                    if c["id"] == depois.id:
                        dados["canais"][i] = snapshot_canal(depois)
                        break
                salvar_backup(depois.guild.id, dados)
            except: pass

@bot.event
async def on_guild_role_create(role):
    st = get_raid(role.guild.id)
    if st["ativo"]:
        st["ultimo_ataque"] = time.time()
        agendar_recuperacao(role.guild)
        return
    try:
        dados = carregar_backup(role.guild.id)
        if not any(r["id"] == role.id for r in dados["cargos"]):
            dados["cargos"].append(snapshot_cargo(role))
            salvar_backup(role.guild.id, dados)
    except: pass
    ex = await pegar_executor(role.guild, discord.AuditLogAction.role_create)
    if ex and registrou("cargo_criar", ex, 2, 3):
        await punir(role.guild, ex, "Criou 2 cargos em 3s")

@bot.event
async def on_guild_role_delete(role):
    st = get_raid(role.guild.id)
    if st["ativo"]:
        st["ultimo_ataque"] = time.time()
        agendar_recuperacao(role.guild)
        return
    ex = await pegar_executor(role.guild, discord.AuditLogAction.role_delete)
    try:
        dados = carregar_backup(role.guild.id)
        dados["cargos"] = [r for r in dados["cargos"] if r["id"] != role.id]
        salvar_backup(role.guild.id, dados)
    except: pass
    if ex and not is_protegido(role.guild, ex) and ex != bot.user.id and role.name != "@everyone":
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
    if ex and not is_protegido(channel.guild, ex):
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
        if ex and not is_protegido(depois, ex):
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
    # REMOVIDO: !limpar não aparece mais aqui, só dono sabe
    embed.add_field(name="📌 Comandos", value="`!protecoes` — Ver este painel", inline=False)
    embed.set_footer(text=f"Servidor: {ctx.guild.name} • Protegido por {bot.user.name}", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)

# 11. COMANDO LIMPAR - SÓ DONO DO SERVIDOR (automatico)
@bot.command(name="limpar")
async def limpar(ctx, quantidade: int = 0):
    if ctx.author.id != get_dono_id(ctx.guild):
        try: await ctx.message.delete()
        except: pass
        return
    if quantidade <= 0 or quantidade > 1000:
        await ctx.send("Usa assim: `!limpar 100` - número entre 1 e 1000", delete_after=5)
        try: await ctx.message.delete()
        except: pass
        return
    try: await ctx.message.delete()
    except: pass
    apagadas = 0
    restante = quantidade
    while restante > 0:
        lote = min(restante, 100)
        try:
            deletadas = await ctx.channel.purge(limit=lote)
            apagadas += len(deletadas)
            restante -= lote
            if len(deletadas) < lote:
                break
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Erro limpar: {e}")
            break
    msg = await ctx.send(f"🧹 Limpas **{apagadas}** mensagens!", delete_after=5)

bot.run(os.getenv("TOKEN"))
