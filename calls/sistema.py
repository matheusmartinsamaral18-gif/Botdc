
"""
SISTEMA DE CALLS TEMPORÁRIAS

- !painelcall #canal -> envia o painel de criação
- Configuração completa antes de criar a call
- Pública ou privada
- Seleção de limite de pessoas
- Nome personalizado opcional
- Seleção antecipada de pessoas autorizadas
- Call privada: somente pessoas autorizadas podem entrar
- Call pública: entrada livre, respeitando o limite
- ADM também é removido se ultrapassar o limite
- Dono possui prioridade na própria call
- Sem mute, retirada de cargos ou punições
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

LINHA = "━━━━━━━━━━━━━━━━━━━━━━"

ARQUIVO = os.path.join(
    os.path.dirname(__file__),
    "dados_calls.json"
)


# =====================================================
# PAINEL FIXO
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
# MODAL PARA NOME
# =====================================================

class NomeModal(discord.ui.Modal, title="Personalizar sua call"):

    nome = discord.ui.TextInput(
        label="Nome da call",
        placeholder="Digite o nome que deseja utilizar",
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
# BOTÕES DE TIPO
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
            label="Personalizar nome",
            emoji="✏️",
            style=discord.ButtonStyle.secondary,
            row=0
        )

    async def callback(self, interaction):

        await interaction.response.send_modal(
            NomeModal(self.view)
        )


# =====================================================
# BOTÕES DE LIMITE
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
# BOTÃO CRIAR
# =====================================================

class BotaoCriar(discord.ui.Button):

    def __init__(self):

        super().__init__(
            label="Criar minha call",
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
                content=(
                    "❌ Não consegui criar sua call.\n"
                    "Verifique as permissões do bot."
                ),
                embed=None,
                view=None
            )

        if ja_existia:

            return await interaction.edit_original_response(
                content=f"⚠️ Você já possui uma call aberta: {canal.mention}",
                embed=None,
                view=None
            )

        embed = discord.Embed(
            title="✅ Sua call foi criada!",
            description=(
                f"🎙️ **Sala:** {canal.mention}\n"
                f"👤 **Criada por:** {interaction.user.mention}\n"
                f"{LINHA}"
            ),
            color=COR_PRINCIPAL
        )

        embed.add_field(
            name="🔐 Tipo",
            value="Privada" if view.privada else "Pública",
            inline=True
        )

        embed.add_field(
            name="👥 Capacidade",
            value=f"{view.limite} pessoas",
            inline=True
        )

        embed.add_field(
            name="✏️ Nome",
            value=canal.name,
            inline=False
        )

        if view.privada:

            convidados = [
                interaction.guild.get_member(uid)
                for uid in view.permitidos
                if uid != interaction.user.id
            ]

            convidados = [
                membro for membro in convidados
                if membro is not None
            ]

            lista = (
                ", ".join(m.mention for m in convidados)
                if convidados
                else "Nenhuma pessoa adicional liberada."
            )

            embed.add_field(
                name="🔑 Pessoas autorizadas",
                value=lista,
                inline=False
            )

            embed.set_footer(
                text="Somente você e as pessoas autorizadas podem entrar."
            )

        else:

            embed.set_footer(
                text="Call pública. Todos podem entrar enquanto houver vagas."
            )

        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=None
        )


# =====================================================
# BOTÃO CANCELAR
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
            content="❌ Criação da call cancelada.",
            embed=None,
            view=None
        )


# =====================================================
# LIMPAR PESSOAS SELECIONADAS
# =====================================================

class BotaoLimpar(discord.ui.Button):

    def __init__(self):

        super().__init__(
            label="Limpar convidados",
            emoji="🧹",
            style=discord.ButtonStyle.secondary,
            row=4
        )

    async def callback(self, interaction):

        view = self.view

        view.permitidos = []
        view.nomes_permitidos = []

        view.atualizar()

        await interaction.response.edit_message(
            embed=view.embed(),
            view=view
        )


# =====================================================
# CONFIGURAÇÃO COMPLETA DA CALL
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
        placeholder="🔑 Selecione quem poderá entrar na call privada",
        min_values=1,
        max_values=MAX_CONVIDADOS,
        row=3
    )
    async def selecionar_permitidos(self, interaction, select):

        selecionados = []
        nomes = []

        for usuario in select.values:

            membro = interaction.guild.get_member(usuario.id)

            if membro is None or membro.bot:
                continue

            if membro.id == interaction.user.id:
                continue

            if membro.id not in selecionados:
                selecionados.append(membro.id)
                nomes.append(membro.display_name)

        self.permitidos = selecionados
        self.nomes_permitidos = nomes

        self.atualizar()

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
            title="📞 CONFIGURE SUA CALL",
            description=(
                "Personalize sua sala antes de criá-la!\n"
                "Todas as opções estão disponíveis nesta tela.\n\n"
                f"{LINHA}\n"
                "**1️⃣ ESCOLHA O TIPO DE CALL**\n\n"
                "🌎 **Pública:** qualquer pessoa pode entrar.\n"
                "🔒 **Privada:** somente você e as pessoas "
                "que você liberar poderão entrar.\n\n"
                "**2️⃣ DEFINA A CAPACIDADE**\n\n"
                "👥 Escolha quantas pessoas poderão ficar na sala.\n\n"
                "**3️⃣ PERSONALIZE O NOME**\n\n"
                "✏️ Você pode colocar qualquer nome ou deixar "
                "o nome padrão.\n\n"
                "**4️⃣ LIBERE QUEM PODERÁ ENTRAR**\n\n"
                "🔑 Use o seletor abaixo para escolher as pessoas "
                "autorizadas a entrar na sua call privada.\n"
                "Essa opção só funciona quando a call é privada.\n\n"
                f"{LINHA}"
            ),
            color=COR_PRINCIPAL
        )

        e.add_field(
            name="🔐 Tipo selecionado",
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

        if self.permitidos:

            lista = "\n".join(
                f"• {nome}"
                for nome in self.nomes_permitidos
            )

        else:

            lista = "Nenhuma pessoa adicional selecionada."

        e.add_field(
            name=f"🔑 Pessoas liberadas ({len(self.permitidos)})",
            value=lista[:1024],
            inline=False
        )

        if self.privada:

            e.add_field(
                name="🛡️ Proteção ativada",
                value=(
                    "Pessoas não autorizadas serão removidas "
                    "da call automaticamente.\n"
                    "Não haverá mute nem retirada de cargos."
                ),
                inline=False
            )

        else:

            e.add_field(
                name="🌎 Call pública",
                value=(
                    "Todos poderão entrar enquanto houver vagas. "
                    "Se alguém ultrapassar o limite, será desconectado, "
                    "inclusive administradores."
                ),
                inline=False
            )

        e.set_footer(
            text="Confira suas escolhas e clique em Criar minha call."
        )

        return e


# =====================================================
# COG PRINCIPAL
# =====================================================

class CallCog(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.calls = {}

        # Evita processamentos simultâneos de entrada
        # no mesmo canal de voz.
        self.locks = {}

    # -------------------------------------------------
    # CICLO DE VIDA
    # -------------------------------------------------

    async def cog_load(self):

        self.carregar()

        self.bot.add_view(PainelView(self))

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

        # Compatibilidade com o arquivo antigo.
        for dados in self.calls.values():

            dados.setdefault("ordem", [])
            dados.setdefault("permitidos", [])

            dados.setdefault(
                "vazia_desde",
                time.time()
            )

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

        for cid, dados in self.calls.items():

            if dados["dono"] == dono_id:

                canal = guild.get_channel(cid)

                if canal:
                    return canal

        return None

    # -------------------------------------------------
    # COMANDO DO PAINEL
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
            title="🎙️ CENTRAL DE CALLS",
            description=(
                "Crie sua própria sala de voz temporária!\n\n"
                "Basta clicar no botão **Abrir call** e configurar "
                "tudo antes de criar sua sala.\n\n"
                f"{LINHA}\n"
                "**📋 COMO FUNCIONA?**\n\n"
                "🌎 **Call pública**\n"
                "Todos podem entrar enquanto houver vagas. "
                "O bot também controla o limite para administradores.\n\n"
                "🔒 **Call privada**\n"
                "Somente você e as pessoas que você autorizar "
                "poderão entrar.\n\n"
                "👥 **Limite de pessoas**\n"
                "Escolha a capacidade da sua sala. "
                "O limite será respeitado mesmo para administradores.\n\n"
                "✏️ **Nome personalizado**\n"
                "Escolha o nome que quiser ou utilize o padrão.\n\n"
                "🔑 **Liberar pessoas**\n"
                "Na configuração inicial, você poderá selecionar "
                "quem terá autorização para entrar na sua call privada.\n\n"
                f"{LINHA}\n"
                "**🛡️ PROTEÇÃO**\n\n"
                "Nas calls privadas, quem não estiver autorizado "
                "será desconectado.\n"
                "Nas calls cheias, quem ultrapassar a capacidade "
                "também será desconectado.\n\n"
                "Não existe punição, mute ou retirada de cargos.\n\n"
                "**⏱️ ENCERRAMENTO AUTOMÁTICO**\n\n"
                f"Se a call ficar vazia por {TEMPO_VAZIA_SEG} segundos, "
                "ela será apagada automaticamente."
            ),
            color=COR_PRINCIPAL
        )

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.set_footer(
            text="📞 Clique abaixo para configurar e criar sua call!"
        )

        await canal.send(
            embed=embed,
            view=PainelView(self)
        )

        await ctx.send(
            f"✅ Painel de calls enviado em {canal.mention}!"
        )

    # -------------------------------------------------
    # CRIAÇÃO DA CALL
    # -------------------------------------------------

    async def criar_call(
        self,
        interaction,
        privada,
        limite,
        nome=None,
        permitidos=None
    ):

        guild = interaction.guild
        dono = interaction.user

        existente = self.call_do_dono(
            guild,
            dono.id
        )

        if existente:
            return existente, True

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
            )
        }

        permitidos = permitidos or []

        if privada:

            overwrites[guild.default_role] = (
                discord.PermissionOverwrite(
                    connect=False
                )
            )

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

        # Saiu de uma call temporária.

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

        # Entrou em uma call temporária.

        if (
            after.channel
            and after.channel.id in self.calls
        ):

            dados = self.calls[after.channel.id]

            dados["vazia_desde"] = None

            ordem = dados.setdefault("ordem", [])

            # Registra a ordem de entrada.
            if member.id in ordem:
                ordem.remove(member.id)

            ordem.append(member.id)

            self.salvar()

            await self._verificar_entrada(
                member,
                after.channel
            )

    # -------------------------------------------------
    # PROTEÇÃO E CONTROLE DE LIMITE
    # -------------------------------------------------

    async def _verificar_entrada(self, member, canal):

        dados = self.calls.get(canal.id)

        if not dados:
            return

        if member.bot:
            return

        lock = self.locks.setdefault(
            canal.id,
            asyncio.Lock()
        )

        async with lock:

            # Confirma que a call ainda existe.
            dados = self.calls.get(canal.id)

            if not dados:
                return

            # Confirma que a pessoa ainda está na call.
            if member.voice is None:
                return

            if member.voice.channel is None:
                return

            if member.voice.channel.id != canal.id:
                return

            # -----------------------------------------
            # 1. VERIFICAR PRIVACIDADE
            # -----------------------------------------

            if dados.get("privada", False):

                permitidos = dados.get("permitidos", [])

                if member.id not in permitidos:

                    try:

                        await member.move_to(
                            None,
                            reason=(
                                "Entrada em call privada "
                                "sem autorização"
                            )
                        )

                        await self._log(
                            texto=(
                                f"🔒 {member.mention} tentou entrar "
                                f"na call privada {canal.mention} "
                                "sem autorização e foi desconectado."
                            )
                        )

                    except (
                        discord.Forbidden,
                        discord.HTTPException
                    ):

                        await self._log(
                            texto=(
                                f"⚠️ Não consegui desconectar "
                                f"{member.mention} da call privada "
                                f"{canal.mention}. Verifique as permissões."
                            )
                        )

                    return

            # -----------------------------------------
            # 2. VERIFICAR LIMITE DE PESSOAS
            # -----------------------------------------

            limite = dados.get("limite", canal.user_limit)

            if not limite:
                return

            quantidade = len(canal.members)

            if quantidade <= limite:
                return

            # O dono tem prioridade.
            dono_id = dados.get("dono")

            candidatos = [
                pessoa
                for pessoa in canal.members
                if pessoa.id != dono_id
            ]

            if not candidatos:
                return

            # Identifica quem entrou por último.
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

            removidos = []

            # Remove os últimos participantes até
            # que a capacidade seja respeitada.
            for pessoa in candidatos:

                if len(removidos) >= excesso:
                    break

                try:

                    await pessoa.move_to(
                        None,
                        reason=(
                            f"Limite de {limite} pessoas "
                            "da call temporária ultrapassado"
                        )
                    )

                    removidos.append(pessoa)

                    if pessoa.id in ordem:
                        ordem.remove(pessoa.id)

                    await self._log(
                        texto=(
                            f"👥 {pessoa.mention} foi desconectado "
                            f"de {canal.mention} porque a call "
                            f"ultrapassou o limite de {limite} pessoas."
                        )
                    )

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):

                    await self._log(
                        texto=(
                            f"⚠️ Não consegui desconectar "
                            f"{pessoa.mention} de {canal.mention}. "
                            "Verifique as permissões e a hierarquia "
                            "do bot."
                        )
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
    # DETECTAR EXCLUSÃO MANUAL
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

        # Reconstruir estado das calls após reiniciar.

        for cid, dados in self.calls.items():

            canal = self.bot.get_channel(cid)

            self.locks.setdefault(
                cid,
                asyncio.Lock()
            )

            if canal:

                # Recupera os participantes atuais.
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
