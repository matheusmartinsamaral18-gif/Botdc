"""Sistema de solicitacao de skins para o mapa CONEXAO (THEUSSYT).
Extensao discord.py: adicione 'skins.sistema' em EXTENSOES no main.py.
"""

import discord
from discord.ext import commands

from config import bot

SITE_IDS = "https://ff-item.netlify.app/"
CATEGORY_NAME = "SOLICITAÇÕES • CONEXÃO"


def is_staff(member: discord.Member) -> bool:
    p = member.guild_permissions
    return (
        member.guild.owner_id == member.id
        or p.administrator
        or p.manage_channels
    )


async def get_or_create_category(guild: discord.Guild) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)

    if category:
        return category

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
    }

    return await guild.create_category(
        CATEGORY_NAME,
        overwrites=overwrites,
        reason="Categoria do sistema de solicitacoes de skins",
    )


class SkinDetailsModal(discord.ui.Modal, title="Solicitação de skins • CONEXÃO"):

    details = discord.ui.TextInput(
        label="Nome e IDs das peças",
        placeholder="Informe categoria, famoso e nomes/IDs das peças.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1900,
    )

    def __init__(self, category_name: str):
        super().__init__()
        self.category_name = category_name

        # Placeholder limitado a menos de 100 caracteres.
        self.details.placeholder = (
            "Informe categoria, famoso e nomes/IDs das peças."
        )

    async def on_submit(self, interaction: discord.Interaction):

        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Não consegui identificar suas permissões no servidor.",
                ephemeral=True,
            )

        guild = interaction.guild

        if guild is None:
            return await interaction.response.send_message(
                "Este formulário só funciona no servidor.",
                ephemeral=True,
            )

        category = await get_or_create_category(guild)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }

        # Permite acesso a membros da equipe.
        for member in guild.members:
            if is_staff(member):
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                )

        base = (
            discord.utils.escape_mentions(
                interaction.user.display_name.lower().replace(" ", "-")[:40]
            )
            or "usuario"
        )

        channel_name = f"skin-{base}"

        existing = discord.utils.get(
            category.channels,
            name=channel_name,
        )

        if existing and interaction.user in existing.members:
            channel = existing

        else:
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"Solicitação de skins de {interaction.user} "
                    "| mapa CONEXÃO | THEUSSYT"
                ),
                reason="Nova solicitação de skins",
            )

        embed = discord.Embed(
            title="📨 NOVA SOLICITAÇÃO DE SKINS",
            color=0x2ECC71,
        )

        embed.add_field(
            name="Solicitante",
            value=f"{interaction.user.mention} (`{interaction.user.id}`)",
            inline=False,
        )

        embed.add_field(
            name="Mapa",
            value="CONEXÃO • Dono: THEUSSYT",
            inline=False,
        )

        embed.add_field(
            name="Categoria",
            value=self.category_name,
            inline=True,
        )

        embed.add_field(
            name="Detalhes / IDs",
            value=discord.utils.escape_mentions(self.details.value),
            inline=False,
        )

        embed.set_footer(text="Status: Pendente de análise")

        await channel.send(
            embed=embed,
            view=StaffActionsView(),
        )

        await interaction.response.send_message(
            f"Sua solicitação foi enviada em {channel.mention}.",
            ephemeral=True,
        )


class CategorySelect(discord.ui.Select):

    def __init__(self):

        options = [
            discord.SelectOption(
                label="Skin de famoso",
                value="Skin de famoso",
                emoji="🌟",
            ),
            discord.SelectOption(
                label="Skin de anime",
                value="Skin de anime",
                emoji="🎭",
            ),
            discord.SelectOption(
                label="Skin normal",
                value="Skin normal",
                emoji="👤",
            ),
            discord.SelectOption(
                label="Skin de arma",
                value="Skin de arma",
                emoji="🎮",
            ),
            discord.SelectOption(
                label="Outra categoria",
                value="Outra categoria",
                emoji="📦",
            ),
        ]

        super().__init__(
            placeholder="Selecione a categoria da solicitação...",
            options=options,
            custom_id="skins:category",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SkinDetailsModal(self.values[0])
        )


class RequestView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(CategorySelect())

        self.add_item(
            discord.ui.Button(
                label="Consultar IDs das skins",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url=SITE_IDS,
            )
        )


class StaffActionsView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def staff_check(self, interaction: discord.Interaction) -> bool:

        if (
            not isinstance(interaction.user, discord.Member)
            or not is_staff(interaction.user)
        ):
            await interaction.response.send_message(
                "Este botão é exclusivo da staff.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="Em análise",
        style=discord.ButtonStyle.secondary,
        emoji="🕐",
        custom_id="skins:analysis",
    )
    async def analysis(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self.staff_check(interaction):
            return

        await interaction.response.send_message(
            "🕐 Solicitação marcada como **em análise**."
        )

    @discord.ui.button(
        label="Aprovar",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="skins:approve",
    )
    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self.staff_check(interaction):
            return

        await interaction.response.send_message(
            "✅ Solicitação **aprovada**."
        )

    @discord.ui.button(
        label="Recusar",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="skins:reject",
    )
    async def reject(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self.staff_check(interaction):
            return

        await interaction.response.send_message(
            "❌ Solicitação **recusada**."
        )

    @discord.ui.button(
        label="Fechar canal",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="skins:close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self.staff_check(interaction):
            return

        await interaction.response.send_message(
            "Canal será excluído em 5 segundos."
        )

        await interaction.channel.delete(
            delay=5,
            reason=f"Solicitação fechada por {interaction.user}",
        )


class SkinPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Solicitar skins para o mapa",
        emoji="🎨",
        style=discord.ButtonStyle.success,
        custom_id="skins:request",
    )
    async def request(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        embed = discord.Embed(
            title="🎨 Solicitação de skins • CONEXÃO",
            description=(
                "Selecione a categoria no menu abaixo. "
                "Depois, preencha os nomes e IDs das peças.\n\n"
                f"🌐 **[Consultar IDs das skins]({SITE_IDS})**\n"
                "Se não souber algum ID, abra o site, "
                "pesquise e volte aqui para preencher.\n\n"
                "Mapa: **CONEXÃO** | Dono: **THEUSSYT**"
            ),
            color=0x2ECC71,
        )

        await interaction.response.send_message(
            embed=embed,
            view=RequestView(),
            ephemeral=True,
        )


@bot.command(name="painelskins")
async def painel_skins(ctx, canal: discord.TextChannel):

    if ctx.guild is None or ctx.author.id != ctx.guild.owner_id:
        return

    embed = discord.Embed(
        title="🎨 PAINEL DE SKINS • CONEXÃO",
        description=(
            "Quer sugerir skins para o mapa **CONEXÃO**, "
            "do **THEUSSYT**?\n\n"
            "Clique no botão abaixo e preencha sua solicitação. "
            "Ela será enviada em um canal privado, visível para você "
            "e para a equipe.\n\n"
            "🌐 Você poderá consultar os IDs no site durante o preenchimento."
        ),
        color=0x2ECC71,
    )

    await canal.send(
        embed=embed,
        view=SkinPanelView(),
    )

    await ctx.send(
        f"✅ Painel publicado em {canal.mention}.",
        delete_after=5,
    )


async def setup(bot):

    bot.add_view(SkinPanelView())
    bot.add_view(StaffActionsView())