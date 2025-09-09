from flask import Flask
import telebot
from config import BOT_TOKEN
from db import init_db, save_file, get_all_files
from search import search_domain

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

init_db()

@bot.channel_post_handler(content_types=['document'])
def handle_channel_file(message):
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size
    save_file(file_id, file_name, file_size)
    print(f"Saved file: {file_name}")

@bot.message_handler(commands=['search'])
def handle_search(message):
    domain = message.text.split(maxsplit=1)[-1].strip()
    files = get_all_files()
    if not files:
        bot.send_message(message.chat.id, "No files available.")
        return
    search_domain(bot, domain, files, message.chat.id)

@app.route('/')
def health():
    return "Bot is running."

if __name__ == "__main__":
    bot.polling()
