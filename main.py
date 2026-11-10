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
# BACKUP DE MENSAGENS (Alterado para 1 hora)
# ---------------------------------------------------------
MSG_POR_CANAL = 20
INTERVALO_BACKUP_MSGS_MIN = 60  # Mudado de 30 para 60 min (1 hora)
LIMITE_RESTAURACAO = 12
INTERVALO_AUDIT = 0.35
MAX_TENTATIVAS_AUDIT = 4

TEMPO_ALERTA_TICKET = 30 * 60
TEMPO_FECHAMENTO_INATIVIDADE_TICKET = 3 * 60 * 60

VIEWS_REGISTRADAS = False

# Locks para evitar dois tickets com o mesmo número.
locks_tickets = defaultdict(asyncio.Lock)


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
# BACKUP
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


def salvar_backup(guild_id, dados):
    return _salvar_arquivo(backup_bom_path(guild_id), dados)


def salvar_backup_temp(guild_id, dados):
    return _salvar_arquivo(backup_temp_path(guild_id), dados)


def salvar_backup_bom(guild_id, dados):
    return _salvar_arquivo(backup_bom_path(guild_id), dados)


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
        dados["default_auto_archive_duration"] = (
            ch.default_auto_archive_duration
        )

    if hasattr(ch, "default_thread_slowmode_delay"):
        dados["default_thread_slowmode_delay"] = (
            ch.default_thread_slowmode_delay
        )

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


def tirar_foto_guild(guild):
    dados = {
        "canais": [],
        "cargos": []
    }

    for canal in guild.channels:
        dados["canais"].append(snapshot_canal(canal))

    for role in guild.roles:
        if role.name != "@everyone" and not role.managed:
            dados["cargos"].append(snapshot_cargo(role))

    return dados


def atualizar_canal_no_backup_temp(guild_id, canal):
    dados = carregar_backup_temp(guild_id)
    item = snapshot_canal(canal)

    for i, atual in enumerate(dados["canais"]):
        if atual.get("id") == canal.id:
            dados["canais"][i] = item
            break
    else:
        dados["canais"].append(item)

    salvar_backup_temp(guild_id, dados)


def remover_canal_do_backup_temp(guild_id, canal_id):
    dados = carregar_backup_temp(guild_id)

    dados["canais"] = [
        c for c in dados["canais"]
        if c.get("id") != canal_id
    ]

    salvar_backup_temp(guild_id, dados)


# =========================================================
# ESTADO DO RAID
# =========================================================

raid_state = {}
ja_banidos = {}
mensagens_processadas = set()

msgs = defaultdict(list)
acoes = defaultdict(list)
locks_restauracao = defaultdict(asyncio.Lock)

canais_pendentes_por_executor = defaultdict(set)
restaurando_mensagens = set()


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
        "canais_criados_pelo_bot": set(),
        "qtd_ataques": 0,
        "restaurando": False
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

    return (
        time.time() - estado["ultimo_ataque"]
    ) < minutos * 60


def registrou(tipo, user_id, limite=4, janela=JANELA_RAID):
    agora = time.time()
    chave = (tipo, user_id)

    acoes[chave] = [
        t for t in acoes[chave]
        if agora - t < janela
    ]

    acoes[chave].append(agora)

    return len(acoes[chave]) >= limite


# =========================================================
# BACKUP AUTOMÁTICO (Loop alterado para 1 hora / 60 min)
# =========================================================

@tasks.loop(minutes=60)
async def sync_backup_loop():
    for guild in bot.guilds:
        try:
            if teve_raid_recente(guild.id, 30):
                print(f"⏸️ Sync pulado em {guild.name}: raid recente.")
                continue

            foto = tirar_foto_guild(guild)

            salvar_backup_temp(guild.id, foto)
            salvar_backup_bom(guild.id, foto)

            print(f"🔄 Backup atualizado (1h): {guild.name}")

        except Exception as erro:
            print(f"Erro sync backup {guild.name}: {erro}")


@sync_backup_loop.before_loop
async def antes_sync():
    await bot.wait_until_ready()


# =========================================================
# BACKUP DE MENSAGENS
# =========================================================

TIPOS_MSG_OK = (discord.MessageType.default, discord.MessageType.reply)


def arquivo_backup_msgs(guild_id):
    return f"backup_msgs_{guild_id}.json"


def carregar_backup_msgs(guild_id):
    try:
        with open(arquivo_backup_msgs(guild_id), "r", encoding="utf-8") as f:
            dados = json.load(f)

            if isinstance(dados, dict):
                return dados

    except FileNotFoundError:
        pass

    except Exception as erro:
        print(f"Erro lendo backup de mensagens: {erro}")

    return {}


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


async def salvar_mensagens_guild(guild):
    antigos = carregar_backup_msgs(guild.id)
    novos = {}
    membro = guild.me

    for canal in guild.text_channels:
        try:
            perms = canal.permissions_for(membro)

            if not (perms.view_channel and perms.read_message_history):
                if str(canal.id) in antigos:
                    novos[str(canal.id)] = antigos[str(canal.id)]
                continue

            lista = []

            async for m in canal.history(limit=MSG_POR_CANAL * 2):
                item = serializar_mensagem(m)

                if item:
                    lista.append(item)

                if len(lista) >= MSG_POR_CANAL:
                    break

            lista.reverse()

            novos[str(canal.id)] = {
                "nome": canal.name,
                "mensagens": lista
            }

        except Exception as erro:
            print(f"Erro salvando mensagens de #{canal.name}: {erro}")

            if str(canal.id) in antigos:
                novos[str(canal.id)] = antigos[str(canal.id)]

        await asyncio.sleep(0.4)

    _salvar_arquivo(arquivo_backup_msgs(guild.id), novos)


@tasks.loop(minutes=INTERVALO_BACKUP_MSGS_MIN)
async def backup_mensagens_loop():
    for guild in bot.guilds:
        try:
            if (
                teve_raid_recente(guild.id, 30)
                or guild.id in restaurando_mensagens
            ):
                continue

            await salvar_mensagens_guild(guild)

        except Exception as erro:
            print(f"Erro no backup de mensagens {guild.name}: {erro}")


@backup_mensagens_loop.before_loop
async def antes_backup_mensagens():
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

        await asyncio.sleep(0.6)

    return enviou_algo


async def restaurar_mensagens(guild, mapa_novos_canais, canais_alvo_ids=None):
    """
    Se canais_alvo_ids for informado, restaura mensagens apenas nesses canais específicos.
    Caso contrário, restaura em todos os canais do mapa.
    """
    resultado = {
        "canais": 0,
        "mensagens": 0,
        "falhas": 0,
        "sem_canal": 0,
        "sem_permissao": False
    }

    dados = carregar_backup_msgs(guild.id)
    if not dados:
        return resultado

    por_nome = defaultdict(list)
    for canal in mapa_novos_canais.values():
        por_nome[canal.name].append(canal)

    for id_antigo, info in dados.items():
        try:
            id_antigo_int = int(id_antigo)
        except (TypeError, ValueError):
            id_antigo_int = None

        if canais_alvo_ids is not None and id_antigo_int not in canais_alvo_ids:
            continue

        mensagens = info.get("mensagens") or []
        if not mensagens:
            continue

        canal = mapa_novos_canais.get(id_antigo_int)

        if canal is None:
            candidatos = por_nome.get(info.get("nome"), [])
            canal = candidatos[0] if len(candidatos) == 1 else None

        if canal is None:
            resultado["sem_canal"] += 1
            continue

        canal = guild.get_channel(canal.id)
        if not isinstance(canal, discord.TextChannel):
            resultado["sem_canal"] += 1
            continue

        try:
            webhook = await canal.create_webhook(
                name="Restauração",
                reason="Anti-Nuke: restaurando mensagens"
            )
        except discord.Forbidden:
            resultado["sem_permissao"] = True
            break
        except Exception:
            resultado["falhas"] += len(mensagens)
            continue

        try:
            for item in mensagens:
                if await _enviar_mensagem_restaurada(webhook, item):
                    resultado["mensagens"] += 1
                else:
                    resultado["falhas"] += 1
            resultado["canais"] += 1
        finally:
            try:
                await webhook.delete(reason="Anti-Nuke: restauração concluída")
            except Exception:
                pass

        await asyncio.sleep(1)

    return resultado


async def restaurar_mensagens_em_segundo_plano(guild, mapa_novos_canais, canais_alvo_ids=None):
    restaurando_mensagens.add(guild.id)

    try:
        print(f"💬 Restaurando mensagens em {guild.name}...")
        r = await restaurar_mensagens(guild, mapa_novos_canais, canais_alvo_ids)

        aviso_perm = (
            "\n⚠️ Faltou permissão **Gerenciar Webhooks** para restaurar as mensagens."
            if r["sem_permissao"] else ""
        )

        await enviar_log(
            guild,
            "💬 Mensagens restauradas",
            (
                f"**Canais com mensagens devolvidas:** {r['canais']}\n"
                f"**Mensagens restauradas:** {r['mensagens']}\n"
                f"**Falhas:** {r['falhas']}\n"
                f"**Canais sem correspondência:** {r['sem_canal']}"
                f"{aviso_perm}"
            ),
            cor=0x2ECC71
        )
    except Exception as erro:
        print(f"Erro restaurando mensagens: {erro}")
    finally:
        restaurando_mensagens.discard(guild.id)


# =========================================================
# LOGS
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
            embed.add_field(
                name="🌐 Servidor",
                value=(f"**{guild.name}**\nID: `{guild.id}`"),
                inline=False
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Sistema Anti-Nuke • Relatório privado")

        usuario = await bot.fetch_user(MEU_ID)
        await usuario.send(embed=embed)
    except Exception as erro:
        print(f"Erro enviando log privado para MEU_ID: {erro}")


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
                if entrada.user is None:
                    continue
                if bot.user and entrada.user.id == bot.user.id:
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
# PERMISSÕES DOS CANAIS NO BACKUP
# =========================================================

def construir_overwrites(guild, lista, mapa_cargos=None):
    overwrites = {}
    mapa_cargos = mapa_cargos or {}

    for ow in lista:
        if ow.get("is_role", False):
            id_antigo = int(ow["id"])
            alvo = (
                mapa_cargos.get(id_antigo)
                or mapa_cargos.get(str(id_antigo))
                or guild.get_role(id_antigo)
            )
        else:
            alvo = guild.get_member(int(ow["id"]))

        if alvo is not None:
            overwrites[alvo] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(ow["allow"]),
                discord.Permissions(ow["deny"])
            )

    return overwrites


# =========================================================
# CRIAR CANAL PELO BACKUP
# =========================================================

async def criar_canal_backup(guild, dados, mapa_categorias, mapa_cargos=None):
    tipo = dados.get("type", "")
    nome = dados["name"]
    categoria_id = dados.get("category_id")
    categoria = mapa_categorias.get(categoria_id) if categoria_id else None

    overwrites = construir_overwrites(guild, dados.get("overwrites", []), mapa_cargos)
    motivo = "Anti-Nuke: restauração manual via comando do dono"

    if "category" in tipo:
        novo = await guild.create_category(
            name=nome, position=dados.get("position", 0), overwrites=overwrites, reason=motivo
        )
        mapa_categorias[dados["id"]] = novo
    elif "text" in tipo:
        kwargs = {
            "name": nome, "category": categoria, "position": dados.get("position", 0),
            "topic": dados.get("topic"), "slowmode_delay": dados.get("slowmode", 0),
            "nsfw": dados.get("nsfw", False), "overwrites": overwrites, "reason": motivo
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
            name=nome, category=categoria, position=dados.get("position", 0),
            bitrate=dados.get("bitrate") or 64000, user_limit=dados.get("user_limit") or 0,
            overwrites=overwrites, reason=motivo
        )
    elif "forum" in tipo:
        metodo = getattr(guild, "create_forum", None)
        novo = await metodo(
            name=nome, category=categoria, position=dados.get("position", 0),
            topic=dados.get("topic"), slowmode_delay=dados.get("slowmode", 0),
            nsfw=dados.get("nsfw", False), overwrites=overwrites, reason=motivo
        )
    elif "stage" in tipo:
        metodo = getattr(guild, "create_stage_channel", None)
        novo = await metodo(
            name=nome, category=categoria, position=dados.get("position", 0),
            topic=dados.get("topic"), overwrites=overwrites, reason=motivo
        )
    else:
        raise RuntimeError(f"Tipo de canal não suportado: {tipo}")

    registrar_novo_id_canal(guild.id, dados["id"], novo.id)
    return novo


# =========================================================
# VISTA DE SELEÇÃO DE CANAIS PARA MENSAGENS
# =========================================================

class CanalMensagemSelect(discord.ui.Select):
    def __init__(self, canais_disponiveis):
        opcoes = [
            discord.SelectOption(
                label=f"#{c.name}"[:100],
                value=str(c.id),
                description="Restaurar mensagens neste canal"
            )
            for c in canais_disponiveis[:25]
        ]
        super().__init__(
            placeholder="Selecione os canais para restaurar mensagens...",
            min_values=1,
            max_values=min(len(opcoes), 25),
            options=opcoes
        )
        self.selecionados = []

    async def callback(self, interaction: discord.Interaction):
        self.selecionados = [int(v) for v in self.values]
        await interaction.response.send_message(
            f"✅ {len(self.selecionados)} canais selecionados para restauração de mensagens!",
            ephemeral=True
        )
        self.view.stop()


class ModalSelecaoCanaisMensagem(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=120)
        self.guild = guild
        self.canais_escolhidos = None
        
        # Pega todos os canais de texto atuais do servidor
        canais_lista = guild.text_channels
        if canais_lista:
            self.select_comp = CanalMensagemSelect(canais_lista)
            self.add_item(self.select_comp)

    @discord.ui.button(label="Restaurar em TODOS os canais", style=discord.ButtonStyle.primary, row=1)
    async def todos(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.canais_escolhidos = None  # None significa todos
        await interaction.response.send_message("✅ Mensagens serão restauradas em **todos** os canais!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, row=1)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.canais_escolhidos = []  # Lista vazia cancela
        await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)
        self.stop()


class ConfirmarRestauracaoView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.autorizado = False

    @discord.ui.button(label="Sim, restaurar servidor", emoji="⚠️", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Apenas o dono que executou o comando pode confirmar.", ephemeral=True)
            return

        self.autorizado = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="🔄 **Processo de restauração iniciado pelo Dono!** Aguarde...", view=self)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Apenas o dono pode cancelar.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Restauração cancelada.", view=None)
        self.stop()


# =========================================================
# EXECUTAR RESTAURAÇÃO COMPLETA VIA COMANDO !restaurar servidor
# =========================================================

async def executar_restauracao_manual(guild, ctx):
    lock = locks_restauracao[guild.id]
    if lock.locked():
        await ctx.send("⚠️ Já existe uma restauração em andamento neste servidor.")
        return

    async with lock:
        backup = carregar_backup(guild.id)
        if not backup["canais"] and not backup["cargos"]:
            await ctx.send("❌ Backup BOM vazio! Impossível restaurar.")
            return

        msg_progresso = await ctx.send("♻️ Lendo backup e preparando a limpeza do servidor...")

        salvar_mapa_canais(guild.id, {})
        mapa_novos_canais = {}

        canais_apagados = 0
        canais_restaurados = 0
        cargos_restaurados = 0
        erros_permissao = 0

        # FASE 1: Apagar canais atuais
        for canal in list(guild.channels):
            try:
                await canal.delete(reason="Restauração manual solicitada pelo Dono")
                canais_apagados += 1
                await asyncio.sleep(0.4)
            except Exception:
                erros_permissao += 1

        # FASE 2: Recriar Cargos
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
                        reason="Restauração manual"
                    )
                    cargos_restaurados += 1
                    await asyncio.sleep(0.4)
                except Exception:
                    erros_permissao += 1
                    continue
            mapa_cargos[id_antigo] = cargo
            mapa_cargos[str(id_antigo)] = cargo

        # FASE 3: Recriar Categorias e Canais
        mapa_categorias = {}
        categorias = [c for c in backup["canais"] if "category" in c.get("type", "")]
        demais = [c for c in backup["canais"] if "category" not in c.get("type", "")]

        for dados in categorias:
            try:
                novo = await criar_canal_backup(guild, dados, mapa_categorias, mapa_cargos)
                canais_restaurados += 1
                await asyncio.sleep(0.5)
            except Exception:
                erros_permissao += 1

        for dados in demais:
            try:
                novo = await criar_canal_backup(guild, dados, mapa_categorias, mapa_cargos)
                canais_restaurados += 1
                if isinstance(novo, discord.TextChannel):
                    mapa_novos_canais[int(dados["id"])] = novo
                await asyncio.sleep(0.5)
            except Exception:
                erros_permissao += 1

        await msg_progresso.edit(content=f"✅ **Servidor restaurado com sucesso!**\n- Canais: {canais_restaurados}\n- Cargos: {cargos_restaurados}")


# =========================================================
# COMANDO: !restaurar servidor E !restaurar msg (Somente o Dono)
# =========================================================

@bot.group(name="restaurar", invoke_without_command=True)
async def restaurar(ctx):
    if ctx.author.id != get_dono_id(ctx.guild):
        return
    await ctx.send("Uso correto:\n`!restaurar servidor`\n`!restaurar msg`", delete_after=7)


@restaurar.command(name="servidor")
async def restaurar_servidor(ctx):
    if ctx.author.id != get_dono_id(ctx.guild):
        await ctx.send("❌ Apenas o dono do servidor pode executar este comando.", delete_after=5)
        return

    view = ConfirmarRestauracaoView(ctx)
    msg = await ctx.send(
        "⚠️ **ATENÇÃO:** Você tem certeza que deseja **restaurar o servidor inteiro** através do backup?\n"
        "Todos os canais atuais serão apagados e substituídos pelo backup salvo!",
        view=view
    )

    await view.wait()
    if view.autorizado:
        await executar_restauracao_manual(ctx.guild, ctx)


@restaurar.command(name="msg", aliases=["mensagens"])
async def restaurar_msg_separado(ctx):
    if ctx.author.id != get_dono_id(ctx.guild):
        await ctx.send("❌ Apenas o dono do servidor pode executar este comando.", delete_after=5)
        return

    # Mapeia os canais atuais do servidor pelo ID atual para o próprio objeto canal
    mapa_atual = {c.id: c for c in ctx.guild.text_channels}

    view_msg = ModalSelecaoCanaisMensagem(ctx.guild)
    await ctx.send("💬 **Restauração avulsa de mensagens**\nEscolha abaixo onde deseja restaurar as mensagens salvas:", view=view_msg)
    await view_msg.wait()

    canais_escolhidos = view_msg.canais_escolhidos
    if canais_escolhidos != [] and canais_escolhidos is not None:
        # Se escolheu canais específicos, monta o dicionário mapeando ID -> Canal
        mapa_alvo = {cid: mapa_atual[cid] for cid in canais_escolhidos if cid in mapa_atual}
        asyncio.create_task(restaurar_mensagens_em_segundo_plano(ctx.guild, mapa_alvo, canais_alvo_ids=None))
        await ctx.send("💬 A restauração das mensagens nos canais selecionados foi iniciada em segundo plano!", delete_after=10)
    elif canais_escolhidos is None:
        # Se escolheu "TODOS", passa o mapa completo com todos os canais de texto
        mapa_todos = {c.id: c for c in ctx.guild.text_channels}
        asyncio.create_task(restaurar_mensagens_em_segundo_plano(ctx.guild, mapa_todos, canais_alvo_ids=None))
        await ctx.send("💬 A restauração das mensagens em **todos os canais** foi iniciada em segundo plano!", delete_after=10)


# =========================================================
# BANIMENTO / ATIVAÇÃO DO RAID (Sem restauração automática)
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


async def punir_pessoa(guild, executor_id, motivo):
    agora = time.time()
    if executor_id in ja_banidos and agora - ja_banidos[executor_id] < 60:
        return False

    try:
        membro = guild.get_member(executor_id)
        if membro is None:
            try:
                membro = await guild.fetch_member(executor_id)
            except discord.NotFound:
                membro = await bot.fetch_user(executor_id)

        await guild.ban(membro, reason=f"ANTI-NUKE: {motivo}")
        ja_banidos[executor_id] = agora

        await enviar_log(
            guild,
            "🔨 Pessoa punida — Anti-Nuke",
            f"**Executor:** <@{executor_id}> (`{executor_id}`)\n**Motivo:** {motivo}\n**Resultado:** banido. O servidor NÃO foi mexido.",
            cor=0xE67E22
        )
        return True
    except Exception:
        pass
    return False


async def punir(guild, executor_id, motivo):
    if guild is None or executor_id is None:
        return False
    if is_protegido(guild, executor_id):
        return False

    if await executor_eh_bot(guild, executor_id):
        return await punir_bot_raid(guild, executor_id, motivo)

    return await punir_pessoa(guild, executor_id, motivo)


async def punir_bot_raid(guild, executor_id, motivo):
    estado = get_raid(guild.id)
    primeiro_acionamento = not estado["ativo"]

    estado["ativo"] = True
    if primeiro_acionamento:
        estado["raider_id"] = executor_id

    estado["ultimo_ataque"] = time.time()
    estado["qtd_ataques"] += 1

    if primeiro_acionamento:
        try:
            membro = guild.get_member(executor_id)
            usuario = membro or await bot.fetch_user(executor_id)
            estado["raider_nome"] = str(usuario)
        except Exception:
            estado["raider_nome"] = f"ID {executor_id}"

        await enviar_log(
            guild,
            "🚨 RAID DE BOT DETECTADA",
            (
                f"**Servidor:** {guild.name}\n"
                f"**Responsável:** {estado['raider_nome']} (`{executor_id}`)\n"
                f"**Motivo:** {motivo}\n\n"
                "🛡️ O bot foi banido, mas **a restauração automática foi desativada**.\n"
                "Para restaurar o servidor, use o comando: `!restaurar servidor`\n"
                "Para restaurar apenas as mensagens, use: `!restaurar msg`"
            ),
            cor=0xE74C3C
        )

    agora = time.time()
    if executor_id in ja_banidos and agora - ja_banidos[executor_id] < 60:
        return False

    try:
        membro = guild.get_member(executor_id)
        if membro is None:
            try:
                membro = await guild.fetch_member(executor_id)
            except discord.NotFound:
                membro = await bot.fetch_user(executor_id)

        await guild.ban(membro, reason=f"ANTI-NUKE: {motivo}")
        ja_banidos[executor_id] = agora
        return True
    except Exception:
        pass
    return False


# =========================================================
# INICIALIZAÇÃO
# =========================================================

@bot.event
async def on_ready():
    global VIEWS_REGISTRADAS

    print(f"✅ ONLINE: {bot.user} | ANTI-NUKE ATUALIZADO")
    await bot.change_presence(activity=discord.Game(name="🛡️ PROTECTION ACTIVE"))

    if not VIEWS_REGISTRADAS:
        bot.add_view(TicketPanelView())
        bot.add_view(TicketCloseView())
        VIEWS_REGISTRADAS = True

    for guild in bot.guilds:
        try:
            if not os.path.exists(backup_bom_path(guild.id)):
                foto = tirar_foto_guild(guild)
                salvar_backup_bom(guild.id, foto)
                salvar_backup_temp(guild.id, foto)
            elif not os.path.exists(backup_temp_path(guild.id)):
                salvar_backup_temp(guild.id, tirar_foto_guild(guild))
        except Exception:
            pass

    if not sync_backup_loop.is_running():
        sync_backup_loop.start()

    if not backup_mensagens_loop.is_running():
        backup_mensagens_loop.start()

    if not verificar_tickets_sem_resposta.is_running():
        verificar_tickets_sem_resposta.start()

    if not fechar_tickets_por_inatividade.is_running():
        fechar_tickets_por_inatividade.start()


@bot.event
async def on_guild_join(guild):
    try:
        foto = tirar_foto_guild(guild)
        salvar_backup_bom(guild.id, foto)
        salvar_backup_temp(guild.id, foto)
    except Exception:
        pass


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


def limpar_estado_tickets_orfaos():
    if not bot.guilds:
        return
    existentes = {str(canal.id) for guild in bot.guilds for canal in guild.channels}
    orfaos = [k for k in estado_tickets if k not in existentes]
    if orfaos:
        for chave in orfaos:
            estado_tickets.pop(chave, None)
        _salvar_estado_tickets()


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


# =========================================================
# TRANSCRIÇÃO E FECHAMENTO DE TICKETS
# =========================================================

async def gerar_transcricao(canal, fechado_por=None):
    dados = ler_dados_ticket(canal)
    mensagens = []

    async for mensagem in canal.history(limit=None, oldest_first=True):
        data = mensagem.created_at.strftime("%d/%m/%Y às %H:%M:%S UTC")
        conteudo = mensagem.content or ""
        if mensagem.embeds: conteudo += "\n[Embed]"
        if mensagem.attachments: conteudo += "\nAnexos:\n" + "\n".join(f"- {a.url}" for a in mensagem.attachments)
        mensagens.append(f"[{data}] {mensagem.author}: {conteudo}")

    conteudo_final = "\n".join(mensagens) or "Nenhuma mensagem."
    arquivo = io.BytesIO(conteudo_final.encode("utf-8"))
    return discord.File(arquivo, filename=f"transcricao-{dados.get('numero') or 'ticket'}.txt")


async def fechar_ticket(canal, fechado_por):
    if not isinstance(canal, discord.TextChannel):
        return False
    dados = ler_dados_ticket(canal)
    if dados["owner_id"] is None:
        return False

    try:
        arquivo = await gerar_transcricao(canal, fechado_por)
        usuario = await bot.fetch_user(dados["owner_id"])
        await usuario.send("Seu ticket foi fechado. Segue o histórico:", file=arquivo)
    except Exception:
        pass

    try:
        await canal.delete(reason=f"Ticket fechado por {fechado_por}")
        return True
    except Exception:
        return False


# =========================================================
# ALERTAS DE TICKETS
# =========================================================

@tasks.loop(minutes=1)
async def verificar_tickets_sem_resposta():
    for guild in bot.guilds:
        for canal in list(guild.text_channels):
            try:
                dados = ler_dados_ticket(canal)
                if not dados["owner_id"] or dados.get("alertado"):
                    continue
            except Exception:
                pass


@tasks.loop(minutes=1)
async def fechar_tickets_por_inatividade():
    pass


@verificar_tickets_sem_resposta.before_loop
async def antes_verificar_tickets():
    await bot.wait_until_ready()


@fechar_tickets_por_inatividade.before_loop
async def antes_fechar_tickets_por_inatividade():
    await bot.wait_until_ready()


# =========================================================
# MENSAGENS E COMANDOS
# =========================================================

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    if message.content.startswith("!"):
        ctx = await bot.get_context(message)
        try:
            await message.delete()
        except Exception:
            pass
        if ctx.command:
            await bot.invoke(ctx)
        return


# =========================================================
# DETECÇÃO DE AÇÕES EM MASSA (ANTI-NUKE)
# =========================================================

def acao_em_massa(tipo, executor_id):
    limite, janela = LIMITES_MASSA.get(tipo, LIMITE_PADRAO_MASSA)
    if registrou(tipo, executor_id, limite, janela):
        return True
    limite_c, janela_c = LIMITE_COMBINADO
    return registrou("combinado", executor_id, limite_c, janela_c)


async def checar_massa(guild, executor, tipo, rotulo):
    if executor is None or (bot.user and executor == bot.user.id):
        return False
    if is_protegido(guild, executor):
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
async def on_guild_channel_create(channel):
    guild = channel.guild
    executor = await pegar_executor(guild, discord.AuditLogAction.channel_create, channel.id)
    await checar_massa(guild, executor, "canal_criar", "Criou canais")


@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    executor = await pegar_executor(guild, discord.AuditLogAction.channel_delete, channel.id)
    await checar_massa(guild, executor, "canal_del", "Deletou canais")


@bot.event
async def on_guild_role_create(role):
    guild = role.guild
    executor = await pegar_executor(guild, discord.AuditLogAction.role_create, role.id)
    await checar_massa(guild, executor, "cargo_criar", "Criou cargos")


@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    executor = await pegar_executor(guild, discord.AuditLogAction.role_delete, role.id)
    await checar_massa(guild, executor, "cargo_del", "Deletou cargos")


# =========================================================
# COMANDOS DE SUPORTE E UTILIDADES
# =========================================================

@bot.command(name="atualizar")
async def atualizar_backup(ctx):
    if ctx.author.id != get_dono_id(ctx.guild):
        return
    try:
        foto = tirar_foto_guild(ctx.guild)
        salvar_backup_bom(ctx.guild.id, foto)
        salvar_backup_temp(ctx.guild.id, foto)
        await ctx.send("✅ Backup manual atualizado com sucesso!", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Erro ao atualizar: {e}", delete_after=5)


# =========================================================
# SISTEMA DE TICKETS — VIEWS E BOTÕES
# =========================================================

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fechar ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not eh_responsavel_ticket(interaction.guild, interaction.user):
            await interaction.response.send_message("Apenas a staff pode fechar.", ephemeral=True)
            return
        await interaction.response.send_message("Fechando...", ephemeral=True)
        await fechar_ticket(interaction.channel, interaction.user)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir ticket", emoji="🎫", style=discord.ButtonStyle.success, custom_id="ticket_abrir")
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        membro = interaction.user
        numero = await proximo_numero_ticket(guild.id)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membro: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        canal = await guild.create_text_channel(name=f"ticket-{numero}", overwrites=overwrites)
        await canal.send(f"Olá {membro.mention}, como podemos ajudar?", view=TicketCloseView())
        await interaction.response.send_message(f"Ticket criado: {canal.mention}", ephemeral=True)


@bot.command(name="ticket")
async def ticket_cmd(ctx, acao: str, canal: discord.TextChannel = None):
    if ctx.author.id != get_dono_id(ctx.guild):
        return
    if acao == "painel" and canal:
        await canal.send("🎫 Clique abaixo para abrir um atendimento:", view=TicketPanelView())
        await ctx.send("Painel enviado!")


# =========================================================
# TOKEN DO BOT
# =========================================================

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("A variável de ambiente TOKEN não foi configurada.")

bot.run(TOKEN)
