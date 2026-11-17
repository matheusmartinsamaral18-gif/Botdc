"""Ativação do modo raid e banimento do invasor."""
import time
import asyncio

import discord

from config import bot, LIMITE_RESTAURACAO
from core.permissoes import is_protegido
from core.raid_estado import get_raid, ja_banidos, canais_pendentes_por_executor
from core.logs import enviar_log


def agendar_recuperacao(guild):
    """
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
