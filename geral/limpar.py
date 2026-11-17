"""Comando !limpar (apagar mensagens ou recriar o canal)."""
import asyncio

import discord

from config import bot


@bot.command(name="limpar")
async def limpar(ctx, *, argumento: str = ""):
    if ctx.author.id != ctx.guild.owner_id:
        return

    argumento = argumento.strip().lower()

    # -----------------------------------------------------
    # !limpar canal todo
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

            novo_canal = await canal_antigo.clone(
                name=nome_antigo,
                reason=(
                    f"Limpeza completa solicitada por {ctx.author}"
                )
            )

            await novo_canal.edit(
                position=posicao_antiga,
                reason="Mantendo posição original do canal"
            )

            try:
                await canal_antigo.delete(
                    reason=(
                        f"Canal substituído por limpeza solicitada "
                        f"por {ctx.author}"
                    )
                )

            except Exception:
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
    # !limpar 100
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


async def setup(bot):
    pass
