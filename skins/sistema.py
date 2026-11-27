
"""Sistema de solicitacao de skins para o mapa CONEXAO (THEUSSYT).
Solicitacoes em threads privadas dentro do canal do painel.
"""

import discord
from discord.ext import commands

from config import bot

SITE_IDS = "https://ff-item.netlify.app/"


def is_staff(member: discord.Member) -> bool:
    p = member.guild_permissions
    return (
        member.guild.owner_id == member.id
        or p.administrator
        or p.manage_channels
        or p.manage_threads
    )


class SkinDetailsModal(discord.ui.Modal, title="Solicitação de skins • CONEXÃO"):

    details = discord.ui.TextInput(
        label="Nome e IDs das peças",
        placeholder="Informe o famoso e os nomes/IDs de cada peça.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1900,
    )

    def __init__(self, category_name: str, parent_channel):
        super().__init__()
        self.category_name = category_name
        self.parent_channel = parent_channel

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild
        user = interaction.user

        if guild is None or not isinstance(user, discord.Member):
            return await interaction.response.send_message(
                "Não foi possível identificar o servidor ou usuário.",
                ephemeral=True,
            )

        parent = self.parent_channel

        if not isinstance(parent, discord.TextChannel):
            return await interaction.response.send_message(
                "O canal do painel não é compatível com solicitações.",
                ephemeral=True,
            )

        try:
            # Cria uma THREAD PRIVADA dentro do canal do painel.
            thread = await parent.create_thread(
                name=f"skin-{user.display_name[:70]}",
                type=discord.ChannelType.private_thread,
                invitable=False,
                reason="Nova solicitação de skins",
            )

            # Adiciona o solicitante à thread.
            await thread.add_user(user)

            embed = discord.Embed(
                title="📨 NOVA SOLICITAÇÃO DE SKINS",
                color=0x2ECC71,
                description=(
                    f"**Solicitante:** {user.mention}\n"
                    f"**ID:** `{user.id}`\n"
                    f"**Mapa:** CONEXÃO • THEUSSYT\n"
                    f"**Categoria:** {self.category_name}\n\n"
                    f"**Detalhes / IDs das peças:**\n"
                    f"{discord.utils.escape_mentions(self.details.value)}"
                ),
            )

            embed.set_footer(text="Status: Pendente de análise")

            await thread.send(
                embed=embed,
                view=StaffActionsView(),
            )

            await interaction.response.send_message(
                f"✅ Solicitação criada: {thread.mention}",
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissões para criar ou acessar "
                "threads privadas neste canal.",
                ephemeral=True,
            )

        except Exception as erro:
            print(f"Erro criando solicitação de skins: {erro}")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Ocorreu um erro ao criar sua solicitação.",
                    ephemeral=True,
                )


class CategorySelect(discord.ui.Select):

    def __init__(self, parent_channel):

        self.parent_channel = parent_channel

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
            SkinDetailsModal(
                self.values[0],
                self.parent_channel,
            )
        )


class RequestView(discord.ui.View):

    def __init__(self, parent_channel):
        super().__init__(timeout=180)

        self.add_item(CategorySelect(parent_channel))

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
    async def analysis(self, interaction, button):

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
    async def approve(self, interaction, button):

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
    async def reject(self, interaction, button):

        if not await self.staff_check(interaction):
            return

        await interaction.response.send_message(
            "❌ Solicitação **recusada**."
        )

    @discord.ui.button(
        label="Fechar solicitação",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="skins:close",
    )
    async def close(self, interaction, button):

        if not await self.staff_check(interaction):
            return

        thread = interaction.channel

        if not isinstance(thread, discord.Thread):
            return await interaction.response.send_message(
                "Este botão só funciona dentro da thread da solicitação.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            "🔒 Solicitação encerrada. A thread será arquivada."
        )

        await thread.edit(
            archived=True,
            locked=True,
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
    async def request(self, interaction, button):

        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Este painel precisa estar em um canal de texto.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="🎨 Solicitação de skins • CONEXÃO",
            description=(
                "Selecione a categoria no menu abaixo.\n"
                "Depois, preencha o nome e os IDs das peças.\n\n"
                f"🌐 **[Consultar IDs das skins]({SITE_IDS})**\n\n"
                "A solicitação será criada em uma thread privada "
                "dentro deste canal.\n\n"
                "Mapa: **CONEXÃO** | Dono: **THEUSSYT**"
            ),
            color=0x2ECC71,
        )

        await interaction.response.send_message(
            embed=embed,
            view=RequestView(interaction.channel),
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
            "Clique no botão abaixo e preencha sua solicitação.\n"
            "Ela será criada em uma **thread privada** "
            "dentro deste canal.\n\n"
            "🌐 Você poderá consultar os IDs das peças durante "
            "o preenchimento."
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
