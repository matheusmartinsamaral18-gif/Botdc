"""Leitura/gravação dos arquivos de backup (canais e cargos)."""
import os
import json

import discord


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
