TOKEN = "123:abc"
ADMIN_ID = 321
LOGIN = "username"
PASSWORD = "Pa$$word"

import re
import sqlite3
import schedule
import time
from requests.auth import HTTPBasicAuth
from telegram import Bot, Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler
import requests

bot = Bot(token=TOKEN)

def init_db():
    with sqlite3.connect("subscriptions.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS subscriptions (url TEXT PRIMARY KEY, pub_date TEXT)")
        conn.commit()

init_db()

def validate_link(link):
    return re.match(r"https://toloka.to/t(\d+)", link)

def extract_pub_date(xml_data):
    start = xml_data.find("<pubDate>") + len("<pubDate>")
    end = xml_data.find("</pubDate>", start)
    return xml_data[start:end] if start > len("<pubDate>") - 1 and end != -1 else None

def add_subscription(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return
    link = update.message.text.strip()
    if validate_link(link):
        topic_id = link.split("/t")[-1]
        track_url = f"https://toloka.to/rss.php?t=1&login&topic={topic_id}&toronly=1"
        try:
            response = requests.get(track_url, auth=HTTPBasicAuth(LOGIN, PASSWORD), timeout=10)
            response.raise_for_status()
            pub_date = extract_pub_date(response.text)
            if pub_date:
                with sqlite3.connect("subscriptions.db") as conn:
                    conn.execute("INSERT OR IGNORE INTO subscriptions (url, pub_date) VALUES (?, ?)", (link, pub_date))
                    conn.commit()
                update.message.reply_text(f"Підписка додана. Остання дата оновлення: {pub_date}")
            else:
                update.message.reply_text(f"Помилка: дата оновлення (pubDate) відсутня для {link}.")
        except Exception:
            update.message.reply_text("Виникла помилка під час обробки підписки. Спробуйте пізніше.")
    else:
        update.message.reply_text("Невірний формат посилання. Спробуйте ще раз.")

def list_subscriptions(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return
    with sqlite3.connect("subscriptions.db") as conn:
        subscriptions = conn.execute("SELECT url FROM subscriptions").fetchall()
    if not subscriptions:
        update.message.reply_text("Немає активних підписок.")
        return
    keyboard = [
        [InlineKeyboardButton(sub[0], url=sub[0]), InlineKeyboardButton("Видалити", callback_data=f"remove_{sub[0]}")]
        for sub in subscriptions
    ]
    update.message.reply_text("Ваші підписки:", reply_markup=InlineKeyboardMarkup(keyboard))

def remove_subscription(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.message.chat_id != ADMIN_ID:
        return
    link = query.data.replace("remove_", "")
    with sqlite3.connect("subscriptions.db") as conn:
        conn.execute("DELETE FROM subscriptions WHERE url = ?", (link,))
        conn.commit()
    query.answer()
    query.edit_message_text("Підписка видалена.")

def check_updates():
    with sqlite3.connect("subscriptions.db") as conn:
        subscriptions = conn.execute("SELECT * FROM subscriptions").fetchall()
    for url, last_pub_date in subscriptions:
        topic_id = url.split("/t")[-1]
        track_url = f"https://toloka.to/rss.php?t=1&login&topic={topic_id}&toronly=1"
        try:
            response = requests.get(track_url, auth=HTTPBasicAuth(LOGIN, PASSWORD), timeout=10)
            response.raise_for_status()
            new_pub_date = extract_pub_date(response.text)
            if new_pub_date and new_pub_date != last_pub_date:
                bot.send_message(chat_id=ADMIN_ID, text=f"Оновлення {url}.")
                with sqlite3.connect("subscriptions.db") as conn:
                    conn.execute("UPDATE subscriptions SET pub_date = ? WHERE url = ?", (new_pub_date, url))
                    conn.commit()
        except Exception:
            pass

def handle_text(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if text == "Список":
        list_subscriptions(update, context)
    else:
        add_subscription(update, context)

def start(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return
    keyboard = ReplyKeyboardMarkup([["Список"]], resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Використовуйте кнопку для перегляду списку.", reply_markup=keyboard)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(CallbackQueryHandler(remove_subscription))

    schedule.every(1).hours.do(check_updates)

    updater.start_polling()
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
