import discord
from discord.ext import commands
import json
from pathlib import Path

from config import bot


SITE_IDS = "https://ff-item.netlify.app/"
REQUEST_CHANNEL_NAME = "solicitacoes-skins"
DATA_FILE = Path(__file__).with_name("skins_requests.json")

MAX_WEAPONS = 10

# Categorias que NÃO pedem nome.
CATEGORIES_WITHOUT_NAME = ("Skin normal",)


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
# SOMENTE O DONO DO SERVIDOR
# =========================================================

def is_server_owner(interaction):
    return (
        interaction.guild is not None
        and interaction.user.id == interaction.guild.owner_id
    )


# =========================================================
# CANAL PRIVADO
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
        topic="Solicitações de skins • CONEXÃO THEUSSYT",
        reason="Criação do canal de solicitações",
    )


# =========================================================
# CAMPOS DAS SKINS
# =========================================================

SKIN_FIELDS = {
    "head": ("🧑 Cabeça", "ID da cabeça"),
    "face": ("👤 Rosto", "ID do rosto"),
    "mask": ("🎭 Máscara", "ID da máscara"),
    "shirt": ("👕 Camisa", "ID da camisa"),
    "pants": ("👖 Calça / short", "ID da calça ou short"),
    "shoes": ("👟 Tênis", "ID do tênis"),
}


def category_name_label(category):
    labels = {
        "Skin de famoso": "Nome do famoso",
        "Skin de anime": "Nome do anime / personagem",
        "Skin normal": "Nome da skin",
        "Outra categoria": "Nome / descrição da skin",
    }

    return labels.get(category, "Nome da skin")


def category_name_placeholder(category):
    placeholders = {
        "Skin de famoso": "Ex: Cristiano Ronaldo",
        "Skin de anime": "Ex: Naruto, Goku, Luffy...",
        "Skin normal": "Digite o nome da skin ou o ID",
        "Outra categoria": "Descreva sua sugestão",
    }

    return placeholders.get(category, "Digite o nome")


# =========================================================
# ATUALIZAR FORMULÁRIO
# =========================================================

async def refresh_form(form):
    """
    Atualiza a mensagem do formulário depois de uma resposta
    de modal, sem depender da mensagem da interação do modal.
    """

    try:
        if form.message is None:
            print("Mensagem do formulário não encontrada.")
            return False

        await form.message.edit(
            embed=form.create_embed(),
            view=form,
        )

        return True

    except discord.NotFound:
        print("A mensagem do formulário não existe mais.")
        return False

    except discord.HTTPException as erro:
        print(f"Erro atualizando formulário: {erro}")
        return False

    except Exception as erro:
        print(f"Erro inesperado atualizando formulário: {erro}")
        return False


# =========================================================
# MODAL DE CAMPO INDIVIDUAL
# =========================================================

class SkinFieldModal(discord.ui.Modal):

    def __init__(self, form, field_key):

        if field_key == "name":
            label = category_name_label(form.category)
            placeholder = category_name_placeholder(form.category)
        else:
            label, placeholder = SKIN_FIELDS[field_key]

        super().__init__(title=label)

        self.form = form
        self.field_key = field_key

        self.field = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=False,
            max_length=100,
            default=form.values.get(field_key, ""),
        )

        self.add_item(self.field)

    async def on_submit(self, interaction):

        self.form.values[self.field_key] = self.field.value.strip()

        await interaction.response.defer(ephemeral=True)

        updated = await refresh_form(self.form)

        if updated:
            await interaction.followup.send(
                "✅ Campo atualizado!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "⚠️ Não consegui atualizar o formulário.",
                ephemeral=True,
            )


# =========================================================
# BOTÃO DE CAMPO
# =========================================================

class SkinFieldButton(discord.ui.Button):

    def __init__(self, form, field_key, row):

        if field_key == "name":
            label = category_name_label(form.category)
            emoji = "✏️"
        else:
            label, _ = SKIN_FIELDS[field_key]
            emoji = None

        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
        )

        self.form = form
        self.field_key = field_key

    async def callback(self, interaction):

        await interaction.response.send_modal(
            SkinFieldModal(self.form, self.field_key)
        )


# =========================================================
# ADICIONAR ARMAS
# =========================================================

class AddWeaponModal(discord.ui.Modal):

    def __init__(self, form):

        super().__init__(title="Adicionar arma")

        self.form = form

        self.weapon_name = discord.ui.TextInput(
            label="Nome da arma / skin",
            placeholder="Ex: MP40, AK, M1014...",
            required=False,
            max_length=100,
        )

        self.weapon_id = discord.ui.TextInput(
            label="ID da arma",
            placeholder="Digite o ID, se souber",
            required=False,
            max_length=100,
        )

        self.add_item(self.weapon_name)
        self.add_item(self.weapon_id)

    async def on_submit(self, interaction):

        name = self.weapon_name.value.strip()
        weapon_id = self.weapon_id.value.strip()

        if not name and not weapon_id:
            return await interaction.response.send_message(
                "Informe pelo menos o nome ou o ID da arma.",
                ephemeral=True,
            )

        if len(self.form.weapons) >= MAX_WEAPONS:
            return await interaction.response.send_message(
                f"Limite de {MAX_WEAPONS} armas atingido.",
                ephemeral=True,
            )

        # Adiciona a arma à lista do formulário.
        self.form.weapons.append({
            "name": name,
            "id": weapon_id,
        })

        # Atualiza o texto do botão.
        self.form.update_weapon_button()

        await interaction.response.defer(ephemeral=True)

        # Atualiza a mensagem original com a nova arma.
        updated = await refresh_form(self.form)

        if updated:
            await interaction.followup.send(
                f"✅ Arma adicionada! "
                f"({len(self.form.weapons)}/{MAX_WEAPONS})",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "⚠️ A arma foi registrada, mas não consegui atualizar "
                "a mensagem do formulário.",
                ephemeral=True,
            )


class AddWeaponButton(discord.ui.Button):

    def __init__(self, form):

        label = (
            "Adicionar outra arma"
            if form.weapons
            else "Adicionar arma"
        )

        super().__init__(
            label=label,
            emoji="➕",
            style=discord.ButtonStyle.primary,
            row=0,
        )

        self.form = form

    async def callback(self, interaction):

        if len(self.form.weapons) >= MAX_WEAPONS:
            return await interaction.response.send_message(
                f"Limite de {MAX_WEAPONS} armas atingido.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            AddWeaponModal(self.form)
        )


# =========================================================
# FORMULÁRIO PRINCIPAL
# =========================================================

class SkinFormView(discord.ui.View):

    def __init__(self, category, panel_channel):

        super().__init__(timeout=900)

        self.category = category
        self.panel_channel = panel_channel
        self.message = None

        # Skin normal não pede nome.
        self.uses_name = category not in CATEGORIES_WITHOUT_NAME

        self.values = {
            "name": "",
            "head": "",
            "face": "",
            "mask": "",
            "shirt": "",
            "pants": "",
            "shoes": "",
        }

        self.weapons = []

        # Botão de consulta.
        self.add_item(
            discord.ui.Button(
                label="Consultar IDs",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url=SITE_IDS,
                row=3,
            )
        )

        if category == "Skin de arma":

            # Começa como "Adicionar arma".
            self.weapon_button = AddWeaponButton(self)
            self.add_item(self.weapon_button)

        else:

            self.weapon_button = None

            # Só adiciona o botão de nome se a categoria usa nome.
            if self.uses_name:
                self.add_item(
                    SkinFieldButton(self, "name", 0)
                )

            field_keys = list(SKIN_FIELDS.keys())

            for index, key in enumerate(field_keys):
                row = 0 if index < 4 else 1

                self.add_item(
                    SkinFieldButton(self, key, row)
                )

    def update_weapon_button(self):
        """
        Muda o botão depois que a primeira arma é adicionada.
        """

        if self.weapon_button is None:
            return

        if self.weapons:
            self.weapon_button.label = "Adicionar outra arma"
        else:
            self.weapon_button.label = "Adicionar arma"

        if len(self.weapons) >= MAX_WEAPONS:
            self.weapon_button.disabled = True
            self.weapon_button.label = "Limite de armas atingido"
        else:
            self.weapon_button.disabled = False

    def create_embed(self):

        embed = discord.Embed(
            title="🎨 Montar solicitação",
            description=(
                f"**Categoria:** {self.category}\n\n"
                "Clique nos botões para preencher.\n"
                "Preencha somente o que souber."
            ),
            color=0x2ECC71,
        )

        if self.category == "Skin de arma":

            embed.add_field(
                name=f"🔫 Armas adicionadas ({len(self.weapons)}/{MAX_WEAPONS})",
                value=(
                    "Nenhuma arma adicionada ainda."
                    if not self.weapons
                    else "Confira abaixo as armas que você adicionou."
                ),
                inline=False,
            )

            for index, weapon in enumerate(self.weapons, start=1):

                name = weapon["name"] or "Não informado"
                weapon_id = weapon["id"] or "Não informado"

                embed.add_field(
                    name=f"🔫 Arma {index}",
                    value=(
                        f"**Nome:** {discord.utils.escape_mentions(name)}\n"
                        f"**ID:** {discord.utils.escape_mentions(weapon_id)}"
                    ),
                    inline=False,
                )

        else:

            if self.uses_name and self.values["name"]:
                embed.add_field(
                    name=category_name_label(self.category),
                    value=discord.utils.escape_mentions(
                        self.values["name"]
                    ),
                    inline=False,
                )

            for key, (label, _) in SKIN_FIELDS.items():

                value = self.values.get(key, "").strip()

                if value:
                    embed.add_field(
                        name=label,
                        value=discord.utils.escape_mentions(value),
                        inline=True,
                    )

            if not any(self.values.values()):
                embed.add_field(
                    name="📋 Preenchimento",
                    value="Nenhuma informação preenchida ainda.",
                    inline=False,
                )

        embed.set_footer(
            text="Preencha somente o que souber • THEUSSYT"
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

            # Não envia uma solicitação totalmente vazia.
            if self.category == "Skin de arma":

                if not self.weapons:
                    return await interaction.followup.send(
                        "Adicione pelo menos uma arma antes de enviar.",
                        ephemeral=True,
                    )

            else:

                if not any(self.values.values()):
                    return await interaction.followup.send(
                        "Preencha pelo menos um campo antes de enviar.",
                        ephemeral=True,
                    )

            destination = await get_request_channel(
                guild,
                self.panel_channel,
            )

            requester = interaction.user

            embed = discord.Embed(
                title="📨 NOVA SOLICITAÇÃO • THEUSSYT",
                description="Uma nova sugestão foi enviada.",
                color=0x2ECC71,
            )

            # Mostra quem fez a solicitação.
            embed.set_author(
                name=f"{requester.display_name} ({requester})",
                icon_url=requester.display_avatar.url,
            )

            embed.add_field(
                name="🙋 Solicitante",
                value=(
                    f"{requester.mention}\n"
                    f"**Nome:** "
                    f"{discord.utils.escape_markdown(requester.display_name)}\n"
                    f"**ID:** `{requester.id}`"
                ),
                inline=False,
            )

            embed.add_field(
                name="🌐 Mapa",
                value="**CONEXÃO • THEUSSYT**",
                inline=False,
            )

            embed.add_field(
                name="📂 Categoria",
                value=discord.utils.escape_mentions(self.category),
                inline=False,
            )

            character = ""

            if self.category == "Skin de arma":

                for index, weapon in enumerate(self.weapons, start=1):

                    name = weapon["name"] or "Não informado"
                    weapon_id = weapon["id"] or "Não informado"

                    embed.add_field(
                        name=f"🔫 Arma {index}",
                        value=(
                            f"**Nome:** {discord.utils.escape_mentions(name)}\n"
                            f"**ID:** {discord.utils.escape_mentions(weapon_id)}"
                        ),
                        inline=False,
                    )

                character = ", ".join(
                    weapon["name"]
                    for weapon in self.weapons
                    if weapon["name"]
                )

            else:

                if self.uses_name:

                    character = self.values.get("name", "")

                    if character:
                        embed.add_field(
                            name=category_name_label(self.category),
                            value=discord.utils.escape_mentions(character),
                            inline=False,
                        )

                for key, (label, _) in SKIN_FIELDS.items():

                    value = self.values.get(key, "").strip()

                    if value:
                        embed.add_field(
                            name=label,
                            value=discord.utils.escape_mentions(value),
                            inline=True,
                        )

            embed.set_footer(
                text="Status: Pendente de análise"
            )

            message = await destination.send(
                embed=embed,
                view=StaffActionsView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )

            data = load_requests()

            data[str(message.id)] = {
                "requester_id": requester.id,
                "requester_name": requester.display_name,
                "status": "pending",
                "category": self.category,
                "character": character,
            }

            save_requests(data)

            await interaction.edit_original_response(
                content="✅ **Solicitação enviada com sucesso!**",
                embed=None,
                view=None,
            )

        except discord.Forbidden:

            await interaction.followup.send(
                "❌ Não tenho permissão para enviar no canal privado.",
                ephemeral=True,
            )

        except Exception as erro:

            print(f"Erro enviando solicitação: {erro}")

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
            content="❌ Solicitação cancelada.",
            embed=None,
            view=None,
        )


# =========================================================
# FINALIZAR APROVAÇÃO / RECUSA
# =========================================================

async def finish_decision(
    interaction,
    message,
    decision,
    reason=None,
):

    if not is_server_owner(interaction):
        return await interaction.response.send_message(
            "⛔ Somente o dono do servidor pode gerenciar os pedidos.",
            ephemeral=True,
        )

    request = get_request(message.id)

    if not request:
        return await interaction.response.send_message(
            "⚠️ Registro da solicitação não encontrado.",
            ephemeral=True,
        )

    if request.get("status") in (
        "approved",
        "rejected",
        "closed",
    ):
        return await interaction.response.send_message(
            "⚠️ Esta solicitação já foi finalizada.",
            ephemeral=True,
        )

    status = "Aprovada" if decision == "approved" else "Recusada"
    color = 0x2ECC71 if decision == "approved" else 0xE74C3C

    embed = message.embeds[0]
    embed.color = color
    embed.set_footer(text=f"Status: {status}")

    update_request(
        message.id,
        status=decision,
        reason=reason,
    )

    await message.edit(
        embed=embed,
        view=StaffActionsView(decided=True),
    )

    dm_sent = False

    try:

        requester = await bot.fetch_user(
            int(request["requester_id"])
        )

        if decision == "approved":

            dm_embed = discord.Embed(
                title="✅ SOLICITAÇÃO APROVADA!",
                description=(
                    "Sua sugestão para o mapa "
                    "**CONEXÃO • THEUSSYT** foi aprovada!\n\n"
                    "Em breve, ela poderá ser adicionada ao mapa.\n\n"
                    "Obrigado por participar!"
                ),
                color=0x2ECC71,
            )

        else:

            dm_embed = discord.Embed(
                title="❌ SOLICITAÇÃO RECUSADA",
                description=(
                    "Sua sugestão para o mapa "
                    "**CONEXÃO • THEUSSYT** não foi aprovada.\n\n"
                    "**Motivo:**\n"
                    f"{discord.utils.escape_mentions(reason or 'Não informado')}\n\n"
                    "Você pode enviar outra sugestão quando quiser."
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
            text="THEUSSYT • CONEXÃO"
        )

        await requester.send(embed=dm_embed)
        dm_sent = True

    except discord.Forbidden:
        dm_sent = False

    except Exception as erro:
        print(f"Erro enviando DM: {erro}")
        dm_sent = False

    if dm_sent:
        message_text = "✅ Pedido atualizado e DM enviada!"
    else:
        message_text = (
            "✅ Pedido atualizado, mas não consegui enviar a DM. "
            "A pessoa pode estar com as mensagens privadas bloqueadas."
        )

    await interaction.response.send_message(
        message_text,
        ephemeral=True,
    )


# =========================================================
# MODAL DE RECUSA COM MOTIVO
# =========================================================

class RejectReasonModal(discord.ui.Modal):

    def __init__(self, message):

        super().__init__(title="Motivo da recusa")

        self.request_message = message

        self.reason = discord.ui.TextInput(
            label="Motivo da recusa",
            placeholder="Explique brevemente o motivo...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction):

        await finish_decision(
            interaction,
            self.request_message,
            decision="rejected",
            reason=self.reason.value.strip(),
        )


# =========================================================
# BOTÕES DE GERENCIAMENTO
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

    async def check_owner(self, interaction):

        if not is_server_owner(interaction):
            await interaction.response.send_message(
                "⛔ Somente o dono do servidor pode gerenciar os pedidos.",
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

        if not await self.check_owner(interaction):
            return

        request = get_request(interaction.message.id)

        if not request:
            return await interaction.response.send_message(
                "Solicitação não encontrada.",
                ephemeral=True,
            )

        if request.get("status") in ("approved", "rejected", "closed"):
            return await interaction.response.send_message(
                "Esta solicitação já foi finalizada.",
                ephemeral=True,
            )

        embed = interaction.message.embeds[0]
        embed.color = 0xF1C40F
        embed.set_footer(text="Status: Em análise")

        update_request(
            interaction.message.id,
            status="analysis",
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Aprovar",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="skins:approve",
    )
    async def approve(self, interaction, button):

        if not await self.check_owner(interaction):
            return

        await finish_decision(
            interaction,
            interaction.message,
            decision="approved",
        )

    @discord.ui.button(
        label="Recusar",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="skins:reject",
    )
    async def reject(self, interaction, button):

        if not await self.check_owner(interaction):
            return

        request = get_request(interaction.message.id)

        if not request:
            return await interaction.response.send_message(
                "Solicitação não encontrada.",
                ephemeral=True,
            )

        if request.get("status") in ("approved", "rejected", "closed"):
            return await interaction.response.send_message(
                "Esta solicitação já foi finalizada.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            RejectReasonModal(interaction.message)
        )

    @discord.ui.button(
        label="Encerrar",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="skins:close",
    )
    async def close(self, interaction, button):

        if not await self.check_owner(interaction):
            return

        request = get_request(interaction.message.id)

        if request and request.get("status") in (
            "approved",
            "rejected",
            "closed",
        ):
            return await interaction.response.send_message(
                "Esta solicitação já foi finalizada.",
                ephemeral=True,
            )

        if request:
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
# SELEÇÃO DE CATEGORIA
# =========================================================

class CategorySelect(discord.ui.Select):

    def __init__(self, panel_channel):

        self.panel_channel = panel_channel

        options = [
            discord.SelectOption(
                label="Skin de famoso",
                description="Sugestões de famosos",
                value="Skin de famoso",
                emoji="🌟",
            ),
            discord.SelectOption(
                label="Skin de anime",
                description="Personagens de anime",
                value="Skin de anime",
                emoji="🎭",
            ),
            discord.SelectOption(
                label="Skin normal",
                description="IDs das peças",
                value="Skin normal",
                emoji="👤",
            ),
            discord.SelectOption(
                label="Skin de arma",
                description="Adicione uma ou várias armas",
                value="Skin de arma",
                emoji="🔫",
            ),
            discord.SelectOption(
                label="Outra categoria",
                description="Outras sugestões",
                value="Outra categoria",
                emoji="📦",
            ),
        ]

        super().__init__(
            placeholder="🎨 Escolha a categoria...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction):

        form = SkinFormView(
            self.values[0],
            self.panel_channel,
        )

        await interaction.response.edit_message(
            content=None,
            embed=form.create_embed(),
            view=form,
        )

        # Guarda a mensagem efetivamente editada.
        # Assim os modais conseguem atualizar o mesmo formulário.
        try:
            form.message = await interaction.original_response()
        except Exception as erro:
            print(f"Erro obtendo mensagem do formulário: {erro}")


# =========================================================
# TELA INICIAL
# =========================================================

class RequestView(discord.ui.View):

    def __init__(self, panel_channel):

        super().__init__(timeout=180)

        self.add_item(CategorySelect(panel_channel))

        self.add_item(
            discord.ui.Button(
                label="Consultar IDs",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url=SITE_IDS,
            )
        )


# =========================================================
# PAINEL PÚBLICO
# =========================================================

class SkinPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Solicitar skin",
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
            title="🎨 CENTRAL DE SKINS",
            description=(
                "**CONEXÃO • THEUSSYT**\n\n"
                "Sugira uma skin para o mapa!\n\n"
                "1️⃣ Escolha a categoria.\n"
                "2️⃣ Preencha o que souber.\n"
                "3️⃣ Envie sua sugestão.\n\n"
                "Todos os campos são opcionais."
            ),
            color=0x2ECC71,
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
async def painel_skins(ctx, canal: discord.TextChannel = None):

    if ctx.guild is None:
        return

    if ctx.author.id != ctx.guild.owner_id:
        return await ctx.send(
            "⛔ Somente o dono do servidor pode usar esse comando."
        )

    if canal is None:
        return await ctx.send(
            "❌ Mencione um canal.\nExemplo: `!painelskins #skins`"
        )

    try:

        embed = discord.Embed(
            title="🎨 PAINEL DE SKINS",
            description=(
                "**CONEXÃO • THEUSSYT**\n\n"
                "Quer sugerir uma skin para o mapa?\n\n"
                "Clique abaixo, escolha a categoria "
                "e preencha o que souber.\n\n"
                "Todos os campos são opcionais."
            ),
            color=0x2ECC71,
        )

        embed.set_footer(
            text="Central de solicitações • THEUSSYT"
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
            "❌ Não tenho permissão para enviar mensagens nesse canal."
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