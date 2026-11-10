import discord
from discord.ext import commands, tasks
import os
import time
import json
import asyncio
import inspect
import io
import re
from collections import defaultdict
from datetime import timedelta, datetime, timezone

# =========================================================
# CONFIGURAÇÃO
# =========================================================

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

ADM_CONFIANCA = []
LOGS_CHANNEL_ID = 1567711809396277318
SOLO_DONO_CHANNEL_ID = 1567716695760703528
MEU_ID = 926223827590078504

JANELA_RAID = 2

# ---------------------------------------------------------
# DETECÇÃO DE AÇÃO EM MASSA
# (quantidade de ações, janela em segundos)
# Ação isolada NUNCA aciona nada: só passa do limite = em massa.
# ---------------------------------------------------------
LIMITE_PADRAO_MASSA = (4, 2)

LIMITES_MASSA = {
    "ban": (4, 2),
    "kick": (4, 2),
    "canal_criar": (4, 2),
    "canal_del": (4, 2),
    "canal_update": (4, 2),
    "cargo_criar": (4, 2),
    "cargo_del": (4, 2),
    "cargo_update": (4, 2),
    "emoji": (4, 2),
    "sticker": (4, 2),
    "webhook": (4, 2),
    "msg_massa": (4, 2),
    "guild_update": (3, 5),
}

# Soma de QUALQUER ações destrutivas misturadas do mesmo executor.
LIMITE_COMBINADO = (6, 3)

# ---------------------------------------------------------
# BACKUP DE MENSAGENS E CONFIGURAÇÕES
# ---------------------------------------------------------
MSG_POR_CANAL = 20
INTERVALO_BACKUP_MIN = 30
INTERVALO_AUDIT = 0.35
MAX_TENTATIVAS_AUDIT = 4

TEMPO_ALERTA_TICKET = 30 * 60
TEMPO_FECHAMENTO_INATIVIDADE_TICKET = 3 * 60 * 60

VIEWS_REGISTRADAS = False

# Locks para evitar dois tickets com o mesmo número.
locks_tickets = defaultdict(asyncio.Lock)
locks_restauracao = defaultdict(asyncio.Lock)


# =========================================================
# MAPA DE IDS DOS CANAIS
# =========================================================

def arquivo_mapa_canais(guild_id):
    return f"mapa_canais_{guild_id}.json"


def carregar_mapa_canais(guild_id):
    try:
        with open(arquivo_mapa_canais(guild_id), "r", encoding="utf-8") as f:
            dados = json.load(f)
            if isinstance(dados, dict):
                return dados
    except Exception:
        pass

    return {}


def salvar_mapa_canais(guild_id, mapa):
    try:
        with open(arquivo_mapa_canais(guild_id), "w", encoding="utf-8") as f:
            json.dump(mapa, f, indent=2)
        return True
    except Exception as erro:
        print(f"Erro salvando mapa de canais: {erro}")
        return False


def registrar_novo_id_canal(guild_id, id_antigo, id_novo):
    mapa = carregar_mapa_canais(guild_id)
    mapa[str(id_antigo)] = id_novo
    salvar_mapa_canais(guild_id, mapa)


def resolver_canal_configurado(guild, id_original):
    mapa = carregar_mapa_canais(guild.id)
    id_atual = mapa.get(str(id_original), id_original)
    return guild.get_channel(int(id_atual))


# =========================================================
# PERMISSÕES / PROTEGIDOS
# =========================================================

def get_dono_id(guild):
    if guild is None:
        return None

    return guild.owner_id or (
        guild.owner.id if guild.owner else None
    )


def is_protegido(guild, user_id):
    if user_id is None:
        return False

    if user_id == MEU_ID:
        return True

    if guild and user_id == get_dono_id(guild):
        return True

    return user_id in ADM_CONFIANCA


def permissao_bot(guild):
    membro = guild.me
    return membro.guild_permissions if membro else None


# =========================================================
# SISTEMA DE BACKUP UNIFICADO (Canais, Cargos e Mensagens)
# =========================================================

def backup_bom_path(guild_id):
    return f"backup_bom_{guild_id}.json"


def backup_temp_path(guild_id):
    return f"backup_temp_{guild_id}.json"


def _carregar_arquivo(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)

                if isinstance(dados, dict):
                    dados.setdefault("canais", [])
                    dados.setdefault("cargos", [])
                    dados.setdefault("mensagens", {})
                    return dados

    except Exception as erro:
        print(f"Erro lendo {path}: {erro}")

    return {"canais": [], "cargos": [], "mensagens": {}}


def _salvar_arquivo(path, dados):
    temporario = path + ".tmp"

    try:
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(
                dados,
                arquivo,
                indent=2,
                ensure_ascii=False
            )

        os.replace(temporario, path)
        return True

    except Exception as erro:
        print(f"Erro salvando {path}: {erro}")

        try:
            if os.path.exists(temporario):
                os.remove(temporario)
        except OSError:
            pass

        return False


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


def salvar_backup_bom(guild_id, dados):
    return _salvar_arquivo(backup_bom_path(guild_id), dados)


def salvar_backup_temp(guild_id, dados):
    return _salvar_arquivo(backup_temp_path(guild_id), dados)


TIPOS_MSG_OK = (discord.MessageType.default, discord.MessageType.reply)


def serializar_mensagem(m):
    if m.type not in TIPOS_MSG_OK:
        return None

    if getattr(m, "components", None):
        return None

    embeds = [
        e.to_dict() for e in m.embeds
        if getattr(e, "type", "rich") == "rich"
    ][:10]

    anexos = [a.url for a in m.attachments]

    if not m.content and not embeds and not anexos:
        return None

    return {
        "id": m.id,
        "autor_id": m.author.id,
        "nome": m.author.display_name,
        "avatar": str(m.author.display_avatar.url),
        "conteudo": m.content,
        "anexos": anexos,
        "embeds": embeds,
        "criada_em": m.created_at.isoformat()
    }


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

    dados = {
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

    try:
        dados["news"] = bool(ch.is_news())
    except Exception:
        dados["news"] = False

    if hasattr(ch, "default_auto_archive_duration"):
        dados["default_auto_archive_duration"] = ch.default_auto_archive_duration

    if hasattr(ch, "default_thread_slowmode_delay"):
        dados["default_thread_slowmode_delay"] = ch.default_thread_slowmode_delay

    return dados


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


async def tirar_foto_guild_completa(guild):
    """Cria o snapshot completo da guild incluindo canais, cargos e as últimas 20 mensagens de texto."""
    dados = {
        "canais": [],
        "cargos": [],
        "mensagens": {}
    }

    for canal in guild.channels:
        dados["canais"].append(snapshot_canal(canal))

    for role in guild.roles:
        if role.name != "@everyone" and not role.managed:
            dados["cargos"].append(snapshot_cargo(role))

    membro = guild.me
    for canal in guild.text_channels:
        try:
            perms = canal.permissions_for(membro)
            if not (perms.view_channel and perms.read_message_history):
                continue

            lista = []
            async for m in canal.history(limit=MSG_POR_CANAL * 2):
                item = serializar_mensagem(m)
                if item:
                    lista.append(item)
                if len(lista) >= MSG_POR_CANAL:
                    break

            lista.reverse()
            dados["mensagens"][str(canal.id)] = {
                "nome": canal.name,
                "mensagens": lista
            }
        except Exception as erro:
            print(f"Erro salvando mensagens de #{canal.name}: {erro}")
        await asyncio.sleep(0.2)

    return dados


@tasks.loop(minutes=INTERVALO_BACKUP_MIN)
async def sync_backup_loop():
    for guild in bot.guilds:
        try:
            foto = await tirar_foto_guild_completa(guild)
            salvar_backup_temp(guild.id, foto)
            salvar_backup_bom(guild.id, foto)
            print(f"🔄 Backup unificado atualizado: {guild.name}")
        except Exception as erro:
            print(f"Erro sync backup {guild.name}: {erro}")


@sync_backup_loop.before_loop
async def antes_sync():
    await bot.wait_until_ready()


def nome_webhook_seguro(nome):
    nome = (nome or "").strip() or "Usuário"
    nome = re.sub(
        r"(?i)discord",
        lambda m: m.group(0).replace("i", "\u0456").replace("I", "\u0406"),
        nome
    )
    nome = re.sub(
        r"(?i)clyde",
        lambda m: m.group(0).replace("y", "\u0443").replace("Y", "\u0423"),
        nome
    )
    return nome[:80]


def dividir_texto(texto, limite=2000):
    partes = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte <= 0:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip("\n")
    if texto:
        partes.append(texto)
    return partes


async def _enviar_mensagem_restaurada(webhook, item):
    texto = item.get("conteudo") or ""
    anexos = item.get("anexos") or []
    if anexos:
        texto = (texto + "\n" if texto else "") + "\n".join(anexos)

    partes = dividir_texto(texto) if texto else []
    embeds = []
    for dados_embed in item.get("embeds") or []:
        try:
            embeds.append(discord.Embed.from_dict(dados_embed))
        except Exception:
            pass

    if not partes and not embeds:
        return False

    avatar = item.get("avatar")
    nome = nome_webhook_seguro(item.get("nome"))
    enviou_algo = False

    for indice in range(max(len(partes), 1)):
        kwargs = {
            "username": nome,
            "allowed_mentions": discord.AllowedMentions.none(),
            "wait": False
        }
        if avatar:
            kwargs["avatar_url"] = avatar
        if indice < len(partes):
            kwargs["content"] = partes[indice]
        if indice == 0 and embeds:
            kwargs["embeds"] = embeds[:10]

        tentativas = [dict(kwargs)]
        if "embeds" in kwargs and "content" in kwargs:
            tentativas.append({k: v for k, v in kwargs.items() if k != "embeds"})
        tentativas.append({k: v for k, v in tentativas[-1].items() if k != "avatar_url"})

        for tentativa in tentativas:
            try:
                await webhook.send(**tentativa)
                enviou_algo = True
                break
            except discord.HTTPException:
                pass
        await asyncio.sleep(0.4)

    return enviou_algo


async def restaurar_mensagens_canal_especifico(guild, canal, info_mensagens):
    mensagens = info_mensagens.get("mensagens") or []
    if not mensagens:
        return 0, 0

    try:
        webhook = await canal.create_webhook(
            name="Restauração",
            reason="Restaurando mensagens"
        )
    except Exception:
        return 0, len(mensagens)

    enviadas = 0
    falhas = 0
    try:
        for item in mensagens:
            if await _enviar_mensagem_restaurada(webhook, item):
                enviadas += 1
            else:
                falhas += 1
    finally:
        try:
            await webhook.delete(reason="Restauração concluída")
        except Exception:
            pass

    return enviadas, falhas


# =========================================================
# ESTADO DO RAID
# =========================================================

raid_state = {}
ja_banidos = {}
mensagens_processadas = set()

msgs = defaultdict(list)
acoes = defaultdict(list)
canais_pendentes_por_executor = defaultdict(set)


def novo_estado_raid():
    return {
        "ativo": False,
        "raider_id": None,
        "raider_nome": "Desconhecido",
        "canais_apagados_ids": set(),
        "cargos_apagados": [],
        "ultimo_ataque": 0,
        "canais_raid_criados": set(),
        "canais_criados_pelo_bot": set(),
        "qtd_ataques": 0,
        "restaurando": False
    }


def get_raid(guild_id):
    if guild_id not in raid_state:
        raid_state[guild_id] = novo_estado_raid()
    return raid_state[guild_id]


def registrou(tipo, user_id, limite=4, janela=JANELA_RAID):
    agora = time.time()
    chave = (tipo, user_id)
    acoes[chave] = [t for t in acoes[chave] if agora - t < janela]
    acoes[chave].append(agora)
    return len(acoes[chave]) >= limite


# =========================================================
# LOGS — SOMENTE PARA O DONO DO BOT
# =========================================================

async def enviar_log_simples(guild, titulo, descricao, cor=0xFF0000):
    try:
        embed = discord.Embed(
            title=titulo,
            description=descricao,
            color=cor,
            timestamp=discord.utils.utcnow()
        )
        if guild:
            embed.add_field(name="🌐 Servidor", value=f"**{guild.name}**\nID: `{guild.id}`", inline=False)
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Sistema Anti-Nuke • Relatório privado")

        usuario = await bot.fetch_user(MEU_ID)
        await usuario.send(embed=embed)
    except Exception as erro:
        print(f"Erro enviando log privado: {erro}")


async def enviar_log(guild, titulo, descricao, cor=0xFF0000):
    await enviar_log_simples(guild, titulo, descricao, cor)


# =========================================================
# AUDIT LOG
# =========================================================

async def pegar_executor(guild, action, target_id=None, janela=12):
    if guild is None:
        return None

    for tentativa in range(MAX_TENTATIVAS_AUDIT):
        try:
            async for entrada in guild.audit_logs(limit=12, action=action):
                idade = (discord.utils.utcnow() - entrada.created_at).total_seconds()
                if idade < 0 or idade > janela:
                    continue
                if entrada.user is None or (bot.user and entrada.user.id == bot.user.id):
                    continue
                if target_id is not None:
                    alvo = getattr(entrada, "target", None)
                    if alvo is None or getattr(alvo, "id", None) != target_id:
                        continue
                return entrada.user.id
        except Exception:
            pass
        if tentativa < MAX_TENTATIVAS_AUDIT - 1:
            await asyncio.sleep(INTERVALO_AUDIT)
    return None


# =========================================================
# FUNÇÕES DE RESTAURAÇÃO MANUAL (Canais, Cargos e Mensagens)
# =========================================================

def construir_overwrites(guild, lista, mapa_cargos=None):
    overwrites = {}
    mapa_cargos = mapa_cargos or {}

    for ow in lista:
        if ow.get("is_role", False):
            id_antigo = int(ow["id"])
            alvo = mapa_cargos.get(id_antigo) or mapa_cargos.get(str(id_antigo)) or guild.get_role(id_antigo)
        else:
            alvo = guild.get_member(int(ow["id"]))

        if alvo is not None:
            overwrites[alvo] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(ow["allow"]),
                discord.Permissions(ow["deny"])
            )
    return overwrites


async def criar_canal_backup(guild, dados, mapa_categorias, mapa_cargos=None):
    tipo = dados.get("type", "")
    nome = dados["name"]
    categoria_id = dados.get("category_id")
    categoria = mapa_categorias.get(categoria_id) if categoria_id else None

    overwrites = construir_overwrites(guild, dados.get("overwrites", []), mapa_cargos)
    motivo = "Restauração manual do backup"

    if "category" in tipo:
        novo = await guild.create_category(
            name=nome,
            position=dados.get("position", 0),
            overwrites=overwrites,
            reason=motivo
        )
        mapa_categorias[dados["id"]] = novo
    elif "text" in tipo:
        kwargs = {
            "name": nome,
            "category": categoria,
            "position": dados.get("position", 0),
            "topic": dados.get("topic"),
            "slowmode_delay": dados.get("slowmode", 0),
            "nsfw": dados.get("nsfw", False),
            "overwrites": overwrites,
            "reason": motivo
        }
        try:
            parametros = inspect.signature(guild.create_text_channel).parameters
            if "news" in parametros:
                kwargs["news"] = dados.get("news", False)
        except Exception:
            pass
        novo = await guild.create_text_channel(**kwargs)
    elif "voice" in tipo:
        novo = await guild.create_voice_channel(
            name=nome,
            category=categoria,
            position=dados.get("position", 0),
            bitrate=dados.get("bitrate") or 64000,
            user_limit=dados.get("user_limit") or 0,
            overwrites=overwrites,
            reason=motivo
        )
    elif "forum" in tipo:
        metodo = getattr(guild, "create_forum", None)
        novo = await metodo(
            name=nome,
            category=categoria,
            position=dados.get("position", 0),
            topic=dados.get("topic"),
            slowmode_delay=dados.get("slowmode", 0),
            nsfw=dados.get("nsfw", False),
            overwrites=overwrites,
            reason=motivo
        )
    elif "stage" in tipo:
        metodo = getattr(guild, "create_stage_channel", None)
        novo = await metodo(
            name=nome,
            category=categoria,
            position=dados.get("position", 0),
            topic=dados.get("topic"),
            overwrites=overwrites,
            reason=motivo
        )
    else:
        raise RuntimeError(f"Tipo não suportado: {tipo}")

    registrar_novo_id_canal(guild.id, dados["id"], novo.id)
    return novo


async def executar_restauracao_completa(guild):
    backup = carregar_backup(guild.id)
    if not backup["canais"] and not backup["cargos"]:
        return False, "Backup vazio!"

    salvar_mapa_canais(guild.id, {})

    # 1. Apagar canais atuais
    for canal in list(guild.channels):
        try:
            await canal.delete(reason="Restauração completa do servidor")
            await asyncio.sleep(0.4)
        except Exception:
            pass

    await asyncio.sleep(1)

    # 2. Recriar cargos
    mapa_cargos = {}
    cargos_por_nome = {role.name: role for role in guild.roles if role.name != "@everyone"}

    for dados in backup["cargos"]:
        id_antigo = int(dados.get("id", 0))
        nome = dados.get("name")
        if not nome:
            continue
        cargo = guild.get_role(id_antigo) or cargos_por_nome.get(nome)
        if cargo is None:
            try:
                cargo = await guild.create_role(
                    name=nome,
                    colour=discord.Colour(dados["color"]),
                    hoist=dados["hoist"],
                    mentionable=dados["mentionable"],
                    permissions=discord.Permissions(dados["permissions"]),
                    reason="Restauração de backup"
                )
                cargos_por_nome[nome] = cargo
                await asyncio.sleep(0.4)
            except Exception:
                continue
        mapa_cargos[id_antigo] = cargo
        mapa_cargos[str(id_antigo)] = cargo

    # 3. Recriar categorias e canais
    mapa_categorias = {}
    categorias = [c for c in backup["canais"] if "category" in c.get("type", "")]
    demais = [c for c in backup["canais"] if "category" not in c.get("type", "")]

    for dados in categorias:
        try:
            await criar_canal_backup(guild, dados, mapa_categorias, mapa_cargos)
            await asyncio.sleep(0.5)
        except Exception:
            pass

    mapa_novos_canais = {}
    for dados in demais:
        try:
            novo = await criar_canal_backup(guild, dados, mapa_categorias, mapa_cargos)
            if isinstance(novo, discord.TextChannel):
                mapa_novos_canais[int(dados["id"])] = novo
            await asyncio.sleep(0.5)
        except Exception:
            pass

    # 4. Restaurar mensagens salvas junto no backup unificado
    mensagens_backup = backup.get("mensagens", {})
    if mensagens_backup and mapa_novos_canais:
        for id_antigo_str, info in mensagens_backup.items():
            try:
                id_antigo = int(id_antigo_str)
            except ValueError:
                continue
            novo_canal = mapa_novos_canais.get(id_antigo)
            if novo_canal:
                await restaurar_mensagens_canal_especifico(guild, novo_canal, info)
                await asyncio.sleep(0.8)

    return True, "Servidor restaurado com sucesso!"


# =========================================================
# BANIMENTO / PUNIÇÃO (Sem Restauração Automática)
# =========================================================

async def executor_eh_bot(guild, executor_id):
    membro = guild.get_member(executor_id)
    if membro is not None:
        return membro.bot
    try:
        usuario = await bot.fetch_user(executor_id)
        return usuario.bot
    except Exception:
        return False


async def punir(guild, executor_id, motivo):
    if guild is None or executor_id is None:
        return False
    if is_protegido(guild, executor_id):
        return False

    agora = time.time()
    if executor_id in ja_banidos and agora - ja_banidos[executor_id] < 60:
        return False

    try:
        membro = guild.get_member(executor_id) or await guild.fetch_member(executor_id)
        await guild.ban(membro, reason=f"ANTI-NUKE: {motivo}")
        ja_banidos[executor_id] = agora

        is_bot = await executor_eh_bot(guild, executor_id)
        tipo_str = "🤖 Bot" if is_bot else "👤 Usuário"

        await enviar_log(
            guild,
            f"🚨 Ação Detectada & Banimento ({tipo_str})",
            f"**Executor:** <@{executor_id}> (`{executor_id}`)\n"
            f"**Motivo:** {motivo}\n"
            "**Nota:** O bot baniu o invasor, mas **não** executa restauração automática. Use `!restaurar tudo` se necessário.",
            cor=0xE74C3C
        )
        return True
    except Exception as erro:
        print(f"Erro ao punir {executor_id}: {erro}")
    return False


# =========================================================
# INICIALIZAÇÃO
# =========================================================

@bot.event
async def on_ready():
    global VIEWS_REGISTRADAS
    print(f"✅ ONLINE: {bot.user} | SISTEMA DE RESTAURAÇÃO MANUAL ATIVADO")
    await bot.change_presence(activity=discord.Game(name="🛡️ MANUAL RESTORE MODE"))

    if not VIEWS_REGISTRADAS:
        bot.add_view(TicketPanelView())
        bot.add_view(TicketCloseView())
        VIEWS_REGISTRADAS = True

    for guild in bot.guilds:
        try:
            if not os.path.exists(backup_bom_path(guild.id)):
                foto = await tirar_foto_guild_completa(guild)
                salvar_backup_bom(guild.id, foto)
                salvar_backup_temp(guild.id, foto)
                print(f"📸 Backup inicial criado: {guild.name}")
        except Exception as erro:
            print(f"Erro backup inicial {guild.name}: {erro}")

    if not sync_backup_loop.is_running():
        sync_backup_loop.start()
    if not verificar_tickets_sem_resposta.is_running():
        verificar_tickets_sem_resposta.start()
    if not fechar_tickets_por_inatividade.is_running():
        fechar_tickets_por_inatividade.start()


@bot.event
async def on_guild_join(guild):
    try:
        foto = await tirar_foto_guild_completa(guild)
        salvar_backup_bom(guild.id, foto)
        salvar_backup_temp(guild.id, foto)
    except Exception as erro:
        print(f"Erro no join do servidor: {erro}")


# =========================================================
# SISTEMA DE TICKETS — DADOS
# =========================================================

def arquivo_contador_ticket(guild_id):
    return f"contador_tickets_{guild_id}.json"


def carregar_contador_ticket(guild_id):
    path = arquivo_contador_ticket(guild_id)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return int(dados.get("contador", 0))
    except Exception:
        pass
    return 0


def salvar_contador_ticket(guild_id, numero):
    path = arquivo_contador_ticket(guild_id)
    temporario = path + ".tmp"
    try:
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump({"contador": numero}, f)
        os.replace(temporario, path)
        return True
    except Exception:
        return False


async def proximo_numero_ticket(guild_id):
    async with locks_tickets[guild_id]:
        numero = carregar_contador_ticket(guild_id) + 1
        salvar_contador_ticket(guild_id, numero)
        return numero


def _ler_dados_topic(canal):
    topic = getattr(canal, "topic", None) or ""
    dados = {
        "owner_id": None, "numero": None, "aberto_em": None,
        "alertado": False, "respondido": False, "assumido_por": None,
        "ultima_atividade": None, "ultimo_alerta_msg": None, "msg_controle_id": None
    }
    if not topic:
        return dados
    for parte in topic.split("|"):
        if ":" not in parte:
            continue
        chave, valor = parte.split(":", 1)
        try:
            if chave == "ticket_owner": dados["owner_id"] = int(valor)
            elif chave == "ticket_numero": dados["numero"] = int(valor)
            elif chave == "ticket_aberto": dados["aberto_em"] = int(valor)
            elif chave == "ticket_alertado": dados["alertado"] = valor == "1"
            elif chave == "ticket_respondido": dados["respondido"] = valor == "1"
            elif chave == "ticket_assumido_por": dados["assumido_por"] = int(valor) if valor not in ("", "None", "0") else None
            elif chave == "ticket_ultima_atividade": dados["ultima_atividade"] = int(valor)
            elif chave == "ticket_ultimo_alerta_msg": dados["ultimo_alerta_msg"] = valor or None
        except Exception:
            pass
    return dados


ARQUIVO_ESTADO_TICKETS = "estado_tickets.json"
CAMPOS_ESTADO_TICKET = ("alertado", "respondido", "assumido_por", "ultima_atividade", "ultimo_alerta_msg", "msg_controle_id")
estado_tickets = {}


def _carregar_estado_tickets():
    global estado_tickets
    try:
        if os.path.exists(ARQUIVO_ESTADO_TICKETS):
            with open(ARQUIVO_ESTADO_TICKETS, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, dict):
                estado_tickets = dados
    except Exception:
        pass


def _salvar_estado_tickets():
    temporario = ARQUIVO_ESTADO_TICKETS + ".tmp"
    try:
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(estado_tickets, f, ensure_ascii=False)
        os.replace(temporario, ARQUIVO_ESTADO_TICKETS)
        return True
    except Exception:
        return False


_carregar_estado_tickets()


def ler_dados_ticket(canal):
    dados = _ler_dados_topic(canal)
    if dados["owner_id"]:
        extra = estado_tickets.get(str(canal.id))
        if extra:
            for campo in CAMPOS_ESTADO_TICKET:
                if campo in extra:
                    dados[campo] = extra[campo]
    return dados


async def atualizar_dados_ticket(canal, **alteracoes):
    try:
        item = estado_tickets.setdefault(str(canal.id), {})
        for chave, valor in alteracoes.items():
            if chave in CAMPOS_ESTADO_TICKET:
                item[chave] = valor
        return _salvar_estado_tickets()
    except Exception:
        return False


def eh_responsavel_ticket(guild, membro):
    if guild is None or membro is None:
        return False
    if membro.id == guild.owner_id or membro.id in ADM_CONFIANCA:
        return True
    permissoes = membro.guild_permissions
    return permissoes.administrator or permissoes.manage_channels


def obter_responsaveis_ticket(guild):
    responsaveis = {}
    dono = guild.get_member(guild.owner_id)
    if dono:
        responsaveis[dono.id] = dono
    for membro in guild.members:
        if eh_responsavel_ticket(guild, membro):
            responsaveis[membro.id] = membro
    return list(responsaveis.values())


async def gerar_transcricao(canal, fechado_por=None):
    dados = ler_dados_ticket(canal)
    mensagens = []
    async for mensagem in canal.history(limit=None, oldest_first=True):
        data = mensagem.created_at.strftime("%d/%m/%Y às %H:%M:%S UTC")
        conteudo = mensagem.content or ""
        if mensagem.embeds: conteudo += "\n[Mensagem contém embed]"
        if mensagem.attachments:
            conteudo += "\nANEXOS:\n" + "\n".join(f"- {a.filename}: {a.url}" for a in mensagem.attachments)
        mensagens.append(f"{'─'*72}\nAutor: {mensagem.author} | Data: {data}\n{conteudo}\n")

    conteudo_final = "HISTÓRICO DO TICKET\n\n" + ("\n".join(mensagens) if mensagens else "Vazio")
    return discord.File(io.BytesIO(conteudo_final.encode("utf-8")), filename=f"transcricao-{dados.get('numero') or 'ticket'}.txt")


async def fechar_ticket(canal, fechado_por):
    if not isinstance(canal, discord.TextChannel):
        return False
    dados = ler_dados_ticket(canal)
    if dados["owner_id"] is None:
        return False
    try:
        arquivo = await gerar_transcricao(canal, fechado_por)
        usuario = await bot.fetch_user(dados["owner_id"])
        await usuario.send("Seu ticket foi encerrado. Segue o histórico:", file=arquivo)
    except Exception:
        pass
    try:
        await canal.delete(reason="Ticket fechado")
        return True
    except Exception:
        return False


@tasks.loop(minutes=1)
async def verificar_tickets_sem_resposta():
    pass


@tasks.loop(minutes=1)
async def fechar_tickets_por_inatividade():
    pass


@verificar_tickets_sem_resposta.before_loop
async def antes_verificar_tickets():
    await bot.wait_until_ready()


@fechar_tickets_por_inatividade.before_loop
async def antes_fechar_tickets():
    await bot.wait_until_ready()


# =========================================================
# EVENTOS DE MENSAGENS E COMANDOS
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

    if message.content.strip().lower() == ".f":
        dados = ler_dados_ticket(message.channel)
        if dados["owner_id"] and eh_responsavel_ticket(message.guild, message.author):
            try: await message.delete() except Exception: pass
            await fechar_ticket(message.channel, message.author)
            return

    if message.content.startswith("!"):
        ctx = await bot.get_context(message)
        try: await message.delete() except Exception: pass
        if ctx.command is None:
            return
        if ctx.command.qualified_name in ("recursos", "restaurar"):
            await bot.invoke(ctx)
            return
        if message.author.id != message.guild.owner_id:
            return
        await bot.invoke(ctx)
        return


# =========================================================
# EVENTOS ANTI-NUKE (Apenas Detecção e Banimento)
# =========================================================

def acao_em_massa(tipo, executor_id):
    limite, janela = LIMITES_MASSA.get(tipo, LIMITE_PADRAO_MASSA)
    if registrou(tipo, executor_id, limite, janela):
        return True
    limite_c, janela_c = LIMITE_COMBINADO
    return registrou("combinado", executor_id, limite_c, janela_c)


async def checar_massa(guild, executor, tipo, rotulo):
    if executor is None or (bot.user and executor == bot.user.id) or is_protegido(guild, executor):
        return False
    if acao_em_massa(tipo, executor):
        await punir(guild, executor, f"{rotulo} em massa")
        return True
    return False


@bot.event
async def on_member_ban(guild, user):
    executor = await pegar_executor(guild, discord.AuditLogAction.ban, user.id)
    await checar_massa(guild, executor, "ban", "Baniu membros")


@bot.event
async def on_member_remove(member):
    executor = await pegar_executor(member.guild, discord.AuditLogAction.kick, member.id)
    await checar_massa(member.guild, executor, "kick", "Expulsou membros")


@bot.event
async def on_guild_channel_create(channel):
    executor = await pegar_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
    await checar_massa(channel.guild, executor, "canal_criar", "Criou canais")


@bot.event
async def on_guild_channel_delete(channel):
    executor = await pegar_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    await checar_massa(channel.guild, executor, "canal_del", "Deletou canais")


@bot.event
async def on_guild_role_create(role):
    executor = await pegar_executor(role.guild, discord.AuditLogAction.role_create, role.id)
    await checar_massa(role.guild, executor, "cargo_criar", "Criou cargos")


@bot.event
async def on_guild_role_delete(role):
    executor = await pegar_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
    await checar_massa(role.guild, executor, "cargo_del", "Deletou cargos")


# =========================================================
# NOVOS COMANDOS DE RESTAURAÇÃO MANUAL (EXCLUSIVO DONO)
# =========================================================

class ConfirmarRestauracaoTudoView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="Sim, Restaurar", style=discord.ButtonStyle.danger, emoji="⚠️")
    def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return interaction.response.send_message("Apenas o dono pode confirmar.", ephemeral=True)
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return interaction.response.send_message("Apenas o dono pode cancelar.", ephemeral=True)
        self.value = False
        self.stop()


@bot.group(name="restaurar", invoke_without_command=True)
async def restaurar(ctx, *, arg: str = ""):
    if ctx.author.id != ctx.guild.owner_id:
        return

    arg = arg.strip().lower()

    if arg == "tudo":
        view = ConfirmarRestauracaoTudoView(ctx)
        msg = await ctx.send(
            "⚠️ **ATENÇÃO:** Você solicitou a restauração **COMPLETA** do servidor!\n"
            "Isso apagará os canais atuais e recriará cargos, canais e mensagens do backup.\n"
            "Deseja realmente continuar?",
            view=view
        )
        await view.wait()

        if view.value is True:
            await msg.edit(content="♻️ Iniciando restauração completa do servidor...", view=None)
            sucesso, resultado = await executar_restauracao_completa(ctx.guild)
            await ctx.send(f"✅ {resultado}" if sucesso else f"❌ {resultado}")
        else:
            await msg.edit(content="❌ Restauração cancelada.", view=None)
        return

    await ctx.send(
        "Uso correto:\n"
        "`!restaurar tudo` — Restaura o servidor inteiro\n"
        "`!restaurar canal #canal` — Restaura um canal específico\n"
        "`!restaurar msg deste canal` — Restaura as mensagens salvas deste canal\n"
        "`!restaurar msg de todos canais` — Restaura mensagens de todos os canais\n"
        "`!restaurar msg do #canal` — Restaura mensagens de um canal específico",
        delete_after=10
    )


@restaurar.command(name="canal")
async def restaurar_canal(ctx, canal_alvo: discord.abc.GuildChannel):
    if ctx.author.id != ctx.guild.owner_id:
        return

    backup = carregar_backup(ctx.guild.id)
    canais_backup = backup.get("canais", [])
    
    # Encontra os dados antigos do canal com base no nome ou ID
    dado_canal = None
    for c in canais_backup:
        if c.get("id") == canal_alvo.id or c.get("name").lower() == canal_alvo.name.lower():
            dado_canal = c
            break

    if not dado_canal:
        return await ctx.send(f"❌ Não encontrei dados salvos para o canal **{canal_alvo.name}** no backup.", delete_after=6)

    try:
        mapa_cat = {}
        # Se pertencia a uma categoria, tenta achar ou recriar
        await criar_canal_backup(ctx.guild, dado_canal, mapa_cat)
        await ctx.send(f"✅ Canal **{dado_canal['name']}** restaurado com sucesso!", delete_after=6)
    except Exception as e:
        await ctx.send(f"❌ Erro ao restaurar canal: {e}", delete_after=6)


@restaurar.group(name="msg", invoke_without_command=True)
async def restaurar_msg(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        return
    await ctx.send("Use: `!restaurar msg deste canal`, `!restaurar msg de todos canais` ou `!restaurar msg do #canal`", delete_after=6)


@restaurar_msg.command(name="deste")
async def restaurar_msg_deste(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        return

    backup = carregar_backup(ctx.guild.id)
    mensagens_backup = backup.get("mensagens", {})
    info = mensagens_backup.get(str(ctx.channel.id))

    if not info:
        return await ctx.send("❌ Não há mensagens salvas no backup para este canal.", delete_after=6)

    msg_status = await ctx.send(f"💬 Restaurando mensagens em {ctx.channel.mention}...")
    enviadas, falhas = await restaurar_mensagens_canal_especifico(ctx.guild, ctx.channel, info)
    await msg_status.edit(content=f"✅ Restauração de mensagens concluída! **{enviadas}** enviadas, **{falhas}** falhas.")


@restaurar_msg.command(name="todos")
async def restaurar_msg_todos(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        return

    backup = carregar_backup(ctx.guild.id)
    mensagens_backup = backup.get("mensagens", {})
    if not mensagens_backup:
        return await ctx.send("❌ Nenhum backup de mensagens encontrado.", delete_after=6)

    msg_status = await ctx.send("💬 Restaurando mensagens em todos os canais salvos...")
    total_env = 0
    total_falhas = 0

    for cid_str, info in mensagens_backup.items():
        try:
            canal = ctx.guild.get_channel(int(cid_str))
            if isinstance(canal, discord.TextChannel):
                env, falh = await restaurar_mensagens_canal_especifico(ctx.guild, canal, info)
                total_env += env
                total_falhas += falh
                await asyncio.sleep(1)
        except Exception:
            pass

    await msg_status.edit(content=f"✅ Restauração geral de mensagens concluída! **{total_env}** mensagens enviadas.")


@restaurar_msg.command(name="do")
async def restaurar_msg_do(ctx, canal_alvo: discord.TextChannel):
    if ctx.author.id != ctx.guild.owner_id:
        return

    backup = carregar_backup(ctx.guild.id)
    mensagens_backup = backup.get("mensagens", {})
    
    # Procura por ID ou nome correspondente
    info = mensagens_backup.get(str(canal_alvo.id))
    if not info:
        for cid, dados in mensagens_backup.items():
            if dados.get("nome", "").lower() == canal_alvo.name.lower():
                info = dados
                break

    if not info:
        return await ctx.send(f"❌ Não há mensagens salvas para **{canal_alvo.name}**.", delete_after=6)

    msg_status = await ctx.send(f"💬 Restaurando mensagens em {canal_alvo.mention}...")
    enviadas, falhas = await restaurar_mensagens_canal_especifico(ctx.guild, canal_alvo, info)
    await msg_status.edit(content=f"✅ Concluído em {canal_alvo.mention}! **{enviadas}** mensagens enviadas.")


# =========================================================
# COMANDOS ORIGINAIS (Recursos, Atualizar, Limpar, Tickets)
# =========================================================

@bot.command(name="recursos")
async def recursos(ctx):
    embed = discord.Embed(
        title="🛡️ CENTRAL DE RECURSOS",
        description="Sistema de segurança e ferramentas atualizado para controle manual de restauração.",
        color=0x5865F2
    )
    await ctx.send(embed=embed)


@bot.command(name="atualizar", aliases=["atualizarbackup", "backup", "salvar"])
async def atualizar_backup(ctx, *, arg: str = ""):
    if ctx.author.id != ctx.guild.owner_id:
        return

    try:
        foto = await tirar_foto_guild_completa(ctx.guild)
        salvar_backup_bom(ctx.guild.id, foto)
        salvar_backup_temp(ctx.guild.id, foto)
        await ctx.send(
            f"✅ Backup unificado atualizado com sucesso!\n"
            f"**{len(foto['canais'])} canais**, **{len(foto['cargos'])} cargos** e as "
            f"últimas mensagens de **{len(foto['mensagens'])} canais** salvos.",
            delete_after=8
        )
    except Exception as erro:
        await ctx.send(f"❌ Erro ao atualizar backup: {erro}", delete_after=8)


@bot.command(name="limpar")
async def limpar(ctx, *, argumento: str = ""):
    if ctx.author.id != ctx.guild.owner_id:
        return
    argumento = argumento.strip().lower()

    if argumento in ("canal todo", "canal", "tudo", "canal inteiro"):
        canal_antigo = ctx.channel
        if not isinstance(canal_antigo, discord.TextChannel):
            return
        try:
            novo_canal = await canal_antigo.clone(name=canal_antigo.name, reason="Limpeza completa")
            await novo_canal.edit(position=canal_antigo.position)
            await canal_antigo.delete(reason="Canal limpo")
            await novo_canal.send("🧹 **Canal limpo com sucesso!**")
        except Exception:
            pass
        return

    try:
        quantidade = int(argumento)
    except Exception:
        return

    if 0 < quantidade <= 1000:
        await ctx.channel.purge(limit=quantidade)


# =========================================================
# SISTEMA DE TICKETS (Mantido Completo)
# =========================================================

class TicketCloseView(discord.ui.View):
    def __init__(self, assumido=False):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fechar ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_fechar")
    async def fechar_ticket_botao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fechando ticket...", ephemeral=True)
        await fechar_ticket(interaction.channel, interaction.user)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir ticket", emoji="🎫", style=discord.ButtonStyle.success, custom_id="ticket_abrir")
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        membro = interaction.user
        
        numero = await proximo_numero_ticket(guild.id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membro: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        ticket_canal = await guild.create_text_channel(
            name=f"🎫・atendimento-{numero}",
            category=interaction.channel.category,
            overwrites=overwrites
        )
        embed = discord.Embed(title=f"🎫 Atendimento #{numero}", description="Explique seu problema abaixo.", color=0x5865F2)
        await ticket_canal.send(content=membro.mention, embed=embed, view=TicketCloseView())
        await interaction.response.send_message(f"✅ Ticket criado: {ticket_canal.mention}", ephemeral=True)


@bot.group(name="ticket", invoke_without_command=True)
async def ticket(ctx):
    pass


@ticket.command(name="painel")
async def ticket_painel(ctx, canal: discord.TextChannel):
    if ctx.author.id != ctx.guild.owner_id:
        return
    embed = discord.Embed(title="🎫 SUPORTE", description="Clique abaixo para abrir um ticket.", color=0x5865F2)
    await canal.send(embed=embed, view=TicketPanelView())
    await ctx.send("✅ Painel publicado!", delete_after=5)


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("A variável de ambiente TOKEN não foi configurada.")

bot.run(TOKEN)
