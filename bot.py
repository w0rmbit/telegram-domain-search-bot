import os
import re
import threading
import requests
import psycopg2
import telebot
from flask import Flask

# =========================
# Environment
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "8080"))
GOFILE_TOKEN = os.getenv("GOFILE_TOKEN")  # optional

MAX_TG_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
API_URL = "https://api.gofile.io"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# Database
# =========================
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id SERIAL PRIMARY KEY,
        file_name TEXT,
        file_size BIGINT,
        source TEXT,
        source_ref TEXT,
        uploaded_at TIMESTAMP DEFAULT NOW()
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS domains (
        id SERIAL PRIMARY KEY,
        domain TEXT UNIQUE,
        source_file TEXT,
        indexed_at TIMESTAMP DEFAULT NOW()
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_domains_domain ON domains (domain)")
print("✅ Connected to PostgreSQL and ensured tables exist.")

# =========================
# Domain indexing
# =========================
DOMAIN_REGEX = re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b')

def index_domains_from_file(file_path: str):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        domains = {d.lower() for d in DOMAIN_REGEX.findall(content)}
        print(f"🔍 Found {len(domains)} domains in {file_path}")
        for d in domains:
            try:
                cur.execute(
                    "INSERT INTO domains (domain, source_file) VALUES (%s, %s) ON CONFLICT (domain) DO NOTHING",
                    (d, os.path.basename(file_path))
                )
            except Exception as ie:
                print(f"[DB INSERT ERROR] {ie}")
        print(f"✅ Indexed {len(domains)} domains from {file_path}")
    except Exception as e:
        print(f"[INDEX ERROR] {e}")

# =========================
# GoFile helpers
# =========================
def gofile_get_content(content_id: str):
    try:
        params = {"contentId": content_id}
        if GOFILE_TOKEN:
            params["token"] = GOFILE_TOKEN
        r = requests.get(f"{API_URL}/getContent", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "ok":
            return data["data"]
        raise RuntimeError(f"GoFile API error: {data}")
    except requests.exceptions.HTTPError:
        raise RuntimeError("Dossier GoFile introuvable ou supprimé.")

def download_stream_to_file(url: str, dest_path: str) -> int:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        size = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
        return size

def handle_gofile_folder(content_id: str, chat_id: int):
    try:
        data = gofile_get_content(content_id)
        contents = data.get("contents", {})
        if not contents:
            bot.send_message(chat_id, "❌ Aucun contenu trouvé dans ce dossier GoFile.")
            return

        for _, item in contents.items():
            typ = item.get("type")
            name = item.get("name", "file")
            if typ == "file" and name.endswith(".txt"):
                link = item.get("link")
                local_name = name
                try:
                    size = download_stream_to_file(link, local_name)
                    cur.execute(
                        "INSERT INTO files (file_name, file_size, source, source_ref) VALUES (%s, %s, %s, %s)",
                        (local_name, size, "gofile", content_id)
                    )
                    index_domains_from_file(local_name)
                    bot.send_message(chat_id, f"✅ Téléchargé et indexé: <code>{local_name}</code> ({size//1024} KB)")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ Erreur sur le fichier <code>{local_name}</code>: {e}")
            elif typ == "folder":
                sub_code = item.get("code")
                if sub_code:
                    handle_gofile_folder(sub_code, chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Erreur GoFile: {e}")

# =========================
# Telegram handlers
# =========================
@bot.message_handler(commands=["start", "help"])
def handle_help(message):
    help_text = (
        "👋 Bot d'indexation de domaines\n\n"
        "- Envoyez un fichier .txt (max 50 MB) pour indexation.\n"
        "- Ou envoyez un lien GoFile de dossier: https://gofile.io/d/XXXXXX\n"
        "- Ou un lien direct GoFile: https://storeX.gofile.io/...txt\n"
        "- Cherchez avec: /search motcle\n"
        "- Test: ping"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "ping")
def handle_ping(message):
    bot.reply_to(message, "pong 🏓")

@bot.message_handler(commands=["search"])
def search_domain(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "❌ Utilisation: /search exemple.com")
        return
    term = parts[1].strip().lower()
    try:
        cur.execute("SELECT domain FROM domains WHERE domain LIKE %s LIMIT 1000", (f"%{term}%",))
        rows = cur.fetchall()
        if not rows:
            bot.reply_to(message, "❌ Aucun domaine trouvé.")
            return
        with open("result.txt", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(r[0] + "\n")
        with open("result.txt", "rb") as f:
            bot.send_document(message.chat.id, f, caption=f"🔎 {len(rows)} domaines trouvés pour '{term}'")
    except Exception as e:
        bot.reply_to(message, f"❌ Erreur de recherche: {e}")

@bot.message_handler(regexp=r'^https?://gofile\.io/d/[^ \n\t]+')
def handle_gofile_link(message):
    link = message.text.strip()
    content_id = link.split("/d/")[-1].split("/")[0]
    bot.send_message(message.chat.id, "⏳ Traitement du dossier GoFile...")
    handle_gofile_folder(content_id, message.chat.id)

@bot.message_handler(regexp=r'^https?://store\d+\.gofile\.io/download/')
def handle_direct_gofile_download(message):
    url = message.text.strip()
    file_name = url.split("/")[-1].split("?")[0] or "downloaded.txt"
    bot.send_message(message.chat.id, f"⏳ Téléchargement du fichier GoFile : <code>{file_name}</code>")
    try:
        size = download_stream_to_file(url, file_name)
        cur.execute(
            "INSERT INTO files (file_name, file_size, source, source_ref) VALUES (%s, %s, %s, %s)",
            (file_name, size, "gofile-direct", url)
        )
        index_domains_from_file(file_name)
        bot.send_message(message.chat.id, f"✅ Fichier téléchargé et indexé : <code>{file_name}</code> ({size//1024} KB)")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Erreur lors du téléchargement : {e}")

@bot.message_handler(content_types=["document"])
def handle_document(message):
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        bot.send_message(message.chat.id, "⚠️ Seuls les fichiers .txt sont acceptés.")
        return
    if doc.file_size and doc.file_size > MAX_TG_FILE_SIZE:
        bot.send_message(
            message.chat.id,
            "❌ Fichier trop volumineux (50 MB maximum). Uploadez sur GoFile et envoyez le lien du dossier."
        )
        return
    try:
        file_info = bot.get_file(doc.file_id)
        file_bytes = bot.download_file(file_info.file_path)
        local_name = doc.file_name
        with open(local_name, "wb") as f:
            f.write(file_bytes)
        cur.execute(
            "INSERT INTO files (file_name, file_size, source, source_ref) VALUES (%s, %s, %s, %s)",
            (local_name, doc.file_size or 0, "telegram", str(message.chat.id))
        )
        index_domains_from_file(local_name)
        bot.send_message(CHANNEL_ID, f"✅ Fichier reçu et indexé: <code>{local_name}</code>")
    except Exception as e:
        bot.send_message(CHANNEL_ID, f"❌ Erreur lors du traitement: {e}")

# =========================
# Flask healthcheck
# =========================
app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# =========================
# Main
# =========================
if __name__ == "__main__":
    print("🤖 Bot started and listening...")
    threading.Thread(target=run_flask, daemon=True).start()
    bot.polling(none_stop=True, timeout=60, interval=0)
