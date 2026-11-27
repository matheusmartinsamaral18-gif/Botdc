"""
ARQUIVO PRINCIPAL — só liga o bot e carrega os módulos.
"""
import os
import traceback
import discord
from config import bot

EXTENSOES = [
"moderacao.controle_comandos",
"moderacao.mensagens",
"antinuke.membros",
"antinuke.canais",
"antinuke.cargos",
"antinuke.servidor",
"backup.automatico",
"backup.mensagens",
"backup.comandos",
"tickets.tarefas",
"tickets.eventos",
"tickets.comandos",
"geral.recursos",
"geral.limpar",
"calls.sistema",
"skins.sistema",
"painel.painel_dono",
]

@bot.event
async def setup_hook(): await carregar_extensoes()

async def carregar_extensoes():
for extensao in EXTENSOES:
try:
await bot.load_extension(extensao)
print(f"📦 Módulo carregado: {extensao}")
except Exception as erro:
print(f"❌ Erro carregando {extensao}: {erro}")
traceback.print_exc()

@bot.event
async def on_ready(): print(f"✅ ONLINE: {bot.user} | ANTI-NUKE + BACKUP DUPLO"); await bot.change_presence(activity=discord.Game(name="🛡️ SYSTEM PROTECTING"))

TOKEN = os.getenv("TOKEN")
if not TOKEN: raise RuntimeError("A variável de ambiente TOKEN não foi configurada.")
bot.run(TOKEN)