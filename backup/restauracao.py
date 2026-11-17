"""Funções de restauração manual (canais, cargos e mensagens)."""
import os
import asyncio
import inspect

import discord

from config import bot
from core.raid_estado import get_raid
from backup.armazenamento import carregar_backup
from backup.mapa_canais import (
    registrar_novo_id_canal,
    resolver_canal_configurado,
    obter_id_backup_canal,
)
from backup.mensagens import obter_mensagens_backup


# ---------- permissões dos canais no backup ----------

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


# ---------- criar canal pelo backup ----------

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


# ---------- restauração da estrutura ----------

def mapa_categorias_existentes(guild, backup):
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

        mapa_categorias = mapa_categorias_existentes(guild, backup)
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
                await criar_canal_backup(guild, item, mapa_categorias, mapa_cargos)
                canais_criados += 1
                await asyncio.sleep(0.4)
            except Exception as erro:
                erros += 1
                print(f"Erro recriando canal {item.get('name')}: {erro}")

    finally:
        estado["restaurando"] = False

    return {"canais": canais_criados, "cargos": cargos_criados, "erros": erros}


# ---------- restauração das mensagens ----------

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


# ---------- botão de confirmação ----------

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
