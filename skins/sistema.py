
"""Sistema de solicitacao de skins CONEXAO (THEUSSYT).
Todas as solicitacoes sao enviadas para um canal privado fixo.
"""

import discord
from discord.ext import commands

from config import bot

SITE_IDS = "https://ff-item.netlify.app/"
REQUEST_CHANNEL_NAME = "solicitacoes-skins"


def is_staff(member: discord.Member) -> bool:
    p = member.guild_permissions
    return (
        member.guild.owner_id == member.id
        or p.administrator
        or p.manage_channels
        or p.manage_threads
    )


async def get_request_channel(guild, panel_channel):
    channel = discord.utils.get(
        guild.text_channels,
        name=REQUEST_CHANNEL_NAME,
    )

    if channel:
        return channel

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
    }

    # Permite acesso à equipe identificada pelas permissões.
    for member in guild.members:
        if is_staff(member):
            overwrites[member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

    bot_member = guild.me

    if bot_member:
        overwrites[bot_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        )

    # Cria o canal na categoria do painel, se houver.
    return await guild.create_text_channel(
        REQUEST_CHANNEL_NAME,
        category=panel_channel.category,
        overwrites=overwrites,
        topic="Canal privado para receber todas as solicitacoes de skins.",
        reason="Criacao do canal fixo de solicitacoes de skins",
    )


class SkinSecondModal(discord.ui.Modal, title="IDs das skins • Etapa 2"):

    pants = discord.ui.TextInput(
        label="ID da calça / short",
        placeholder="Digite o ID da calça ou short",
        required=True,
        max_length=100,
    )

    shoes = discord.ui.TextInput(
        label="ID do tênis",
        placeholder="Digite o ID do tênis",
        required=True,
        max_length=100,
    )

    weapon = discord.ui.TextInput(
        label="ID da arma (opcional)",
        placeholder="Digite o ID da arma, se desejar",
        required=False,
        max_length=100,
    )

    def __init__(self, category_name, panel_channel, first_values):
        super().__init__()
        self.category_name = category_name
        self.panel_channel = panel_channel
        self.first_values = first_values

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild

        if guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Não foi possível identificar o servidor.",
                ephemeral=True,
            )

        if not isinstance(self.panel_channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Canal do painel inválido.",
                ephemeral=True,
            )

        try:
            destination = await get_request_channel(
                guild,
                self.panel_channel,
            )

            v = self.first_values

            embed = discord.Embed(
                title="📨 NOVA SOLICITAÇÃO DE SKINS",
                color=0x2ECC71,
            )

            embed.add_field(
                name="Mapa",
                value="CONEXÃO • THEUSSYT",
                inline=False,
            )

            embed.add_field(
                name="Categoria",
                value=self.category_name,
                inline=False,
            )

            embed.add_field(
                name="Nome do famoso / personagem",
                value=discord.utils.escape_mentions(v["name"]),
                inline=False,
            )

            embed.add_field(
                name="Cabeça",
                value=discord.utils.escape_mentions(v["head"]),
                inline=True,
            )

            embed.add_field(
                name="Rosto",
                value=discord.utils.escape_mentions(v["face"]),
                inline=True,
            )

            embed.add_field(
                name="Máscara",
                value=discord.utils.escape_mentions(v["mask"]),
                inline=True,
            )

            embed.add_field(
                name="Camisa",
                value=discord.utils.escape_mentions(v["shirt"]),
                inline=True,
            )

            embed.add_field(
                name="Calça / Short",
                value=discord.utils.escape_mentions(self.pants.value),
                inline=True,
            )

            embed.add_field(
                name="Tênis",
                value=discord.utils.escape_mentions(self.shoes.value),
                inline=True,
            )

            embed.add_field(
                name="Arma",
                value=(
                    discord.utils.escape_mentions(self.weapon.value)
                    if self.weapon.value
                    else "Não informado"
                ),
                inline=True,
            )

            embed.set_footer(text="Status: Pendente de análise")

            await destination.send(
                embed=embed,
                view=StaffActionsView(),
            )

            await interaction.response.send_message(
                "✅ Sua solicitação foi enviada com sucesso!",
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissões para acessar ou enviar "
                "mensagens no canal de solicitações.",
                ephemeral=True,
            )

        except Exception as erro:
            print(f"Erro enviando solicitacao de skins: {erro}")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao enviar sua solicitação.",
                    ephemeral=True,
                )


class SkinFirstModal(discord.ui.Modal, title="Solicitação de skins • Etapa 1"):

    famous = discord.ui.TextInput(
        label="Nome do famoso / personagem",
        placeholder="Digite o nome do famoso",
        required=True,
        max_length=100,
    )

    head = discord.ui.TextInput(
        label="ID da cabeça",
        placeholder="Digite o ID da cabeça",
        required=True,
        max_length=100,
    )

    face = discord.ui.TextInput(
        label="ID do rosto",
        placeholder="Digite o ID do rosto",
        required=True,
        max_length=100,
    )

    mask = discord.ui.TextInput(
        label="ID da máscara",
        placeholder="Digite o ID da máscara",
        required=True,
        max_length=100,
    )

    shirt = discord.ui.TextInput(
        label="ID da camisa",
        placeholder="Digite o ID da camisa",
        required=True,
        max_length=100,
    )

    def __init__(self, category_name, panel_channel):
        super().__init__()
        self.category_name = category_name
        self.panel_channel = panel_channel

    async def on_submit(self, interaction: discord.Interaction):

        values = {
            "name": self.famous.value,
            "head": self.head.value,
            "face": self.face.value,
            "mask": self.mask.value,
            "shirt": self.shirt.value,
        }

        await interaction.response.send_modal(
            SkinSecondModal(
                self.category_name,
                self.panel_channel,
                values,
            )
        )


class CategorySelect(discord.ui.Select):

    def __init__(self, panel_channel):

        self.panel_channel = panel_channel

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
            placeholder="Selecione a categoria...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):

        await interaction.response.send_modal(
            SkinFirstModal(
                self.values[0],
                self.panel_channel,
            )
        )


class RequestView(discord.ui.View):

    def __init__(self, panel_channel):
        super().__init__(timeout=180)

        self.add_item(CategorySelect(panel_channel))

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

    async def staff_check(self, interaction):

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

    async def change_status(self, interaction, status, color):

        if not await self.staff_check(interaction):
            return

        embed = interaction.message.embeds[0]
        embed.color = color
        embed.set_footer(text=f"Status: {status}")

        await interaction.response.edit_message(
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Em análise",
        style=discord.ButtonStyle.secondary,
        emoji="🕐",
        custom_id="skins:analysis",
    )
    async def analysis(self, interaction, button):

        await self.change_status(
            interaction,
            "Em análise",
            0xF1C40F,
        )

    @discord.ui.button(
        label="Aprovar",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="skins:approve",
    )
    async def approve(self, interaction, button):

        await self.change_status(
            interaction,
            "Aprovada",
            0x2ECC71,
        )

    @discord.ui.button(
        label="Recusar",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="skins:reject",
    )
    async def reject(self, interaction, button):

        await self.change_status(
            interaction,
            "Recusada",
            0xE74C3C,
        )

    @discord.ui.button(
        label="Encerrar solicitação",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="skins:close",
    )
    async def close(self, interaction, button):

        if not await self.staff_check(interaction):
            return

        embed = interaction.message.embeds[0]
        embed.color = 0x808080
        embed.set_footer(text="Status: Encerrada")

        await interaction.response.edit_message(
            embed=embed,
            view=None,
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
                "Selecione a categoria abaixo.\n\n"
                "Os nomes e IDs das peças serão preenchidos "
                "em campos separados.\n\n"
                f"🌐 [Consultar IDs das skins]({SITE_IDS})\n\n"
                "Todas as solicitações serão enviadas para "
                "o canal privado fixo da equipe."
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
            "Clique no botão abaixo e preencha os campos "
            "individuais dos IDs.\n\n"
            "Todas as solicitações serão encaminhadas "
            "para o canal privado fixo da equipe."
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
