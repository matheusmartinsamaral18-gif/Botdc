"""
SISTEMA DE CALLS TEMPORÁRIAS
- !painelcall #canal  -> envia o painel "Abrir call" no canal escolhido
- Tudo por botões (nada para digitar)
- A call é criada na MESMA categoria do canal do painel
- Dono da call tem prioridade (entra mesmo com a call cheia)
- Call cheia: quem entrar de fora (inclusive ADM) é desconectado
- 3 tentativas forçadas -> castigo (timeout) de 30 minutos
- Call vazia por 1 minuto -> é apagada
"""
import json
import os
import time
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from config import MEU_ID, LOGS_CHANNEL_ID

# ---------- Ajustes ----------
CATEGORIA_CALLS_ID = None      # None = usa a categoria do canal do painel
LIMITES = [2, 3, 4, 5, 6, 7, 8, 10, 15, 20]   # botões de limite de pessoas
MAX_INFRACOES = 3              # tentativas antes do castigo
CASTIGO_MINUTOS = 30           # tempo do castigo
TEMPO_VAZIA_SEG = 60           # call vazia por esse tempo é apagada

COR_PRINCIPAL = 0x57F287
ARQUIVO = os.path.join(os.path.dirname(__file__), "dados_calls.json")


# =====================================================
# PAINEL FIXO (o botão continua funcionando após reiniciar)
# =====================================================
class PainelView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Abrir call",
        style=discord.ButtonStyle.success,
        emoji="📞",
        custom_id="call:abrir",
    )
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Se já tem call aberta, só avisa
        existente = self.cog.call_do_dono(interaction.guild, interaction.user.id)
        if existente:
            return await interaction.response.send_message(
                f"Você já tem uma call aberta: {existente.mention}", ephemeral=True
            )

        view = CriarCallView(self.cog)
        await interaction.response.send_message(
            embed=view.embed(), view=view, ephemeral=True
        )


# =====================================================
# CRIAÇÃO DA CALL (100% botões)
# =====================================================
class BotaoTipo(discord.ui.Button):
    def __init__(self, privada: bool):
        super().__init__(
            label="Privada" if privada else "Pública",
            emoji="🔒" if privada else "🔓",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.privada = privada

    async def callback(self, interaction: discord.Interaction):
        view: CriarCallView = self.view
        view.privada = self.privada
        view.atualizar()
        await interaction.response.edit_message(embed=view.embed(), view=view)


class BotaoLimite(discord.ui.Button):
    def __init__(self, limite: int, row: int):
        super().__init__(
            label=str(limite),
            emoji="👥",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.limite = limite

    async def callback(self, interaction: discord.Interaction):
        view: CriarCallView = self.view
        view.limite = self.limite
        view.atualizar()
        await interaction.response.edit_message(embed=view.embed(), view=view)


class BotaoCriar(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Criar call",
            emoji="✅",
            style=discord.ButtonStyle.success,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        view: CriarCallView = self.view
        await interaction.response.defer()

        canal, ja_existia = await view.cog.criar_call(
            interaction, view.privada, view.limite
        )

        if canal is None:
            return await interaction.edit_original_response(
                content="❌ Não consegui criar a call. Verifique as permissões do bot.",
                embed=None,
                view=None,
            )

        if ja_existia:
            return await interaction.edit_original_response(
                content=f"Você já tem uma call aberta: {canal.mention}",
                embed=None,
                view=None,
            )

        embed = discord.Embed(
            title="✅ Call criada!",
            description=f"{canal.mention}",
            color=COR_PRINCIPAL,
        )
        embed.add_field(name="Tipo", value="🔒 Privada" if view.privada else "🔓 Pública")
        embed.add_field(name="Limite", value=f"👥 {view.limite} pessoas")
        if interaction.user.voice:
            embed.set_footer(text="Te movi para a call.")
        else:
            embed.set_footer(
                text=f"Entre nela em até {TEMPO_VAZIA_SEG}s ou ela será apagada."
            )

        nova_view = None
        if view.privada:
            embed.add_field(
                name="Convidar",
                value="Use o menu abaixo para escolher quem pode entrar.",
                inline=False,
            )
            nova_view = ConvidarView(view.cog, canal.id, interaction.user.id)

        await interaction.edit_original_response(embed=embed, view=nova_view)


class BotaoCancelar(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Cancelar",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="Cancelado.", embed=None, view=None
        )


class CriarCallView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog
        self.privada = False
        self.limite = 2

        self.botoes_tipo = [BotaoTipo(False), BotaoTipo(True)]
        self.botoes_limite = []

        for b in self.botoes_tipo:
            self.add_item(b)

        # 5 botões por linha: linhas 1 e 2
        for i, n in enumerate(LIMITES):
            b = BotaoLimite(n, row=1 + i // 5)
            self.botoes_limite.append(b)
            self.add_item(b)

        self.add_item(BotaoCriar())
        self.add_item(BotaoCancelar())
        self.atualizar()

    def atualizar(self):
        """Pinta de azul o botão escolhido."""
        for b in self.botoes_tipo:
            b.style = (
                discord.ButtonStyle.primary
                if b.privada == self.privada
                else discord.ButtonStyle.secondary
            )
        for b in self.botoes_limite:
            b.style = (
                discord.ButtonStyle.primary
                if b.limite == self.limite
                else discord.ButtonStyle.secondary
            )

    def embed(self):
        e = discord.Embed(
            title="📞 Configure sua call",
            description=(
                "Escolha o **tipo** e o **limite de pessoas** clicando nos botões.\n"
                "Depois toque em **Criar call**."
            ),
            color=COR_PRINCIPAL,
        )
        e.add_field(
            name="Tipo",
            value="🔒 Privada" if self.privada else "🔓 Pública",
            inline=True,
        )
        e.add_field(name="Limite", value=f"👥 {self.limite} pessoas", inline=True)
        return e


# =====================================================
# CONVITES (call privada) - menu de seleção, sem digitar
# =====================================================
class ConvidarView(discord.ui.View):
    def __init__(self, cog, canal_id, dono_id):
        super().__init__(timeout=600)
        self.cog = cog
        self.canal_id = canal_id
        self.dono_id = dono_id

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="👤 Convidar pessoas",
        min_values=1,
        max_values=10,
    )
    async def convidar(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.dono_id:
            return await interaction.response.send_message(
                "Só o dono da call.", ephemeral=True
            )

        canal = interaction.guild.get_channel(self.canal_id)
        dados = self.cog.calls.get(self.canal_id)
        if canal is None or dados is None:
            return await interaction.response.send_message(
                "Essa call não existe mais.", ephemeral=True
            )

        add = []
        for u in select.values:
            membro = interaction.guild.get_member(u.id)
            if membro is None or membro.bot:
                continue
            await canal.set_permissions(
                membro, view_channel=True, connect=True, speak=True
            )
            if membro.id not in dados["permitidos"]:
                dados["permitidos"].append(membro.id)
            add.append(membro.mention)

        self.cog.salvar()
        await interaction.response.send_message(
            f"✅ Liberados: {', '.join(add) if add else 'ninguém'}", ephemeral=True
        )


# =====================================================
# COG PRINCIPAL
# =====================================================
class CallCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.calls = {}  # canal_id -> dados

    # ---------- ciclo de vida ----------
    async def cog_load(self):
        self.carregar()
        self.bot.add_view(PainelView(self))
        self.limpeza.start()

    async def cog_unload(self):
        self.limpeza.cancel()

    # ---------- persistência ----------
    def carregar(self):
        try:
            with open(ARQUIVO, "r", encoding="utf-8") as f:
                bruto = json.load(f)
            self.calls = {int(k): v for k, v in bruto.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.calls = {}

    def salvar(self):
        try:
            with open(ARQUIVO, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in self.calls.items()}, f)
        except OSError as erro:
            print(f"❌ Erro salvando calls: {erro}")

    async def _log(self, texto):
        canal = self.bot.get_channel(LOGS_CHANNEL_ID)
        if canal:
            try:
                await canal.send(texto)
            except discord.HTTPException:
                pass

    def call_do_dono(self, guild, dono_id):
        for cid, d in self.calls.items():
            if d["dono"] == dono_id:
                canal = guild.get_channel(cid)
                if canal:
                    return canal
        return None

    # ---------- comando do painel ----------
    @commands.command(name="painelcall")
    async def painelcall(self, ctx, canal: discord.TextChannel = None):
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == MEU_ID):
            return await ctx.send("❌ Sem permissão.")
        if canal is None:
            return await ctx.send("Use: `!painelcall #canal`")

        embed = discord.Embed(
            title="🎙️  CENTRAL DE CALLS",
            description=(
                "Crie a sua própria sala de voz **temporária** em segundos!\n"
                "Tudo por botões, sem digitar nada.\n\n"
                "**Como funciona**\n"
                "1️⃣ Clique em **📞 Abrir call**\n"
                "2️⃣ Escolha **pública** ou **privada**\n"
                "3️⃣ Escolha o **limite de pessoas**\n"
                "4️⃣ Pronto! Sua call é criada na hora"
            ),
            color=COR_PRINCIPAL,
        )
        embed.add_field(
            name="🔓 Pública", value="Qualquer pessoa pode entrar", inline=True
        )
        embed.add_field(
            name="🔒 Privada", value="Só quem você convidar", inline=True
        )
        embed.add_field(
            name="👥 Limite", value="De 2 até 20 pessoas", inline=True
        )
        embed.add_field(
            name="👑 Prioridade",
            value="Você sempre entra na sua call, mesmo cheia",
            inline=False,
        )
        embed.add_field(
            name="⏱️ Auto-fechamento",
            value="Call vazia por 1 minuto é apagada automaticamente",
            inline=False,
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(text="Clique no botão abaixo para começar ⬇️")

        await canal.send(embed=embed, view=PainelView(self))
        await ctx.send(f"✅ Painel enviado em {canal.mention}")

    # ---------- criação da call ----------
    async def criar_call(self, interaction, privada, limite):
        """Retorna (canal, ja_existia)."""
        guild = interaction.guild
        dono = interaction.user

        existente = self.call_do_dono(guild, dono.id)
        if existente:
            return existente, True

        # Mesma categoria do canal do painel (a call fica no fim dela)
        if CATEGORIA_CALLS_ID:
            categoria = guild.get_channel(CATEGORIA_CALLS_ID)
        else:
            categoria = interaction.channel.category

        overwrites = {
            guild.me: discord.PermissionOverwrite(
                view_channel=True, connect=True, move_members=True, manage_channels=True
            ),
            # move_members permite o dono entrar mesmo com a call cheia
            dono: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True, move_members=True
            ),
        }
        if privada:
            overwrites[guild.default_role] = discord.PermissionOverwrite(connect=False)

        try:
            canal = await guild.create_voice_channel(
                name=f"📞 Call de {dono.display_name}"[:100],
                category=categoria,
                user_limit=limite,
                overwrites=overwrites,
                reason=f"Call criada por {dono}",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None, False

        self.calls[canal.id] = {
            "dono": dono.id,
            "limite": limite,
            "privada": privada,
            "permitidos": [dono.id],
            "ordem": [],
            "infracoes": {},
            "vazia_desde": time.time(),
        }
        self.salvar()

        if dono.voice:
            try:
                await dono.move_to(canal)
            except (discord.Forbidden, discord.HTTPException):
                pass

        return canal, False

    # ---------- monitoramento de voz ----------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

        # Saiu de uma call
        if before.channel and before.channel.id in self.calls:
            dados = self.calls[before.channel.id]
            if member.id in dados["ordem"]:
                dados["ordem"].remove(member.id)
            if not before.channel.members:
                dados["vazia_desde"] = time.time()  # começa a contar 1 minuto
            self.salvar()

        # Entrou numa call
        if after.channel and after.channel.id in self.calls:
            self.calls[after.channel.id]["vazia_desde"] = None  # cancela a contagem
            await self._entrou(member, after.channel)

    async def _entrou(self, member, canal):
        dados = self.calls[canal.id]
        if member.id not in dados["ordem"]:
            dados["ordem"].append(member.id)
        if member.bot:
            return

        # Dono: prioridade, remove o(s) último(s) que entrou(aram)
        if member.id == dados["dono"]:
            excesso = len(canal.members) - dados["limite"]
            if excesso > 0:
                ordem = dados["ordem"]
                candidatos = [m for m in canal.members if m.id != member.id]
                candidatos.sort(
                    key=lambda m: ordem.index(m.id) if m.id in ordem else -1,
                    reverse=True,
                )
                for m in candidatos[:excesso]:
                    try:
                        await m.move_to(None, reason="Dono da call entrou (prioridade)")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
            return

        # Outros: privada sem convite ou call cheia -> remove
        autorizado = (not dados["privada"]) or member.id in dados["permitidos"]
        cheia = len(canal.members) > dados["limite"]
        if autorizado and not cheia:
            return

        motivo = "call privada" if not autorizado else "call cheia"
        try:
            await member.move_to(None, reason=f"Entrou em {motivo}")
        except (discord.Forbidden, discord.HTTPException):
            await self._log(f"⚠️ Não consegui remover {member.mention} de {canal.mention}.")
            return

        chave = str(member.id)
        dados["infracoes"][chave] = dados["infracoes"].get(chave, 0) + 1
        n = dados["infracoes"][chave]

        if n >= MAX_INFRACOES:
            dados["infracoes"][chave] = 0
            try:
                await member.timeout(
                    timedelta(minutes=CASTIGO_MINUTOS),
                    reason=f"Forçou entrada em call ({motivo}) {MAX_INFRACOES}x",
                )
                await self._log(
                    f"🔇 {member.mention} ficou {CASTIGO_MINUTOS} min de castigo "
                    f"por forçar entrada em {canal.mention}."
                )
            except (discord.Forbidden, discord.HTTPException):
                await self._log(
                    f"⚠️ {member.mention} forçou {MAX_INFRACOES}x a entrada em "
                    f"{canal.mention}, mas não consegui aplicar o castigo "
                    f"(cargo acima do bot ou permissão de Administrador)."
                )
        self.salvar()

    async def _apagar(self, canal):
        self.calls.pop(canal.id, None)
        self.salvar()
        try:
            await canal.delete(reason="Call vazia")
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canal):
        if canal.id in self.calls:
            self.calls.pop(canal.id, None)
            self.salvar()

    # ---------- fecha calls vazias há 1 minuto ----------
    @tasks.loop(seconds=10)
    async def limpeza(self):
        agora = time.time()
        for cid, d in list(self.calls.items()):
            canal = self.bot.get_channel(cid)
            if canal is None:
                self.calls.pop(cid, None)
                self.salvar()
                continue

            if canal.members:
                d["vazia_desde"] = None
                continue

            if d.get("vazia_desde") is None:
                d["vazia_desde"] = agora
                continue

            if agora - d["vazia_desde"] >= TEMPO_VAZIA_SEG:
                await self._apagar(canal)

    @limpeza.before_loop
    async def antes_limpeza(self):
        await self.bot.wait_until_ready()
        # Depois de reiniciar, reconstrói a ordem de entrada
        for cid, d in self.calls.items():
            canal = self.bot.get_channel(cid)
            if canal:
                d["ordem"] = [m.id for m in canal.members]
                d["vazia_desde"] = None if canal.members else time.time()


async def setup(bot):
    await bot.add_cog(CallCog(bot))
