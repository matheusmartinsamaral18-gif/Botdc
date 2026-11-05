import discord
from discord.ext import commands, tasks
import os
import time
import json
import asyncio
from collections import defaultdict
from datetime import timedelta

# =========================================================
# CONFIGURAÇÃO
# =========================================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

ADM_CONFIANCA = []
LOGS_CHANNEL_ID = 1567711809396277318
SOLO_DONO_CHANNEL_ID = 1567716695760703528
MEU_ID = 926223827590078504

# =========================================================
# PERMISSÕES / PROTEGIDOS
# =========================================================
def get_dono_id(guild):
    if guild is None:
        return None
    return guild.owner_id or (guild.owner.id if guild.owner else None)


def is_protegido(guild, user_id):
    if user_id == MEU_ID:
        return True
    if guild is not None and user_id == get_dono_id(guild):
        return True
    return user_id in ADM_CONFIANCA


# =========================================================
# BACKUP DUPLO: BOM (referência segura) + TEMP
# =========================================================
def backup_bom_path(guild_id):
    return f"backup_bom_{guild_id}.json"


def backup_temp_path(guild_id):
    return f"backup_temp_{guild_id}.json"


def backup_path(guild_id):
    return backup_bom_path(guild_id)


def _carregar_arquivo(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
                if isinstance(dados, dict):
                    dados.setdefault("canais", [])
                    dados.setdefault("cargos", [])
                    return dados
    except Exception as erro:
        print(f"Erro lendo {path}: {erro}")
    return {"canais": [], "cargos": []}


def _salvar_arquivo(path, dados):
    temporario = path + ".tmp"
    try:
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, indent=2, ensure_ascii=False)
        os.replace(temporario, path)
    except Exception as erro:
        print(f"Erro salvando {path}: {erro}")
        try:
            if os.path.exists(temporario):
                os.remove(temporario)
        except OSError:
            pass


def carregar_backup(guild_id):
    dados = _carregar_arquivo(backup_bom_path(guild_id))
    if not dados["canais"] and not dados["cargos"]:
        antigo = f"backup_{guild_id}.json"
        if os.path.exists(antigo):
            dados_antigos = _carregar_arquivo(antigo)
            if dados_antigos["canais"] or dados_antigos["cargos"]:
                dados = dados_antigos
                _salvar_arquivo(backup_bom_path(guild_id), dados)
                _salvar_arquivo(backup_temp_path(guild_id), dados)
    return dados


def carregar_backup_temp(guild_id):
    return _carregar_arquivo(backup_temp_path(guild_id))


def salvar_backup(guild_id, dados):
    _salvar_arquivo(backup_bom_path(guild_id), dados)


def salvar_backup_temp(guild_id, dados):
    _salvar_arquivo(backup_temp_path(guild_id), dados)


def salvar_backup_bom(guild_id, dados):
    _salvar_arquivo(backup_bom_path(guild_id), dados)


def snapshot_canal(ch):
    overwrites = []
    for alvo, permissao in ch.overwrites.items():
        allow, deny = permissao.pair()
        overwrites.append({
            "id": alvo.id,
            "is_role": isinstance(alvo, discord.Role),
            "allow": allow.value,
            "deny": deny.value
        })

    return {
        "id": ch.id,
        "name": ch.name,
        "type": str(ch.type),
        "position": ch.position,
        "category_id": ch.category_id,
        "topic": getattr(ch, "topic", None),
        "slowmode": getattr(ch, "slowmode_delay", 0),
        "nsfw": getattr(ch, "nsfw", False),
        "bitrate": getattr(ch, "bitrate", None),
        "user_limit": getattr(ch, "user_limit", None),
        "overwrites": overwrites
    }


def snapshot_cargo(role):
    return {
        "id": role.id,
        "name": role.name,
        "color": role.colour.value,
        "hoist": role.hoist,
        "mentionable": role.mentionable,
        "permissions": role.permissions.value,
        "position": role.position
    }


def tirar_foto_guild(guild):
    dados = {"canais": [], "cargos": []}

    for canal in guild.channels:
        dados["canais"].append(snapshot_canal(canal))

    for role in guild.roles:
        if (
            role.name != "@everyone"
            and not role.managed
            and (bot.user is None or role.name != bot.user.name)
        ):
            dados["cargos"].append(snapshot_cargo(role))

    return dados


# =========================================================
# ESTADO DO RAID POR SERVIDOR
# =========================================================
raid_state = {}
ja_banidos = {}  # ID -> horário; evita bloquear o mesmo ID para sempre
mensagens_processadas = set()
msgs = defaultdict(list)
acoes = defaultdict(list)


def novo_estado_raid():
    return {
        "ativo": False,
        "raider_id": None,
        "raider_nome": "Desconhecido",
        "canais_apagados_ids": set(),
        "cargos_apagados": [],
        "timer": None,
        "ultimo_ataque": 0,
        "canais_raid_criados": set(),
        "qtd_ataques": 0
    }


def get_raid(guild_id):
    if guild_id not in raid_state:
        raid_state[guild_id] = novo_estado_raid()
    return raid_state[guild_id]


def teve_raid_recente(guild_id, minutos=30):
    estado = get_raid(guild_id)
    if estado["ativo"]:
        return True
    if estado["ultimo_ataque"] == 0:
        return False
    return (time.time() - estado["ultimo_ataque"]) < minutos * 60


def registrou(tipo, user_id, limite=2, janela=3):
    agora = time.time()
    chave = (tipo, user_id)
    acoes[chave] = [t for t in acoes[chave] if agora - t < janela]
    acoes[chave].append(agora)
    return len(acoes[chave]) >= limite


# =========================================================
# BACKUP AUTOMÁTICO A CADA 30 MINUTOS
# =========================================================
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
            print(f"🔄 Backup BOM atualizado: {guild.name}")
        except Exception as erro:
            print(f"Erro sync backup {guild.name}: {erro}")


@sync_backup_loop.before_loop
async def antes_sync():
    await bot.wait_until_ready()


# =========================================================
# LOGS
# =========================================================
async def enviar_log_simples(guild, titulo, descricao, cor=0xFF0000):
    try:
        canal = guild.get_channel(LOGS_CHANNEL_ID)
        if canal is None:
            canal = await bot.fetch_channel(LOGS_CHANNEL_ID)

        if canal and hasattr(canal, "send"):
            embed = discord.Embed(
                title=titulo,
                description=descricao,
                color=cor,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Servidor: {guild.name}")
            await canal.send(embed=embed)
    except Exception as erro:
        print(f"Erro log canal: {erro}")

    if "Raid finalizado" not in titulo and "Banido" not in titulo:
        destinos = {MEU_ID}
        dono_id = get_dono_id(guild)
        if dono_id:
            destinos.add(dono_id)

        for user_id in destinos:
            try:
                usuario = await bot.fetch_user(user_id)
                await usuario.send(f"{titulo}\n{descricao}")
            except Exception:
                pass


async def enviar_log(guild, titulo, descricao, cor=0xFF0000):
    await enviar_log_simples(guild, titulo, descricao, cor)


# =========================================================
# AUDIT LOG: CONFERE O ALVO PARA NÃO PEGAR AÇÃO ERRADA
# =========================================================
async def pegar_executor(guild, action, target_id=None, janela=8):
    if guild is None:
        return None

    try:
        async for entrada in guild.audit_logs(limit=8, action=action):
            idade = (discord.utils.utcnow() - entrada.created_at).total_seconds()
            if idade < 0 or idade > janela:
                continue

            if entrada.user is None or entrada.user.id == bot.user.id:
                continue

            if target_id is not None:
                alvo = getattr(entrada, "target", None)
                if alvo is None or getattr(alvo, "id", None) != target_id:
                    continue

            return entrada.user.id
    except discord.Forbidden:
        print(f"Sem permissão para consultar Audit Log em {guild.name}.")
    except Exception as erro:
        print(f"Erro consultando Audit Log: {erro}")

    return None


# =========================================================
# RESTAURAÇÃO
# =========================================================
def agendar_recuperacao(guild):
    estado = get_raid(guild.id)

    if estado["timer"] and not estado["timer"].done():
        estado["timer"].cancel()

    async def esperar_e_restaurar():
        try:
            await asyncio.sleep(15)
            await restaurar_tudo(guild)
        except asyncio.CancelledError:
            pass
        except Exception as erro:
            print(f"Erro na tarefa de restauração: {erro}")

    estado["timer"] = asyncio.create_task(esperar_e_restaurar())


async def restaurar_tudo(guild):
    estado = get_raid(guild.id)
    if not estado["ativo"]:
        return

    print(f"♻️ Começando restauração em {guild.name}...")
    backup = carregar_backup(guild.id)

    canais_restaurados = 0
    canais_raid_apagados = 0
    canais_renomeados = 0
    cargos_restaurados = 0

    ids_backup = {c["id"] for c in backup["canais"]}

    # Mantém a limpeza de canais que não pertencem ao backup,
    # preservando os canais configurados para logs e comandos do dono.
    for canal in list(guild.channels):
        if canal.id not in ids_backup and canal.id not in estado["canais_apagados_ids"]:
            if canal.id in (LOGS_CHANNEL_ID, SOLO_DONO_CHANNEL_ID):
                continue
            try:
                await canal.delete(reason="Anti-Nuke: Limpando canal de raid")
                canais_raid_apagados += 1
                await asyncio.sleep(0.3)
            except Exception as erro:
                print(f"Erro limpando canal {canal.name}: {erro}")

    mapa_backup = {c["id"]: c for c in backup["canais"]}

    # Corrige nome, posição e configurações de canais existentes.
    for canal in list(guild.channels):
        if canal.id not in mapa_backup:
            continue

        dados = mapa_backup[canal.id]
        kwargs = {}

        if canal.name != dados["name"]:
            kwargs["name"] = dados["name"]
        if canal.position != dados["position"]:
            kwargs["position"] = dados["position"]

        if isinstance(canal, discord.TextChannel):
            if canal.topic != dados.get("topic"):
                kwargs["topic"] = dados.get("topic")
            if canal.slowmode_delay != dados.get("slowmode", 0):
                kwargs["slowmode_delay"] = dados.get("slowmode", 0)
            if canal.nsfw != dados.get("nsfw", False):
                kwargs["nsfw"] = dados.get("nsfw", False)

        if kwargs:
            try:
                await canal.edit(reason="Anti-Nuke: Restaurando nome/configuração", **kwargs)
                canais_renomeados += 1
                await asyncio.sleep(0.3)
            except Exception as erro:
                print(f"Erro corrigir canal {canal.name}: {erro}")

    # Recria canais ausentes. Categorias vêm primeiro para permitir associá-los.
    ordem_tipo = {"category": 0, "text": 1, "voice": 2}
    canais_ordenados = sorted(
        backup["canais"],
        key=lambda item: (ordem_tipo.get(item.get("type", ""), 3), item.get("position", 0))
    )

    canais_atuais_ids = {c.id for c in guild.channels}

    for dados in canais_ordenados:
        if dados["id"] in canais_atuais_ids:
            continue

        try:
            categoria = (
                guild.get_channel(dados.get("category_id"))
                if dados.get("category_id")
                else None
            )

            overwrites = {}
            for ow in dados.get("overwrites", []):
                if ow.get("is_role", False):
                    alvo = guild.get_role(ow["id"])
                else:
                    alvo = guild.get_member(ow["id"])

                if alvo is not None:
                    overwrites[alvo] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(ow["allow"]),
                        discord.Permissions(ow["deny"])
                    )

            tipo = dados.get("type", "")

            if "category" in tipo:
                await guild.create_category(
                    name=dados["name"],
                    position=dados.get("position", 0),
                    overwrites=overwrites,
                    reason="Anti-Nuke Restore"
                )
            elif "text" in tipo:
                await guild.create_text_channel(
                    name=dados["name"],
                    category=categoria,
                    position=dados.get("position", 0),
                    topic=dados.get("topic"),
                    slowmode_delay=dados.get("slowmode", 0),
                    nsfw=dados.get("nsfw", False),
                    overwrites=overwrites,
                    reason="Anti-Nuke Restore"
                )
            elif "voice" in tipo:
                await guild.create_voice_channel(
                    name=dados["name"],
                    category=categoria,
                    position=dados.get("position", 0),
                    bitrate=dados.get("bitrate") or 64000,
                    user_limit=dados.get("user_limit") or 0,
                    overwrites=overwrites,
                    reason="Anti-Nuke Restore"
                )
            else:
                continue

            canais_restaurados += 1
            await asyncio.sleep(0.4)

        except Exception as erro:
            print(f"Erro restaurar canal {dados.get('name')}: {erro}")

    # Recria cargos ausentes pelo nome (o Discord gera um ID novo).
    cargos_atuais = {role.name for role in guild.roles}
    for dados in backup["cargos"]:
        if dados["name"] in cargos_atuais:
            continue

        try:
            await guild.create_role(
                name=dados["name"],
                colour=discord.Colour(dados["color"]),
                hoist=dados["hoist"],
                mentionable=dados["mentionable"],
                permissions=discord.Permissions(dados["permissions"]),
                reason="Anti-Nuke Restore"
            )
            cargos_restaurados += 1
            await asyncio.sleep(0.3)
        except Exception as erro:
            print(f"Erro restaurar cargo {dados['name']}: {erro}")

    try:
        canal_logs = guild.get_channel(LOGS_CHANNEL_ID)
        if canal_logs:
            embed = discord.Embed(
                title="🛡️ Raid finalizado",
                description=(
                    f"**Raider:** {estado['raider_nome']} (`{estado['raider_id']}`)\n"
                    f"**Canais do raid apagados:** {canais_raid_apagados}\n"
                    f"**Canais restaurados:** {canais_restaurados}\n"
                    f"**Canais renomeados corrigidos:** {canais_renomeados}\n"
                    f"**Cargos restaurados:** {cargos_restaurados}\n"
                    f"**Tempo de espera:** 15s"
                ),
                color=0x2ECC71,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Servidor: {guild.name}")
            await canal_logs.send(embed=embed)
    except Exception as erro:
        print(f"Erro enviando relatório de restauração: {erro}")

    raid_state[guild.id] = novo_estado_raid()
    raid_state[guild.id]["ultimo_ataque"] = time.time()

    try:
        foto_limpa = tirar_foto_guild(guild)
        salvar_backup_temp(guild.id, foto_limpa)
    except Exception as erro:
        print(f"Erro atualizando backup temporário após raid: {erro}")

    print(f"✅ Restauração finalizada em {guild.name}")


# =========================================================
# BANIMENTO / ATIVAÇÃO DO RAID
# =========================================================
async def punir(guild, executor_id, motivo):
    if guild is None or executor_id is None:
        return False

    if is_protegido(guild, executor_id):
        return False

    # Ativa a recuperação antes da tentativa de ban.
    # Assim, falha de permissão no ban não deixa a restauração sem agendamento.
    estado = get_raid(guild.id)
    estado["ativo"] = True
    estado["raider_id"] = executor_id
    estado["ultimo_ataque"] = time.time()
    estado["qtd_ataques"] += 1

    if estado["timer"] is None or estado["timer"].done():
        try:
            usuario = await bot.fetch_user(executor_id)
            estado["raider_nome"] = str(usuario)
        except Exception:
            estado["raider_nome"] = f"ID {executor_id}"

    agendar_recuperacao(guild)

    # Evita tentar banir repetidamente o mesmo executor em sequência.
    agora = time.time()
    if executor_id in ja_banidos and agora - ja_banidos[executor_id] < 60:
        return False
    ja_banidos[executor_id] = agora

    try:
        membro = guild.get_member(executor_id)
        if membro is None:
            membro = await guild.fetch_member(executor_id)

        estado["raider_nome"] = str(membro)
        await guild.ban(membro, reason=f"ANTI-NUKE: {motivo}")
        print(f"🚨 Banido: {membro} - {motivo}")
        return True

    except discord.NotFound:
        # O usuário pode já ter saído. Tenta banir pelo objeto User.
        try:
            usuario = await bot.fetch_user(executor_id)
            await guild.ban(usuario, reason=f"ANTI-NUKE: {motivo}")
            print(f"🚨 Ban por ID: {executor_id} - {motivo}")
            return True
        except Exception as erro:
            print(f"Não foi possível banir ID {executor_id}: {erro}")
            return False

    except discord.Forbidden:
        print(f"Sem permissão para banir o executor {executor_id} em {guild.name}.")
        return False

    except Exception as erro:
        print(f"Erro punir: {erro}")
        return False


# =========================================================
# EVENTOS DE INICIALIZAÇÃO
# =========================================================
@bot.event
async def on_ready():
    print(f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP DUPLO 30min")
    await bot.change_presence(
        activity=discord.Game(name="🛡️ SYSTEM PROTECTING")
    )

    for guild in bot.guilds:
        try:
            if not os.path.exists(backup_bom_path(guild.id)):
                foto = tirar_foto_guild(guild)
                salvar_backup_bom(guild.id, foto)
                salvar_backup_temp(guild.id, foto)
                print(f"📸 Backup inicial criado: {guild.name}")
            elif not os.path.exists(backup_temp_path(guild.id)):
                salvar_backup_temp(guild.id, tirar_foto_guild(guild))
                print(f"📂 Backup TEMP criado: {guild.name}")
            else:
                print(f"📂 Backup BOM carregado: {guild.name}")
        except Exception as erro:
            print(f"Erro backup inicial {guild.name}: {erro}")

    if not sync_backup_loop.is_running():
        sync_backup_loop.start()


@bot.event
async def on_guild_join(guild):
    try:
        foto = tirar_foto_guild(guild)
        salvar_backup_bom(guild.id, foto)
        salvar_backup_temp(guild.id, foto)
        print(f"📸 Novo servidor, backup criado: {guild.name}")
    except Exception as erro:
        print(f"Erro criando backup do novo servidor: {erro}")


# =========================================================
# MENSAGENS / ANTI-SPAM / COMANDOS DESTE BOT
# Os comandos de outros bots (ex.: !mute e !create canal) não
# são implementados aqui. Mensagens de bots são ignoradas.
# =========================================================
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    if message.id in mensagens_processadas:
        return

    mensagens_processadas.add(message.id)
    if len(mensagens_processadas) > 5000:
        mensagens_processadas.clear()

    if message.channel.id == SOLO_DONO_CHANNEL_ID:
        if not is_protegido(message.guild, message.author.id):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return

        await bot.process_commands(message)
        return

    if message.channel.id == LOGS_CHANNEL_ID:
        if message.content.startswith("!") and is_protegido(message.guild, message.author.id):
            await bot.process_commands(message)
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return

    if is_protegido(message.guild, message.author.id):
        await bot.process_commands(message)
        return

    # Não conta comandos como spam. Isso evita punir quem usa comandos
    # destinados a outros bots no mesmo servidor.
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    agora = time.time()
    chave = (message.guild.id, message.author.id)
    msgs[chave] = [t for t in msgs[chave] if agora - t < 3]
    msgs[chave].append(agora)

    if len(msgs[chave]) >= 5:
        msgs[chave].clear()
        try:
            await message.author.timeout(
                timedelta(minutes=10),
                reason="Anti-Spam: 5 mensagens em 3 segundos"
            )
            await enviar_log(
                message.guild,
                "💬 Anti-Spam - Mute",
                f"**Usuário:** {message.author.mention} (`{message.author.id}`)\n"
                f"**Canal:** {message.channel.mention}\n"
                f"**Ação:** Mutado por 10 minutos (5 mensagens em 3s)",
                cor=0xFFA500
            )
        except discord.Forbidden:
            print(f"Sem permissão para aplicar timeout em {message.author}.")
        except Exception as erro:
            print(f"Erro no anti-spam: {erro}")
        return

    await bot.process_commands(message)


# =========================================================
# EVENTOS ANTI-NUKE
# =========================================================
@bot.event
async def on_member_ban(guild, user):
    executor = await pegar_executor(
        guild, discord.AuditLogAction.ban, target_id=user.id
    )
    if executor and registrou("ban", executor, 2, 3):
        await punir(guild, executor, "Baniu 2 membros em 3 segundos")


@bot.event
async def on_member_remove(member):
    executor = await pegar_executor(
        member.guild, discord.AuditLogAction.kick, target_id=member.id
    )
    if executor and registrou("kick", executor, 2, 3):
        await punir(member.guild, executor, "Expulsou 2 membros em 3 segundos")


@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    estado = get_raid(guild.id)

    if estado["ativo"]:
        estado["ultimo_ataque"] = time.time()
        estado["canais_raid_criados"].add(channel.id)
        agendar_recuperacao(guild)
        return

    try:
        dados = carregar_backup_temp(guild.id)
        if not any(c["id"] == channel.id for c in dados["canais"]):
            dados["canais"].append(snapshot_canal(channel))
            salvar_backup_temp(guild.id, dados)
    except Exception as erro:
        print(f"Erro atualizando backup TEMP de canal: {erro}")

    executor = await pegar_executor(
        guild, discord.AuditLogAction.channel_create, target_id=channel.id
    )
    if executor and registrou("canal_criar", executor, 2, 3):
        await punir(guild, executor, "Criou 2 canais em 3 segundos")


@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    estado = get_raid(guild.id)

    if estado["ativo"]:
        estado["ultimo_ataque"] = time.time()
        estado["canais_apagados_ids"].add(channel.id)
        agendar_recuperacao(guild)

        executor = await pegar_executor(
            guild, discord.AuditLogAction.channel_delete, target_id=channel.id
        )
        if executor and registrou("canal_del", executor, 2, 3):
            await punir(guild, executor, "Deletou 2 canais em 3 segundos")
        return

    executor = await pegar_executor(
        guild, discord.AuditLogAction.channel_delete, target_id=channel.id
    )

    try:
        dados = carregar_backup_temp(guild.id)
        dados["canais"] = [
            item for item in dados["canais"] if item["id"] != channel.id
        ]
        salvar_backup_temp(guild.id, dados)
    except Exception as erro:
        print(f"Erro removendo canal do backup TEMP: {erro}")

    if executor and not is_protegido(guild, executor) and executor != bot.user.id:
        try:
            categoria = channel.category
            overwrites = channel.overwrites

            if isinstance(channel, discord.TextChannel):
                novo = await guild.create_text_channel(
                    name=channel.name,
                    category=categoria,
                    position=channel.position,
                    topic=channel.topic,
                    slowmode_delay=channel.slowmode_delay,
                    nsfw=channel.nsfw,
                    overwrites=overwrites,
                    reason="BACKUP Anti-Nuke"
                )
            elif isinstance(channel, discord.VoiceChannel):
                novo = await guild.create_voice_channel(
                    name=channel.name,
                    category=categoria,
                    position=channel.position,
                    bitrate=channel.bitrate,
                    user_limit=channel.user_limit,
                    overwrites=overwrites,
                    reason="BACKUP Anti-Nuke"
                )
            elif isinstance(channel, discord.CategoryChannel):
                novo = await guild.create_category(
                    name=channel.name,
                    position=channel.position,
                    overwrites=overwrites,
                    reason="BACKUP Anti-Nuke"
                )
            else:
                novo = None

            if novo:
                print(f"♻️ BACKUP: Canal #{channel.name} recriado!")
                await enviar_log(
                    guild,
                    "♻️ Backup - Canal Recriado",
                    f"**Canal:** #{channel.name}\n"
                    f"**Deletado por:** <@{executor}> (`{executor}`)\n"
                    f"**Ação:** Canal recriado automaticamente",
                    cor=0x2ECC71
                )
        except Exception as erro:
            print(f"Erro backup canal: {erro}")

    if executor and registrou("canal_del", executor, 2, 3):
        await punir(guild, executor, "Deletou 2 canais em 3 segundos")


@bot.event
async def on_guild_channel_update(antes, depois):
    estado = get_raid(depois.guild.id)
    if estado["ativo"]:
        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(depois.guild)
        return

    mudou = (
        antes.name != depois.name
        or antes.position != depois.position
        or getattr(antes, "topic", None) != getattr(depois, "topic", None)
    )

    if mudou:
        try:
            dados = carregar_backup_temp(depois.guild.id)
            encontrado = False

            for indice, item in enumerate(dados["canais"]):
                if item["id"] == depois.id:
                    dados["canais"][indice] = snapshot_canal(depois)
                    encontrado = True
                    break

            if not encontrado:
                dados["canais"].append(snapshot_canal(depois))

            salvar_backup_temp(depois.guild.id, dados)
        except Exception as erro:
            print(f"Erro atualizando canal no backup TEMP: {erro}")

    executor = await pegar_executor(
        depois.guild,
        discord.AuditLogAction.channel_update,
        target_id=depois.id
    )
    if executor and registrou("canal_rename", executor, 2, 3):
        await punir(depois.guild, executor, "Alterou 2 canais em 3 segundos")


@bot.event
async def on_guild_role_create(role):
    estado = get_raid(role.guild.id)
    if estado["ativo"]:
        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(role.guild)
        return

    try:
        dados = carregar_backup_temp(role.guild.id)
        if not any(item["id"] == role.id for item in dados["cargos"]):
            dados["cargos"].append(snapshot_cargo(role))
            salvar_backup_temp(role.guild.id, dados)
    except Exception as erro:
        print(f"Erro atualizando backup TEMP de cargo: {erro}")

    executor = await pegar_executor(
        role.guild, discord.AuditLogAction.role_create, target_id=role.id
    )
    if executor and registrou("cargo_criar", executor, 2, 3):
        await punir(role.guild, executor, "Criou 2 cargos em 3 segundos")


@bot.event
async def on_guild_role_delete(role):
    estado = get_raid(role.guild.id)
    if estado["ativo"]:
        estado["ultimo_ataque"] = time.time()
        estado["cargos_apagados"].append(role.name)
        agendar_recuperacao(role.guild)
        return

    executor = await pegar_executor(
        role.guild, discord.AuditLogAction.role_delete, target_id=role.id
    )

    try:
        dados = carregar_backup_temp(role.guild.id)
        dados["cargos"] = [
            item for item in dados["cargos"] if item["id"] != role.id
        ]
        salvar_backup_temp(role.guild.id, dados)
    except Exception as erro:
        print(f"Erro removendo cargo do backup TEMP: {erro}")

    if (
        executor
        and not is_protegido(role.guild, executor)
        and executor != bot.user.id
        and role.name != "@everyone"
    ):
        try:
            await role.guild.create_role(
                name=role.name,
                colour=role.colour,
                hoist=role.hoist,
                mentionable=role.mentionable,
                permissions=role.permissions,
                reason="BACKUP Anti-Nuke"
            )
            print(f"♻️ BACKUP: Cargo {role.name} recriado!")
            await enviar_log(
                role.guild,
                "♻️ Backup - Cargo Recriado",
                f"**Cargo:** {role.name}\n"
                f"**Deletado por:** <@{executor}> (`{executor}`)\n"
                f"**Ação:** Cargo recriado automaticamente",
                cor=0x2ECC71
            )
        except Exception as erro:
            print(f"Erro backup cargo: {erro}")

    if executor and registrou("cargo_del", executor, 2, 3):
        await punir(role.guild, executor, "Deletou 2 cargos em 3 segundos")


@bot.event
async def on_guild_role_update(antes, depois):
    if (
        not antes.permissions.administrator
        and depois.permissions.administrator
    ):
        executor = await pegar_executor(
            depois.guild,
            discord.AuditLogAction.role_update,
            target_id=depois.id
        )
        if executor:
            await enviar_log(
                depois.guild,
                "⚠️ Tentativa de dar ADM",
                f"**Por:** <@{executor}> (`{executor}`)\n"
                f"**Cargo:** {depois.name}\n"
                f"**Ação:** Tentou dar ADM via cargo",
                cor=0xFFA500
            )
            await punir(depois.guild, executor, "Tentou dar ADM via cargo")


@bot.event
async def on_webhooks_update(channel):
    executor = await pegar_executor(
        channel.guild, discord.AuditLogAction.webhook_create
    )
    if executor and not is_protegido(channel.guild, executor):
        try:
            webhooks = await channel.webhooks()
            for webhook in webhooks:
                if webhook.user and webhook.user.id == executor:
                    await webhook.delete(reason="Anti-Nuke: webhook suspeito")
        except Exception as erro:
            print(f"Erro removendo webhook: {erro}")

        await punir(channel.guild, executor, "Criou webhook suspeito")


@bot.event
async def on_guild_emojis_update(guild, antes, depois):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild, discord.AuditLogAction.emoji_delete
        )
        if executor and registrou("emoji", executor, 2, 3):
            await punir(guild, executor, "Deletou emojis em massa")


@bot.event
async def on_guild_stickers_update(guild, antes, depois):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild, discord.AuditLogAction.sticker_delete
        )
        if executor:
            await punir(guild, executor, "Deletou sticker")


@bot.event
async def on_raw_bulk_message_delete(payload):
    if len(payload.cached_messages) >= 5 and payload.guild_id:
        guild = bot.get_guild(payload.guild_id)
        if guild is None:
            return

        executor = await pegar_executor(
            guild, discord.AuditLogAction.message_bulk_delete
        )
        if executor:
            await punir(guild, executor, "Apagou mensagens em massa")


@bot.event
async def on_guild_update(antes, depois):
    if antes.name != depois.name or antes.icon != depois.icon:
        executor = await pegar_executor(
            depois, discord.AuditLogAction.guild_update
        )

        if executor and not is_protegido(depois, executor):
            try:
                # Guild.edit espera bytes para o ícone, não um objeto Asset.
                icone_bytes = await antes.icon.read() if antes.icon else None
                await depois.edit(
                    name=antes.name,
                    icon=icone_bytes,
                    reason="Anti-Nuke: restaurando nome/ícone"
                )
            except Exception as erro:
                print(f"Erro restaurando nome/ícone: {erro}")

            await enviar_log(
                depois,
                "🏷️ Nome/Ícone Alterado",
                f"**Por:** <@{executor}> (`{executor}`)\n"
                f"**Ação:** Nome/ícone restaurado",
                cor=0xFFA500
            )
            await punir(depois, executor, "Tentou mudar nome/ícone do servidor")


# =========================================================
# COMANDOS DO ANTI-NUKE
# =========================================================
@bot.command()
async def protecoes(ctx):
    embed = discord.Embed(
        title="🛡️ ANTI-NUKE | Proteções Ativas",
        description=(
            "O servidor está protegido 24h. Ataques identificados são "
            "registrados e as estruturas salvas são restauradas."
        ),
        color=0x5865F2
    )

    embed.set_thumbnail(
        url=ctx.guild.icon.url if ctx.guild.icon else bot.user.display_avatar.url
    )
    embed.add_field(
        name="⚔️ Anti-Nuke",
        value=(
            "> 🚫 Mass Ban — 2 bans em 3s\n"
            "> 🚫 Mass Kick — 2 kicks em 3s\n"
            "> 🚫 Dar ADM via cargo\n"
            "> 🚫 Criar webhook suspeito"
        ),
        inline=False
    )
    embed.add_field(
        name="♻️ Backup Automático",
        value=(
            "> 📁 Canais deletados são recriados\n"
            "> 🎭 Cargos deletados são recriados\n"
            "> 🏷️ Nome e ícone do servidor restaurados"
        ),
        inline=False
    )
    embed.add_field(
        name="🛠️ Anti-Raid / Moderação",
        value=(
            "> 💬 Anti-Spam — 5 mensagens em 3s = mute 10min\n"
            "> 🧹 Anti-apagar mensagens em massa\n"
            "> ✏️ Anti-renomear canais em massa"
        ),
        inline=False
    )
    embed.add_field(
        name="🎨 Anti-Vandalismo",
        value=(
            "> 😀 Anti-deletar emojis\n"
            "> 🌟 Anti-deletar stickers\n"
            "> ➕ Anti-criar/deletar canais e cargos em massa"
        ),
        inline=False
    )
    embed.add_field(
        name="📌 Comandos",
        value="`!protecoes` — Ver este painel",
        inline=False
    )
    embed.set_footer(
        text=f"Servidor: {ctx.guild.name} • Protegido por {bot.user.name}",
        icon_url=bot.user.display_avatar.url
    )
    await ctx.send(embed=embed)


@bot.command(
    name="atualizar",
    aliases=["atualizarbackup", "backup", "salvar"]
)
async def atualizar_backup(ctx, *, arg: str = ""):
    if not is_protegido(ctx.guild, ctx.author.id):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        return

    if ctx.invoked_with in ("backup", "salvar"):
        arg = "backup"

    if arg.strip().lower() not in ("backup", ""):
        await ctx.send("Usa assim: `!atualizar backup`", delete_after=5)
        return

    estado = get_raid(ctx.guild.id)
    if estado["ativo"]:
        await ctx.send(
            "⚠️ Há uma raid em andamento. O backup BOM não será atualizado.",
            delete_after=8
        )
        return

    try:
        foto = tirar_foto_guild(ctx.guild)
        salvar_backup_bom(ctx.guild.id, foto)
        salvar_backup_temp(ctx.guild.id, foto)

        await ctx.send(
            f"✅ Backup BOM atualizado! **{len(foto['canais'])} canais** "
            f"e **{len(foto['cargos'])} cargos** salvos.",
            delete_after=8
        )
        print(f"✅ Backup atualizado por {ctx.author} em {ctx.guild.name}")
    except Exception as erro:
        await ctx.send(f"❌ Erro ao atualizar backup: {erro}", delete_after=8)


@bot.command(name="limpar")
async def limpar(ctx, quantidade: int = 0):
    if not is_protegido(ctx.guild, ctx.author.id):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        return

    if quantidade <= 0 or quantidade > 1000:
        await ctx.send(
            "Usa assim: `!limpar 100` — número entre 1 e 1000",
            delete_after=5
        )
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        return

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

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
        except Exception as erro:
            print(f"Erro limpar: {erro}")
            break

    await ctx.send(
        f"🧹 Limpas **{apagadas}** mensagens!",
        delete_after=5
    )


# =========================================================
# TOKEN
# =========================================================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("A variável de ambiente TOKEN não foi configurada.")

bot.run(TOKEN)
