import discord
from discord.ext import commands, tasks
import os
import time
import json
import asyncio
import inspect
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

JANELA_RAID = 3
LIMITE_RESTAURACAO = 12
INTERVALO_AUDIT = 0.35
MAX_TENTATIVAS_AUDIT = 4

# =========================================================
# MAPA DE IDS DOS CANAIS
# =========================================================

def arquivo_mapa_canais(guild_id):
    return f"mapa_canais_{guild_id}.json"


def carregar_mapa_canais(guild_id):
    try:
        with open(
            arquivo_mapa_canais(guild_id),
            "r",
            encoding="utf-8"
        ) as f:
            dados = json.load(f)

            if isinstance(dados, dict):
                return dados

    except Exception:
        pass

    return {}


def salvar_mapa_canais(guild_id, mapa):
    try:
        with open(
            arquivo_mapa_canais(guild_id),
            "w",
            encoding="utf-8"
        ) as f:
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
    dados = _carregar_arquivo(
        backup_bom_path(guild_id)
    )

    if not dados["canais"] and not dados["cargos"]:
        antigo = f"backup_{guild_id}.json"

        if os.path.exists(antigo):
            dados_antigos = _carregar_arquivo(antigo)

            if dados_antigos["canais"] or dados_antigos["cargos"]:
                dados = dados_antigos

                _salvar_arquivo(
                    backup_bom_path(guild_id),
                    dados
                )

                _salvar_arquivo(
                    backup_temp_path(guild_id),
                    dados
                )

    return dados


def carregar_backup_temp(guild_id):
    return _carregar_arquivo(
        backup_temp_path(guild_id)
    )


def salvar_backup(guild_id, dados):
    return _salvar_arquivo(
        backup_bom_path(guild_id),
        dados
    )


def salvar_backup_temp(guild_id, dados):
    return _salvar_arquivo(
        backup_temp_path(guild_id),
        dados
    )


def salvar_backup_bom(guild_id, dados):
    return _salvar_arquivo(
        backup_bom_path(guild_id),
        dados
    )


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
        dados["canais"].append(
            snapshot_canal(canal)
        )

    for role in guild.roles:
        if role.name != "@everyone" and not role.managed:
            dados["cargos"].append(
                snapshot_cargo(role)
            )

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
                print(
                    f"⏸️ Sync pulado em {guild.name}: raid recente."
                )
                continue

            foto = tirar_foto_guild(guild)

            salvar_backup_temp(guild.id, foto)
            salvar_backup_bom(guild.id, foto)

            print(
                f"🔄 Backup BOM atualizado: {guild.name}"
            )

        except Exception as erro:
            print(
                f"Erro sync backup {guild.name}: {erro}"
            )


@sync_backup_loop.before_loop
async def antes_sync():
    await bot.wait_until_ready()


# =========================================================
# LOGS
# =========================================================

async def enviar_log_simples(
    guild,
    titulo,
    descricao,
    cor=0xFF0000
):
    try:
        canal = resolver_canal_configurado(
            guild,
            LOGS_CHANNEL_ID
        )

        if canal and hasattr(canal, "send"):
            embed = discord.Embed(
                title=titulo,
                description=descricao,
                color=cor,
                timestamp=discord.utils.utcnow()
            )

            embed.set_footer(
                text=f"Servidor: {guild.name}"
            )

            await canal.send(embed=embed)

    except Exception as erro:
        print(f"Erro log canal: {erro}")

    if (
        "Raid finalizado" not in titulo
        and "Banido" not in titulo
    ):
        destinos = {MEU_ID}
        dono_id = get_dono_id(guild)

        if dono_id:
            destinos.add(dono_id)

        for user_id in destinos:
            try:
                usuario = await bot.fetch_user(user_id)
                await usuario.send(
                    f"{titulo}\n{descricao}"
                )
                await asyncio.sleep(0.5)

            except Exception:
                pass


async def enviar_log(
    guild,
    titulo,
    descricao,
    cor=0xFF0000
):
    await enviar_log_simples(
        guild,
        titulo,
        descricao,
        cor
    )


# =========================================================
# AUDIT LOG
# =========================================================

async def pegar_executor(
    guild,
    action,
    target_id=None,
    janela=12
):
    if guild is None:
        return None

    for tentativa in range(MAX_TENTATIVAS_AUDIT):
        try:
            async for entrada in guild.audit_logs(
                limit=12,
                action=action
            ):
                idade = (
                    discord.utils.utcnow()
                    - entrada.created_at
                ).total_seconds()

                if idade < 0 or idade > janela:
                    continue

                if entrada.user is None:
                    continue

                if (
                    bot.user
                    and entrada.user.id == bot.user.id
                ):
                    continue

                if target_id is not None:
                    alvo = getattr(
                        entrada,
                        "target",
                        None
                    )

                    if (
                        alvo is None
                        or getattr(alvo, "id", None) != target_id
                    ):
                        continue

                return entrada.user.id

        except discord.Forbidden:
            print(
                f"Sem permissão para consultar Audit Log em {guild.name}."
            )
            return None

        except Exception as erro:
            print(
                f"Erro consultando Audit Log: {erro}"
            )

        if tentativa < MAX_TENTATIVAS_AUDIT - 1:
            await asyncio.sleep(
                INTERVALO_AUDIT
            )

    return None


# =========================================================
# AGENDAMENTO DA RESTAURAÇÃO
# =========================================================

def agendar_recuperacao(guild):
    estado = get_raid(guild.id)
    estado["ultimo_ataque"] = time.time()

    tarefa = estado.get("timer")

    if tarefa and not tarefa.done():
        return

    async def esperar_e_restaurar():
        try:
            while estado["ativo"]:
                restante = (
                    LIMITE_RESTAURACAO
                    - (
                        time.time()
                        - estado["ultimo_ataque"]
                    )
                )

                if restante > 0:
                    await asyncio.sleep(
                        min(restante, 2)
                    )
                    continue

                await restaurar_tudo(guild)
                return

        except asyncio.CancelledError:
            raise

        except Exception as erro:
            print(
                f"Erro na tarefa de restauração: {erro}"
            )

        finally:
            if estado.get("timer") is asyncio.current_task():
                estado["timer"] = None

    estado["timer"] = asyncio.create_task(
        esperar_e_restaurar()
    )


def construir_overwrites(guild, lista):
    overwrites = {}

    for ow in lista:
        if ow.get("is_role", False):
            alvo = guild.get_role(ow["id"])
        else:
            alvo = guild.get_member(ow["id"])

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
    mapa_categorias
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
        dados.get("overwrites", [])
    )

    motivo = (
        "Anti-Nuke: restauração do backup BOM"
    )

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
                kwargs["news"] = dados.get(
                    "news",
                    False
                )

        except Exception:
            pass

        novo = await guild.create_text_channel(
            **kwargs
        )

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
        metodo = getattr(
            guild,
            "create_forum",
            None
        )

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
        metodo = getattr(
            guild,
            "create_stage_channel",
            None
        )

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
        raise RuntimeError(
            f"Tipo de canal não suportado: {tipo}"
        )

    estado = get_raid(guild.id)

    estado["canais_criados_pelo_bot"].add(
        novo.id
    )

    registrar_novo_id_canal(
        guild.id,
        dados["id"],
        novo.id
    )

    return novo


# =========================================================
# RESTAURAÇÃO COMPLETA
# =========================================================

async def restaurar_tudo(guild):
    estado = get_raid(guild.id)
    lock = locks_restauracao[guild.id]

    if lock.locked():
        return

    async with lock:
        if not estado["ativo"]:
            return

        restante = (
            LIMITE_RESTAURACAO
            - (
                time.time()
                - estado["ultimo_ataque"]
            )
        )

        if restante > 0:
            agendar_recuperacao(guild)
            return

        estado["restaurando"] = True

        print(
            f"♻️ Começando restauração COMPLETA em {guild.name}..."
        )

        backup = carregar_backup(guild.id)

        canais_apagados = 0
        canais_restaurados = 0
        cargos_restaurados = 0
        erros_permissao = 0

        if not backup["canais"] and not backup["cargos"]:
            print(
                "❌ Backup vazio! Restauração cancelada para evitar perda da estrutura."
            )

            estado["restaurando"] = False
            estado["ativo"] = False
            return

        # O mapa será reconstruído com os novos IDs.
        salvar_mapa_canais(guild.id, {})

        estado["canais_criados_pelo_bot"].clear()

        # =================================================
        # FASE 1 — APAGAR TODOS OS CANAIS
        # =================================================

        print(
            "🗑️ Apagando todos os canais do servidor..."
        )

        canais_existentes = list(guild.channels)

        canais_existentes.sort(
            key=lambda c: isinstance(
                c,
                discord.CategoryChannel
            )
        )

        for canal in canais_existentes:
            try:
                await canal.delete(
                    reason=(
                        "Anti-Nuke: limpeza completa para restauração do backup"
                    )
                )

                canais_apagados += 1

                print(
                    f"🗑️ Apagado: {canal.name}"
                )

                await asyncio.sleep(0.5)

            except discord.NotFound:
                pass

            except discord.Forbidden as erro:
                erros_permissao += 1

                print(
                    f"Sem permissão para apagar {canal.name}: {erro}"
                )

            except discord.HTTPException as erro:
                print(
                    f"Erro apagando {canal.name}: {erro}"
                )

                await asyncio.sleep(2)

        await asyncio.sleep(2)

        # =================================================
        # FASE 2 — RECRIAR CATEGORIAS
        # =================================================

        print(
            "♻️ Recriando categorias do backup..."
        )

        mapa_categorias = {}

        categorias = [
            c for c in backup["canais"]
            if "category" in c.get("type", "")
        ]

        demais = [
            c for c in backup["canais"]
            if "category" not in c.get("type", "")
        ]

        for dados in categorias:
            try:
                novo = await criar_canal_backup(
                    guild,
                    dados,
                    mapa_categorias
                )

                canais_restaurados += 1

                print(
                    f"♻️ Categoria restaurada: {novo.name}"
                )

                await asyncio.sleep(0.7)

            except discord.Forbidden as erro:
                erros_permissao += 1

                print(
                    f"Sem permissão para criar categoria "
                    f"{dados.get('name')}: {erro}"
                )

            except Exception as erro:
                print(
                    f"Erro recriando categoria "
                    f"{dados.get('name')}: {erro}"
                )

        # =================================================
        # FASE 3 — RECRIAR OS DEMAIS CANAIS
        # =================================================

        print(
            "♻️ Recriando canais do backup..."
        )

        for dados in demais:
            try:
                novo = await criar_canal_backup(
                    guild,
                    dados,
                    mapa_categorias
                )

                canais_restaurados += 1

                print(
                    f"♻️ Canal restaurado: {novo.name}"
                )

                await asyncio.sleep(0.7)

            except discord.Forbidden as erro:
                erros_permissao += 1

                print(
                    f"Sem permissão para recriar "
                    f"{dados.get('name')}: {erro}"
                )

            except Exception as erro:
                print(
                    f"Erro recriando canal "
                    f"{dados.get('name')}: {erro}"
                )

        # =================================================
        # FASE 4 — VARREDURA DE CANAIS EXTRAS
        # =================================================

        print(
            "🔎 Verificando canais que sobraram..."
        )

        for rodada in range(5):
            await asyncio.sleep(2)

            ids_do_bot = set(
                estado["canais_criados_pelo_bot"]
            )

            canais_sobrando = [
                canal
                for canal in list(guild.channels)
                if canal.id not in ids_do_bot
            ]

            if not canais_sobrando:
                print(
                    "✅ Nenhum canal extra encontrado."
                )
                break

            print(
                f"⚠️ Encontrados {len(canais_sobrando)} "
                f"canais extras. Removendo..."
            )

            for canal in canais_sobrando:
                try:
                    await canal.delete(
                        reason=(
                            "Anti-Nuke: removendo canal criado durante a restauração"
                        )
                    )

                    canais_apagados += 1

                    print(
                        f"🗑️ Canal extra removido: {canal.name}"
                    )

                    await asyncio.sleep(0.5)

                except discord.NotFound:
                    pass

                except discord.Forbidden as erro:
                    erros_permissao += 1

                    print(
                        f"Sem permissão para remover canal extra: {erro}"
                    )

                except discord.HTTPException as erro:
                    print(
                        f"Erro na varredura: {erro}"
                    )

                    await asyncio.sleep(2)

        # =================================================
        # FASE 5 — RECRIAR CARGOS AUSENTES
        # =================================================

        print(
            "🎭 Verificando cargos..."
        )

        cargos_atuais = {
            role.name for role in guild.roles
        }

        for dados in backup["cargos"]:
            if dados.get("name") in cargos_atuais:
                continue

            try:
                cargo = await guild.create_role(
                    name=dados["name"],
                    colour=discord.Colour(
                        dados["color"]
                    ),
                    hoist=dados["hoist"],
                    mentionable=dados["mentionable"],
                    permissions=discord.Permissions(
                        dados["permissions"]
                    ),
                    reason=(
                        "Anti-Nuke: restauração do backup BOM"
                    )
                )

                cargos_restaurados += 1
                cargos_atuais.add(cargo.name)

                await asyncio.sleep(0.5)

            except discord.Forbidden as erro:
                erros_permissao += 1

                print(
                    f"Sem permissão para recriar cargo "
                    f"{dados['name']}: {erro}"
                )

            except Exception as erro:
                print(
                    f"Erro recriando cargo "
                    f"{dados['name']}: {erro}"
                )

        # =================================================
        # FASE 6 — VERIFICAR SE A RAID CONTINUA
        # =================================================

        if (
            time.time() - estado["ultimo_ataque"]
            < LIMITE_RESTAURACAO
        ):
            estado["restaurando"] = False
            agendar_recuperacao(guild)
            return

        # =================================================
        # FASE 7 — RELATÓRIO FINAL
        # =================================================

        try:
            canal_logs = resolver_canal_configurado(
                guild,
                LOGS_CHANNEL_ID
            )

            if canal_logs:
                embed = discord.Embed(
                    title="🛡️ Raid finalizado",
                    description=(
                        f"**Raider:** {estado['raider_nome']} "
                        f"(`{estado['raider_id']}`)\n"
                        f"**Canais apagados:** {canais_apagados}\n"
                        f"**Canais restaurados:** {canais_restaurados}\n"
                        f"**Cargos restaurados:** {cargos_restaurados}\n"
                        f"**Falhas de permissão:** {erros_permissao}"
                    ),
                    color=0x2ECC71,
                    timestamp=discord.utils.utcnow()
                )

                embed.set_footer(
                    text=f"Servidor: {guild.name}"
                )

                await canal_logs.send(
                    embed=embed
                )

        except Exception as erro:
            print(
                f"Erro enviando relatório: {erro}"
            )

        # =================================================
        # FINALIZAR RAID
        # =================================================

        raid_state[guild.id] = novo_estado_raid()

        raid_state[guild.id]["ultimo_ataque"] = time.time()

        try:
            foto_limpa = tirar_foto_guild(guild)

            salvar_backup_temp(
                guild.id,
                foto_limpa
            )

        except Exception as erro:
            print(
                f"Erro atualizando backup TEMP: {erro}"
            )

        print(
            f"✅ Restauração completa finalizada em {guild.name}"
        )


# =========================================================
# BANIMENTO / ATIVAÇÃO DO RAID
# =========================================================

async def punir(guild, executor_id, motivo):
    if guild is None or executor_id is None:
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

            usuario = (
                membro
                or await bot.fetch_user(executor_id)
            )

            estado["raider_nome"] = str(usuario)

        except Exception:
            estado["raider_nome"] = (
                f"ID {executor_id}"
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
                membro = await guild.fetch_member(
                    executor_id
                )

            except discord.NotFound:
                membro = await bot.fetch_user(
                    executor_id
                )

        await guild.ban(
            membro,
            reason=f"ANTI-NUKE: {motivo}"
        )

        ja_banidos[executor_id] = agora

        print(
            f"🚨 Banido: {membro} - {motivo}"
        )

        await enviar_log(
            guild,
            "🚨 Banido - Anti-Nuke",
            f"**Executor:** <@{executor_id}> "
            f"(`{executor_id}`)\n"
            f"**Motivo:** {motivo}",
            cor=0xE74C3C
        )

        return True

    except discord.Forbidden as erro:
        print(
            f"Sem permissão/hierarquia para banir "
            f"{executor_id}: {erro}"
        )

    except Exception as erro:
        print(
            f"Erro ao punir {executor_id}: {erro}"
        )

    return False


# =========================================================
# INICIALIZAÇÃO
# =========================================================

@bot.event
async def on_ready():
    print(
        f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP DUPLO"
    )

    await bot.change_presence(
        activity=discord.Game(
            name="🛡️ SYSTEM PROTECTING"
        )
    )

    for guild in bot.guilds:
        try:
            if not os.path.exists(
                backup_bom_path(guild.id)
            ):
                foto = tirar_foto_guild(guild)

                salvar_backup_bom(
                    guild.id,
                    foto
                )

                salvar_backup_temp(
                    guild.id,
                    foto
                )

                print(
                    f"📸 Backup inicial criado: {guild.name}"
                )

            elif not os.path.exists(
                backup_temp_path(guild.id)
            ):
                salvar_backup_temp(
                    guild.id,
                    tirar_foto_guild(guild)
                )

                print(
                    f"📂 Backup TEMP criado: {guild.name}"
                )

            else:
                print(
                    f"📂 Backup BOM carregado: {guild.name}"
                )

        except Exception as erro:
            print(
                f"Erro backup inicial {guild.name}: {erro}"
            )

    if not sync_backup_loop.is_running():
        sync_backup_loop.start()


@bot.event
async def on_guild_join(guild):
    try:
        foto = tirar_foto_guild(guild)

        salvar_backup_bom(
            guild.id,
            foto
        )

        salvar_backup_temp(
            guild.id,
            foto
        )

        print(
            f"📸 Novo servidor, backup criado: {guild.name}"
        )

    except Exception as erro:
        print(
            f"Erro criando backup do novo servidor: {erro}"
        )


# =========================================================
# MENSAGENS / ANTI-SPAM / COMANDOS
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

    canal_dono = resolver_canal_configurado(
        message.guild,
        SOLO_DONO_CHANNEL_ID
    )

    if (
        canal_dono
        and message.channel.id == canal_dono.id
    ):
        if not is_protegido(
            message.guild,
            message.author.id
        ):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

            return

        await bot.process_commands(message)
        return

    canal_logs = resolver_canal_configurado(
        message.guild,
        LOGS_CHANNEL_ID
    )

    if (
        canal_logs
        and message.channel.id == canal_logs.id
    ):
        if (
            message.content.startswith("!")
            and is_protegido(
                message.guild,
                message.author.id
            )
        ):
            await bot.process_commands(message)

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        return

    if is_protegido(
        message.guild,
        message.author.id
    ):
        await bot.process_commands(message)
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

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
                reason=(
                    "Anti-Spam: 5 mensagens em 3 segundos"
                )
            )

            await enviar_log(
                message.guild,
                "💬 Anti-Spam - Mute",
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
            print(
                f"Erro no anti-spam: {erro}"
            )

        return

    await bot.process_commands(message)


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

    if executor and registrou(
        "ban",
        executor,
        2,
        3
    ):
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

    if executor and registrou(
        "kick",
        executor,
        2,
        3
    ):
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

        estado["canais_raid_criados"].add(
            channel.id
        )

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

        estado["canais_raid_criados"].add(
            channel.id
        )

        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)

        if executor is not None:
            await punir(
                guild,
                executor,
                "Criou canal durante raid ativa"
            )

        return

    if executor and not is_protegido(
        guild,
        executor
    ):
        canais_pendentes_por_executor[
            (guild.id, executor)
        ].add(channel.id)

        if registrou(
            "canal_criar",
            executor,
            2,
            3
        ):
            await punir(
                guild,
                executor,
                "Criou 2 canais em 3 segundos"
            )

        return

    if executor and is_protegido(
        guild,
        executor
    ):
        try:
            atualizar_canal_no_backup_temp(
                guild.id,
                channel
            )

        except Exception as erro:
            print(
                f"Erro atualizando TEMP: {erro}"
            )


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

    if estado["restaurando"]:
        if executor is None:
            return

        if bot.user and executor == bot.user.id:
            return

    if estado["ativo"]:
        estado["canais_apagados_ids"].add(
            channel.id
        )

        if executor is not None:
            if bot.user and executor == bot.user.id:
                return

            if not is_protegido(
                guild,
                executor
            ):
                if executor == estado["raider_id"]:
                    if registrou(
                        "canal_del",
                        executor,
                        2,
                        3
                    ):
                        await punir(
                            guild,
                            executor,
                            "Deletou 2 canais em 3 segundos"
                        )

        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)

        return

    if executor and not is_protegido(
        guild,
        executor
    ):
        if registrou(
            "canal_del",
            executor,
            2,
            3
        ):
            await punir(
                guild,
                executor,
                "Deletou 2 canais em 3 segundos"
            )

        if get_raid(guild.id)["ativo"]:
            estado = get_raid(guild.id)

            estado["canais_apagados_ids"].add(
                channel.id
            )

            agendar_recuperacao(guild)
            return

        try:
            categoria = channel.category
            overwrites = channel.overwrites

            if isinstance(
                channel,
                discord.TextChannel
            ):
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

            elif isinstance(
                channel,
                discord.VoiceChannel
            ):
                novo = await guild.create_voice_channel(
                    name=channel.name,
                    category=categoria,
                    position=channel.position,
                    bitrate=channel.bitrate,
                    user_limit=channel.user_limit,
                    overwrites=overwrites,
                    reason="BACKUP Anti-Nuke"
                )

            elif isinstance(
                channel,
                discord.CategoryChannel
            ):
                novo = await guild.create_category(
                    name=channel.name,
                    position=channel.position,
                    overwrites=overwrites,
                    reason="BACKUP Anti-Nuke"
                )

            else:
                novo = None

            if novo:
                print(
                    f"♻️ BACKUP: Canal #{channel.name} recriado!"
                )

                await enviar_log(
                    guild,
                    "♻️ Backup - Canal Recriado",
                    f"**Canal:** #{channel.name}\n"
                    f"**Deletado por:** <@{executor}> "
                    f"(`{executor}`)\n"
                    "**Ação:** Canal recriado automaticamente",
                    cor=0x2ECC71
                )

        except Exception as erro:
            print(
                f"Erro backup canal: {erro}"
            )

    else:
        try:
            remover_canal_do_backup_temp(
                guild.id,
                channel.id
            )

        except Exception as erro:
            print(
                f"Erro removendo canal do TEMP: {erro}"
            )


# =========================================================
# ATUALIZAÇÃO DE CANAIS
# =========================================================

@bot.event
async def on_guild_channel_update(
    antes,
    depois
):
    guild = depois.guild

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.channel_update,
        depois.id
    )

    if executor and not is_protegido(
        guild,
        executor
    ):
        if registrou(
            "canal_update",
            executor,
            2,
            3
        ):
            await punir(
                guild,
                executor,
                "Alterou 2 canais em 3 segundos"
            )

        if get_raid(guild.id)["ativo"]:
            agendar_recuperacao(guild)

        return

    if executor and is_protegido(
        guild,
        executor
    ):
        try:
            atualizar_canal_no_backup_temp(
                guild.id,
                depois
            )

        except Exception as erro:
            print(
                f"Erro atualizando TEMP de canal: {erro}"
            )


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

    if executor and not is_protegido(
        guild,
        executor
    ):
        if estado["ativo"]:
            estado["ultimo_ataque"] = time.time()
            agendar_recuperacao(guild)

        elif registrou(
            "cargo_criar",
            executor,
            2,
            3
        ):
            await punir(
                guild,
                executor,
                "Criou 2 cargos em 3 segundos"
            )

        return

    if executor and is_protegido(
        guild,
        executor
    ):
        try:
            dados = carregar_backup_temp(
                guild.id
            )

            if not any(
                x.get("id") == role.id
                for x in dados["cargos"]
            ):
                dados["cargos"].append(
                    snapshot_cargo(role)
                )

                salvar_backup_temp(
                    guild.id,
                    dados
                )

        except Exception as erro:
            print(
                f"Erro atualizando TEMP de cargo: {erro}"
            )


@bot.event
async def on_guild_role_delete(role):
    guild = role.guild

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.role_delete,
        role.id
    )

    estado = get_raid(guild.id)

    if estado["ativo"]:
        estado["cargos_apagados"].append(
            role.name
        )

        estado["ultimo_ataque"] = time.time()
        agendar_recuperacao(guild)

        return

    if executor and not is_protegido(
        guild,
        executor
    ):
        if registrou(
            "cargo_del",
            executor,
            2,
            3
        ):
            await punir(
                guild,
                executor,
                "Deletou 2 cargos em 3 segundos"
            )

        if get_raid(guild.id)["ativo"]:
            agendar_recuperacao(guild)
            return

        try:
            await guild.create_role(
                name=role.name,
                colour=role.colour,
                hoist=role.hoist,
                mentionable=role.mentionable,
                permissions=role.permissions,
                reason="BACKUP Anti-Nuke"
            )

            print(
                f"♻️ BACKUP: Cargo {role.name} recriado!"
            )

        except Exception as erro:
            print(
                f"Erro backup cargo: {erro}"
            )

    else:
        try:
            dados = carregar_backup_temp(
                guild.id
            )

            dados["cargos"] = [
                x for x in dados["cargos"]
                if x.get("id") != role.id
            ]

            salvar_backup_temp(
                guild.id,
                dados
            )

        except Exception as erro:
            print(
                f"Erro removendo cargo do TEMP: {erro}"
            )


@bot.event
async def on_guild_role_update(
    antes,
    depois
):
    mudou_permissoes = (
        antes.permissions.value
        != depois.permissions.value
    )

    if not mudou_permissoes:
        return

    executor = await pegar_executor(
        depois.guild,
        discord.AuditLogAction.role_update,
        depois.id
    )

    if executor and not is_protegido(
        depois.guild,
        executor
    ):
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

        await punir(
            depois.guild,
            executor,
            motivo
        )


# =========================================================
# WEBHOOKS
# =========================================================

@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.webhook_create
    )

    if executor and not is_protegido(
        guild,
        executor
    ):
        try:
            webhooks = await channel.webhooks()

            for webhook in webhooks:
                if (
                    webhook.user
                    and webhook.user.id == executor
                ):
                    await webhook.delete(
                        reason="Anti-Nuke: webhook suspeito"
                    )

        except Exception as erro:
            print(
                f"Erro removendo webhook: {erro}"
            )

        await punir(
            guild,
            executor,
            "Criou webhook suspeito"
        )


# =========================================================
# EMOJIS E STICKERS
# =========================================================

@bot.event
async def on_guild_emojis_update(
    guild,
    antes,
    depois
):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild,
            discord.AuditLogAction.emoji_delete
        )

        if (
            executor
            and not is_protegido(guild, executor)
            and registrou(
                "emoji",
                executor,
                2,
                3
            )
        ):
            await punir(
                guild,
                executor,
                "Deletou emojis em massa"
            )


@bot.event
async def on_guild_stickers_update(
    guild,
    antes,
    depois
):
    if len(depois) < len(antes):
        executor = await pegar_executor(
            guild,
            discord.AuditLogAction.sticker_delete
        )

        if (
            executor
            and not is_protegido(guild, executor)
        ):
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

    guild = bot.get_guild(
        payload.guild_id
    )

    if guild is None:
        return

    executor = await pegar_executor(
        guild,
        discord.AuditLogAction.message_bulk_delete
    )

    if (
        executor
        and not is_protegido(guild, executor)
    ):
        await punir(
            guild,
            executor,
            "Apagou mensagens em massa"
        )


# =========================================================
# NOME E ÍCONE DO SERVIDOR
# =========================================================

@bot.event
async def on_guild_update(
    antes,
    depois
):
    mudou_nome = antes.name != depois.name
    mudou_icone = antes.icon != depois.icon

    if not mudou_nome and not mudou_icone:
        return

    executor = await pegar_executor(
        depois,
        discord.AuditLogAction.guild_update
    )

    if (
        not executor
        or is_protegido(depois, executor)
    ):
        return

    try:
        icone_bytes = (
            await antes.icon.read()
            if mudou_icone and antes.icon
            else None
        )

        kwargs = {
            "name": antes.name
        }

        if mudou_icone:
            kwargs["icon"] = icone_bytes

        await depois.edit(
            reason="Anti-Nuke: restaurando nome/ícone",
            **kwargs
        )

    except Exception as erro:
        print(
            f"Erro restaurando nome/ícone: {erro}"
        )

    await enviar_log(
        depois,
        "🏷️ Nome/Ícone Alterado",
        f"**Por:** <@{executor}> (`{executor}`)\n"
        "**Ação:** tentativa de alteração revertida",
        cor=0xFFA500
    )

    await punir(
        depois,
        executor,
        "Tentou mudar nome/ícone do servidor"
    )


# =========================================================
# COMANDO: PROTEÇÕES
# =========================================================

@bot.command()
async def protecoes(ctx):
    embed = discord.Embed(
        title="🛡️ ANTI-NUKE | Proteções Ativas",
        description=(
            "O servidor está protegido. Ações suspeitas são "
            "registradas e a estrutura salva no backup BOM "
            "pode ser restaurada."
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
        name="⚔️ Anti-Nuke",
        value=(
            "> 🚫 Mass Ban — 2 bans em 3s\n"
            "> 🚫 Mass Kick — 2 kicks em 3s\n"
            "> 🚫 Alteração de permissões / tentativa de dar ADM\n"
            "> 🚫 Criação de webhook suspeito"
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
            "> 💬 Anti-Spam — 5 mensagens em 3s = timeout 10min\n"
            "> 🧹 Detecção de exclusão em massa\n"
            "> ✏️ Detecção de alterações em canais"
        ),
        inline=False
    )

    embed.add_field(
        name="🎨 Anti-Vandalismo",
        value=(
            "> 😀 Exclusão de emojis\n"
            "> 🌟 Exclusão de stickers\n"
            "> ➕ Criação/exclusão em massa de canais e cargos"
        ),
        inline=False
    )

    embed.add_field(
        name="📌 Comandos",
        value="`!protecoes` — Ver este painel",
        inline=False
    )

    embed.set_footer(
        text=(
            f"Servidor: {ctx.guild.name} "
            f"• Protegido por {bot.user.name}"
        ),
        icon_url=bot.user.display_avatar.url
    )

    await ctx.send(embed=embed)


# =========================================================
# COMANDO: ATUALIZAR BACKUP
# =========================================================

@bot.command(
    name="atualizar",
    aliases=[
        "atualizarbackup",
        "backup",
        "salvar"
    ]
)
async def atualizar_backup(
    ctx,
    *,
    arg: str = ""
):
    if not is_protegido(
        ctx.guild,
        ctx.author.id
    ):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        return

    if ctx.invoked_with in (
        "backup",
        "salvar"
    ):
        arg = "backup"

    if arg.strip().lower() not in (
        "backup",
        ""
    ):
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
        foto = tirar_foto_guild(
            ctx.guild
        )

        salvar_backup_bom(
            ctx.guild.id,
            foto
        )

        salvar_backup_temp(
            ctx.guild.id,
            foto
        )

        await ctx.send(
            f"✅ Backup BOM atualizado! "
            f"**{len(foto['canais'])} canais** "
            f"e **{len(foto['cargos'])} cargos** salvos.",
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
# COMANDO: LIMPAR
# =========================================================

@bot.command(name="limpar")
async def limpar(
    ctx,
    quantidade: int = 0
):
    if not is_protegido(
        ctx.guild,
        ctx.author.id
    ):
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
        lote = min(
            restante,
            100
        )

        try:
            deletadas = await ctx.channel.purge(
                limit=lote
            )

            apagadas += len(deletadas)
            restante -= lote

            if len(deletadas) < lote:
                break

            await asyncio.sleep(0.5)

        except Exception as erro:
            print(
                f"Erro limpar: {erro}"
            )
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
    raise RuntimeError(
        "A variável de ambiente TOKEN não foi configurada."
    )

bot.run(TOKEN)