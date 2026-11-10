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

JANELA_RAID = 3
LIMITE_RESTAURACAO = 12
INTERVALO_AUDIT = 0.35
MAX_TENTATIVAS_AUDIT = 4

TEMPO_ALERTA_TICKET = 30 * 60
TEMPO_FECHAMENTO_INATIVIDADE_TICKET = 3 * 60 * 60

VIEWS_REGISTRADAS = False

# Locks para evitar dois tickets com o mesmo número.
locks_tickets = defaultdict(asyncio.Lock)
locks_backup_mensagens = defaultdict(asyncio.Lock)


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

    if bot.user and user_id == bot.user.id:
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


def salvar_backup(guild_id, dados):
    return _salvar_arquivo(backup_bom_path(guild_id), dados)


def salvar_backup_temp(guild_id, dados):
    return _salvar_arquivo(backup_temp_path(guild_id), dados)


def salvar_backup_bom(guild_id, dados):
    # Atualizações da estrutura nunca apagam o histórico de mensagens.
    dados = dict(dados)
    if not dados.get("mensagens"):
        anterior = _carregar_arquivo(backup_bom_path(guild_id))
        dados["mensagens"] = anterior.get("mensagens", {})
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
        "cargos": [],
        "mensagens": {}
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


def registrou(tipo, user_id, limite=2, janela=JANELA_RAID):
    agora = time.time()
    chave = (tipo, user_id)

    acoes[chave] = [
        t for t in acoes[chave]
        if agora - t < janela
    ]

    acoes[chave].append(agora)

    return len(acoes[chave]) >= limite


# =========================================================
# BACKUP AUTOMÁTICO
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

            print(f"🔄 Backup atualizado: {guild.name}")

        except Exception as erro:
            print(f"Erro sync backup {guild.name}: {erro}")


@sync_backup_loop.before_loop
async def antes_sync():
    await bot.wait_until_ready()


# =========================================================
# BACKUP CONTÍNUO DAS ÚLTIMAS 20 MENSAGENS
# =========================================================

MSG_POR_CANAL = 20
INTERVALO_BACKUP_MSGS_MIN = 5


def arquivo_backup_msgs(guild_id):
    # O histórico fica dentro do mesmo JSON principal dos canais e cargos.
    return backup_bom_path(guild_id)


def _nome_arquivo_seguro(nome):
    nome = os.path.basename(str(nome or "anexo"))
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", nome)
    return nome[:120] or "anexo"


async def _serializar_mensagem(mensagem):
    anexos = []
    pasta = os.path.join(
        "backup_anexos",
        str(mensagem.guild.id),
        str(mensagem.channel.id)
    )
    os.makedirs(pasta, exist_ok=True)

    for indice, anexo in enumerate(mensagem.attachments[:10]):
        nome_seguro = _nome_arquivo_seguro(anexo.filename)
        nome_local = f"{mensagem.id}_{indice}_{nome_seguro}"
        caminho = os.path.join(pasta, nome_local)

        # O arquivo só é baixado uma vez; os próximos ciclos reutilizam a cópia.
        limite_download = min(
            int(getattr(mensagem.guild, "filesize_limit", 25 * 1024 * 1024)),
            25 * 1024 * 1024
        )
        if not os.path.exists(caminho) and anexo.size <= limite_download:
            try:
                conteudo_arquivo = await anexo.read()
                with open(caminho, "wb") as arquivo_local:
                    arquivo_local.write(conteudo_arquivo)
            except Exception as erro:
                print(f"Não foi possível salvar anexo {anexo.filename}: {erro}")
                caminho = None
        elif not os.path.exists(caminho):
            caminho = None

        anexos.append({
            "filename": anexo.filename,
            "url": anexo.url,
            "content_type": anexo.content_type,
            "size": anexo.size,
            "local_path": caminho
        })

    embeds = []
    for embed in mensagem.embeds:
        try:
            embeds.append(embed.to_dict())
        except Exception:
            pass

    avatar = None
    try:
        avatar = mensagem.author.display_avatar.url
    except Exception:
        pass

    return {
        "id": mensagem.id,
        "author_id": mensagem.author.id,
        "author_name": str(mensagem.author),
        "author_display_name": getattr(mensagem.author, "display_name", str(mensagem.author)),
        "author_avatar": avatar,
        "author_is_bot": bool(mensagem.author.bot),
        "content": mensagem.content or "",
        "created_at": mensagem.created_at.isoformat(),
        "attachments": anexos,
        "embeds": embeds
    }


async def capturar_mensagens_canal(canal):
    if not isinstance(canal, discord.TextChannel):
        return []

    mensagens = []
    try:
        async for mensagem in canal.history(limit=MSG_POR_CANAL):
            mensagens.append(await _serializar_mensagem(mensagem))
        mensagens.reverse()
    except discord.Forbidden:
        print(f"Sem permissão para ler histórico em #{canal.name}.")
        return None
    except discord.HTTPException as erro:
        print(f"Erro lendo mensagens de #{canal.name}: {erro}")
        return None

    return mensagens[-MSG_POR_CANAL:]


async def salvar_backup_mensagens_guild(guild):
    total = 0

    for canal in list(guild.text_channels):
        try:
            mensagens_novas = await capturar_mensagens_canal(canal)
            if mensagens_novas is None:
                continue

            async with locks_backup_mensagens[guild.id]:
                dados = carregar_backup(guild.id)
                historico = dados.setdefault("mensagens", {})
                anteriores = historico.get(str(canal.id), {}).get("messages", [])
                por_id = {
                    str(m.get("id")): m
                    for m in (anteriores + mensagens_novas)
                    if m.get("id") is not None
                }
                mensagens_consolidadas = sorted(
                    por_id.values(),
                    key=lambda m: m.get("created_at", "")
                )[-MSG_POR_CANAL:]

                historico[str(canal.id)] = {
                    "channel_id": canal.id,
                    "channel_name": canal.name,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "messages": mensagens_consolidadas
                }
                salvar_backup_bom(guild.id, dados)

            total += len(mensagens_consolidadas)
            await asyncio.sleep(0.15)
        except Exception as erro:
            print(f"Erro no backup de mensagens de #{canal.name}: {erro}")

    print(f"💬 Backup de mensagens atualizado: {guild.name} ({total} mensagens).")
    return total

@tasks.loop(minutes=INTERVALO_BACKUP_MSGS_MIN)
async def backup_mensagens_loop():
    for guild in bot.guilds:
        try:
            await salvar_backup_mensagens_guild(guild)
        except Exception as erro:
            print(f"Erro no backup periódico de mensagens em {guild.name}: {erro}")


@backup_mensagens_loop.before_loop
async def antes_backup_mensagens():
    await bot.wait_until_ready()


def obter_mensagens_backup(guild_id, canal_id):
    dados = carregar_backup(guild_id)
    item = dados.get("mensagens", {}).get(str(canal_id), {})
    mensagens = item.get("messages", []) if isinstance(item, dict) else []
    return mensagens[-MSG_POR_CANAL:]


async def salvar_mensagem_individual(mensagem):
    if (
        mensagem.guild is None
        or not isinstance(mensagem.channel, discord.TextChannel)
        or mensagem.webhook_id is not None
        or (bot.user and mensagem.author.id == bot.user.id)
    ):
        return

    nova = await _serializar_mensagem(mensagem)
    async with locks_backup_mensagens[mensagem.guild.id]:
        dados = carregar_backup(mensagem.guild.id)
        historico = dados.setdefault("mensagens", {})
        chave = str(mensagem.channel.id)
        item = historico.get(chave, {})
        anteriores = item.get("messages", []) if isinstance(item, dict) else []

        por_id = {
            str(m.get("id")): m
            for m in (anteriores + [nova])
            if m.get("id") is not None
        }
        mensagens = sorted(
            por_id.values(),
            key=lambda m: m.get("created_at", "")
        )[-MSG_POR_CANAL:]

        historico[chave] = {
            "channel_id": mensagem.channel.id,
            "channel_name": mensagem.channel.name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "messages": mensagens
        }
        salvar_backup_bom(mensagem.guild.id, dados)


# =========================================================
# LOGS — SOMENTE PARA O DONO DO BOT
# =========================================================

async def enviar_log_simples(guild, titulo, descricao, cor=0xFF0000):
    """
    Envia os logs exclusivamente por mensagem privada para MEU_ID.
    Não envia logs para o canal configurado e não envia DM
    para o dono do servidor onde ocorreu o evento.
    """

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


# =========================================================
# AUDIT LOG
# =========================================================

async def pegar_executor(guild, action, target_id=None, janela=12):
    if guild is None:
        return None

    for tentativa in range(MAX_TENTATIVAS_AUDIT):
        try:
            async for entrada in guild.audit_logs(limit=12, action=action):
                idade = (
                    discord.utils.utcnow() - entrada.created_at
                ).total_seconds()

                if idade < 0 or idade > janela:
                    continue

                if entrada.user is None:
                    continue

                if bot.user and entrada.user.id == bot.user.id:
                    continue

                if target_id is not None:
                    alvo = getattr(entrada, "target", None)

                    if (
                        alvo is None
                        or getattr(alvo, "id", None) != target_id
                    ):
                        continue

                return entrada.user.id

        except discord.Forbidden:
            print(f"Sem permissão para consultar Audit Log em {guild.name}.")
            return None

        except Exception as erro:
            print(f"Erro consultando Audit Log: {erro}")

        if tentativa < MAX_TENTATIVAS_AUDIT - 1:
            await asyncio.sleep(INTERVALO_AUDIT)

    return None


# =========================================================
# AGENDAMENTO DA RESTAURAÇÃO
# =========================================================

def agendar_recuperacao(guild):
    """
    Compatibilidade com os eventos antigos do Anti-Nuke.
    Aguarda o fim da sequência de ataques apenas para limpar o estado.
    Não recria, apaga ou edita canais/cargos.
    """
    estado = get_raid(guild.id)
    estado["ultimo_ataque"] = time.time()

    tarefa = estado.get("timer")
    if tarefa and not tarefa.done():
        tarefa.cancel()

    async def finalizar_modo_raid():
        try:
            while True:
                restante = LIMITE_RESTAURACAO - (time.time() - estado["ultimo_ataque"])
                if restante <= 0:
                    break
                await asyncio.sleep(min(restante, 2))

            estado["ativo"] = False
            estado["restaurando"] = False
            estado["timer"] = None
            print(f"🛡️ Modo de detecção de raid encerrado em {guild.name}.")
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            print(f"Erro encerrando estado de raid: {erro}")
        finally:
            if estado.get("timer") is asyncio.current_task():
                estado["timer"] = None

    estado["timer"] = asyncio.create_task(finalizar_modo_raid())


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
            overwrites[alvo] = (
                discord.PermissionOverwrite.from_pair(
                    discord.Permissions(ow["allow"]),
                    discord.Permissions(ow["deny"])
                )
            )

    return overwrites


# =========================================================
# CRIAR CANAL PELO BACKUP
# =========================================================

async def criar_canal_backup(
    guild,
    dados,
    mapa_categorias,
    mapa_cargos=None
):
    tipo = dados.get("type", "")
    nome = dados["name"]

    categoria_id = dados.get("category_id")

    categoria = (
        mapa_categorias.get(categoria_id)
        if categoria_id
        else None
    )

    overwrites = construir_overwrites(
        guild,
        dados.get("overwrites", []),
        mapa_cargos
    )

    motivo = "Anti-Nuke: restauração do backup BOM"

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
            parametros = inspect.signature(
                guild.create_text_channel
            ).parameters

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

        if metodo is None:
            raise RuntimeError(
                "Esta versão do discord.py não oferece create_forum."
            )

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

        if metodo is None:
            raise RuntimeError(
                "Esta versão do discord.py não oferece create_stage_channel."
            )

        novo = await metodo(
            name=nome,
            category=categoria,
            position=dados.get("position", 0),
            topic=dados.get("topic"),
            overwrites=overwrites,
            reason=motivo
        )

    else:
        raise RuntimeError(f"Tipo de canal não suportado: {tipo}")

    estado = get_raid(guild.id)
    estado["canais_criados_pelo_bot"].add(novo.id)

    registrar_novo_id_canal(guild.id, dados["id"], novo.id)

    return novo


# =========================================================
# RESTAURAÇÃO COMPLETA
# =========================================================

async def restaurar_tudo(guild):
    """
    Compatibilidade com chamadas antigas.
    A restauração agora é manual e não apaga canais/cargos existentes.
    """
    return await restaurar_estrutura_manual(guild)


# =========================================================
# BANIMENTO / ATIVAÇÃO DO RAID
# =========================================================

async def punir(guild, executor_id, motivo):
    if guild is None or executor_id is None:
        return False

    if bot.user and executor_id == bot.user.id:
        return False

    if is_protegido(guild, executor_id):
        return False

    estado = get_raid(guild.id)
    primeiro_acionamento = not estado["ativo"]

    estado["ativo"] = True

    if primeiro_acionamento:
        estado["raider_id"] = executor_id

    estado["ultimo_ataque"] = time.time()
    estado["qtd_ataques"] += 1

    estado["canais_raid_criados"].update(
        canais_pendentes_por_executor.get(
            (guild.id, executor_id),
            set()
        )
    )

    if (
        primeiro_acionamento
        or estado["raider_nome"] == "Desconhecido"
    ):
        try:
            membro = guild.get_member(executor_id)
            usuario = membro or await bot.fetch_user(executor_id)
            estado["raider_nome"] = str(usuario)

        except Exception:
            estado["raider_nome"] = f"ID {executor_id}"

    # Avisa você somente na primeira detecção desta raid.
    if primeiro_acionamento:
        await enviar_log(
            guild,
            "🚨 RAID DETECTADA — PROTEÇÃO ATIVADA",
            (
                f"**Servidor:** {guild.name}\n"
                f"**Possível responsável:** {estado['raider_nome']} "
                f"(`{executor_id}`)\n"
                f"**Primeira ação identificada:** {motivo}\n\n"
                "🛡️ O Anti-Nuke foi ativado. O invasor será punido "
                "e os eventos serão registrados. Nenhuma restauração "
                "automática será executada; use `!restaurar` quando quiser."

            ),
            cor=0xE74C3C
        )

    agendar_recuperacao(guild)

    agora = time.time()

    if (
        executor_id in ja_banidos
        and agora - ja_banidos[executor_id] < 60
    ):
        return False

    try:
        membro = guild.get_member(executor_id)

        if membro is None:
            try:
                membro = await guild.fetch_member(executor_id)
            except discord.NotFound:
                membro = await bot.fetch_user(executor_id)

        await guild.ban(
            membro,
            reason=f"ANTI-NUKE: {motivo}"
        )

        ja_banidos[executor_id] = agora

        print(f"🚨 Banido: {membro} - {motivo}")

        await enviar_log(
            guild,
            "🚨 Banido — Anti-Nuke",
            f"**Executor:** <@{executor_id}> (`{executor_id}`)\n"
            f"**Motivo:** {motivo}\n"
            "**Resultado:** banimento aplicado com sucesso.",
            cor=0xE74C3C
        )

        return True

    except discord.Forbidden as erro:
        print(
            f"Sem permissão/hierarquia para banir "
            f"{executor_id}: {erro}"
        )

        await enviar_log(
            guild,
            "⚠️ Anti-Nuke — Não foi possível banir",
            (
                f"**Executor:** <@{executor_id}> (`{executor_id}`)\n"
                f"**Motivo:** {motivo}\n"
                "O bot detectou a ação, mas não conseguiu banir "
                "o usuário. Verifique a hierarquia de cargos "
                "e as permissões do bot."
            ),
            cor=0xFFA500
        )

    except Exception as erro:
        print(f"Erro ao punir {executor_id}: {erro}")

    return False


# =========================================================
# INICIALIZAÇÃO
# =========================================================

@bot.event
async def on_ready():
    global VIEWS_REGISTRADAS

    print(f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP DUPLO")

    await bot.change_presence(
        activity=discord.Game(name="🛡️ SYSTEM PROTECTING")
    )

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

    if not sync_backup_loop.is_running():
        sync_backup_loop.start()

    if not backup_mensagens_loop.is_running():
        backup_mensagens_loop.start()

    # Na primeira inicialização, cria também o histórico inicial de mensagens.
    for guild in bot.guilds:
        try:
            if not carregar_backup(guild.id).get("mensagens"):
                await salvar_backup_mensagens_guild(guild)
        except Exception as erro:
            print(f"Erro no backup inicial de mensagens ({guild.name}): {erro}")

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
        await salvar_backup_mensagens_guild(guild)

        print(f"📸 Novo servidor, backup criado: {guild.name}")

    except Exception as erro:
        print(f"Erro criando backup do novo servidor: {erro}")


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
    except Exception as erro:
        print(f"Erro lendo contador de tickets: {erro}")

    return 0


def salvar_contador_ticket(guild_id, numero):
    path = arquivo_contador_ticket(guild_id)
    temporario = path + ".tmp"

    try:
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump({"contador": numero}, f)

        os.replace(temporario, path)
        return True

    except Exception as erro:
        print(f"Erro salvando contador de tickets: {erro}")
        return False


async def proximo_numero_ticket(guild_id):
    async with locks_tickets[guild_id]:
        numero = carregar_contador_ticket(guild_id) + 1
        salvar_contador_ticket(guild_id, numero)
        return numero


def _ler_dados_topic(canal):
    """
    Lê os dados do ticket pelo topic.
    Também aceita o formato antigo ticket_owner:ID.
    """

    topic = getattr(canal, "topic", None) or ""

    dados = {
        "owner_id": None,
        "numero": None,
        "aberto_em": None,
        "alertado": False,
        "respondido": False,
        "assumido_por": None,
        "ultima_atividade": None,
        "ultimo_alerta_msg": None,
        "msg_controle_id": None
    }

    if not topic:
        return dados

    partes = topic.split("|")

    for parte in partes:
        if ":" not in parte:
            continue

        chave, valor = parte.split(":", 1)

        try:
            if chave == "ticket_owner":
                dados["owner_id"] = int(valor)

            elif chave == "ticket_numero":
                dados["numero"] = int(valor)

            elif chave == "ticket_aberto":
                dados["aberto_em"] = int(valor)

            elif chave == "ticket_alertado":
                dados["alertado"] = valor == "1"

            elif chave == "ticket_respondido":
                dados["respondido"] = valor == "1"

            elif chave == "ticket_assumido_por":
                dados["assumido_por"] = int(valor) if valor not in ("", "None", "0") else None

            elif chave == "ticket_ultima_atividade":
                dados["ultima_atividade"] = int(valor)

            elif chave == "ticket_ultimo_alerta_msg":
                dados["ultimo_alerta_msg"] = valor or None

        except (ValueError, TypeError):
            pass

    return dados


# Estado dinâmico dos tickets (assumido, atividade, alertas...).
# Antes isso era gravado no tópico do canal, e o Discord limita muito
# a edição de canais (cerca de 2 edições a cada 10 minutos), por isso
# assumir/enviar mensagem demorava. Agora fica em arquivo + memória,
# o que é instantâneo. O tópico continua com os dados fixos do ticket.
ARQUIVO_ESTADO_TICKETS = "estado_tickets.json"
CAMPOS_ESTADO_TICKET = (
    "alertado",
    "respondido",
    "assumido_por",
    "ultima_atividade",
    "ultimo_alerta_msg",
    "msg_controle_id"
)
estado_tickets = {}


def _carregar_estado_tickets():
    global estado_tickets

    try:
        if os.path.exists(ARQUIVO_ESTADO_TICKETS):
            with open(ARQUIVO_ESTADO_TICKETS, "r", encoding="utf-8") as f:
                dados = json.load(f)

            if isinstance(dados, dict):
                estado_tickets = dados

    except Exception as erro:
        print(f"Erro lendo estado dos tickets: {erro}")


def _salvar_estado_tickets():
    temporario = ARQUIVO_ESTADO_TICKETS + ".tmp"

    try:
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(estado_tickets, f, ensure_ascii=False)

        os.replace(temporario, ARQUIVO_ESTADO_TICKETS)
        return True

    except Exception as erro:
        print(f"Erro salvando estado dos tickets: {erro}")
        return False


def limpar_estado_tickets_orfaos():
    """Remove do arquivo o estado de tickets cujo canal não existe mais."""

    if not bot.guilds:
        return

    existentes = {
        str(canal.id)
        for guild in bot.guilds
        for canal in guild.channels
    }

    orfaos = [k for k in estado_tickets if k not in existentes]

    if orfaos:
        for chave in orfaos:
            estado_tickets.pop(chave, None)

        _salvar_estado_tickets()


_carregar_estado_tickets()


def ler_dados_ticket(canal):
    """Dados fixos vêm do tópico; dados que mudam vêm do estado salvo."""

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

    except Exception as erro:
        print(f"Erro atualizando dados do ticket: {erro}")
        return False


def eh_responsavel_ticket(guild, membro):
    if guild is None or membro is None:
        return False

    if membro.id == guild.owner_id:
        return True

    if membro.id in ADM_CONFIANCA:
        return True

    permissoes = membro.guild_permissions

    if permissoes.administrator or permissoes.manage_channels:
        return True

    return False


def obter_responsaveis_ticket(guild):
    responsaveis = {}

    dono = guild.get_member(guild.owner_id)

    if dono:
        responsaveis[dono.id] = dono

    for membro in guild.members:
        if eh_responsavel_ticket(guild, membro):
            responsaveis[membro.id] = membro

    for user_id in ADM_CONFIANCA:
        try:
            membro = guild.get_member(user_id)

            if membro:
                responsaveis[membro.id] = membro
        except Exception:
            pass

    return list(responsaveis.values())


# =========================================================
# TRANSCRIÇÃO E FECHAMENTO
# =========================================================

async def gerar_transcricao(canal, fechado_por=None):
    dados = ler_dados_ticket(canal)
    mensagens = []

    async for mensagem in canal.history(limit=None, oldest_first=True):
        data = mensagem.created_at.strftime("%d/%m/%Y às %H:%M:%S UTC")
        conteudo = mensagem.content or ""

        if mensagem.embeds:
            conteudo += "\n[Mensagem contém embed]"

        if mensagem.attachments:
            conteudo += "\nANEXOS:\n" + "\n".join(
                f"- {anexo.filename}: {anexo.url}"
                for anexo in mensagem.attachments
            )

        if mensagem.stickers:
            conteudo += "\n[Sticker enviado]"

        if not conteudo.strip():
            conteudo = "[Mensagem sem texto]"

        mensagens.append(
            f"{'─' * 72}\n"
            f"MENSAGEM {len(mensagens) + 1:03d}\n"
            f"Data: {data}\n"
            f"Autor: {mensagem.author}\n"
            f"ID do autor: {mensagem.author.id}\n"
            f"{'─' * 72}\n"
            f"{conteudo}\n"
        )

    inicio = dados.get("aberto_em")
    if inicio:
        data_inicio = datetime.fromtimestamp(inicio, timezone.utc)
        duracao = max(0, int(time.time() - inicio))
        horas, resto = divmod(duracao, 3600)
        minutos, segundos = divmod(resto, 60)
        tempo_aberto = f"{horas}h {minutos}min {segundos}s"
        data_formatada = data_inicio.strftime("%d/%m/%Y às %H:%M:%S UTC")
    else:
        tempo_aberto = "Não registrado"
        data_formatada = "Não registrado"

    numero = dados.get('numero') or 'Não registrado'
    solicitante = f"ID {dados['owner_id']}" if dados.get('owner_id') else "Não registrado"
    encerramento = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M:%S UTC")
    responsavel = str(fechado_por) if fechado_por is not None else "Não registrado"

    cabecalho = (
        "╔══════════════════════════════════════════════════════════════════════╗\n"
        "                         HISTÓRICO DE ATENDIMENTO\n"
        "╚══════════════════════════════════════════════════════════════════════╝\n\n"
        f"SERVIDOR: {canal.guild.name}\n"
        f"CANAL: #{canal.name}\n"
        f"PROTOCOLO: #{numero}\n"
        f"SOLICITANTE: {solicitante}\n"
        f"ABERTO EM: {data_formatada}\n"
        f"TEMPO DE ATENDIMENTO: {tempo_aberto}\n"
        f"ENCERRADO EM: {encerramento}\n"
        f"ENCERRADO POR: {responsavel}\n"
        f"TOTAL DE MENSAGENS: {len(mensagens)}\n\n"
        f"{'=' * 72}\n"
        "                         CONVERSA DO TICKET\n"
        f"{'=' * 72}\n\n"
    )

    conteudo_final = cabecalho + ("\n".join(mensagens) if mensagens else "Nenhuma mensagem foi registrada neste ticket.\n")
    arquivo = io.BytesIO(conteudo_final.encode("utf-8"))
    return discord.File(arquivo, filename=f"historico-atendimento-{dados.get('numero') or 'ticket'}.txt")


async def fechar_ticket(canal, fechado_por):
    if not isinstance(canal, discord.TextChannel):
        return False

    dados = ler_dados_ticket(canal)
    guild = canal.guild
    if dados["owner_id"] is None:
        return False

    arquivo = None
    try:
        arquivo = await gerar_transcricao(canal, fechado_por)
    except Exception as erro:
        print(f"Erro gerando transcrição: {erro}")

    # Evita enviar duas mensagens caso o solicitante também seja o dono do servidor.
    destinatarios = {guild.owner_id, dados["owner_id"]}
    destinatarios.discard(None)

    for user_id in destinatarios:
        try:
            usuario = await bot.fetch_user(user_id)
            eh_solicitante = user_id == dados["owner_id"]
            embed = discord.Embed(
                title=("✅ Atendimento finalizado" if eh_solicitante else "📋 Relatório de atendimento encerrado"),
                description=(
                    "Seu atendimento foi encerrado. O histórico completo da conversa está anexado." 
                    if eh_solicitante else
                    "Um ticket foi encerrado no servidor. Confira os dados e o histórico da conversa em anexo."
                ),
                color=0x2ECC71,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="🌐 Servidor", value=guild.name, inline=False)
            embed.add_field(name="🎫 Ticket", value=f"`#{dados.get('numero') or 'Sem número'}` • `#{canal.name}`", inline=True)
            embed.add_field(name="👤 Solicitante", value=f"<@{dados['owner_id']}>\n`{dados['owner_id']}`", inline=True)
            embed.add_field(name="🔒 Encerrado por", value=str(fechado_por), inline=False)
            embed.add_field(
                name="📎 Histórico da conversa",
                value="Arquivo TXT anexado com as mensagens, datas, autores e anexos do atendimento." if arquivo else "Não foi possível gerar o arquivo de histórico.",
                inline=False
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Central de Atendimento • Relatório automático")

            if arquivo:
                arquivo.fp.seek(0)
                await usuario.send(embed=embed, file=discord.File(arquivo.fp, filename=arquivo.filename))
            else:
                await usuario.send(embed=embed)
        except Exception as erro:
            print(f"Não foi possível enviar relatório para {user_id}: {erro}")

    try:
        await canal.delete(reason=f"Ticket fechado por {fechado_por}")
        return True
    except Exception as erro:
        print(f"Erro excluindo ticket: {erro}")
        return False


# =========================================================
# ALERTA DE TICKET SEM RESPOSTA
# =========================================================

async def notificar_responsaveis_ticket(canal, dados):
    guild = canal.guild

    responsaveis = obter_responsaveis_ticket(guild)

    mensagem = (
        "🎫 **Ticket aguardando atendimento**\n"
        f"Servidor: **{guild.name}**\n"
        f"Ticket: **{canal.name}**\n"
        f"Autor: <@{dados['owner_id']}>\n"
        f"Canal: {canal.mention}\n\n"
        "Este ticket está aberto há 30 minutos "
        "e ainda não recebeu resposta de um responsável."
    )

    enviados = 0

    for responsavel in responsaveis:
        try:
            await responsavel.send(mensagem)
            enviados += 1
            await asyncio.sleep(0.3)

        except Exception:
            pass

    return enviados


@tasks.loop(minutes=1)
async def verificar_tickets_sem_resposta():
    for guild in bot.guilds:
        for canal in list(guild.text_channels):
            try:
                dados = ler_dados_ticket(canal)
                if not dados["owner_id"]:
                    continue

                # O alerta depende sempre da última mensagem humana do canal.
                # Se a última mensagem for da equipe, não há cobrança.
                ultima_mensagem_humana = None
                async for mensagem in canal.history(limit=30):
                    if not mensagem.author.bot:
                        ultima_mensagem_humana = mensagem
                        break

                if ultima_mensagem_humana is None:
                    continue

                if ultima_mensagem_humana.author.id != dados["owner_id"]:
                    continue

                mensagem_id = str(ultima_mensagem_humana.id)
                if dados.get("ultimo_alerta_msg") == mensagem_id:
                    continue

                tempo_sem_resposta = (
                    discord.utils.utcnow() - ultima_mensagem_humana.created_at
                ).total_seconds()
                if tempo_sem_resposta < TEMPO_ALERTA_TICKET:
                    continue

                # Salva o ID antes de notificar para impedir alertas duplicados.
                atualizado = await atualizar_dados_ticket(
                    canal,
                    ultimo_alerta_msg=mensagem_id,
                    alertado=True
                )
                if not atualizado:
                    continue

                enviados = await notificar_responsaveis_ticket(canal, dados)

                try:
                    await canal.send(
                        content=(
                            f"<@{dados['owner_id']}> ⏰\n\n"
                            "Sua última mensagem está aguardando uma resposta "
                            "da equipe há **30 minutos**. Já avisamos os "
                            "administradores e responsáveis pelo atendimento."
                        ),
                        allowed_mentions=discord.AllowedMentions(users=True)
                    )
                except Exception as erro:
                    print(f"Erro avisando autor do ticket: {erro}")

                print(
                    f"⏰ Alerta de ticket enviado: {canal.name} "
                    f"| Responsáveis notificados: {enviados}"
                )

            except Exception as erro:
                print(f"Erro verificando ticket {canal.name}: {erro}")


@tasks.loop(minutes=1)
async def fechar_tickets_por_inatividade():
    """Fecha tickets que ficam 3 horas sem nenhuma nova mensagem."""
    agora = int(time.time())

    try:
        limpar_estado_tickets_orfaos()
    except Exception as erro:
        print(f"Erro limpando estado de tickets: {erro}")

    for guild in bot.guilds:
        for canal in list(guild.text_channels):
            try:
                dados = ler_dados_ticket(canal)
                if not dados["owner_id"]:
                    continue

                ultima_atividade = dados.get("ultima_atividade")

                # Compatibilidade com tickets antigos que ainda não possuem
                # o campo de última atividade no tópico.
                if not ultima_atividade:
                    ultima_atividade = dados.get("aberto_em")
                    try:
                        async for mensagem in canal.history(limit=100):
                            if not mensagem.author.bot:
                                ultima_atividade = int(mensagem.created_at.timestamp())
                                break
                    except Exception as erro:
                        print(f"Erro lendo atividade antiga do ticket {canal.name}: {erro}")

                    if ultima_atividade:
                        await atualizar_dados_ticket(
                            canal,
                            ultima_atividade=ultima_atividade
                        )

                if not ultima_atividade:
                    continue

                if agora - ultima_atividade < TEMPO_FECHAMENTO_INATIVIDADE_TICKET:
                    continue

                aviso = (
                    "⏰ Este ticket foi encerrado automaticamente após "
                    "3 horas sem novas mensagens. A transcrição será enviada no privado."
                )
                try:
                    await canal.send(aviso)
                except Exception as erro:
                    print(f"Erro avisando fechamento por inatividade: {erro}")

                await asyncio.sleep(1)
                await fechar_ticket(canal, "Sistema automático (3 horas de inatividade)")

            except Exception as erro:
                print(f"Erro verificando inatividade do ticket {canal.name}: {erro}")


@fechar_tickets_por_inatividade.before_loop
async def antes_fechar_tickets_por_inatividade():
    await bot.wait_until_ready()


@verificar_tickets_sem_resposta.before_loop
async def antes_verificar_tickets():
    await bot.wait_until_ready()


# =========================================================
# MENSAGENS / ANTI-SPAM / COMANDOS
# =========================================================

@bot.listen("on_message")
async def backup_mensagem_listener(message):
    try:
        await salvar_mensagem_individual(message)
    except Exception as erro:
        print(f"Erro salvando mensagem individual: {erro}")


@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    if message.id in mensagens_processadas:
        return

    mensagens_processadas.add(message.id)

    if len(mensagens_processadas) > 5000:
        mensagens_processadas.clear()

    # =====================================================
    # ATUALIZAR ATIVIDADE DO TICKET (PRAZO DE 3 HORAS)
    # =====================================================

    dados_ticket = ler_dados_ticket(message.channel)
    if dados_ticket["owner_id"]:
        await atualizar_dados_ticket(
            message.channel,
            ultima_atividade=int(time.time())
        )

    # =====================================================
    # IDENTIFICAR RESPOSTA DE RESPONSÁVEL NO TICKET
    # =====================================================

    dados_ticket = ler_dados_ticket(message.channel)

    if (
        dados_ticket["owner_id"]
        and eh_responsavel_ticket(message.guild, message.author)
    ):
        alteracoes = {"respondido": True}

        # Se ninguém assumiu manualmente, o primeiro responsável que
        # responder passa a ser o responsável automaticamente.
        if not dados_ticket.get("assumido_por"):
            alteracoes["assumido_por"] = message.author.id
            await atualizar_dados_ticket(message.channel, **alteracoes)
            asyncio.create_task(
                _anunciar_assuncao(
                    message.channel,
                    f"🙋 {message.author.mention} assumiu este atendimento!"
                )
            )
        elif not dados_ticket["respondido"]:
            await atualizar_dados_ticket(message.channel, **alteracoes)

    # =====================================================
    # COMANDO .f PARA FECHAR TICKET — SOMENTE RESPONSÁVEIS
    # =====================================================

    if message.content.strip().lower() == ".f":
        dados = ler_dados_ticket(message.channel)

        if not dados["owner_id"]:
            return

        if not eh_responsavel_ticket(
            message.guild,
            message.author
        ):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        await message.channel.send(
            f"🔒 Ticket fechado por {message.author.mention}. "
            "Estou enviando a transcrição no privado..."
        )

        await asyncio.sleep(2)

        await fechar_ticket(
            message.channel,
            message.author
        )

        return

    # =====================================================
    # CONTROLE DE COMANDOS
    # =====================================================

    if message.content.startswith("!"):
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
        return

    # =====================================================
    # CANAL EXCLUSIVO DO DONO
    # =====================================================

    canal_dono = resolver_canal_configurado(
        message.guild,
        SOLO_DONO_CHANNEL_ID
    )

    if canal_dono and message.channel.id == canal_dono.id:
        if not is_protegido(message.guild, message.author.id):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

        return

    # =====================================================
    # CANAL DE LOGS
    # =====================================================

    canal_logs = resolver_canal_configurado(
        message.guild,
        LOGS_CHANNEL_ID
    )

    if canal_logs and message.channel.id == canal_logs.id:
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        return

    # =====================================================
    # ANTI-SPAM
    # =====================================================

    agora = time.time()

    chave = (
        message.guild.id,
        message.author.id
    )

    msgs[chave] = [
        t for t in msgs[chave]
        if agora - t < 3
    ]

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
                "💬 Anti-Spam — Mute",
                f"**Usuário:** {message.author.mention} "
                f"(`{message.author.id}`)\n"
                f"**Canal:** {message.channel.mention}\n"
                "**Ação:** Timeout por 10 minutos",
                cor=0xFFA500
            )

        except discord.Forbidden:
            print(
                f"Sem permissão para aplicar timeout "
                f"em {message.author}."
            )

        except Exception as erro:
            print(f"Erro no anti-spam: {erro}")

        return


# =========================================================
# EVENTOS ANTI-NUKE
# =========================================================

@bot.event
async def on_member_ban(guild, user):
    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.ban,
        user.id
    )

    if executor and registrou("ban", executor, 2, 3):
        await punir(
            guild,
            executor,
            "Baniu 2 membros em 3 segundos"
        )


@bot.event
async def on_member_remove(member):
    executor = await pegar_executor(
        member.guild,
        discord.AuditLogAction.kick,
        member.id
    )

    if executor and registrou("kick", executor, 2, 3):
        await punir(
            member.guild,
            executor,
            "Expulsou 2 membros em 3 segundos"
        )


# =========================================================
# CRIAÇÃO DE CANAIS
# =========================================================

@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    estado = get_raid(guild.id)

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_create,
        channel.id
    )

    if estado["restaurando"]:
        if executor is None:
            return

        if bot.user and executor == bot.user.id:
            return

        if is_protegido(guild, executor):
            return

        estado["canais_raid_criados"].add(channel.id)
        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)
        return

    if estado["ativo"]:
        if executor is not None:
            if bot.user and executor == bot.user.id:
                return

            if is_protegido(guild, executor):
                return

            canais_pendentes_por_executor[
                (guild.id, executor)
            ].add(channel.id)

        estado["canais_raid_criados"].add(channel.id)
        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)

        if executor is not None:
            await punir(
                guild,
                executor,
                "Criou canal durante raid ativa"
            )

        return

    if executor and not is_protegido(guild, executor):
        canais_pendentes_por_executor[
            (guild.id, executor)
        ].add(channel.id)

        if registrou("canal_criar", executor, 2, 3):
            await punir(
                guild,
                executor,
                "Criou 2 canais em 3 segundos"
            )

        return

    if executor and is_protegido(guild, executor):
        try:
            atualizar_canal_no_backup_temp(guild.id, channel)
        except Exception as erro:
            print(f"Erro atualizando TEMP: {erro}")


# =========================================================
# EXCLUSÃO DE CANAIS
# =========================================================

@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    estado = get_raid(guild.id)

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_delete,
        channel.id
    )

    # Nunca recria canais automaticamente. Apenas registra e pune.
    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        if estado["ativo"] or registrou("canal_del", executor, 2, 3):
            estado["canais_apagados_ids"].add(channel.id)
            await punir(
                guild,
                executor,
                "Deletou canal / possível tentativa de nuke"
            )
            await enviar_log(
                guild,
                "🗑️ Canal excluído — restauração manual necessária",
                f"**Canal:** #{channel.name} (`{channel.id}`)\\n"
                f"**Executor:** <@{executor}> (`{executor}`)\\n"
                "**Ação:** invasor punido; nenhuma restauração automática foi executada.",
                cor=0xE74C3C
            )
        return

    # Alterações legítimas feitas por pessoas protegidas atualizam o backup TEMP.
    if executor and is_protegido(guild, executor):
        try:
            remover_canal_do_backup_temp(guild.id, channel.id)
        except Exception as erro:
            print(f"Erro removendo canal do TEMP: {erro}")


# =========================================================
# ATUALIZAÇÃO DE CANAIS
# =========================================================

@bot.event
async def on_guild_channel_update(antes, depois):
    guild = depois.guild

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_update,
        depois.id
    )

    if executor and not is_protegido(guild, executor):
        if registrou("canal_update", executor, 2, 3):
            await punir(
                guild,
                executor,
                "Alterou 2 canais em 3 segundos"
            )

        if get_raid(guild.id)["ativo"]:
            agendar_recuperacao(guild)

        return

    if executor and is_protegido(guild, executor):
        try:
            atualizar_canal_no_backup_temp(guild.id, depois)
        except Exception as erro:
            print(f"Erro atualizando TEMP de canal: {erro}")


# =========================================================
# CARGOS
# =========================================================

@bot.event
async def on_guild_role_create(role):
    guild = role.guild
    estado = get_raid(guild.id)

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.role_create,
        role.id
    )

    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        if estado["ativo"]:
            estado["ultimo_ataque"] = time.time()
            agendar_recuperacao(guild)

        elif registrou("cargo_criar", executor, 2, 3):
            await punir(
                guild,
                executor,
                "Criou 2 cargos em 3 segundos"
            )

        return

    if executor and is_protegido(guild, executor):
        try:
            dados = carregar_backup_temp(guild.id)

            if not any(x.get("id") == role.id for x in dados["cargos"]):
                dados["cargos"].append(snapshot_cargo(role))
                salvar_backup_temp(guild.id, dados)

        except Exception as erro:
            print(f"Erro atualizando TEMP de cargo: {erro}")


@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.role_delete,
        role.id
    )

    estado = get_raid(guild.id)
    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        if estado["ativo"] or registrou("cargo_del", executor, 2, 3):
            estado["cargos_apagados"].append(role.name)
            await punir(
                guild,
                executor,
                "Deletou cargo / possível tentativa de nuke"
            )
            await enviar_log(
                guild,
                "🎭 Cargo excluído — restauração manual necessária",
                f"**Cargo:** {role.name} (`{role.id}`)\\n"
                f"**Executor:** <@{executor}> (`{executor}`)\\n"
                "**Ação:** invasor punido; nenhuma restauração automática foi executada.",
                cor=0xE74C3C
            )
        return

    if executor and is_protegido(guild, executor):
        try:
            dados = carregar_backup_temp(guild.id)
            dados["cargos"] = [
                x for x in dados["cargos"]
                if x.get("id") != role.id
            ]
            salvar_backup_temp(guild.id, dados)
        except Exception as erro:
            print(f"Erro removendo cargo do TEMP: {erro}")


@bot.event
async def on_guild_role_update(antes, depois):
    mudou_permissoes = (
        antes.permissions.value != depois.permissions.value
    )

    if not mudou_permissoes:
        return

    executor = await pegar_executor(
        depois.guild,
        discord.AuditLogAction.role_update,
        depois.id
    )

    if executor and not is_protegido(depois.guild, executor):
        if (
            depois.permissions.administrator
            and not antes.permissions.administrator
        ):
            motivo = "Tentou dar ADM via cargo"
        else:
            motivo = "Alterou permissões de cargo"

        await enviar_log(
            depois.guild,
            "⚠️ Alteração de permissões de cargo",
            f"**Por:** <@{executor}> (`{executor}`)\n"
            f"**Cargo:** {depois.name}\n"
            f"**Ação:** {motivo}",
            cor=0xFFA500
        )

        await punir(depois.guild, executor, motivo)


# =========================================================
# WEBHOOKS
# =========================================================

@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild

    # Ignora o evento disparado pela criação de webhook feita pelo próprio bot.
    try:
        webhooks_atuais = await channel.webhooks()
        agora = discord.utils.utcnow()
        if any(
            webhook.user and bot.user and webhook.user.id == bot.user.id
            and (agora - webhook.created_at).total_seconds() < 20
            for webhook in webhooks_atuais
        ):
            return
    except Exception:
        pass

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.webhook_create
    )

    if executor and bot.user and executor == bot.user.id:
        return

    if executor and not is_protegido(guild, executor):
        try:
            webhooks = await channel.webhooks()

            for webhook in webhooks:
                if webhook.user and webhook.user.id == executor:
                    await webhook.delete(
                        reason="Anti-Nuke: webhook suspeito"
                    )

        except Exception as erro:
            print(f"Erro removendo webhook: {erro}")

        await punir(
            guild,
            executor,
            "Criou webhook suspeito"
        )


# =========================================================
# EMOJIS E STICKERS
# =========================================================

@bot.event
async def on_guild_emojis_update(guild, antes, depois):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild,
            discord.AuditLogAction.emoji_delete
        )

        if (
            executor
            and not is_protegido(guild, executor)
            and registrou("emoji", executor, 2, 3)
        ):
            await punir(
                guild,
                executor,
                "Deletou emojis em massa"
            )


@bot.event
async def on_guild_stickers_update(guild, antes, depois):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild,
            discord.AuditLogAction.sticker_delete
        )

        if executor and not is_protegido(guild, executor):
            await punir(
                guild,
                executor,
                "Deletou sticker"
            )


# =========================================================
# EXCLUSÃO EM MASSA DE MENSAGENS
# =========================================================

@bot.event
async def on_raw_bulk_message_delete(payload):
    if payload.guild_id is None:
        return

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.message_bulk_delete
    )

    if executor and not is_protegido(guild, executor):
        await punir(
            guild,
            executor,
            "Apagou mensagens em massa"
        )


# =========================================================
# NOME E ÍCONE DO SERVIDOR
# =========================================================

@bot.event
async def on_guild_update(antes, depois):
    mudou_nome = antes.name != depois.name
    mudou_icone = antes.icon != depois.icon

    if not mudou_nome and not mudou_icone:
        return

    executor = await pegar_executor(
        depois,
        discord.AuditLogAction.guild_update
    )

    if not executor or is_protegido(depois, executor):
        return

    alteracoes = []
    if mudou_nome:
        alteracoes.append(f"nome: `{antes.name}` → `{depois.name}`")
    if mudou_icone:
        alteracoes.append("ícone do servidor")

    await enviar_log(
        depois,
        "🏷️ Nome/ícone do servidor alterado",
        f"**Executor:** <@{executor}> (`{executor}`)\\n"
        f"**Alterações:** {', '.join(alteracoes)}\\n"
        "**Ação:** invasor punido. A reversão é manual.",
        cor=0xE74C3C
    )

    await punir(
        depois,
        executor,
        "Tentou mudar nome/ícone do servidor"
    )


# =========================================================
# COMANDO: RECURSOS
# =========================================================

@bot.command(name="recursos")
async def recursos(ctx):
    embed = discord.Embed(
        title="🛡️ CENTRAL DE RECURSOS",
        description=(
            "Um sistema desenvolvido para oferecer mais segurança, "
            "organização e praticidade ao seu servidor Discord."
        ),
        color=0x5865F2
    )

    embed.set_thumbnail(
        url=(
            ctx.guild.icon.url
            if ctx.guild.icon
            else bot.user.display_avatar.url
        )
    )

    embed.add_field(
        name="🛡️ Proteção Anti-Nuke e Anti-Raid",
        value=(
            "> Proteção contra ataques, invasões e ações administrativas suspeitas.\n"
            "> Monitoramento de alterações e ações em massa.\n"
            "> Identificação de responsáveis e recuperação do servidor quando necessário."
        ),
        inline=False
    )

    embed.add_field(
        name="🎫 Sistema de Tickets",
        value=(
            "> Painel próprio para abertura de atendimentos.\n"
            "> Canais privados para conversar com a equipe.\n"
            "> Fechamento de tickets e geração de transcrições.\n"
            "> Alertas automáticos quando um atendimento fica sem resposta."
        ),
        inline=False
    )

    embed.add_field(
        name="📦 Backup e Restauração",
        value=(
            "> Salvamento automático da estrutura do servidor.\n"
            "> Backup de canais e cargos.\n"
            "> Recuperação da estrutura após ações destrutivas ou ataques."
        ),
        inline=False
    )

    embed.add_field(
        name="🚨 Sistema de Logs",
        value=(
            "> Registro de atividades suspeitas.\n"
            "> Identificação de responsáveis por alterações.\n"
            "> Notificações sobre ações importantes realizadas no servidor."
        ),
        inline=False
    )

    embed.add_field(
        name="💬 Proteção Anti-Spam",
        value=(
            "> Identificação de mensagens enviadas em excesso.\n"
            "> Aplicação automática de timeout em usuários que praticam spam."
        ),
        inline=False
    )

    embed.add_field(
        name="🧹 Gerenciamento e Limpeza",
        value=(
            "> Ferramentas para organização dos canais.\n"
            "> Limpeza de mensagens em grande quantidade.\n"
            "> Recriação de canais quando necessário."
        ),
        inline=False
    )

    embed.set_footer(
        text="Mais proteção, controle e organização. Tudo em um só bot.",
        icon_url=bot.user.display_avatar.url
    )

    await ctx.send(embed=embed)

# =========================================================
# COMANDO: ATUALIZAR BACKUP
# =========================================================

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


# =========================================================
# RESTAURAÇÃO MANUAL — SEM AÇÕES AUTOMÁTICAS
# =========================================================

def _mapa_categorias_existentes(guild, backup):
    mapa = {}
    por_nome = {c.name: c for c in guild.categories}
    for item in backup.get("canais", []):
        if "category" not in item.get("type", ""):
            continue
        categoria = guild.get_channel(int(item.get("id", 0)))
        if not isinstance(categoria, discord.CategoryChannel):
            categoria = por_nome.get(item.get("name"))
        if categoria:
            mapa[item.get("id")] = categoria
            mapa[str(item.get("id"))] = categoria
    return mapa


async def restaurar_estrutura_manual(guild):
    backup = carregar_backup(guild.id)
    if not backup.get("canais") and not backup.get("cargos"):
        return {"canais": 0, "cargos": 0, "erros": 1}

    estado = get_raid(guild.id)
    estado["restaurando"] = True
    canais_criados = 0
    cargos_criados = 0
    erros = 0

    try:
        mapa_cargos = {}
        cargos_por_nome = {r.name: r for r in guild.roles if r.name != "@everyone"}

        # Recria somente cargos ausentes; não apaga nem rebaixa cargos atuais.
        for item in backup.get("cargos", []):
            nome = item.get("name")
            if not nome:
                continue
            cargo = guild.get_role(int(item.get("id", 0))) or cargos_por_nome.get(nome)
            if cargo is None:
                try:
                    cargo = await guild.create_role(
                        name=nome,
                        colour=discord.Colour(int(item.get("color", 0))),
                        hoist=bool(item.get("hoist", False)),
                        mentionable=bool(item.get("mentionable", False)),
                        permissions=discord.Permissions(int(item.get("permissions", 0))),
                        reason="Restauração manual de backup"
                    )
                    cargos_criados += 1
                    cargos_por_nome[nome] = cargo
                    await asyncio.sleep(0.35)
                except Exception as erro:
                    erros += 1
                    print(f"Erro recriando cargo {nome}: {erro}")
                    continue
            mapa_cargos[item.get("id")] = cargo
            mapa_cargos[str(item.get("id"))] = cargo

        mapa_categorias = _mapa_categorias_existentes(guild, backup)
        itens = backup.get("canais", [])
        categorias = [x for x in itens if "category" in x.get("type", "")]
        demais = [x for x in itens if "category" not in x.get("type", "")]

        # Categorias primeiro.
        for item in categorias:
            atual = guild.get_channel(int(item.get("id", 0)))
            if isinstance(atual, discord.CategoryChannel):
                mapa_categorias[item.get("id")] = atual
                mapa_categorias[str(item.get("id"))] = atual
                continue
            if any(c.name == item.get("name") for c in guild.categories):
                atual = next(c for c in guild.categories if c.name == item.get("name"))
                registrar_novo_id_canal(guild.id, item.get("id"), atual.id)
                mapa_categorias[item.get("id")] = atual
                mapa_categorias[str(item.get("id"))] = atual
                continue
            try:
                novo = await criar_canal_backup(guild, item, mapa_categorias, mapa_cargos)
                mapa_categorias[item.get("id")] = novo
                mapa_categorias[str(item.get("id"))] = novo
                canais_criados += 1
                await asyncio.sleep(0.4)
            except Exception as erro:
                erros += 1
                print(f"Erro recriando categoria {item.get('name')}: {erro}")

        # Canais que não são categorias.
        for item in demais:
            atual = guild.get_channel(int(item.get("id", 0)))
            if atual is not None:
                continue
            # Evita duplicar um canal que tenha sido recriado com outro ID.
            tipo = item.get("type", "")
            existente = next(
                (c for c in guild.channels
                 if c.name == item.get("name") and str(c.type) == tipo),
                None
            )
            if existente:
                registrar_novo_id_canal(guild.id, item.get("id"), existente.id)
                continue
            try:
                novo = await criar_canal_backup(guild, item, mapa_categorias, mapa_cargos)
                canais_criados += 1
                await asyncio.sleep(0.4)
            except Exception as erro:
                erros += 1
                print(f"Erro recriando canal {item.get('name')}: {erro}")

    finally:
        estado["restaurando"] = False

    return {"canais": canais_criados, "cargos": cargos_criados, "erros": erros}


async def _obter_webhook_restauracao(canal):
    try:
        webhooks = await canal.webhooks()
        for webhook in webhooks:
            if webhook.user and bot.user and webhook.user.id == bot.user.id:
                return webhook
        return await canal.create_webhook(
            name="Backup de mensagens",
            reason="Webhook para restauração manual do histórico"
        )
    except discord.Forbidden:
        return None


def obter_id_backup_canal(guild_id, canal):
    if canal is None:
        return None
    mapa = carregar_mapa_canais(guild_id)
    for id_antigo, id_novo in mapa.items():
        try:
            if int(id_novo) == canal.id:
                return int(id_antigo)
        except (TypeError, ValueError):
            continue
    return canal.id


async def restaurar_mensagens_canal(canal, backup_channel_id=None):
    id_backup = backup_channel_id or obter_id_backup_canal(canal.guild.id, canal)
    mensagens = obter_mensagens_backup(canal.guild.id, id_backup)
    if not mensagens:
        return 0, "Não há mensagens salvas para este canal."

    webhook = await _obter_webhook_restauracao(canal)
    restauradas = 0

    for item in mensagens:
        autor = (
            item.get("author_display_name")
            or item.get("author_name")
            or "Usuário"
        )
        avatar = item.get("author_avatar")
        conteudo = item.get("content", "") or ""

        links_anexos = []
        arquivos_abertos = []
        arquivos_discord = []

        for anexo in item.get("attachments", [])[:10]:
            nome = anexo.get("filename", "anexo")
            caminho = anexo.get("local_path")
            if caminho and os.path.isfile(caminho):
                try:
                    arquivo_local = open(caminho, "rb")
                    arquivos_abertos.append(arquivo_local)
                    arquivos_discord.append(
                        discord.File(arquivo_local, filename=nome)
                    )
                    continue
                except Exception as erro:
                    print(f"Erro abrindo anexo salvo {nome}: {erro}")

            url = anexo.get("url")
            if url:
                links_anexos.append(f"[📎 {nome}]({url})")

        if links_anexos:
            conteudo = (conteudo + "\n" if conteudo else "") + "\n".join(links_anexos)

        embeds = []
        for dado_embed in item.get("embeds", [])[:10]:
            try:
                embeds.append(discord.Embed.from_dict(dado_embed))
            except Exception:
                pass

        if not conteudo.strip() and not embeds:
            conteudo = "[Mensagem sem texto ou conteúdo incorporado]"

        try:
            if webhook:
                await webhook.send(
                    content=conteudo[:2000] if conteudo else None,
                    username=str(autor)[:80],
                    avatar_url=avatar,
                    embeds=embeds if embeds else None,
                    files=arquivos_discord if arquivos_discord else None,
                    allowed_mentions=discord.AllowedMentions.none(),
                    wait=True
                )
            else:
                await canal.send(
                    f"**{discord.utils.escape_markdown(str(autor)[:80])}:** "
                    f"{conteudo[:1700]}",
                    embeds=embeds if embeds else None,
                    files=arquivos_discord if arquivos_discord else None,
                    allowed_mentions=discord.AllowedMentions.none()
                )
            restauradas += 1
            await asyncio.sleep(0.25)
        except discord.HTTPException as erro:
            print(f"Erro restaurando mensagem no canal {canal.id}: {erro}")
        finally:
            for arquivo_local in arquivos_abertos:
                try:
                    arquivo_local.close()
                except Exception:
                    pass

    return restauradas, None


async def restaurar_mensagens_todos_canais(guild):
    # Recria canais/categorias que tenham sido apagados antes de reenviar mensagens.
    await restaurar_estrutura_manual(guild)
    dados = carregar_backup(guild.id)
    total = 0
    canais_sem_historico = 0

    for id_canal, item in dados.get("mensagens", {}).items():
        canal = guild.get_channel(int(id_canal))
        if not isinstance(canal, discord.TextChannel):
            canal = resolver_canal_configurado(guild, int(id_canal))
        if not isinstance(canal, discord.TextChannel):
            nome_salvo = item.get("channel_name") if isinstance(item, dict) else None
            canal = discord.utils.get(guild.text_channels, name=nome_salvo) if nome_salvo else None
        if not isinstance(canal, discord.TextChannel):
            canais_sem_historico += 1
            continue
        qtd, erro = await restaurar_mensagens_canal(
            canal, backup_channel_id=int(id_canal)
        )
        total += qtd
        await asyncio.sleep(0.3)

    return total, canais_sem_historico


class ConfirmarRestauracaoTudoView(discord.ui.View):
    def __init__(self, guild_id, solicitante_id):
        super().__init__(timeout=90)
        self.guild_id = guild_id
        self.solicitante_id = solicitante_id

    async def interaction_check(self, interaction: discord.Interaction):
        if (
            interaction.guild is None
            or interaction.guild.id != self.guild_id
            or interaction.user.id != self.solicitante_id
            or interaction.user.id != interaction.guild.owner_id
        ):
            await interaction.response.send_message(
                "Somente o dono que iniciou esta restauração pode confirmar.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Confirmar restauração",
        emoji="♻️",
        style=discord.ButtonStyle.danger
    )
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        self.stop()
        resultado = await restaurar_estrutura_manual(interaction.guild)
        qtd_msgs, canais_ignorados = await restaurar_mensagens_todos_canais(interaction.guild)
        await interaction.followup.send(
            "✅ **Restauração manual finalizada.**\n"
            f"• Canais recriados: **{resultado['canais']}**\n"
            f"• Cargos recriados: **{resultado['cargos']}**\n"
            f"• Mensagens reenviadas: **{qtd_msgs}**\n"
            f"• Canais do backup indisponíveis: **{canais_ignorados}**\n"
            f"• Erros na estrutura: **{resultado['erros']}**\n\n"
            "Os canais e cargos atuais não foram apagados.",
            ephemeral=True
        )
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Restauração cancelada. Nenhuma alteração foi feita.",
            view=self
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
            mapa_categorias = _mapa_categorias_existentes(ctx.guild, backup)
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


# =========================================================
# COMANDO: LIMPAR
# =========================================================

@bot.command(name="limpar")
async def limpar(ctx, *, argumento: str = ""):
    if ctx.author.id != ctx.guild.owner_id:
        return

    argumento = argumento.strip().lower()

    # -----------------------------------------------------
    # NOVA OPÇÃO: !limpar canal todo
    # -----------------------------------------------------

    if argumento in (
        "canal todo",
        "canal",
        "tudo",
        "canal inteiro"
    ):
        canal_antigo = ctx.channel

        if not isinstance(canal_antigo, discord.TextChannel):
            await ctx.send(
                "❌ Esse comando só funciona em canais de texto.",
                delete_after=5
            )
            return

        try:
            nome_antigo = canal_antigo.name
            posicao_antiga = canal_antigo.position

            # Primeiro cria uma cópia com as configurações,
            # categoria e permissões do canal original.
            novo_canal = await canal_antigo.clone(
                name=nome_antigo,
                reason=(
                    f"Limpeza completa solicitada por {ctx.author}"
                )
            )

            # Mantém a posição do canal na lista.
            await novo_canal.edit(
                position=posicao_antiga,
                reason="Mantendo posição original do canal"
            )

            # Só exclui o canal antigo depois que o novo existe.
            try:
                await canal_antigo.delete(
                    reason=(
                        f"Canal substituído por limpeza solicitada "
                        f"por {ctx.author}"
                    )
                )

            except Exception:
                # Se não conseguir excluir o antigo, tenta apagar
                # o clone para não deixar dois canais iguais.
                try:
                    await novo_canal.delete(
                        reason="Falha ao substituir canal antigo"
                    )
                except Exception:
                    pass

                raise

            await novo_canal.send(
                "🧹 **Canal limpo com sucesso!**\n"
                "O canal foi recriado mantendo suas configurações, "
                "categoria e permissões. Todas as mensagens antigas "
                "foram removidas."
            )

            print(
                f"🧹 Canal #{nome_antigo} recriado por "
                f"{ctx.author} em {ctx.guild.name}"
            )

        except discord.Forbidden:
            try:
                await ctx.author.send(
                    f"❌ Não consegui recriar o canal **#{canal_antigo.name}** "
                    "porque faltam permissões. Verifique se o bot tem "
                    "`Gerenciar Canais`."
                )
            except Exception:
                pass

        except Exception as erro:
            print(f"Erro limpando canal inteiro: {erro}")

            try:
                await ctx.author.send(
                    "❌ Ocorreu um erro ao recriar o canal. "
                    "Verifique as permissões do bot."
                )
            except Exception:
                pass

        return

    # -----------------------------------------------------
    # OPÇÃO ORIGINAL: !limpar 100
    # -----------------------------------------------------

    try:
        quantidade = int(argumento)
    except (ValueError, TypeError):
        await ctx.send(
            "Usa assim:\n"
            "`!limpar 100` — apagar mensagens\n"
            "`!limpar canal todo` — recriar o canal inteiro",
            delete_after=7
        )
        return

    if quantidade <= 0 or quantidade > 1000:
        await ctx.send(
            "Usa assim: `!limpar 100` — número entre 1 e 1000",
            delete_after=5
        )
        return

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
# SISTEMA DE TICKETS — BOTÃO FECHAR
# =========================================================

async def atualizar_mensagem_controle(canal):
    """
    Atualiza a mensagem principal do ticket: mostra o responsável e
    remove o botão "Assumir ticket" enquanto o ticket está assumido.
    """

    try:
        dados = ler_dados_ticket(canal)
        mensagem = None
        mid = dados.get("msg_controle_id")

        if mid:
            try:
                mensagem = await canal.fetch_message(int(mid))
            except discord.NotFound:
                mensagem = None

        if mensagem is None:
            async for m in canal.history(limit=15, oldest_first=True):
                if (
                    bot.user
                    and m.author.id == bot.user.id
                    and m.embeds
                    and (m.embeds[0].title or "").startswith("🎫 Atendimento")
                ):
                    mensagem = m
                    await atualizar_dados_ticket(
                        canal,
                        msg_controle_id=m.id
                    )
                    break

        if mensagem is None:
            return

        assumido = dados.get("assumido_por")
        embed = mensagem.embeds[0].copy() if mensagem.embeds else None

        if embed is not None:
            for i, campo in enumerate(list(embed.fields)):
                if campo.name == "🙋 Responsável":
                    embed.remove_field(i)
                    break

            if assumido:
                embed.add_field(
                    name="🙋 Responsável",
                    value=f"<@{assumido}>",
                    inline=False
                )

        await mensagem.edit(
            embed=embed,
            view=TicketCloseView(assumido=bool(assumido))
        )

    except Exception as erro:
        print(f"Erro atualizando mensagem do ticket: {erro}")


async def _anunciar_assuncao(canal, texto):
    try:
        await canal.send(
            texto,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    except Exception as erro:
        print(f"Erro anunciando responsável: {erro}")

    await atualizar_mensagem_controle(canal)


async def processar_assumir(interaction):
    canal = interaction.channel
    guild = interaction.guild

    if guild is None or not isinstance(canal, discord.TextChannel):
        return

    dados = ler_dados_ticket(canal)

    if not dados["owner_id"]:
        await interaction.response.send_message(
            "Este canal não é um ticket válido.", ephemeral=True
        )
        return

    if not eh_responsavel_ticket(guild, interaction.user):
        await interaction.response.send_message(
            "Apenas a equipe de atendimento pode assumir tickets.",
            ephemeral=True
        )
        return

    anterior = dados.get("assumido_por")

    if anterior == interaction.user.id:
        await interaction.response.send_message(
            "Você já está responsável por este ticket.", ephemeral=True
        )
        return

    # Reconhece a interação na hora, antes de qualquer outra coisa.
    await interaction.response.defer(ephemeral=True)

    await atualizar_dados_ticket(
        canal,
        assumido_por=interaction.user.id,
        respondido=True,
        ultima_atividade=int(time.time())
    )

    if anterior:
        texto = (
            f"🔄 {interaction.user.mention} assumiu este atendimento "
            f"no lugar de <@{anterior}>!"
        )
    else:
        texto = f"🙋 {interaction.user.mention} assumiu este atendimento!"

    await interaction.followup.send(
        "Você assumiu este atendimento.", ephemeral=True
    )

    asyncio.create_task(_anunciar_assuncao(canal, texto))


async def _validar_gestao_ticket(interaction):
    """Confere ticket válido + equipe. Retorna (canal, dados) ou None."""

    canal = interaction.channel
    guild = interaction.guild

    if guild is None or not isinstance(canal, discord.TextChannel):
        await interaction.response.send_message(
            "Canal de ticket inválido.", ephemeral=True
        )
        return None

    if not eh_responsavel_ticket(guild, interaction.user):
        await interaction.response.send_message(
            "Apenas a equipe pode gerenciar participantes.", ephemeral=True
        )
        return None

    dados = ler_dados_ticket(canal)

    if not dados.get("owner_id"):
        await interaction.response.send_message(
            "Este canal não é um ticket válido.", ephemeral=True
        )
        return None

    return canal, dados


class TicketMembroSelect(discord.ui.Select):
    """Lista só com membros que estão dentro do servidor."""

    def __init__(self, membros, modo):
        self.modo = modo

        opcoes = [
            discord.SelectOption(
                label=m.display_name[:100],
                description=f"@{m.name}"[:100],
                value=str(m.id)
            )
            for m in membros[:25]
        ]

        super().__init__(
            placeholder=(
                "Escolha quem adicionar ao ticket..."
                if modo == "adicionar"
                else "Escolha quem remover do ticket..."
            ),
            min_values=1,
            max_values=1,
            options=opcoes
        )

    async def callback(self, interaction: discord.Interaction):
        validado = await _validar_gestao_ticket(interaction)

        if validado is None:
            return

        canal, dados = validado
        guild = interaction.guild
        alvo_id = int(self.values[0])
        membro = guild.get_member(alvo_id)

        if membro is None:
            await interaction.response.send_message(
                "❌ Essa pessoa não está neste servidor.", ephemeral=True
            )
            return

        if membro.id == dados["owner_id"]:
            await interaction.response.send_message(
                "O solicitante principal não pode ser alterado no próprio ticket.",
                ephemeral=True
            )
            return

        try:
            if self.modo == "adicionar":
                await canal.set_permissions(
                    membro,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                    reason=f"Adicionado ao ticket por {interaction.user}"
                )
                texto = f"✅ {membro.mention} agora tem acesso a este ticket."
            else:
                await canal.set_permissions(
                    membro,
                    overwrite=None,
                    reason=f"Removido do ticket por {interaction.user}"
                )
                texto = f"✅ {membro.mention} foi removido deste ticket."

            await interaction.response.send_message(texto, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar as permissões deste canal.",
                ephemeral=True
            )
        except Exception as erro:
            print(f"Erro gerenciando participante do ticket: {erro}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Ocorreu um erro ao atualizar o participante.",
                    ephemeral=True
                )


class TicketMembroSelectView(discord.ui.View):
    def __init__(self, membros, modo):
        super().__init__(timeout=180)
        self.add_item(TicketMembroSelect(membros, modo))


class TicketBuscaMembroModal(discord.ui.Modal, title="➕ Adicionar pessoa"):
    busca = discord.ui.TextInput(
        label="Nome, @usuário ou ID",
        placeholder="Ex.: theus",
        min_length=2,
        max_length=40
    )

    async def on_submit(self, interaction: discord.Interaction):
        validado = await _validar_gestao_ticket(interaction)

        if validado is None:
            return

        canal, dados = validado
        guild = interaction.guild
        termo = str(self.busca.value).strip().lower().lstrip("@")

        resultados = []

        for m in guild.members:
            if m.bot or m.id == dados["owner_id"]:
                continue

            nomes = (
                m.name.lower(),
                m.display_name.lower(),
                (m.global_name or "").lower()
            )

            if (termo.isdigit() and m.id == int(termo)) or any(
                termo in n for n in nomes
            ):
                resultados.append(m)

        resultados.sort(key=lambda m: m.display_name.lower())

        if not resultados:
            await interaction.response.send_message(
                f"❌ Não encontrei ninguém no servidor com **{termo}**. "
                "Só aparecem membros que estão aqui dentro.",
                ephemeral=True
            )
            return

        extra = (
            f"\n(Mostrando 25 de {len(resultados)}. Digite mais letras "
            "do nome para filtrar.)"
            if len(resultados) > 25 else ""
        )

        await interaction.response.send_message(
            f"Membros do servidor encontrados:{extra}",
            view=TicketMembroSelectView(resultados, "adicionar"),
            ephemeral=True
        )


async def enviar_lista_remover(interaction):
    validado = await _validar_gestao_ticket(interaction)

    if validado is None:
        return

    canal, dados = validado

    removiveis = [
        alvo for alvo in canal.overwrites
        if isinstance(alvo, discord.Member)
        and not alvo.bot
        and alvo.id != dados["owner_id"]
        and alvo.id != interaction.guild.owner_id
    ]

    if not removiveis:
        await interaction.response.send_message(
            "Não há pessoas adicionadas manualmente neste ticket.",
            ephemeral=True
        )
        return

    removiveis.sort(key=lambda m: m.display_name.lower())

    await interaction.response.send_message(
        "Escolha quem perderá o acesso ao ticket:",
        view=TicketMembroSelectView(removiveis, "remover"),
        ephemeral=True
    )


class TicketStaffPanelView(discord.ui.View):
    def __init__(self, mostrar_assumir=True):
        super().__init__(timeout=180)

        # Quem já é o responsável não vê o botão de assumir.
        if not mostrar_assumir:
            self.remove_item(self.assumir_no_painel)

    @discord.ui.button(
        label="Assumir ticket",
        emoji="🙋",
        style=discord.ButtonStyle.primary
    )
    async def assumir_no_painel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await processar_assumir(interaction)

    @discord.ui.button(
        label="Adicionar pessoa",
        emoji="➕",
        style=discord.ButtonStyle.success
    )
    async def adicionar_pessoa(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not eh_responsavel_ticket(
            interaction.guild, interaction.user
        ):
            await interaction.response.send_message(
                "Apenas a equipe pode usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(TicketBuscaMembroModal())

    @discord.ui.button(
        label="Remover pessoa",
        emoji="➖",
        style=discord.ButtonStyle.danger
    )
    async def remover_pessoa(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not eh_responsavel_ticket(
            interaction.guild, interaction.user
        ):
            await interaction.response.send_message(
                "Apenas a equipe pode usar este painel.", ephemeral=True
            )
            return
        await enviar_lista_remover(interaction)


class TicketCloseView(discord.ui.View):
    def __init__(self, assumido=False):
        super().__init__(timeout=None)

        # Com o ticket assumido, o botão público some. Outros admins
        # podem assumir por cima pelo "Ver painel".
        if assumido:
            self.remove_item(self.assumir_ticket_botao)

    @discord.ui.button(
        label="Assumir ticket",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_assumir"
    )
    async def assumir_ticket_botao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await processar_assumir(interaction)

    @discord.ui.button(
        label="Ver painel",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_ver_painel"
    )
    async def ver_painel_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        canal = interaction.channel
        guild = interaction.guild
        if guild is None or not isinstance(canal, discord.TextChannel):
            return

        dados = ler_dados_ticket(canal)
        if not dados.get("owner_id"):
            await interaction.response.send_message(
                "Este canal não é um ticket válido.", ephemeral=True
            )
            return

        if not eh_responsavel_ticket(guild, interaction.user):
            await interaction.response.send_message(
                "Apenas a equipe pode abrir o painel de gerenciamento.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "⚙️ **Painel de gerenciamento do ticket**\n"
            "Escolha uma ação abaixo. Este painel é visível somente para você.",
            view=TicketStaffPanelView(
                mostrar_assumir=(
                    dados.get("assumido_por") != interaction.user.id
                )
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="Fechar ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_fechar"
    )
    async def fechar_ticket_botao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        canal = interaction.channel
        guild = interaction.guild

        if guild is None or not isinstance(canal, discord.TextChannel):
            return

        dados = ler_dados_ticket(canal)

        if not dados["owner_id"]:
            await interaction.response.send_message(
                "Este canal não é um ticket válido.",
                ephemeral=True
            )
            return

        # Somente responsáveis/administradores podem fechar.
        # Quem abriu o ticket NÃO consegue fechar.
        if not eh_responsavel_ticket(guild, interaction.user):
            await interaction.response.send_message(
                "Apenas a equipe (administradores) pode fechar este ticket.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 Ticket será fechado. Estou enviando a transcrição no privado.",
            ephemeral=True
        )

        try:
            await canal.send(
                f"🔒 Ticket fechado por {interaction.user.mention}. "
                "Estou enviando a transcrição no privado..."
            )
        except Exception as erro:
            print(f"Erro enviando aviso de fechamento: {erro}")

        await asyncio.sleep(2)

        await fechar_ticket(canal, interaction.user)


# =========================================================
# SISTEMA DE TICKETS — BOTÃO ABRIR
# =========================================================

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir ticket",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="ticket_abrir"
    )
    async def abrir_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        guild = interaction.guild
        membro = interaction.user
        canal_painel = interaction.channel

        if guild is None:
            return

        if not isinstance(canal_painel, discord.TextChannel):
            return

        # Verifica se o usuário já possui ticket aberto.
        for canal in guild.text_channels:
            dados = ler_dados_ticket(canal)

            if dados["owner_id"] == membro.id:
                await interaction.response.send_message(
                    f"Você já possui um ticket aberto: {canal.mention}",
                    ephemeral=True
                )
                return

        categoria = canal_painel.category

        nome = membro.display_name.lower()

        nome = "".join(
            caractere
            if caractere.isalnum() or caractere == "-"
            else "-"
            for caractere in nome
        )

        nome = nome.strip("-")[:80] or "usuario"

        try:
            await interaction.response.defer(ephemeral=True)

            numero = await proximo_numero_ticket(guild.id)
            nome_canal = f"🎫・{nome}-{numero}"[:100]

            agora = int(time.time())

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                ),

                membro: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
            }

            # Dono do servidor.
            dono = guild.get_member(guild.owner_id)

            if dono:
                overwrites[dono] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True
                )

            # Cargos de administradores e responsáveis.
            for cargo in guild.roles:
                if (
                    cargo.permissions.administrator
                    or cargo.permissions.manage_channels
                ):
                    overwrites[cargo] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_channels=True
                    )

            # Administradores configurados por ID.
            for user_id in ADM_CONFIANCA:
                responsavel = guild.get_member(user_id)

                if responsavel:
                    overwrites[responsavel] = (
                        discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                            manage_channels=True
                        )
                    )

            # Bot.
            if guild.me:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True
                )

            topic = (
                f"ticket_owner:{membro.id}"
                f"|ticket_numero:{numero}"
                f"|ticket_aberto:{agora}"
                f"|ticket_alertado:0"
                f"|ticket_respondido:0"
                f"|ticket_assumido_por:0"
                f"|ticket_ultima_atividade:{agora}"
            )

            ticket_canal = await guild.create_text_channel(
                name=nome_canal,
                category=categoria,
                topic=topic,
                overwrites=overwrites,
                reason=f"Ticket aberto por {membro}"
            )

            embed = discord.Embed(
                title=f"🎫 Atendimento #{numero}",
                description=(
                    f"Olá, {membro.mention}!\n\n"
                    "Seu ticket foi criado com sucesso.\n"
                    "Conte abaixo o que você precisa e aguarde o retorno da equipe.\n\n"
                    f"🕒 **Criado:** <t:{agora}:R>"
                ),
                color=0x5865F2
            )

            embed.add_field(
                name="📌 Informações do atendimento",
                value=(
                    f"**Solicitante:** {membro.mention}\n"
                    f"**Protocolo:** `#{numero}`"
                ),
                inline=False
            )
            embed.add_field(
                name="📨 Como prosseguir",
                value="Envie sua mensagem neste canal. Se precisar, você também pode anexar imagens ou arquivos.",
                inline=False
            )

            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.set_footer(
                text=f"{guild.name} • Central de Atendimento"
            )

            msg_controle = await ticket_canal.send(
                content=membro.mention,
                embed=embed,
                view=TicketCloseView()
            )

            await atualizar_dados_ticket(
                ticket_canal,
                msg_controle_id=msg_controle.id
            )

            await interaction.followup.send(
                f"✅ Seu ticket foi criado: {ticket_canal.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "Não tenho permissão para criar o ticket. "
                "Verifique minhas permissões e minha posição na hierarquia.",
                ephemeral=True
            )

        except Exception as erro:
            print(f"Erro criando ticket: {erro}")

            await interaction.followup.send(
                "Ocorreu um erro ao criar seu ticket.",
                ephemeral=True
            )


# =========================================================
# COMANDO: CONFIGURAR PAINEL DE TICKETS
# =========================================================

@bot.group(
    name="ticket",
    invoke_without_command=True
)
async def ticket(ctx):
    await ctx.send(
        "Use: `!ticket painel #canal`",
        delete_after=5
    )


@ticket.command(name="painel")
async def ticket_painel(ctx, canal: discord.TextChannel):
    if ctx.author.id != ctx.guild.owner_id:
        return

    embed = discord.Embed(
        title="🎫 SUPORTE • THEUSSYT COMMUNITY",
        description=(
            "Precisa de ajuda? Fale com a nossa staff.\n\n"
            "✅ **Faça**\n"
            "> Explique seu problema com detalhes\n"
            "> Envie prints ou vídeos se tiver\n"
            "> Aguarde a resposta com paciência\n\n"
            "❌ **Evite**\n"
            "> Abrir ticket sem motivo\n"
            "> Marcar a staff várias vezes\n\n"
            "📋 Ao fechar, você recebe a transcrição no privado\n"
            "🔒 Só você e a equipe veem o ticket"
        ),
        color=0x5865F2
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_footer(
        text=f"{ctx.guild.name} • Sistema de Tickets"
    )

    try:
        await canal.send(
            embed=embed,
            view=TicketPanelView()
        )

        await ctx.send(
            f"✅ Painel de tickets publicado em {canal.mention}.",
            delete_after=5
        )

    except discord.Forbidden:
        await ctx.send(
            "❌ Não tenho permissão para enviar mensagens nesse canal.",
            delete_after=5
        )

    except Exception as erro:
        print(f"Erro publicando painel: {erro}")

        await ctx.send(
            "❌ Não foi possível publicar o painel.",
            delete_after=5
        )


# =========================================================
# COMANDO: !painel (SOMENTE DONO DO SERVIDOR)
# =========================================================

class _CtxPainel:
    """
    Contexto simplificado para o painel reaproveitar exatamente os
    mesmos comandos que já existem (recursos, atualizar, limpar...),
    sem duplicar código. As respostas são privadas (ephemeral).
    """

    def __init__(self, interaction):
        self.interaction = interaction
        self.guild = interaction.guild
        self.author = interaction.user
        self.channel = interaction.channel
        self.invoked_with = "painel"
        self.bot = bot

    async def send(self, content=None, **kwargs):
        kwargs.pop("delete_after", None)
        kwargs["ephemeral"] = True

        if not self.interaction.response.is_done():
            await self.interaction.response.send_message(content, **kwargs)
        else:
            await self.interaction.followup.send(content, **kwargs)


async def _rodar_comando_painel(interaction, comando, *args, **kwargs):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        await comando.callback(_CtxPainel(interaction), *args, **kwargs)

    except Exception as erro:
        print(f"Erro executando função do painel: {erro}")

        try:
            await interaction.followup.send(
                "❌ Ocorreu um erro ao executar essa função.",
                ephemeral=True
            )
        except Exception:
            pass


def _data_arquivo(path):
    try:
        return f"<t:{int(os.path.getmtime(path))}:R>"
    except Exception:
        return "nunca"


def embed_painel_dono(guild):
    embed = discord.Embed(
        title="👑 PAINEL DO DONO",
        description=(
            "Todas as funções do bot em um só lugar.\n"
            "Somente você consegue usar os botões. "
            "As respostas aparecem só para você.\n\n"
            "📋 **Recursos** — lista de recursos do bot\n"
            "🛡️ **Status** — estado da proteção e dos backups\n"
            "🎫 **Tickets abertos** — quem abriu e quem assumiu\n"
            "💾 **Atualizar backup** — salva canais e cargos agora\n"
            "🎫 **Painel de tickets** — publica o painel em um canal\n"
            "🧹 **Limpar mensagens** — apaga uma quantidade neste canal\n"
            "💥 **Limpar canal todo** — recria este canal vazio"
        ),
        color=0x5865F2
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.set_footer(text="Este painel se fecha sozinho em 5 minutos.")
    return embed


def embed_status_protecao(guild):
    estado = get_raid(guild.id)
    backup = carregar_backup(guild.id)

    embed = discord.Embed(
        title="🛡️ Status da proteção",
        color=0xE74C3C if estado["ativo"] else 0x2ECC71,
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(
        name="Anti-Nuke",
        value=(
            "🚨 **RAID EM ANDAMENTO**"
            if estado["ativo"] else "✅ Ativo e sem ameaças"
        ),
        inline=True
    )
    embed.add_field(
        name="Restaurando",
        value="Sim" if estado["restaurando"] else "Não",
        inline=True
    )
    embed.add_field(
        name="Backup BOM",
        value=(
            f"{len(backup['canais'])} canais • "
            f"{len(backup['cargos'])} cargos\n"
            f"Atualizado: {_data_arquivo(backup_bom_path(guild.id))}"
        ),
        inline=False
    )
    embed.add_field(
        name="Anti-Spam",
        value="5 mensagens em 3s = timeout de 10 minutos",
        inline=False
    )
    embed.add_field(
        name="Tickets",
        value=(
            f"Alerta após {TEMPO_ALERTA_TICKET // 60} min sem resposta\n"
            f"Fecha após {TEMPO_FECHAMENTO_INATIVIDADE_TICKET // 3600}h "
            "de inatividade"
        ),
        inline=False
    )

    return embed


def embed_tickets_abertos(guild):
    linhas = []

    for canal in guild.text_channels:
        dados = ler_dados_ticket(canal)

        if not dados["owner_id"]:
            continue

        responsavel = (
            f"<@{dados['assumido_por']}>"
            if dados.get("assumido_por") else "ninguém"
        )

        linhas.append(
            f"{canal.mention} • autor <@{dados['owner_id']}> "
            f"• assumido por {responsavel}"
        )

    embed = discord.Embed(
        title=f"🎫 Tickets abertos ({len(linhas)})",
        description=(
            "\n".join(linhas[:25]) if linhas
            else "Nenhum ticket aberto no momento."
        ),
        color=0x5865F2
    )

    if len(linhas) > 25:
        embed.set_footer(text=f"E mais {len(linhas) - 25} tickets...")

    return embed


class LimparMensagensModal(discord.ui.Modal, title="🧹 Limpar mensagens"):
    quantidade = discord.ui.TextInput(
        label="Quantidade (1 a 1000)",
        placeholder="100",
        max_length=4
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _rodar_comando_painel(
            interaction,
            limpar,
            argumento=str(self.quantidade.value).strip()
        )


class ConfirmarLimparCanalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(
        label="Sim, limpar tudo",
        emoji="💥",
        style=discord.ButtonStyle.danger
    )
    async def confirmar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await _rodar_comando_painel(
            interaction, limpar, argumento="canal todo"
        )
        self.stop()

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary
    )
    async def cancelar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Cancelado.", view=None
        )
        self.stop()


class EscolherCanalPainelTicket(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Escolha o canal do painel de tickets...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        canal = interaction.guild.get_channel(self.values[0].id)

        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                "Canal inválido.", ephemeral=True
            )
            return

        await _rodar_comando_painel(interaction, ticket_painel, canal)


class EscolherCanalRestaurar(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Escolha o canal para restaurar as mensagens...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        canal = interaction.guild.get_channel(self.values[0].id)
        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                "Canal inválido.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        qtd, erro = await restaurar_mensagens_canal(canal)
        await interaction.followup.send(
            erro or f"✅ {qtd} mensagens restauradas em {canal.mention}.",
            ephemeral=True
        )


class RestauracaoMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(EscolherCanalRestaurar())

    async def interaction_check(self, interaction: discord.Interaction):
        if (
            interaction.guild is None
            or interaction.user.id != interaction.guild.owner_id
        ):
            await interaction.response.send_message(
                "Apenas o dono do servidor pode usar esta restauração.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Restaurar tudo",
        emoji="♻️",
        style=discord.ButtonStyle.danger,
        row=1
    )
    async def restaurar_tudo_botao(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        view = ConfirmarRestauracaoTudoView(
            interaction.guild.id, interaction.user.id
        )
        await interaction.response.send_message(
            "⚠️ Confirma restaurar canais, cargos e mensagens do backup?",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(
        label="Mensagens deste canal",
        emoji="💬",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def restaurar_atual(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Abra o painel em um canal de texto para usar esta opção.",
                ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        qtd, erro = await restaurar_mensagens_canal(interaction.channel)
        await interaction.followup.send(
            erro or f"✅ {qtd} mensagens restauradas neste canal.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Mensagens de todos",
        emoji="📚",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def restaurar_todas_mensagens(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        qtd, ignorados = await restaurar_mensagens_todos_canais(interaction.guild)
        await interaction.followup.send(
            f"✅ {qtd} mensagens restauradas. "
            f"Canais sem correspondência: {ignorados}.",
            ephemeral=True
        )


class PainelDonoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction):
        if (
            interaction.guild is None
            or interaction.user.id != interaction.guild.owner_id
        ):
            await interaction.response.send_message(
                "Apenas o dono do servidor pode usar este painel.",
                ephemeral=True
            )
            return False

        return True

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass

    @discord.ui.button(label="Recursos", emoji="📋", row=0,
                       style=discord.ButtonStyle.primary)
    async def b_recursos(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await _rodar_comando_painel(interaction, recursos)

    @discord.ui.button(label="Status", emoji="🛡️", row=0,
                       style=discord.ButtonStyle.primary)
    async def b_status(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_status_protecao(interaction.guild), ephemeral=True
        )

    @discord.ui.button(label="Tickets abertos", emoji="🎫", row=0,
                       style=discord.ButtonStyle.primary)
    async def b_tickets(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_tickets_abertos(interaction.guild), ephemeral=True
        )

    @discord.ui.button(label="Atualizar backup", emoji="💾", row=1,
                       style=discord.ButtonStyle.success)
    async def b_backup(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        await _rodar_comando_painel(interaction, atualizar_backup, arg="")

    @discord.ui.button(label="Restaurar backup", emoji="♻️", row=1,
                       style=discord.ButtonStyle.primary)
    async def b_restaurar(self, interaction: discord.Interaction,
                          button: discord.ui.Button):
        await interaction.response.send_message(
            "♻️ **Restauração manual**\\n"
            "Escolha se deseja restaurar tudo, as mensagens deste canal, "
            "as mensagens de todos os canais ou selecione um canal específico.",
            view=RestauracaoMenuView(),
            ephemeral=True
        )

    @discord.ui.button(label="Painel de tickets", emoji="📨", row=1,
                       style=discord.ButtonStyle.success)
    async def b_painel_ticket(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        view = discord.ui.View(timeout=120)
        view.add_item(EscolherCanalPainelTicket())
        await interaction.response.send_message(
            "Em qual canal publicar o painel de tickets?",
            view=view, ephemeral=True
        )

    @discord.ui.button(label="Limpar mensagens", emoji="🧹", row=2,
                       style=discord.ButtonStyle.secondary)
    async def b_limpar(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        await interaction.response.send_modal(LimparMensagensModal())

    @discord.ui.button(label="Limpar canal todo", emoji="💥", row=2,
                       style=discord.ButtonStyle.danger)
    async def b_limpar_canal(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        await interaction.response.send_message(
            "⚠️ Isso recria **este canal** vazio (mantendo configurações "
            "e permissões). Confirmar?",
            view=ConfirmarLimparCanalView(), ephemeral=True
        )

    @discord.ui.button(label="Fechar painel", emoji="❌", row=3,
                       style=discord.ButtonStyle.secondary)
    async def b_fechar(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()

        try:
            await interaction.message.delete()
        except Exception:
            pass


@bot.command(name="painel")
async def painel(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        return

    view = PainelDonoView()
    view.message = await ctx.send(
        embed=embed_painel_dono(ctx.guild),
        view=view
    )


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "A variável de ambiente TOKEN não foi configurada."
    )

bot.run(TOKEN)
