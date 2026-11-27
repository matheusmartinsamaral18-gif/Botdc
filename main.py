"""
ARQUIVO PRINCIPAL — só liga o bot e carrega os módulos.
Para desativar um sistema inteiro, comente a linha dele em EXTENSOES.
"""
import os
import traceback

import discord

from config import bot

EXTENSOES = [
# Mensagens / controle de comandos
"moderacao.controle_comandos",
"moderacao.mensagens",

# Anti-Nuke
"antinuke.membros",
"antinuke.canais",
"antinuke.cargos",
"antinuke.servidor",

# Backup
"backup.automatico",
"backup.mensagens",
"backup.comandos",

# Tickets
"tickets.tarefas",
"tickets.eventos",
"tickets.comandos",

# Comandos gerais
"geral.recursos",
"geral.limpar",

# Calls
"calls.sistema",

# Skins
"skins.sistema",

# Painel do dono (depende dos outros)
"painel.painel_dono",

]

@bot.event
async def setup_hook():
for extensao in EXTENSOES:
try:
await bot.load_extension(extensao)
print(f"📦 Módulo carregado: {extensao}")
except Exception as erro:
print(f"❌ Erro carregando {extensao}: {erro}")
traceback.print_exc()

@bot.event
async def on_ready():
print(f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP DUPLO")

await bot.change_presence(
    activity=discord.Game(name="🛡️ SYSTEM PROTECTING")
)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
raise RuntimeError(
"A variável de ambiente TOKEN não foi configurada."
)

bot.run(TOKEN)