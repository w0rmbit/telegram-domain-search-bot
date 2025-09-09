import os
import telebot
from flask import Flask
import threading

# =========================
# Variables d'environnement
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Exemple: -1001234567890

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# Gestion des documents
# =========================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        # Vérifie si c'est bien un .txt
        if not message.document.file_name.endswith(".txt"):
            bot.send_message(chat_id=CHANNEL_ID, text="⚠️ Seuls les fichiers .txt sont acceptés.")
            return

        # Récupération du fichier
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = message.document.file_name

        # Sauvegarde locale
        with open(file_name, "wb") as f:
            f.write(downloaded_file)

        print(f"✅ Saved file: {file_name}")

        # Confirmation dans le channel
        bot.send_message(chat_id=CHANNEL_ID, text=f"✅ Fichier reçu et enregistré : {file_name}")

    except Exception as e:
        print(f"[ERROR] {e}")
        bot.send_message(chat_id=CHANNEL_ID, text=f"❌ Erreur lors de l'enregistrement: {e}")


# =========================
# Gestion des messages texte
# =========================
@bot.message_handler(func=lambda m: m.text and m.text.lower() == "ping")
def handle_ping(message):
    bot.reply_to(message, "pong 🏓")


# =========================
# Flask Healthcheck pour Koyeb
# =========================
app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# =========================
# Main
# =========================
if __name__ == "__main__":
    print("🤖 Bot started and listening...")

    # Lancer Flask dans un thread
    threading.Thread(target=run_flask).start()

    # Lancer le bot en mode polling
    bot.polling(none_stop=True)
