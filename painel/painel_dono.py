"""Comando !painel — painel com botões, somente para o dono do servidor."""
import os

import discord

from config import (
    bot,
    TEMPO_ALERTA_TICKET,
    TEMPO_FECHAMENTO_INATIVIDADE_TICKET,
)
from core.raid_estado import get_raid
from backup.armazenamento import backup_bom_path, carregar_backup
from backup.comandos import atualizar_backup
from backup.restauracao import (
    restaurar_mensagens_canal,
    restaurar_mensagens_todos_canais,
    ConfirmarRestauracaoTudoView,
)
from geral.recursos import recursos
from geral.limpar import limpar
from tickets.dados import ler_dados_ticket
from tickets.comandos import ticket_painel


class _CtxPainel:
    """
    Contexto simplificado para o painel reaproveitar os mesmos comandos
    que já existem (recursos, atualizar, limpar...). Respostas privadas.
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
            "♻️ **Restauração manual**\n"
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


async def setup(bot):
    pass
