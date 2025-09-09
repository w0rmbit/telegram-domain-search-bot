from telebot import TeleBot
from io import BytesIO

def search_domain(bot: TeleBot, domain: str, files: list, chat_id: int):
    result = BytesIO()
    result.write(f"Search results for: {domain}\n\n".encode())

    for file_id, file_name in files:
        file_info = bot.get_file(file_id)
        content = bot.download_file(file_info.file_path).decode("utf-8", errors="ignore")
        matches = [line for line in content.splitlines() if domain in line]
        if matches:
            result.write(f"--- {file_name} ---\n".encode())
            for line in matches:
                result.write(f"{line}\n".encode())
            result.write(b"\n")

    result.seek(0)
    bot.send_document(chat_id, result, caption=f"Results for {domain}")
