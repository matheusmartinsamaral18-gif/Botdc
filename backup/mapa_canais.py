"""Mapa 'ID antigo do canal -> ID novo' (usado depois de restaurar)."""
import json


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
