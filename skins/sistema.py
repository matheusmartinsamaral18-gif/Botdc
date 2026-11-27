
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
        )
    }

    # Permite acesso aos cargos da equipe com permissões administrativas.
    for role in guild.roles:
        if (
            role.permissions.administrator
            or role.permissions.manage_channels
            or role.permissions.manage_threads
        ):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        )

    return await guild.create_text_channel(
        REQUEST_CHANNEL_NAME,
        category=panel_channel.category,
        overwrites=overwrites,
        topic="Canal privado para receber todas as solicitacoes de skins.",
        reason="Criacao do canal fixo de solicitacoes de skins",
    )


class SkinSecondModal(discord.ui.Modal):

    def __init__(self, category_name, panel_channel, first_values):
        super().__init__(
            title="🎨 Finalizar solicitação"
        )

        self.category_name = category_name
        self.panel_channel = panel_channel
        self.first_values = first_values

        self.pants = discord.ui.TextInput(
            label="ID da calça / short",
            placeholder="Digite o ID da calça ou short",
            required=True,
            max_length=100,
        )

        self.shoes = discord.ui.TextInput(
            label="ID do tênis",
            placeholder="Digite o ID do tênis",
            required=True,
            max_length=100,
        )

        self.weapon = discord.ui.TextInput(
            label="ID da arma (opcional)",
            placeholder="Se quiser, informe o ID da arma",
            required=False,
            max_length=100,
        )

        self.add_item(self.pants)
        self.add_item(self.shoes)
        self.add_item(self.weapon)

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild

        if guild is None:
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
                title="📨 NOVA SOLICITAÇÃO",
                description=(
                    "Uma nova sugestão de skin foi enviada "
                    "para análise da equipe."
                ),
                color=0x2ECC71,
            )

            embed.add_field(
                name="🌐 Mapa",
                value="**CONEXÃO • THEUSSYT**",
                inline=False,
            )

            embed.add_field(
                name="📂 Categoria",
                value=discord.utils.escape_mentions(
                    self.category_name
                ),
                inline=False,
            )

            embed.add_field(
                name="🌟 Nome do famoso / personagem",
                value=discord.utils.escape_mentions(
                    v["name"]
                ),
                inline=False,
            )

            embed.add_field(
                name="🧑 Cabeça",
                value=discord.utils.escape_mentions(v["head"]),
                inline=True,
            )

            embed.add_field(
                name="👤 Rosto",
                value=discord.utils.escape_mentions(v["face"]),
                inline=True,
            )

            embed.add_field(
                name="🎭 Máscara",
                value=discord.utils.escape_mentions(v["mask"]),
                inline=True,
            )

            embed.add_field(
                name="👕 Camisa",
                value=discord.utils.escape_mentions(v["shirt"]),
                inline=True,
            )

            embed.add_field(
                name="👖 Calça / Short",
                value=discord.utils.escape_mentions(
                    self.pants.value
                ),
                inline=True,
            )

            embed.add_field(
                name="👟 Tênis",
                value=discord.utils.escape_mentions(
                    self.shoes.value
                ),
                inline=True,
            )

            embed.add_field(
                name="🔫 Arma",
                value=(
                    discord.utils.escape_mentions(
                        self.weapon.value
                    )
                    if self.weapon.value
                    else "Não informado"
                ),
                inline=False,
            )

            embed.set_footer(
                text="Status: Pendente de análise"
            )

            await destination.send(
                embed=embed,
                view=StaffActionsView(),
            )

            await interaction.response.send_message(
                "✅ **Solicitação enviada!**\n"
                "Sua sugestão foi encaminhada para a equipe.",
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissões para acessar "
                "ou enviar mensagens no canal de solicitações.",
                ephemeral=True,
            )

        except Exception as erro:
            print(f"Erro enviando solicitacao: {erro}")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Ocorreu um erro ao enviar a solicitação.",
                    ephemeral=True,
                )


class SkinFirstModal(discord.ui.Modal):

    def __init__(self, category_name, panel_channel):
        super().__init__(
            title="🎨 Solicitar skin • Etapa 1"
        )

        self.category_name = category_name
        self.panel_channel = panel_channel

        self.famous = discord.ui.TextInput(
            label="Nome do famoso / personagem",
            placeholder="Ex: Cristiano Ronaldo, Naruto...",
            required=True,
            max_length=100,
        )

        self.head = discord.ui.TextInput(
            label="ID da cabeça",
            placeholder="Digite o ID da cabeça",
            required=True,
            max_length=100,
        )

        self.face = discord.ui.TextInput(
            label="ID do rosto",
            placeholder="Digite o ID do rosto",
            required=True,
            max_length=100,
        )

        self.mask = discord.ui.TextInput(
            label="ID da máscara",
            placeholder="Digite o ID da máscara",
            required=True,
            max_length=100,
        )

        self.shirt = discord.ui.TextInput(
            label="ID da camisa",
            placeholder="Digite o ID da camisa",
            required=True,
            max_length=100,
        )

        self.add_item(self.famous)
        self.add_item(self.head)
        self.add_item(self.face)
        self.add_item(self.mask)
        self.add_item(self.shirt)

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
                description="Skins inspiradas em famosos",
                value="Skin de famoso",
                emoji="🌟",
            ),
            discord.SelectOption(
                label="Skin de anime",
                description="Skins inspiradas em animes",
                value="Skin de anime",
                emoji="🎭",
            ),
            discord.SelectOption(
                label="Skin normal",
                description="Skins comuns ou personalizadas",
                value="Skin normal",
                emoji="👤",
            ),
            discord.SelectOption(
                label="Skin de arma",
                description="Sugestões envolvendo armas",
                value="Skin de arma",
                emoji="🔫",
            ),
            discord.SelectOption(
                label="Outra categoria",
                description="Uma sugestão diferente",
                value="Outra categoria",
                emoji="📦",
            ),
        ]

        super().__init__(
            placeholder="🎨 Escolha a categoria da skin...",
            min_values=1,
            max_values=1,
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

    @discord.ui.button(
        label="Consultar IDs das skins",
        emoji="🌐",
        style=discord.ButtonStyle.link,
        url=SITE_IDS,
    )
    async def site(self, interaction, button):
        pass


class StaffActionsView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def staff_check(self, interaction):

        if (
            not isinstance(interaction.user, discord.Member)
            or not is_staff(interaction.user)
        ):
            await interaction.response.send_message(
                "⛔ Este botão é exclusivo da equipe.",
                ephemeral=True,
            )
            return False

        return True

    async def change_status(self, interaction, status, color):

        if not await self.staff_check(interaction):
            return

        if not interaction.message.embeds:
            return await interaction.response.send_message(
                "Não foi possível localizar a solicitação.",
                ephemeral=True,
            )

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

        if not interaction.message.embeds:
            return await interaction.response.send_message(
                "Não foi possível localizar a solicitação.",
                ephemeral=True,
            )

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
            title="🎨 SOLICITAÇÃO DE SKINS",
            description=(
                "### CONEXÃO • THEUSSYT\n"
                "Quer sugerir uma skin para o mapa?\n\n"
                "Escolha uma categoria e preencha os IDs "
                "das peças nos campos correspondentes.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🌐 **CONSULTAR IDs**\n"
                f"[Clique aqui para encontrar os IDs]({SITE_IDS})\n\n"
                "Você pode abrir o site, consultar as peças "
                "e retornar ao Discord para continuar.\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📋 **Como funciona?**\n"
                "• Escolha a categoria.\n"
                "• Preencha os IDs individualmente.\n"
                "• Confira os dados e envie.\n\n"
                "🔒 Sua sugestão será encaminhada "
                "para análise da equipe."
            ),
            color=0x2ECC71,
        )

        embed.set_footer(
            text="CONEXÃO • Sistema de sugestões de skins"
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
        title="🎨 PAINEL DE SKINS",
        description=(
            "### CONEXÃO • THEUSSYT\n\n"
            "Quer sugerir uma skin para o nosso mapa?\n\n"
            "Utilize o botão abaixo para enviar sua sugestão "
            "de forma organizada.\n\n"
            "🌟 **Escolha a categoria**\n"
            "👕 **Informe os IDs das peças**\n"
            "📨 **Envie para análise da equipe**\n\n"
            "Todas as solicitações serão encaminhadas "
            "para um canal privado da equipe."
        ),
        color=0x2ECC71,
    )

    embed.set_footer(
        text="CONEXÃO • Central de solicitações"
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
