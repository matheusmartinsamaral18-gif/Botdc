"""Botões do ticket: painel de abertura e botões dentro do ticket."""
import time
import asyncio

import discord

from config import ADM_CONFIANCA
from tickets.dados import (
    ler_dados_ticket,
    atualizar_dados_ticket,
    eh_responsavel_ticket,
    proximo_numero_ticket,
)
from tickets.assumir import processar_assumir
from tickets.painel_equipe import TicketStaffPanelView
from tickets.transcricao import fechar_ticket


class TicketCloseView(discord.ui.View):
    def __init__(self, assumido=False):
        super().__init__(timeout=None)

        # Com o ticket assumido, o botão público some. Outros admins
        # podem assumir por cima pelo "Ver painel".
        if assumido:
            self.remove_item(self.assumir_ticket_botao)

    @discord.ui.button(
        label="Assumir ticket",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_assumir"
    )
    async def assumir_ticket_botao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await processar_assumir(interaction)

    @discord.ui.button(
        label="Ver painel",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_ver_painel"
    )
    async def ver_painel_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        canal = interaction.channel
        guild = interaction.guild
        if guild is None or not isinstance(canal, discord.TextChannel):
            return

        dados = ler_dados_ticket(canal)
        if not dados.get("owner_id"):
            await interaction.response.send_message(
                "Este canal não é um ticket válido.", ephemeral=True
            )
            return

        if not eh_responsavel_ticket(guild, interaction.user):
            await interaction.response.send_message(
                "Apenas a equipe pode abrir o painel de gerenciamento.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "⚙️ **Painel de gerenciamento do ticket**\n"
            "Escolha uma ação abaixo. Este painel é visível somente para você.",
            view=TicketStaffPanelView(
                mostrar_assumir=(
                    dados.get("assumido_por") != interaction.user.id
                )
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="Fechar ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_fechar"
    )
    async def fechar_ticket_botao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        canal = interaction.channel
        guild = interaction.guild

        if guild is None or not isinstance(canal, discord.TextChannel):
            return

        dados = ler_dados_ticket(canal)

        if not dados["owner_id"]:
            await interaction.response.send_message(
                "Este canal não é um ticket válido.",
                ephemeral=True
            )
            return

        # Somente responsáveis/administradores podem fechar.
        if not eh_responsavel_ticket(guild, interaction.user):
            await interaction.response.send_message(
                "Apenas a equipe (administradores) pode fechar este ticket.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 Ticket será fechado. Estou enviando a transcrição no privado.",
            ephemeral=True
        )

        try:
            await canal.send(
                f"🔒 Ticket fechado por {interaction.user.mention}. "
                "Estou enviando a transcrição no privado..."
            )
        except Exception as erro:
            print(f"Erro enviando aviso de fechamento: {erro}")

        await asyncio.sleep(2)

        await fechar_ticket(canal, interaction.user)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir ticket",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="ticket_abrir"
    )
    async def abrir_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        guild = interaction.guild
        membro = interaction.user
        canal_painel = interaction.channel

        if guild is None:
            return

        if not isinstance(canal_painel, discord.TextChannel):
            return

        # Verifica se o usuário já possui ticket aberto.
        for canal in guild.text_channels:
            dados = ler_dados_ticket(canal)

            if dados["owner_id"] == membro.id:
                await interaction.response.send_message(
                    f"Você já possui um ticket aberto: {canal.mention}",
                    ephemeral=True
                )
                return

        categoria = canal_painel.category

        nome = membro.display_name.lower()

        nome = "".join(
            caractere
            if caractere.isalnum() or caractere == "-"
            else "-"
            for caractere in nome
        )

        nome = nome.strip("-")[:80] or "usuario"

        try:
            await interaction.response.defer(ephemeral=True)

            numero = await proximo_numero_ticket(guild.id)
            nome_canal = f"🎫・{nome}-{numero}"[:100]

            agora = int(time.time())

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                ),

                membro: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
            }

            # Dono do servidor.
            dono = guild.get_member(guild.owner_id)

            if dono:
                overwrites[dono] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True
                )

            # Cargos de administradores e responsáveis.
            for cargo in guild.roles:
                if (
                    cargo.permissions.administrator
                    or cargo.permissions.manage_channels
                ):
                    overwrites[cargo] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_channels=True
                    )

            # Administradores configurados por ID.
            for user_id in ADM_CONFIANCA:
                responsavel = guild.get_member(user_id)

                if responsavel:
                    overwrites[responsavel] = (
                        discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                            manage_channels=True
                        )
                    )

            # Bot.
            if guild.me:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True
                )

            topic = (
                f"ticket_owner:{membro.id}"
                f"|ticket_numero:{numero}"
                f"|ticket_aberto:{agora}"
                f"|ticket_alertado:0"
                f"|ticket_respondido:0"
                f"|ticket_assumido_por:0"
                f"|ticket_ultima_atividade:{agora}"
            )

            ticket_canal = await guild.create_text_channel(
                name=nome_canal,
                category=categoria,
                topic=topic,
                overwrites=overwrites,
                reason=f"Ticket aberto por {membro}"
            )

            embed = discord.Embed(
                title=f"🎫 Atendimento #{numero}",
                description=(
                    f"Olá, {membro.mention}!\n\n"
                    "Seu ticket foi criado com sucesso.\n"
                    "Conte abaixo o que você precisa e aguarde o retorno da equipe.\n\n"
                    f"🕒 **Criado:** <t:{agora}:R>"
                ),
                color=0x5865F2
            )

            embed.add_field(
                name="📌 Informações do atendimento",
                value=(
                    f"**Solicitante:** {membro.mention}\n"
                    f"**Protocolo:** `#{numero}`"
                ),
                inline=False
            )
            embed.add_field(
                name="📨 Como prosseguir",
                value="Envie sua mensagem neste canal. Se precisar, você também pode anexar imagens ou arquivos.",
                inline=False
            )

            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.set_footer(
                text=f"{guild.name} • Central de Atendimento"
            )

            msg_controle = await ticket_canal.send(
                content=membro.mention,
                embed=embed,
                view=TicketCloseView()
            )

            await atualizar_dados_ticket(
                ticket_canal,
                msg_controle_id=msg_controle.id
            )

            await interaction.followup.send(
                f"✅ Seu ticket foi criado: {ticket_canal.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "Não tenho permissão para criar o ticket. "
                "Verifique minhas permissões e minha posição na hierarquia.",
                ephemeral=True
            )

        except Exception as erro:
            print(f"Erro criando ticket: {erro}")

            await interaction.followup.send(
                "Ocorreu um erro ao criar seu ticket.",
                ephemeral=True
            )
