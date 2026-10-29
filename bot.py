import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"♟️ Welcome to Chess Arena!\n\n"
"Play chess with people around the world.\n\n"
"🎮 /play - Find a chess opponent\n"
"👤 /profile - Your profile\n"
"🏆 /leaderboard - Top players\n\n"
"Multiplayer chess is coming soon!"
)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"♟️ Chess matchmaking is coming soon!\n"
"We are building the multiplayer chess arena."
)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = update.effective_user
await update.message.reply_text(
f"👤 Player: {user.first_name}\n"
f"🆔 Telegram ID: {user.id}\n"
"🏆 Rating: 1000\n"
"🎮 Games played: 0"
)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"🏆 Chess Arena Leaderboard\n\n"
"The leaderboard will be available soon!"
)

def main():
if not TOKEN:
raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("play", play))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.run_polling()

if name == "main":
main()
