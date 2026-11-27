
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
# CONFIGURACAO DOS CAMPOS
# =========================================================

FIELDS = {
    "name": {
        "label": "Personagem / famoso",
        "button": "🌟 Personagem",
        "placeholder": "Ex: Naruto, Cristiano Ronaldo...",
        "required": True,
    },
    "head": {
        "label": "ID da cabeça",
        "button": "🧑 Cabeça",
        "placeholder": "Digite o ID da cabeça",
        "required": True,
    },
    "face": {
        "label": "ID do rosto",
        "button": "👤 Rosto",
        "placeholder": "Digite o ID do rosto",
        "required": True,
    },
    "mask": {
        "label": "ID da máscara",
        "button": "🎭 Máscara",
        "placeholder": "Digite o ID da máscara",
        "required": True,
    },
    "shirt": {
        "label": "ID da camisa",
        "button": "👕 Camisa",
        "placeholder": "Digite o ID da camisa",
        "required": True,
    },
    "pants": {
        "label": "ID da calça / short",
        "button": "👖 Calça",
        "placeholder": "Digite o ID da calça",
        "required": True,
    },
    "shoes": {
        "label": "ID do tênis",
        "button": "👟 Tênis",
        "placeholder": "Digite o ID do tênis",
        "required": True,
    },
    "weapon": {
        "label": "ID da arma",
        "button": "🔫 Arma",
        "placeholder": "Opcional: digite o ID da arma",
        "required": False,
    },
}


# =========================================================
# MODAL DE UM CAMPO
# =========================================================

class SkinFieldModal(discord.ui.Modal):

    def __init__(self, form_view, field_key):

        config = FIELDS[field_key]

        super().__init__(
            title=f"Preencher • {config['label']}"
        )

        self.form_view = form_view
        self.field_key = field_key

        self.value_input = discord.ui.TextInput(
            label=config["label"],
            placeholder=config["placeholder"],
            required=config["required"],
            max_length=100,
            default=form_view.values.get(field_key, ""),
        )

        self.add_item(self.value_input)

    async def on_submit(self, interaction):

        self.form_view.values[self.field_key] = (
            self.value_input.value.strip()
        )

        await interaction.response.defer(ephemeral=True)

        # Atualiza o painel original com o campo preenchido.
        try:
            await self.form_view.panel_interaction.edit_original_response(
                embed=self.form_view.create_embed(),
                view=self.form_view,
            )
        except Exception as erro:
            print(f"Erro atualizando painel de skins: {erro}")


# =========================================================
# BOTAO INDIVIDUAL DE PREENCHIMENTO
# =========================================================

class SkinFieldButton(discord.ui.Button):

    def __init__(self, form_view, field_key, row):

        config = FIELDS[field_key]

        super().__init__(
            label=config["button"],
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

        # Cada peça possui seu próprio botão.

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
            title="📞 CRIAR SUA SKIN",
            description=(
                "**CONEXÃO • THEUSSYT**\n\n"
                "Personalize sua skin antes de enviar.\n"
                "Clique nos botões para preencher cada peça.\n\n"
                "━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2ECC71,
        )

        embed.add_field(
            name="📂 Categoria",
            value=self.category_name,
            inline=False,
        )

        field_emojis = {
            "name": "🌟",
            "head": "🧑",
            "face": "👤",
            "mask": "🎭",
            "shirt": "👕",
            "pants": "👖",
            "shoes": "👟",
            "weapon": "🔫",
        }

        field_names = {
            "name": "Personagem",
            "head": "Cabeça",
            "face": "Rosto",
            "mask": "Máscara",
            "shirt": "Camisa",
            "pants": "Calça / short",
            "shoes": "Tênis",
            "weapon": "Arma",
        }

        for key in FIELDS:

            value = self.values.get(key, "")

            if value:
                display = discord.utils.escape_mentions(value)
            elif key == "weapon":
                display = "Não informado (opcional)"
            else:
                display = "Não preenchido"

            embed.add_field(
                name=f"{field_emojis[key]} {field_names[key]}",
                value=display,
                inline=True,
            )

        required_fields = [
            key for key, config in FIELDS.items()
            if config["required"]
        ]

        completed = sum(
            1 for key in required_fields
            if self.values.get(key)
        )

        embed.add_field(
            name="📋 Progresso",
            value=f"**{completed}/{len(required_fields)} campos obrigatórios preenchidos**",
            inline=False,
        )

        embed.set_footer(
            text="Preencha os campos e depois clique em Enviar solicitação."
        )

        return embed

    async def refresh(self):

        await self.panel_interaction.edit_original_response(
            embed=self.create_embed(),
            view=self,
        )

    @discord.ui.button(
        label="Enviar solicitação",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=4,
    )
    async def submit_request(self, interaction, button):

        missing = [
            FIELDS[key]["label"]
            for key, config in FIELDS.items()
            if config["required"] and not self.values.get(key)
        ]

        if missing:

            return await interaction.response.send_message(
                "❌ **Ainda faltam alguns campos!**\n\n"
                + "\n".join(f"• {field}" for field in missing),
                ephemeral=True,
            )

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

            field_names = {
                "name": "🌟 Famoso / personagem",
                "head": "🧑 Cabeça",
                "face": "👤 Rosto",
                "mask": "🎭 Máscara",
                "shirt": "👕 Camisa",
                "pants": "👖 Calça / short",
                "shoes": "👟 Tênis",
                "weapon": "🔫 Arma",
            }

            for key, label in field_names.items():

                value = self.values.get(key) or "Não informado"

                embed.add_field(
                    name=label,
                    value=discord.utils.escape_mentions(value),
                    inline=key != "name",
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
                "character": self.values["name"],
            }

            save_requests(data)

            # Finaliza o painel de preenchimento.

            for item in self.children:
                item.disabled = True

            await interaction.edit_original_response(
                content="",
                embed=discord.Embed(
                    title="✅ SOLICITAÇÃO ENVIADA!",
                    description=(
                        "Sua sugestão foi encaminhada "
                        "para análise da equipe.\n\n"
                        "Obrigado por contribuir com o mapa "
                        "**CONEXÃO • THEUSSYT**!"
                    ),
                    color=0x2ECC71,
                ),
                view=None,
            )

        except discord.Forbidden:

            await interaction.followup.send(
                "❌ Não tenho permissão para acessar "
                "ou enviar mensagens no canal privado.",
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

    async def callback(self, interaction):

        category = self.values[0]

        form_view = SkinFormView(
            category,
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

        # Envia DM ao solicitante.

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
                                "🎉 Sua sugestão foi aprovada pela equipe!\n\n"
                                "Em breve, a skin poderá ser adicionada "
                                "ao mapa.\n\n"
                                "Agradecemos por participar!"
                            ),
                            color=0x2ECC71,
                        )

                    else:

                        dm_embed = discord.Embed(
                            title="❌ SOLICITAÇÃO RECUSADA",
                            description=(
                                "Infelizmente, sua sugestão de skin "
                                "para o mapa **CONEXÃO • THEUSSYT** "
                                "não foi aprovada.\n\n"
                                "Mas não desanime! Você pode enviar "
                                "uma nova sugestão quando quiser.\n\n"
                                "Agradecemos por participar!"
                            ),
                            color=0xE74C3C,
                        )

                    dm_embed.add_field(
                        name="🌟 Personagem",
                        value=discord.utils.escape_mentions(
                            request.get("character", "Não informado")
                        ),
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
                message = (
                    "✅ Solicitação atualizada e DM enviada "
                    "ao solicitante!"
                )
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
                "### CONEXÃO • THEUSSYT\n\n"
                "Crie sua sugestão de skin para o mapa "
                "de maneira organizada.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📋 **COMO FUNCIONA**\n\n"
                "1️⃣ Escolha a categoria.\n"
                "2️⃣ Preencha cada peça pelos botões.\n"
                "3️⃣ Confira os dados e envie sua sugestão.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🌐 **CONSULTAR IDs**\n"
                f"[Clique aqui para encontrar os IDs]({SITE_IDS})\n\n"
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
                "👕 Preencha os IDs das peças\n"
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
            "❌ Erro ao publicar o painel. Confira o terminal."
        )


# =========================================================
# CARREGAMENTO
# =========================================================

async def setup(bot):

    bot.add_view(SkinPanelView())
    bot.add_view(StaffActionsView())
