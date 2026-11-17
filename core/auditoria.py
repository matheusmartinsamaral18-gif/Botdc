"""Descobre quem executou uma ação lendo o Audit Log."""
import asyncio

import discord

from config import bot, INTERVALO_AUDIT, MAX_TENTATIVAS_AUDIT


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
