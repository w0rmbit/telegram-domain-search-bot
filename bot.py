import os
import telebot
from flask import Flask
import threading
import psycopg2

# =========================
# Variables d'environnement
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Exemple: -1001234567890
DATABASE_URL = os.getenv("DATABASE_URL")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# Connexion PostgreSQL
# =========================
try:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            file_name TEXT,
            file_size BIGINT,
            uploaded_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Connected to PostgreSQL and ensured table exists.")
except Exception as e:
    print(f"[DB ERROR] {e}")
    conn = None

# =========================
# Gestion des documents
# =========================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        doc = message.document

        # Vérifie si c'est bien un .txt
        if not doc.file_name.endswith(".txt"):
            bot.send_message(chat_id=message.chat.id, text="⚠️ Seuls les fichiers .txt sont acceptés.")
            return

        # Vérifie la taille
        if doc.file_size > MAX_FILE_SIZE:
            bot.send_message(chat_id=message.chat.id,
                             text=f"❌ Fichier trop volumineux ({doc.file_size / (1024*1024):.2f} MB). "
                                  "Limite : 50 MB. Merci de le découper ou d'envoyer un lien.")
            return

        # Récupération du fichier
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = doc.file_name

        # Sauvegarde locale (éphémère sur Koyeb)
        with open(file_name, "wb") as f:
            f.write(downloaded_file)

        print(f"✅ Saved file: {file_name}")

        # Enregistrement en base
        if conn:
            cur.execute("INSERT INTO files (file_name, file_size) VALUES (%s, %s)",
                        (file_name, doc.file_size))

        # Confirmation
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
    threading.Thread(target=run_flask).start()
    bot.polling(none_stop=True)
