"""Painel da equipe dentro do ticket: assumir, adicionar e remover pessoas."""
import discord

from tickets.dados import ler_dados_ticket, eh_responsavel_ticket
from tickets.assumir import processar_assumir


async def _validar_gestao_ticket(interaction):
    """Confere ticket válido + equipe. Retorna (canal, dados) ou None."""

    canal = interaction.channel
    guild = interaction.guild

    if guild is None or not isinstance(canal, discord.TextChannel):
        await interaction.response.send_message(
            "Canal de ticket inválido.", ephemeral=True
        )
        return None

    if not eh_responsavel_ticket(guild, interaction.user):
        await interaction.response.send_message(
            "Apenas a equipe pode gerenciar participantes.", ephemeral=True
        )
        return None

    dados = ler_dados_ticket(canal)

    if not dados.get("owner_id"):
        await interaction.response.send_message(
            "Este canal não é um ticket válido.", ephemeral=True
        )
        return None

    return canal, dados


class TicketMembroSelect(discord.ui.Select):
    """Lista só com membros que estão dentro do servidor."""

    def __init__(self, membros, modo):
        self.modo = modo

        opcoes = [
            discord.SelectOption(
                label=m.display_name[:100],
                description=f"@{m.name}"[:100],
                value=str(m.id)
            )
            for m in membros[:25]
        ]

        super().__init__(
            placeholder=(
                "Escolha quem adicionar ao ticket..."
                if modo == "adicionar"
                else "Escolha quem remover do ticket..."
            ),
            min_values=1,
            max_values=1,
            options=opcoes
        )

    async def callback(self, interaction: discord.Interaction):
        validado = await _validar_gestao_ticket(interaction)

        if validado is None:
            return

        canal, dados = validado
        guild = interaction.guild
        alvo_id = int(self.values[0])
        membro = guild.get_member(alvo_id)

        if membro is None:
            await interaction.response.send_message(
                "❌ Essa pessoa não está neste servidor.", ephemeral=True
            )
            return

        if membro.id == dados["owner_id"]:
            await interaction.response.send_message(
                "O solicitante principal não pode ser alterado no próprio ticket.",
                ephemeral=True
            )
            return

        try:
            if self.modo == "adicionar":
                await canal.set_permissions(
                    membro,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                    reason=f"Adicionado ao ticket por {interaction.user}"
                )
                texto = f"✅ {membro.mention} agora tem acesso a este ticket."
            else:
                await canal.set_permissions(
                    membro,
                    overwrite=None,
                    reason=f"Removido do ticket por {interaction.user}"
                )
                texto = f"✅ {membro.mention} foi removido deste ticket."

            await interaction.response.send_message(texto, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar as permissões deste canal.",
                ephemeral=True
            )
        except Exception as erro:
            print(f"Erro gerenciando participante do ticket: {erro}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Ocorreu um erro ao atualizar o participante.",
                    ephemeral=True
                )


class TicketMembroSelectView(discord.ui.View):
    def __init__(self, membros, modo):
        super().__init__(timeout=180)
        self.add_item(TicketMembroSelect(membros, modo))


class TicketBuscaMembroModal(discord.ui.Modal, title="➕ Adicionar pessoa"):
    busca = discord.ui.TextInput(
        label="Nome, @usuário ou ID",
        placeholder="Ex.: theus",
        min_length=2,
        max_length=40
    )

    async def on_submit(self, interaction: discord.Interaction):
        validado = await _validar_gestao_ticket(interaction)

        if validado is None:
            return

        canal, dados = validado
        guild = interaction.guild
        termo = str(self.busca.value).strip().lower().lstrip("@")

        resultados = []

        for m in guild.members:
            if m.bot or m.id == dados["owner_id"]:
                continue

            nomes = (
                m.name.lower(),
                m.display_name.lower(),
                (m.global_name or "").lower()
            )

            if (termo.isdigit() and m.id == int(termo)) or any(
                termo in n for n in nomes
            ):
                resultados.append(m)

        resultados.sort(key=lambda m: m.display_name.lower())

        if not resultados:
            await interaction.response.send_message(
                f"❌ Não encontrei ninguém no servidor com **{termo}**. "
                "Só aparecem membros que estão aqui dentro.",
                ephemeral=True
            )
            return

        extra = (
            f"\n(Mostrando 25 de {len(resultados)}. Digite mais letras "
            "do nome para filtrar.)"
            if len(resultados) > 25 else ""
        )

        await interaction.response.send_message(
            f"Membros do servidor encontrados:{extra}",
            view=TicketMembroSelectView(resultados, "adicionar"),
            ephemeral=True
        )


async def enviar_lista_remover(interaction):
    validado = await _validar_gestao_ticket(interaction)

    if validado is None:
        return

    canal, dados = validado

    removiveis = [
        alvo for alvo in canal.overwrites
        if isinstance(alvo, discord.Member)
        and not alvo.bot
        and alvo.id != dados["owner_id"]
        and alvo.id != interaction.guild.owner_id
    ]

    if not removiveis:
        await interaction.response.send_message(
            "Não há pessoas adicionadas manualmente neste ticket.",
            ephemeral=True
        )
        return

    removiveis.sort(key=lambda m: m.display_name.lower())

    await interaction.response.send_message(
        "Escolha quem perderá o acesso ao ticket:",
        view=TicketMembroSelectView(removiveis, "remover"),
        ephemeral=True
    )


class TicketStaffPanelView(discord.ui.View):
    def __init__(self, mostrar_assumir=True):
        super().__init__(timeout=180)

        # Quem já é o responsável não vê o botão de assumir.
        if not mostrar_assumir:
            self.remove_item(self.assumir_no_painel)

    @discord.ui.button(
        label="Assumir ticket",
        emoji="🙋",
        style=discord.ButtonStyle.primary
    )
    async def assumir_no_painel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await processar_assumir(interaction)

    @discord.ui.button(
        label="Adicionar pessoa",
        emoji="➕",
        style=discord.ButtonStyle.success
    )
    async def adicionar_pessoa(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not eh_responsavel_ticket(
            interaction.guild, interaction.user
        ):
            await interaction.response.send_message(
                "Apenas a equipe pode usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(TicketBuscaMembroModal())

    @discord.ui.button(
        label="Remover pessoa",
        emoji="➖",
        style=discord.ButtonStyle.danger
    )
    async def remover_pessoa(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not eh_responsavel_ticket(
            interaction.guild, interaction.user
        ):
            await interaction.response.send_message(
                "Apenas a equipe pode usar este painel.", ephemeral=True
            )
            return
        await enviar_lista_remover(interaction)
