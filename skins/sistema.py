
import discord
from discord.ext import commands
import json
from pathlib import Path

from config import bot


SITE_IDS = "https://ff-item.netlify.app/"
REQUEST_CHANNEL_NAME = "solicitacoes-skins"
DATA_FILE = Path(__file__).with_name("skins_requests.json")


# =========================================================
# ARMAZENAMENTO
# =========================================================

def load_requests():
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as erro:
        print(f"Erro carregando pedidos: {erro}")

    return {}


def save_requests(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as erro:
        print(f"Erro salvando pedidos: {erro}")


def get_request(message_id):
    return load_requests().get(str(message_id))


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

def is_server_owner(interaction):
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
# CAMPOS DO FORMULARIO
# =========================================================

FIELDS = {
    "name": {
        "button": "✏️ Nome",
        "placeholder": "Nome do famoso, personagem ou skin",
    },
    "head": {
        "button": "🧑 Cabeça",
        "placeholder": "Digite o ID da cabeça",
    },
    "face": {
        "button": "👤 Rosto",
        "placeholder": "Digite o ID do rosto",
    },
    "mask": {
        "button": "🎭 Máscara",
        "placeholder": "Digite o ID da máscara",
    },
    "shirt": {
        "button": "👕 Camisa",
        "placeholder": "Digite o ID da camisa",
    },
    "pants": {
        "button": "👖 Calça",
        "placeholder": "Digite o ID da calça ou short",
    },
    "shoes": {
        "button": "👟 Tênis",
        "placeholder": "Digite o ID do tênis",
    },
    "weapon": {
        "button": "🔫 Arma",
        "placeholder": "Digite o ID da arma (opcional)",
    },
}


def get_name_label(category):

    if category == "Skin normal":
        return "Nome da skin"

    if category == "Skin de arma":
        return "Nome da arma / skin"

    return "Nome do famoso / personagem"


def get_name_placeholder(category):

    if category == "Skin normal":
        return "Digite o nome da skin ou o ID, se souber"

    if category == "Skin de arma":
        return "Digite o nome da arma ou da skin"

    return "Digite o nome do famoso ou personagem"


# =========================================================
# MODAL DE CADA CAMPO
# =========================================================

class SkinFieldModal(discord.ui.Modal):

    def __init__(self, form_view, field_key):

        if field_key == "name":
            label = get_name_label(form_view.category_name)
            placeholder = get_name_placeholder(form_view.category_name)
        else:
            label = FIELDS[field_key]["button"]
            placeholder = FIELDS[field_key]["placeholder"]

        super().__init__(
            title=f"Preencher • {label}"
        )

        self.form_view = form_view
        self.field_key = field_key

        self.value_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=False,
            max_length=100,
            default=form_view.values.get(field_key, ""),
        )

        self.add_item(self.value_input)

    async def on_submit(self, interaction):

        self.form_view.values[self.field_key] = (
            self.value_input.value.strip()
        )

        await interaction.response.defer(ephemeral=True)

        try:
            await self.form_view.panel_interaction.edit_original_response(
                embed=self.form_view.create_embed(),
                view=self.form_view,
            )
        except Exception as erro:
            print(f"Erro atualizando painel de skins: {erro}")


# =========================================================
# BOTAO INDIVIDUAL
# =========================================================

class SkinFieldButton(discord.ui.Button):

    def __init__(self, form_view, field_key, row):

        if field_key == "name":
            label = get_name_label(form_view.category_name)
            emoji = "✏️"
        else:
            label = FIELDS[field_key]["button"]
            emoji = None

        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
        )

        self.form_view = form_view
        self.field_key = field_key

    async def callback(self, interaction):

        await interaction.response.send_modal(
            SkinFieldModal(
                self.form_view,
                self.field_key,
            )
        )


# =========================================================
# PAINEL DE PREENCHIMENTO
# =========================================================

class SkinFormView(discord.ui.View):

    def __init__(
        self,
        category_name,
        panel_channel,
        panel_interaction,
    ):

        super().__init__(timeout=900)

        self.category_name = category_name
        self.panel_channel = panel_channel
        self.panel_interaction = panel_interaction

        self.values = {
            "name": "",
            "head": "",
            "face": "",
            "mask": "",
            "shirt": "",
            "pants": "",
            "shoes": "",
            "weapon": "",
        }

        field_rows = {
            "name": 0,
            "head": 0,
            "face": 1,
            "mask": 1,
            "shirt": 2,
            "pants": 2,
            "shoes": 3,
            "weapon": 3,
        }

        for key, row in field_rows.items():
            self.add_item(
                SkinFieldButton(self, key, row)
            )

        self.add_item(
            discord.ui.Button(
                label="Consultar IDs",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url=SITE_IDS,
                row=4,
            )
        )

    def create_embed(self):

        embed = discord.Embed(
            title="🎨 Montar sua skin",
            description=(
                f"**{self.category_name}**\n"
                "Clique nas peças que deseja preencher."
            ),
            color=0x2ECC71,
        )

        field_names = {
            "name": get_name_label(self.category_name),
            "head": "Cabeça",
            "face": "Rosto",
            "mask": "Máscara",
            "shirt": "Camisa",
            "pants": "Calça / short",
            "shoes": "Tênis",
            "weapon": "Arma",
        }

        emojis = {
            "name": "✏️",
            "head": "🧑",
            "face": "👤",
            "mask": "🎭",
            "shirt": "👕",
            "pants": "👖",
            "shoes": "👟",
            "weapon": "🔫",
        }

        filled = 0

        for key in FIELDS:

            value = self.values.get(key, "").strip()

            if not value:
                continue

            filled += 1

            embed.add_field(
                name=f"{emojis[key]} {field_names[key]}",
                value=discord.utils.escape_mentions(value),
                inline=True,
            )

        if filled == 0:
            embed.add_field(
                name="📋 Peças",
                value="Nenhuma peça preenchida ainda.",
                inline=False,
            )

        embed.set_footer(
            text="Preencha somente o que souber e envie quando terminar."
        )

        return embed

    @discord.ui.button(
        label="Enviar solicitação",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=4,
    )
    async def submit_request(self, interaction, button):

        await interaction.response.defer(ephemeral=True)

        try:

            guild = interaction.guild

            if guild is None:
                return await interaction.followup.send(
                    "Não foi possível identificar o servidor.",
                    ephemeral=True,
                )

            destination = await get_request_channel(
                guild,
                self.panel_channel,
            )

            embed = discord.Embed(
                title="📨 NOVA SOLICITAÇÃO DE SKIN",
                description="Uma nova sugestão foi enviada para análise.",
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

            field_names = {
                "name": get_name_label(self.category_name),
                "head": "Cabeça",
                "face": "Rosto",
                "mask": "Máscara",
                "shirt": "Camisa",
                "pants": "Calça / short",
                "shoes": "Tênis",
                "weapon": "Arma",
            }

            emojis = {
                "name": "✏️",
                "head": "🧑",
                "face": "👤",
                "mask": "🎭",
                "shirt": "👕",
                "pants": "👖",
                "shoes": "👟",
                "weapon": "🔫",
            }

            for key in FIELDS:

                value = self.values.get(key, "").strip()

                if not value:
                    continue

                embed.add_field(
                    name=f"{emojis[key]} {field_names[key]}",
                    value=discord.utils.escape_mentions(value),
                    inline=True,
                )

            embed.set_footer(
                text="Status: Pendente de análise"
            )

            message = await destination.send(
                embed=embed,
                view=StaffActionsView(),
            )

            data = load_requests()

            data[str(message.id)] = {
                "requester_id": interaction.user.id,
                "status": "pending",
                "category": self.category_name,
                "character": self.values.get("name", ""),
            }

            save_requests(data)

            await interaction.edit_original_response(
                content="",
                embed=discord.Embed(
                    title="✅ Solicitação enviada!",
                    description="Sua sugestão foi encaminhada para análise.",
                    color=0x2ECC71,
                ),
                view=None,
            )

        except discord.Forbidden:

            await interaction.followup.send(
                "❌ Não tenho permissão para enviar mensagens "
                "no canal privado.",
                ephemeral=True,
            )

        except Exception as erro:

            print(f"Erro enviando solicitacao: {erro}")

            await interaction.followup.send(
                "❌ Ocorreu um erro ao enviar o pedido.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="Cancelar",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        row=4,
    )
    async def cancel_request(self, interaction, button):

        await interaction.response.edit_message(
            content="❌ Preenchimento cancelado.",
            embed=None,
            view=None,
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
                description="Pode informar o nome da skin ou os IDs",
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

    async def callback(self, interaction):

        form_view = SkinFormView(
            self.values[0],
            self.panel_channel,
            interaction,
        )

        await interaction.response.edit_message(
            content=None,
            embed=form_view.create_embed(),
            view=form_view,
        )


# =========================================================
# TELA INICIAL
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

        if not is_server_owner(interaction):

            await interaction.response.send_message(
                "⛔ Somente o dono do servidor pode "
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

        if current_status in ("approved", "rejected", "closed"):
            return await interaction.response.send_message(
                "⚠️ Esta solicitação já foi decidida ou encerrada.",
                ephemeral=True,
            )

        embed = interaction.message.embeds[0]
        embed.color = color
        embed.set_footer(text=f"Status: {status}")

        if decision:
            update_request(
                interaction.message.id,
                status=decision,
            )
            view = StaffActionsView(decided=True)

        elif status == "Em análise":
            update_request(
                interaction.message.id,
                status="analysis",
            )
            view = StaffActionsView()

        else:
            view = StaffActionsView()

        await interaction.response.edit_message(
            embed=embed,
            view=view,
        )

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
                                "Sua solicitação para o mapa "
                                "**CONEXÃO • THEUSSYT** foi aprovada!\n\n"
                                "Em breve, sua sugestão poderá ser "
                                "adicionada ao mapa.\n\n"
                                "Obrigado por participar!"
                            ),
                            color=0x2ECC71,
                        )

                    else:

                        dm_embed = discord.Embed(
                            title="❌ SOLICITAÇÃO RECUSADA",
                            description=(
                                "Sua sugestão não foi aprovada desta vez.\n\n"
                                "Você pode enviar uma nova sugestão "
                                "quando quiser!\n\n"
                                "Obrigado por participar."
                            ),
                            color=0xE74C3C,
                        )

                    character = request.get("character", "")

                    if character:
                        dm_embed.add_field(
                            name="✏️ Nome informado",
                            value=discord.utils.escape_mentions(character),
                            inline=False,
                        )

                    dm_embed.set_footer(
                        text="CONEXÃO • THEUSSYT"
                    )

                    await requester.send(embed=dm_embed)
                    dm_sent = True

                except discord.Forbidden:
                    dm_sent = False

                except Exception as erro:
                    print(f"Erro enviando DM de skins: {erro}")
                    dm_sent = False

            if dm_sent:
                message = "✅ Solicitação atualizada e DM enviada!"
            else:
                message = (
                    "✅ Solicitação atualizada, mas não consegui "
                    "enviar a DM. O usuário pode estar com as "
                    "mensagens privadas bloqueadas."
                )

            await interaction.followup.send(
                message,
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

            if current_status in ("approved", "rejected", "closed"):
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
        embed.set_footer(text="Status: Encerrada")

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
                "**CONEXÃO • THEUSSYT**\n\n"
                "Sugira uma skin para o nosso mapa!\n\n"
                "1️⃣ Escolha a categoria.\n"
                "2️⃣ Preencha o que souber.\n"
                "3️⃣ Envie sua sugestão.\n\n"
                "Você pode informar o nome da skin "
                "ou os IDs das peças."
            ),
            color=0x2ECC71,
        )

        embed.set_footer(
            text="Central de solicitações • CONEXÃO"
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
                "**CONEXÃO • THEUSSYT**\n\n"
                "Quer sugerir uma skin para o mapa?\n\n"
                "Clique abaixo, escolha a categoria "
                "e preencha o que souber.\n\n"
                "Você pode informar o nome da skin "
                "ou os IDs das peças."
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
            "❌ Erro ao publicar o painel. Confira o terminal."
        )


# =========================================================
# CARREGAMENTO
# =========================================================

async def setup(bot):

    bot.add_view(SkinPanelView())
    bot.add_view(StaffActionsView())
