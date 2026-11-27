
import discord
from discord.ext import commands
import json
from pathlib import Path

from config import bot

SITE_IDS = "https://ff-item.netlify.app/"
REQUEST_CHANNEL_NAME = "solicitacoes-skins"

DATA_FILE = Path(__file__).with_name("skins_requests.json")


# =========================================================
# ARMAZENAMENTO DOS PEDIDOS
# =========================================================

def load_requests():
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as erro:
        print(f"Erro carregando pedidos de skins: {erro}")

    return {}


def save_requests(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as erro:
        print(f"Erro salvando pedidos de skins: {erro}")


def get_request(message_id):
    data = load_requests()
    return data.get(str(message_id))


def update_request(message_id, **changes):
    data = load_requests()
    key = str(message_id)

    if key not in data:
        return False

    data[key].update(changes)
    save_requests(data)
    return True


# =========================================================
# PERMISSAO EXCLUSIVA DO DONO
# =========================================================

def is_server_owner(interaction: discord.Interaction):

    return (
        interaction.guild is not None
        and interaction.user.id == interaction.guild.owner_id
    )


# =========================================================
# CANAL FIXO DE SOLICITACOES
# =========================================================

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


# =========================================================
# SEGUNDA ETAPA
# =========================================================

class SkinSecondModal(discord.ui.Modal):

    def __init__(self, category_name, panel_channel, first_values):

        super().__init__(
            title="Finalizar pedido de skin"
        )

        self.category_name = category_name
        self.panel_channel = panel_channel
        self.first_values = first_values

        self.pants = discord.ui.TextInput(
            label="ID da calça / short",
            placeholder="Informe o ID da peça",
            required=True,
            max_length=100,
        )

        self.shoes = discord.ui.TextInput(
            label="ID do tênis",
            placeholder="Informe o ID do tênis",
            required=True,
            max_length=100,
        )

        self.weapon = discord.ui.TextInput(
            label="ID da arma (opcional)",
            placeholder="Deixe vazio se não desejar",
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

        try:

            destination = await get_request_channel(
                guild,
                self.panel_channel,
            )

            v = self.first_values

            embed = discord.Embed(
                title="📨 NOVA SOLICITAÇÃO DE SKIN",
                description=(
                    "Uma nova sugestão foi enviada "
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
                name="🌟 Famoso / personagem",
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
                name="👖 Calça / short",
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

            message = await destination.send(
                embed=embed,
                view=StaffActionsView(),
            )

            # Guarda o solicitante fora do Embed.

            data = load_requests()

            data[str(message.id)] = {
                "requester_id": interaction.user.id,
                "status": "pending",
                "category": self.category_name,
                "character": v["name"],
            }

            save_requests(data)

            await interaction.response.send_message(
                "✅ **Pedido enviado com sucesso!**\n\n"
                "Sua sugestão foi encaminhada para a equipe.",
                ephemeral=True,
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ Não tenho permissões para acessar "
                "ou enviar mensagens no canal privado.",
                ephemeral=True,
            )

        except Exception as erro:

            print(f"Erro enviando solicitacao: {erro}")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Ocorreu um erro ao enviar o pedido.",
                    ephemeral=True,
                )


# =========================================================
# BOTAO DE FINALIZACAO
# =========================================================

class ContinueRequestView(discord.ui.View):

    def __init__(self, category_name, panel_channel, values):

        super().__init__(timeout=300)

        self.category_name = category_name
        self.panel_channel = panel_channel
        self.values = values

        self.add_item(
            discord.ui.Button(
                label="Consultar IDs",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url=SITE_IDS,
            )
        )

    @discord.ui.button(
        label="Preencher peças restantes",
        emoji="➡️",
        style=discord.ButtonStyle.success,
    )
    async def continue_form(self, interaction, button):

        await interaction.response.send_modal(
            SkinSecondModal(
                self.category_name,
                self.panel_channel,
                self.values,
            )
        )


# =========================================================
# PRIMEIRA ETAPA
# =========================================================

class SkinFirstModal(discord.ui.Modal):

    def __init__(self, category_name, panel_channel):

        super().__init__(
            title="Criar skin • Primeira etapa"
        )

        self.category_name = category_name
        self.panel_channel = panel_channel

        self.famous = discord.ui.TextInput(
            label="Nome do famoso / personagem",
            placeholder="Ex: Naruto, Cristiano Ronaldo...",
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

        embed = discord.Embed(
            title="✨ PRIMEIRA ETAPA CONCLUÍDA",
            description=(
                "Seus primeiros dados foram preenchidos!\n\n"
                "Agora falta informar a calça, o tênis "
                "e, caso queira, a arma.\n\n"
                "Clique no botão abaixo para continuar."
            ),
            color=0x2ECC71,
        )

        embed.add_field(
            name="📂 Categoria",
            value=discord.utils.escape_mentions(
                self.category_name
            ),
            inline=False,
        )

        embed.add_field(
            name="🌟 Personagem",
            value=discord.utils.escape_mentions(
                values["name"]
            ),
            inline=False,
        )

        embed.set_footer(
            text="CONEXÃO • Etapa 2 de preenchimento"
        )

        view = ContinueRequestView(
            self.category_name,
            self.panel_channel,
            values,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )


# =========================================================
# SELECAO DE CATEGORIA
# =========================================================

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
                description="Sugestões de skins de armas",
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
            placeholder="🎨 Selecione a categoria...",
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


# =========================================================
# TELA INICIAL DE PREENCHIMENTO
# =========================================================

class RequestView(discord.ui.View):

    def __init__(self, panel_channel):

        super().__init__(timeout=180)

        self.add_item(
            CategorySelect(panel_channel)
        )

        self.add_item(
            discord.ui.Button(
                label="Consultar IDs das skins",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url=SITE_IDS,
            )
        )


# =========================================================
# BOTOES DA STAFF - SOMENTE DONO
# =========================================================

class StaffActionsView(discord.ui.View):

    def __init__(self, decided=False):

        super().__init__(timeout=None)

        if decided:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.custom_id in (
                        "skins:analysis",
                        "skins:approve",
                        "skins:reject",
                    ):
                        item.disabled = True

    async def staff_check(self, interaction):

        # Somente o dono do servidor pode usar os botões.

        if not is_server_owner(interaction):

            await interaction.response.send_message(
                "⛔ **Acesso negado!**\n\n"
                "Somente o dono do servidor pode "
                "gerenciar as solicitações de skins.",
                ephemeral=True,
            )

            return False

        return True

    async def change_status(
        self,
        interaction,
        status,
        color,
        decision=None,
    ):

        if not await self.staff_check(interaction):
            return

        if not interaction.message.embeds:

            return await interaction.response.send_message(
                "Não foi possível localizar a solicitação.",
                ephemeral=True,
            )

        request = get_request(interaction.message.id)

        if not request:

            return await interaction.response.send_message(
                "⚠️ Registro deste pedido não encontrado.",
                ephemeral=True,
            )

        current_status = request.get("status", "pending")

        if current_status in (
            "approved",
            "rejected",
            "closed",
        ):

            return await interaction.response.send_message(
                "⚠️ Esta solicitação já foi decidida ou encerrada.",
                ephemeral=True,
            )

        embed = interaction.message.embeds[0]

        embed.color = color
        embed.set_footer(
            text=f"Status: {status}"
        )

        if decision:

            update_request(
                interaction.message.id,
                status=decision,
            )

            view = StaffActionsView(decided=True)

        else:

            view = StaffActionsView()

        await interaction.response.edit_message(
            embed=embed,
            view=view,
        )

        # =================================================
        # NOTIFICACAO POR DM
        # =================================================

        if decision:

            requester_id = request.get("requester_id")
            dm_sent = False

            if requester_id:

                try:

                    requester = await bot.fetch_user(
                        int(requester_id)
                    )

                    if decision == "approved":

                        dm_embed = discord.Embed(
                            title="✅ SOLICITAÇÃO APROVADA!",
                            description=(
                                "Sua solicitação de skin para o mapa "
                                "**CONEXÃO • THEUSSYT** foi aprovada!\n\n"
                                "🎉 **Sua sugestão foi aprovada pela equipe!**\n\n"
                                "Em breve, a skin poderá ser adicionada "
                                "ao mapa.\n\n"
                                "Agradecemos por participar e enviar "
                                "sua sugestão!"
                            ),
                            color=0x2ECC71,
                        )

                    else:

                        dm_embed = discord.Embed(
                            title="❌ SOLICITAÇÃO RECUSADA",
                            description=(
                                "Infelizmente, sua sugestão de skin "
                                "para o mapa **CONEXÃO • THEUSSYT** "
                                "não foi aprovada pela equipe.\n\n"
                                "Mas não desanime! Você pode enviar "
                                "uma nova sugestão quando quiser.\n\n"
                                "Agradecemos por participar e "
                                "contribuir com o mapa!"
                            ),
                            color=0xE74C3C,
                        )

                    dm_embed.add_field(
                        name="🌟 Personagem",
                        value=discord.utils.escape_mentions(
                            request.get(
                                "character",
                                "Não informado",
                            )
                        ),
                        inline=False,
                    )

                    dm_embed.set_footer(
                        text="CONEXÃO • THEUSSYT"
                    )

                    await requester.send(
                        embed=dm_embed
                    )

                    dm_sent = True

                except discord.Forbidden:
                    dm_sent = False

                except Exception as erro:
                    print(
                        f"Erro enviando DM de skins: {erro}"
                    )
                    dm_sent = False

            if dm_sent:

                await interaction.followup.send(
                    "✅ Solicitação atualizada e DM enviada "
                    "ao solicitante!",
                    ephemeral=True,
                )

            else:

                await interaction.followup.send(
                    "✅ Solicitação atualizada, mas não foi "
                    "possível enviar a DM. O usuário pode "
                    "estar com as mensagens privadas bloqueadas.",
                    ephemeral=True,
                )

        else:

            await interaction.followup.send(
                f"📝 Status atualizado: **{status}**.",
                ephemeral=True,
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
            decision="approved",
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
            decision="rejected",
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

        request = get_request(interaction.message.id)

        if request:

            current_status = request.get("status", "pending")

            if current_status in (
                "approved",
                "rejected",
                "closed",
            ):

                return await interaction.response.send_message(
                    "⚠️ Esta solicitação já foi decidida ou encerrada.",
                    ephemeral=True,
                )

            update_request(
                interaction.message.id,
                status="closed",
            )

        embed = interaction.message.embeds[0]

        embed.color = 0x808080
        embed.set_footer(
            text="Status: Encerrada"
        )

        await interaction.response.edit_message(
            embed=embed,
            view=None,
        )


# =========================================================
# PAINEL PUBLICO
# =========================================================

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

        if not isinstance(
            interaction.channel,
            discord.TextChannel,
        ):

            return await interaction.response.send_message(
                "Este painel precisa estar em um canal de texto.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="🎨 CENTRAL DE SOLICITAÇÕES",
            description=(
                "### CONEXÃO • THEUSSYT\n\n"
                "Crie sua sugestão de skin para o mapa "
                "de maneira organizada.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📋 **COMO FUNCIONA**\n\n"
                "1️⃣ Escolha a categoria.\n"
                "2️⃣ Informe os IDs das peças.\n"
                "3️⃣ Finalize e envie sua sugestão.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🌐 **CONSULTAR IDs**\n"
                "[Clique aqui para encontrar os IDs]("
                + SITE_IDS
                + ")\n\n"
                "Você também pode utilizar o botão "
                "de consulta abaixo.\n\n"
                "🔒 Os pedidos serão encaminhados "
                "para análise da equipe."
            ),
            color=0x2ECC71,
        )

        embed.set_footer(
            text="Sistema de sugestões • CONEXÃO"
        )

        await interaction.response.send_message(
            embed=embed,
            view=RequestView(interaction.channel),
            ephemeral=True,
        )


# =========================================================
# COMANDO DO PAINEL
# =========================================================

@bot.command(name="painelskins")
async def painel_skins(
    ctx,
    canal: discord.TextChannel = None,
):

    if ctx.guild is None:
        return

    if ctx.author.id != ctx.guild.owner_id:

        return await ctx.send(
            "⛔ Somente o dono do servidor pode usar esse comando."
        )

    if canal is None:

        return await ctx.send(
            "❌ Você precisa mencionar um canal.\n"
            "Exemplo: `!painelskins #skins`"
        )

    try:

        embed = discord.Embed(
            title="🎨 PAINEL DE SKINS",
            description=(
                "### CONEXÃO • THEUSSYT\n\n"
                "Deseja sugerir uma skin para o nosso mapa?\n\n"
                "Utilize o botão abaixo para iniciar "
                "sua solicitação.\n\n"
                "🌟 Escolha a categoria\n"
                "👕 Informe os IDs das peças\n"
                "📨 Envie para análise\n\n"
                "Todas as sugestões serão encaminhadas "
                "para o canal privado da equipe."
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
            f"✅ Painel publicado em {canal.mention}!",
            delete_after=5,
        )

    except discord.Forbidden:

        await ctx.send(
            "❌ Não tenho permissão para enviar mensagens "
            "ou embeds nesse canal."
        )

    except Exception as erro:

        print(f"Erro no comando painelskins: {erro}")

        await ctx.send(
            "❌ Erro ao publicar o painel. "
            "Confira o terminal."
        )


# =========================================================
# CARREGAMENTO
# =========================================================

async def setup(bot):

    bot.add_view(SkinPanelView())
    bot.add_view(StaffActionsView())
