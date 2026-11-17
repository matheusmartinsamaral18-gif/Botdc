"""Quem é protegido (dono, você, bot, ADMs de confiança)."""
from config import bot, ADM_CONFIANCA, MEU_ID


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
