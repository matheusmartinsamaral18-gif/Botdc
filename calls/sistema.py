"""
SISTEMA DE CALLS TEMPORÁRIAS

- !painelcall #canal -> envia painel
- Criação pública ou privada
- Limite personalizável
- Nome personalizado
- Pessoas autorizadas
- Gerenciamento privado para o dono
- Botão para entrar na própria call
- Adicionar pessoas a qualquer momento
- Alterar limite a qualquer momento
- Alternar entre pública e privada
- Apenas uma call aberta por criador
- Dono possui prioridade
- Administradores também respeitam o limite
- Call vazia por 30 segundos -> é apagada
"""

import asyncio
import json
import os
import time

import discord
from discord.ext import commands, tasks

from config import MEU_ID, LOGS_CHANNEL_ID


# =====================================================
# CONFIGURAÇÕES
# =====================================================

CATEGORIA_CALLS_ID = None

LIMITES = [2, 3, 4, 5, 6, 7, 8, 10, 15, 20]

TEMPO_VAZIA_SEG = 30
MAX_CONVIDADOS = 10

COR_PRINCIPAL = 0x57F287
COR_ALERTA = 0xED4245

ARQUIVO = os.path.join(
    os.path.dirname(__file__),
    "dados_calls.json"
)


# =====================================================
# PAINEL PRINCIPAL
# =====================================================

class PainelView(discord.ui.View):

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Abrir call",
        style=discord.ButtonStyle.success,
        emoji="📞",
        custom_id="call:abrir"
    )
    async def abrir(self, interaction, button):

        existente = self.cog.call_do_dono(
            interaction.guild,
            interaction.user.id
        )

        if existente:
            return await interaction.response.send_message(
                f"⚠️ Você já possui uma call aberta: {existente.mention}",
                ephemeral=True
            )

        view = CriarCallView(
            self.cog,
            interaction.user.display_name
        )

        await interaction.response.send_message(
            embed=view.embed(),
            view=view,
            ephemeral=True
        )


# =====================================================
# MODAL DE NOME
# =====================================================

class NomeModal(discord.ui.Modal, title="Nome da call"):

    nome = discord.ui.TextInput(
        label="Nome personalizado",
        placeholder="Digite o nome da sua call",
        required=False,
        max_length=50
    )

    def __init__(self, view):
        super().__init__()

        self.view_ref = view

        if view.nome:
            self.nome.default = view.nome

    async def on_submit(self, interaction):

        self.view_ref.nome = self.nome.value.strip() or None

        self.view_ref.atualizar()

        await interaction.response.edit_message(
            embed=self.view_ref.embed(),
            view=self.view_ref
        )


# =====================================================
# TIPO DE CALL
# =====================================================

class BotaoTipo(discord.ui.Button):

    def __init__(self, privada):

        super().__init__(
            label="Privada" if privada else "Pública",
            emoji="🔒" if privada else "🌎",
            style=discord.ButtonStyle.secondary,
            row=0
        )

        self.privada = privada

    async def callback(self, interaction):

        view = self.view

        view.privada = self.privada

        view.atualizar()

        await interaction.response.edit_message(
            embed=view.embed(),
            view=view
        )


# =====================================================
# BOTÃO NOME
# =====================================================

class BotaoNome(discord.ui.Button):

    def __init__(self):

        super().__init__(
            label="Nome",
            emoji="✏️",
            style=discord.ButtonStyle.secondary,
            row=0
        )

    async def callback(self, interaction):

        await interaction.response.send_modal(
            NomeModal(self.view)
        )


# =====================================================
# LIMITE INICIAL
# =====================================================

class BotaoLimite(discord.ui.Button):

    def __init__(self, limite, row):

        super().__init__(
            label=str(limite),
            emoji="👥",
            style=discord.ButtonStyle.secondary,
            row=row
        )

        self.limite = limite

    async def callback(self, interaction):

        view = self.view

        view.limite = self.limite

        view.atualizar()

        await interaction.response.edit_message(
            embed=view.embed(),
            view=view
        )


# =====================================================
# CRIAR CALL
# =====================================================

class BotaoCriar(discord.ui.Button):

    def __init__(self):

        super().__init__(
            label="Criar call",
            emoji="✅",
            style=discord.ButtonStyle.success,
            row=4
        )

    async def callback(self, interaction):

        view = self.view

        await interaction.response.defer()

        canal, ja_existia = await view.cog.criar_call(
            interaction,
            view.privada,
            view.limite,
            view.nome,
            view.permitidos
        )

        if canal is None:

            return await interaction.edit_original_response(
                content="❌ Não consegui criar sua call. Verifique as permissões do bot.",
                embed=None,
                view=None
            )

        if ja_existia:

            return await interaction.edit_original_response(
                content=f"⚠️ Você já possui uma call: {canal.mention}",
                embed=None,
                view=None
            )

        # ---------------------------------------------
        # GERENCIAMENTO EXCLUSIVO DO DONO
        # ---------------------------------------------

        gerenciar = GerenciarCallView(
            view.cog,
            canal.id,
            interaction.user.id
        )

        view.cog.bot.add_view(gerenciar)

        embed = GerenciarCallView.embed_gerenciamento(
            view.cog,
            canal.id
        )

        # Mensagem efêmera: somente o dono consegue ver.
        await interaction.followup.send(
            content="⚙️ **Sua call foi criada! Gerencie sua sala por aqui:**",
            embed=embed,
            view=gerenciar,
            ephemeral=True
        )

        await interaction.edit_original_response(
            content=f"✅ Sua call foi criada: {canal.mention}",
            embed=None,
            view=None
        )


# =====================================================
# CANCELAR
# =====================================================

class BotaoCancelar(discord.ui.Button):

    def __init__(self):

        super().__init__(
            label="Cancelar",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
            row=4
        )

    async def callback(self, interaction):

        await interaction.response.edit_message(
            content="❌ Criação cancelada.",
            embed=None,
            view=None
        )


# =====================================================
# LIMPAR CONVIDADOS
# =====================================================

class BotaoLimpar(discord.ui.Button):

    def __init__(self):

        super().__init__(
            label="Limpar",
            emoji="🧹",
            style=discord.ButtonStyle.secondary,
            row=4
        )

    async def callback(self, interaction):

        view = self.view

        view.permitidos = []
        view.nomes_permitidos = []

        await interaction.response.edit_message(
            embed=view.embed(),
            view=view
        )


# =====================================================
# CONFIGURAÇÃO INICIAL
# =====================================================

class CriarCallView(discord.ui.View):

    def __init__(self, cog, dono_nome):

        super().__init__(timeout=300)

        self.cog = cog
        self.dono_nome = dono_nome

        self.privada = False
        self.limite = 2
        self.nome = None

        self.permitidos = []
        self.nomes_permitidos = []

        self.botoes_tipo = [
            BotaoTipo(False),
            BotaoTipo(True)
        ]

        self.botao_nome = BotaoNome()

        self.botoes_limite = []

        for botao in self.botoes_tipo:
            self.add_item(botao)

        self.add_item(self.botao_nome)

        for i, numero in enumerate(LIMITES):

            botao = BotaoLimite(
                numero,
                row=1 + i // 5
            )

            self.botoes_limite.append(botao)
            self.add_item(botao)

        self.add_item(BotaoCriar())
        self.add_item(BotaoCancelar())
        self.add_item(BotaoLimpar())

        self.atualizar()

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Adicionar pessoas autorizadas",
        min_values=1,
        max_values=MAX_CONVIDADOS,
        row=3
    )
    async def selecionar_permitidos(self, interaction, select):

        selecionados = list(self.permitidos)
        nomes = list(self.nomes_permitidos)

        for usuario in select.values:

            membro = interaction.guild.get_member(usuario.id)

            if membro is None or membro.bot:
                continue

            if membro.id == interaction.user.id:
                continue

            if membro.id not in selecionados:

                selecionados.append(membro.id)
                nomes.append(membro.display_name)

        self.permitidos = selecionados[:MAX_CONVIDADOS]
        self.nomes_permitidos = nomes[:MAX_CONVIDADOS]

        await interaction.response.edit_message(
            embed=self.embed(),
            view=self
        )

    def atualizar(self):

        for botao in self.botoes_tipo:

            botao.style = (
                discord.ButtonStyle.primary
                if botao.privada == self.privada
                else discord.ButtonStyle.secondary
            )

        for botao in self.botoes_limite:

            botao.style = (
                discord.ButtonStyle.primary
                if botao.limite == self.limite
                else discord.ButtonStyle.secondary
            )

        self.botao_nome.style = (
            discord.ButtonStyle.primary
            if self.nome
            else discord.ButtonStyle.secondary
        )

    def embed(self):

        e = discord.Embed(
            title="📞 Criar sua call",
            description="Personalize sua sala antes de criar.",
            color=COR_PRINCIPAL
        )

        e.add_field(
            name="🔐 Tipo",
            value="🔒 Privada" if self.privada else "🌎 Pública",
            inline=True
        )

        e.add_field(
            name="👥 Limite",
            value=f"{self.limite} pessoas",
            inline=True
        )

        e.add_field(
            name="✏️ Nome da sala",
            value=self.nome or f"Call de {self.dono_nome}",
            inline=False
        )

        e.add_field(
            name=f"🔑 Pessoas autorizadas ({len(self.permitidos)})",
            value=", ".join(self.nomes_permitidos) or "Nenhuma selecionada",
            inline=False
        )

        return e


# =====================================================
# GERENCIAMENTO DA CALL
# =====================================================

class GerenciarCallView(discord.ui.View):

    def __init__(self, cog, canal_id, dono_id):

        super().__init__(timeout=None)

        self.cog = cog
        self.canal_id = canal_id
        self.dono_id = dono_id

        dados = cog.calls.get(canal_id, {})
        privada = dados.get("privada", False)

        # BOTÃO ENTRAR NA CALL

        entrar = discord.ui.Button(
            label="Entrar na call",
            emoji="🎙️",
            style=discord.ButtonStyle.success,
            custom_id=f"call:gerenciar:{canal_id}:entrar",
            row=0
        )

        # ADICIONAR PESSOAS

        adicionar = discord.ui.Button(
            label="Adicionar pessoas",
            emoji="➕",
            style=discord.ButtonStyle.success,
            custom_id=f"call:gerenciar:{canal_id}:adicionar",
            row=1
        )

        # ALTERAR LIMITE

        limite = discord.ui.Button(
            label="Alterar limite",
            emoji="👥",
            style=discord.ButtonStyle.primary,
            custom_id=f"call:gerenciar:{canal_id}:limite",
            row=1
        )

        # ALTERAR PRIVACIDADE

        tipo = discord.ui.Button(
            label="Tornar pública" if privada else "Tornar privada",
            emoji="🌎" if privada else "🔒",
            style=discord.ButtonStyle.secondary,
            custom_id=f"call:gerenciar:{canal_id}:tipo",
            row=1
        )

        entrar.callback = self.entrar_callback
        adicionar.callback = self.adicionar_callback
        limite.callback = self.limite_callback
        tipo.callback = self.tipo_callback

        self.add_item(entrar)
        self.add_item(adicionar)
        self.add_item(limite)
        self.add_item(tipo)

        self.botao_tipo = tipo

    @staticmethod
    def embed_gerenciamento(cog, canal_id):

        dados = cog.calls.get(canal_id)

        embed = discord.Embed(
            title="⚙️ Gerenciar sua call",
            color=COR_PRINCIPAL
        )

        if not dados:
            embed.description = "Esta call não está mais disponível."
            return embed

        canal = cog.bot.get_channel(canal_id)

        embed.description = (
            f"🎙️ **Sala:** {canal.mention if canal else 'Indisponível'}\n"
            f"🔐 **Tipo:** {'Privada' if dados.get('privada') else 'Pública'}\n"
            f"👥 **Limite:** {dados.get('limite', 2)} pessoas\n\n"
            "Use os botões abaixo para modificar sua sala."
        )

        return embed

    async def verificar(self, interaction):

        dados = self.cog.calls.get(self.canal_id)

        if not dados:

            await interaction.response.send_message(
                "❌ Essa call não existe mais.",
                ephemeral=True
            )

            return None

        if interaction.user.id != dados.get("dono"):

            await interaction.response.send_message(
                "❌ Somente o dono da call pode gerenciá-la.",
                ephemeral=True
            )

            return None

        canal = interaction.guild.get_channel(
            self.canal_id
        )

        if canal is None:

            await interaction.response.send_message(
                "❌ A call não foi encontrada.",
                ephemeral=True
            )

            return None

        return canal, dados

    # -------------------------------------------------
    # ENTRAR NA PRÓPRIA CALL
    # -------------------------------------------------

    async def entrar_callback(self, interaction):

        resultado = await self.verificar(interaction)

        if not resultado:
            return

        canal, dados = resultado

        membro = interaction.user

        # Verifica se o usuário já está na própria call.
        if membro.voice and membro.voice.channel:

            if membro.voice.channel.id == canal.id:

                return await interaction.response.send_message(
                    "✅ Você já está na sua call!",
                    ephemeral=True
                )

        else:

            return await interaction.response.send_message(
                "⚠️ Você precisa estar conectado a um canal de voz primeiro para que eu possa te mover.",
                ephemeral=True
            )

        # Move o dono para a própria call.
        try:

            await membro.move_to(
                canal,
                reason="Dono entrou na própria call temporária"
            )

            await interaction.response.send_message(
                f"✅ Você foi movido para sua call: {canal.mention}",
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ Não tenho permissão para mover você. Verifique se o bot possui a permissão **Mover membros**.",
                ephemeral=True
            )

        except discord.HTTPException:

            await interaction.response.send_message(
                "❌ Não consegui mover você para sua call. Tente novamente.",
                ephemeral=True
            )

    # -------------------------------------------------
    # ADICIONAR PESSOAS
    # -------------------------------------------------

    async def adicionar_callback(self, interaction):

        resultado = await self.verificar(interaction)

        if not resultado:
            return

        view = AdicionarPessoasView(
            self.cog,
            self.canal_id,
            self.dono_id
        )

        await interaction.response.send_message(
            content="Selecione as pessoas que deseja liberar:",
            view=view,
            ephemeral=True
        )

    # -------------------------------------------------
    # ALTERAR LIMITE
    # -------------------------------------------------

    async def limite_callback(self, interaction):

        resultado = await self.verificar(interaction)

        if not resultado:
            return

        view = AlterarLimiteView(
            self.cog,
            self.canal_id,
            self.dono_id
        )

        await interaction.response.send_message(
            content="Escolha o novo limite da sua call:",
            view=view,
            ephemeral=True
        )

    # -------------------------------------------------
    # ALTERNAR PÚBLICA / PRIVADA
    # -------------------------------------------------

    async def tipo_callback(self, interaction):

        resultado = await self.verificar(interaction)

        if not resultado:
            return

        canal, dados = resultado

        guild = interaction.guild

        nova_privacidade = not dados.get("privada", False)

        try:

            if nova_privacidade:

                # Torna privada.
                await canal.set_permissions(
                    guild.default_role,
                    view_channel=True,
                    connect=False
                )

                # Libera o dono.
                dono = guild.get_member(dados["dono"])

                if dono:

                    await canal.set_permissions(
                        dono,
                        view_channel=True,
                        connect=True,
                        speak=True
                    )

                # Libera todos os convidados cadastrados.
                for uid in dados.get("permitidos", []):

                    membro = guild.get_member(uid)

                    if membro and not membro.bot:

                        await canal.set_permissions(
                            membro,
                            view_channel=True,
                            connect=True,
                            speak=True
                        )

            else:

                # Torna pública.
                await canal.set_permissions(
                    guild.default_role,
                    view_channel=True,
                    connect=True
                )

                # Remove permissões individuais dos convidados.
                for uid in dados.get("permitidos", []):

                    membro = guild.get_member(uid)

                    if membro:

                        await canal.set_permissions(
                            membro,
                            overwrite=None
                        )

                # Restaura a permissão explícita do dono.
                dono = guild.get_member(dados["dono"])

                if dono:

                    await canal.set_permissions(
                        dono,
                        view_channel=True,
                        connect=True,
                        speak=True
                    )

        except discord.Forbidden:

            return await interaction.response.send_message(
                "❌ Não tenho permissão para alterar a privacidade da call.",
                ephemeral=True
            )

        except discord.HTTPException:

            return await interaction.response.send_message(
                "❌ Ocorreu um erro ao alterar a privacidade.",
                ephemeral=True
            )

        dados["privada"] = nova_privacidade

        self.cog.salvar()

        # Atualiza o botão e a mensagem.
        self.botao_tipo.label = (
            "Tornar pública"
            if nova_privacidade
            else "Tornar privada"
        )

        self.botao_tipo.emoji = (
            "🌎"
            if nova_privacidade
            else "🔒"
        )

        await interaction.response.edit_message(
            embed=self.embed_gerenciamento(
                self.cog,
                self.canal_id
            ),
            view=self
        )


# =====================================================
# ADICIONAR PESSOAS DEPOIS DA CRIAÇÃO
# =====================================================

class AdicionarPessoasView(discord.ui.View):

    def __init__(self, cog, canal_id, dono_id):

        super().__init__(timeout=180)

        self.cog = cog
        self.canal_id = canal_id
        self.dono_id = dono_id

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Selecione quem poderá entrar",
        min_values=1,
        max_values=MAX_CONVIDADOS
    )
    async def selecionar(self, interaction, select):

        dados = self.cog.calls.get(self.canal_id)

        if not dados:

            return await interaction.response.send_message(
                "❌ Essa call não existe mais.",
                ephemeral=True
            )

        if interaction.user.id != dados.get("dono"):

            return await interaction.response.send_message(
                "❌ Somente o dono pode adicionar pessoas.",
                ephemeral=True
            )

        canal = interaction.guild.get_channel(
            self.canal_id
        )

        if canal is None:

            return await interaction.response.send_message(
                "❌ Call não encontrada.",
                ephemeral=True
            )

        adicionados = []

        permitidos = dados.setdefault(
            "permitidos",
            [self.dono_id]
        )

        for usuario in select.values:

            membro = interaction.guild.get_member(
                usuario.id
            )

            if membro is None or membro.bot:
                continue

            if membro.id == self.dono_id:
                continue

            if membro.id not in permitidos:

                permitidos.append(membro.id)

            # Se estiver privada, libera imediatamente.
            if dados.get("privada", False):

                try:

                    await canal.set_permissions(
                        membro,
                        view_channel=True,
                        connect=True,
                        speak=True
                    )

                except discord.HTTPException:
                    continue

            adicionados.append(membro.mention)

        self.cog.salvar()

        if adicionados:

            await interaction.response.edit_message(
                content=(
                    "✅ **Pessoas adicionadas:**\n"
                    + "\n".join(adicionados)
                ),
                view=None
            )

        else:

            await interaction.response.edit_message(
                content="⚠️ Nenhuma pessoa nova foi adicionada.",
                view=None
            )


# =====================================================
# ALTERAR LIMITE DEPOIS DA CRIAÇÃO
# =====================================================

class AlterarLimiteView(discord.ui.View):

    def __init__(self, cog, canal_id, dono_id):

        super().__init__(timeout=180)

        self.cog = cog
        self.canal_id = canal_id
        self.dono_id = dono_id

        opcoes = [
            discord.SelectOption(
                label=f"{n} pessoas",
                value=str(n),
                emoji="👥"
            )
            for n in LIMITES
        ]

        select = discord.ui.Select(
            placeholder="Escolha o novo limite",
            options=opcoes
        )

        select.callback = self.selecionar_limite

        self.add_item(select)

    async def selecionar_limite(self, interaction):

        dados = self.cog.calls.get(self.canal_id)

        if not dados:

            return await interaction.response.send_message(
                "❌ Essa call não existe mais.",
                ephemeral=True
            )

        if interaction.user.id != dados.get("dono"):

            return await interaction.response.send_message(
                "❌ Somente o dono pode alterar o limite.",
                ephemeral=True
            )

        canal = interaction.guild.get_channel(
            self.canal_id
        )

        if canal is None:

            return await interaction.response.send_message(
                "❌ Call não encontrada.",
                ephemeral=True
            )

        limite = int(interaction.data["values"][0])

        try:

            await canal.edit(
                user_limit=limite,
                reason="Limite alterado pelo dono da call"
            )

        except discord.HTTPException:

            return await interaction.response.send_message(
                "❌ Não consegui alterar o limite.",
                ephemeral=True
            )

        dados["limite"] = limite

        self.cog.salvar()

        await interaction.response.edit_message(
            content=f"✅ Limite alterado para **{limite} pessoas**.",
            view=None
        )

        # Desconecta participantes excedentes.
        if len(canal.members) > limite:

            ordem = dados.setdefault("ordem", [])

            candidatos = [
                membro
                for membro in canal.members
                if membro.id != dados.get("dono")
                and not membro.bot
            ]

            candidatos.sort(
                key=lambda pessoa: (
                    ordem.index(pessoa.id)
                    if pessoa.id in ordem
                    else -1
                ),
                reverse=True
            )

            excesso = len(canal.members) - limite

            for membro in candidatos[:excesso]:

                try:

                    await membro.move_to(
                        None,
                        reason="Novo limite da call ultrapassado"
                    )

                    if membro.id in ordem:
                        ordem.remove(membro.id)

                except discord.HTTPException:
                    pass

            self.cog.salvar()


# =====================================================
# COG PRINCIPAL
# =====================================================

class CallCog(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.calls = {}
        self.locks = {}

        # Trava individual para cada criador.
        # Impede criação simultânea de várias calls.
        self.owner_locks = {}

    # -------------------------------------------------
    # CICLO DE VIDA
    # -------------------------------------------------

    async def cog_load(self):

        self.carregar()

        self.bot.add_view(
            PainelView(self)
        )

        # Recupera os controles persistentes das calls.
        for cid, dados in self.calls.items():

            self.locks.setdefault(
                cid,
                asyncio.Lock()
            )

            self.owner_locks.setdefault(
                dados["dono"],
                asyncio.Lock()
            )

            self.bot.add_view(
                GerenciarCallView(
                    self,
                    cid,
                    dados["dono"]
                )
            )

        self.limpeza.start()

    async def cog_unload(self):

        self.limpeza.cancel()

    # -------------------------------------------------
    # PERSISTÊNCIA
    # -------------------------------------------------

    def carregar(self):

        try:

            with open(ARQUIVO, "r", encoding="utf-8") as f:
                bruto = json.load(f)

        except (FileNotFoundError, json.JSONDecodeError):

            self.calls = {}
            return

        if isinstance(bruto, dict) and "calls" in bruto:
            bruto = bruto.get("calls", {})

        self.calls = {
            int(k): v
            for k, v in bruto.items()
        }

        for dados in self.calls.values():

            dados.setdefault("ordem", [])
            dados.setdefault("permitidos", [])
            dados.setdefault("vazia_desde", time.time())

    def salvar(self):

        try:

            with open(ARQUIVO, "w", encoding="utf-8") as f:

                json.dump(
                    {
                        "calls": {
                            str(k): v
                            for k, v in self.calls.items()
                        }
                    },
                    f,
                    ensure_ascii=False,
                    indent=4
                )

        except OSError as erro:

            print(f"Erro salvando calls: {erro}")

    # -------------------------------------------------
    # LOGS
    # -------------------------------------------------

    async def _log(self, texto=None, embed=None):

        canal = self.bot.get_channel(LOGS_CHANNEL_ID)

        if canal:

            try:

                await canal.send(
                    content=texto,
                    embed=embed
                )

            except discord.HTTPException:
                pass

    # -------------------------------------------------
    # CALL DO DONO
    # -------------------------------------------------

    def call_do_dono(self, guild, dono_id):

        for cid, dados in list(self.calls.items()):

            if dados["dono"] == dono_id:

                canal = guild.get_channel(cid)

                if canal:
                    return canal

                # Remove registro antigo caso o canal não exista.
                self.calls.pop(cid, None)
                self.locks.pop(cid, None)

                self.salvar()

        return None

    # -------------------------------------------------
    # PAINEL PRINCIPAL
    # -------------------------------------------------

    @commands.command(name="painelcall")
    async def painelcall(self, ctx, canal: discord.TextChannel = None):

        if not (
            ctx.author.guild_permissions.administrator
            or ctx.author.id == MEU_ID
        ):

            return await ctx.send(
                "❌ Você não tem permissão para isso."
            )

        if canal is None:

            return await ctx.send(
                "Use: `!painelcall #canal`"
            )

        embed = discord.Embed(
            title="🎙️ CALLS TEMPORÁRIAS",
            description=(
                "Crie sua própria sala de voz e personalize "
                "as configurações do seu jeito!\n\n"
                "🌎 Escolha entre call pública ou privada.\n"
                "👥 Defina o limite de participantes.\n"
                "⚙️ Gerencie sua sala sempre que precisar.\n\n"
                "**📞 Clique abaixo para começar!**"
            ),
            color=COR_PRINCIPAL
        )

        if ctx.guild.icon:
            embed.set_thumbnail(
                url=ctx.guild.icon.url
            )

        await canal.send(
            embed=embed,
            view=PainelView(self)
        )

        await ctx.send(
            f"✅ Painel enviado em {canal.mention}!"
        )

    # -------------------------------------------------
    # CRIAR CALL COM TRAVA POR DONO
    # -------------------------------------------------

    async def criar_call(
        self,
        interaction,
        privada,
        limite,
        nome=None,
        permitidos=None
    ):

        dono_id = interaction.user.id

        lock = self.owner_locks.setdefault(
            dono_id,
            asyncio.Lock()
        )

        async with lock:

            # Verifica novamente dentro da trava.
            # Assim, dois cliques simultâneos não criam
            # duas calls para o mesmo usuário.
            existente = self.call_do_dono(
                interaction.guild,
                dono_id
            )

            if existente:
                return existente, True

            return await self._criar_call(
                interaction,
                privada,
                limite,
                nome,
                permitidos
            )

    # -------------------------------------------------
    # CRIAÇÃO REAL DA CALL
    # -------------------------------------------------

    async def _criar_call(
        self,
        interaction,
        privada,
        limite,
        nome=None,
        permitidos=None
    ):

        guild = interaction.guild
        dono = interaction.user

        if CATEGORIA_CALLS_ID:

            categoria = guild.get_channel(
                CATEGORIA_CALLS_ID
            )

        else:

            categoria = interaction.channel.category

        overwrites = {

            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                move_members=True,
                manage_channels=True
            ),

            dono: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True
            ),

            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=not privada
            )
        }

        permitidos = permitidos or []

        if privada:

            for uid in permitidos:

                membro = guild.get_member(uid)

                if membro and not membro.bot:

                    overwrites[membro] = (
                        discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True,
                            speak=True
                        )
                    )

        nome_canal = (
            f"📞 {nome}"
            if nome
            else f"📞 Call de {dono.display_name}"
        )

        try:

            canal = await guild.create_voice_channel(
                name=nome_canal[:100],
                category=categoria,
                user_limit=limite,
                overwrites=overwrites,
                reason=f"Call criada por {dono}"
            )

        except (discord.Forbidden, discord.HTTPException):

            return None, False

        self.calls[canal.id] = {

            "dono": dono.id,
            "limite": limite,
            "privada": privada,

            "permitidos": list(
                set([dono.id] + permitidos)
            ),

            "ordem": [],
            "vazia_desde": time.time()

        }

        self.locks[canal.id] = asyncio.Lock()

        self.salvar()

        if dono.voice:

            try:

                await dono.move_to(canal)

            except (
                discord.Forbidden,
                discord.HTTPException
            ):

                pass

        return canal, False

    # -------------------------------------------------
    # MONITORAMENTO DE VOZ
    # -------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member,
        before,
        after
    ):

        if before.channel == after.channel:
            return

        if (
            before.channel
            and before.channel.id in self.calls
        ):

            dados = self.calls[before.channel.id]

            ordem = dados.setdefault("ordem", [])

            if member.id in ordem:
                ordem.remove(member.id)

            if not before.channel.members:
                dados["vazia_desde"] = time.time()

            self.salvar()

        if (
            after.channel
            and after.channel.id in self.calls
        ):

            dados = self.calls[after.channel.id]

            dados["vazia_desde"] = None

            ordem = dados.setdefault("ordem", [])

            if member.id in ordem:
                ordem.remove(member.id)

            ordem.append(member.id)

            self.salvar()

            await self._verificar_entrada(
                member,
                after.channel
            )

    # -------------------------------------------------
    # PROTEÇÃO E LIMITE
    # -------------------------------------------------

    async def _verificar_entrada(self, member, canal):

        dados = self.calls.get(canal.id)

        if not dados or member.bot:
            return

        lock = self.locks.setdefault(
            canal.id,
            asyncio.Lock()
        )

        async with lock:

            dados = self.calls.get(canal.id)

            if not dados:
                return

            if member.voice is None:
                return

            if member.voice.channel is None:
                return

            if member.voice.channel.id != canal.id:
                return

            # PRIVACIDADE

            if dados.get("privada", False):

                permitidos = dados.get("permitidos", [])

                if member.id not in permitidos:

                    try:

                        await member.move_to(
                            None,
                            reason="Entrada não autorizada em call privada"
                        )

                        await self._log(
                            texto=(
                                f"🔒 {member.mention} tentou entrar "
                                f"na call privada {canal.mention} "
                                "sem autorização."
                            )
                        )

                    except discord.HTTPException:

                        await self._log(
                            texto=f"⚠️ Não consegui desconectar {member.mention}."
                        )

                    return

            # LIMITE

            limite = dados.get("limite", canal.user_limit)

            if not limite:
                return

            quantidade = len(canal.members)

            if quantidade <= limite:
                return

            dono_id = dados.get("dono")

            candidatos = [
                pessoa
                for pessoa in canal.members
                if pessoa.id != dono_id
                and not pessoa.bot
            ]

            ordem = dados.setdefault("ordem", [])

            candidatos.sort(
                key=lambda pessoa: (
                    ordem.index(pessoa.id)
                    if pessoa.id in ordem
                    else -1
                ),
                reverse=True
            )

            excesso = quantidade - limite

            for pessoa in candidatos[:excesso]:

                try:

                    await pessoa.move_to(
                        None,
                        reason=f"Limite de {limite} pessoas ultrapassado"
                    )

                    if pessoa.id in ordem:
                        ordem.remove(pessoa.id)

                    await self._log(
                        texto=(
                            f"👥 {pessoa.mention} foi desconectado "
                            f"de {canal.mention} pelo limite de pessoas."
                        )
                    )

                except discord.HTTPException:

                    await self._log(
                        texto=f"⚠️ Não consegui desconectar {pessoa.mention}."
                    )

            self.salvar()

    # -------------------------------------------------
    # APAGAR CALL
    # -------------------------------------------------

    async def _apagar(self, canal):

        self.calls.pop(canal.id, None)

        self.locks.pop(canal.id, None)

        self.salvar()

        try:

            await canal.delete(
                reason="Call temporária vazia"
            )

        except (
            discord.Forbidden,
            discord.HTTPException,
            discord.NotFound
        ):

            pass

    # -------------------------------------------------
    # EXCLUSÃO MANUAL
    # -------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canal):

        if canal.id in self.calls:

            self.calls.pop(canal.id, None)

            self.locks.pop(canal.id, None)

            self.salvar()

    # -------------------------------------------------
    # LIMPEZA AUTOMÁTICA
    # -------------------------------------------------

    @tasks.loop(seconds=5)
    async def limpeza(self):

        agora = time.time()

        for cid, dados in list(self.calls.items()):

            canal = self.bot.get_channel(cid)

            if canal is None:

                self.calls.pop(cid, None)

                self.locks.pop(cid, None)

                self.salvar()

                continue

            if canal.members:

                dados["vazia_desde"] = None

                continue

            if dados.get("vazia_desde") is None:

                dados["vazia_desde"] = agora

                continue

            if (
                agora - dados["vazia_desde"]
                >= TEMPO_VAZIA_SEG
            ):

                await self._apagar(canal)

    @limpeza.before_loop
    async def antes_limpeza(self):

        await self.bot.wait_until_ready()

        for cid, dados in self.calls.items():

            canal = self.bot.get_channel(cid)

            self.locks.setdefault(
                cid,
                asyncio.Lock()
            )

            self.owner_locks.setdefault(
                dados["dono"],
                asyncio.Lock()
            )

            if canal:

                dados["ordem"] = [
                    membro.id
                    for membro in canal.members
                ]

                dados["vazia_desde"] = (
                    None if canal.members else time.time()
                )


# =====================================================
# SETUP
# =====================================================

async def setup(bot):

    await bot.add_cog(
        CallCog(bot)
    )