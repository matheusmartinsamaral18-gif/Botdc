"""
CONFIGURAÇÕES GERAIS DO BOT
Tudo que você quiser mudar (IDs, tempos, limites) fica aqui.
"""
import discord
from discord.ext import commands

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# ---------- IDs ----------
ADM_CONFIANCA = []
LOGS_CHANNEL_ID = 1567711809396277318
SOLO_DONO_CHANNEL_ID = 1567716695760703528
MEU_ID = 926223827590078504

# ---------- Anti-Nuke ----------
JANELA_RAID = 3
LIMITE_RESTAURACAO = 12
INTERVALO_AUDIT = 0.35
MAX_TENTATIVAS_AUDIT = 4

# ---------- Tickets ----------
TEMPO_ALERTA_TICKET = 30 * 60
TEMPO_FECHAMENTO_INATIVIDADE_TICKET = 3 * 60 * 60

# ---------- Backup de mensagens ----------
MSG_POR_CANAL = 20
INTERVALO_BACKUP_MSGS_MIN = 5
