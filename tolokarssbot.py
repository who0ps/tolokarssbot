TOKEN = "123:abc"
ADMIN_ID = 321
LOGIN = "username"
PASSWORD = "Pa$$word"

import re
import requests
import sqlite3
import schedule
import time
from requests.auth import HTTPBasicAuth
from telegram import Bot, Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler

bot = Bot(token=TOKEN)

def init_db():
    conn = sqlite3.connect("subscriptions.db")
    conn.execute("CREATE TABLE IF NOT EXISTS subscriptions (url TEXT PRIMARY KEY, pub_date TEXT)")
    conn.commit()
    conn.close()

init_db()

def validate_link(link):
    match = re.match(r"https://toloka.to/t(\d+)", link)
    return match.group(0) if match else None

def add_subscription(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return

    link = update.message.text.strip()
    if validate_link(link):
        conn = sqlite3.connect("subscriptions.db")
        conn.execute("INSERT OR IGNORE INTO subscriptions (url, pub_date) VALUES (?, '')", (link,))
        conn.commit()
        conn.close()
        update.message.reply_text("Підписка додана.")
    else:
        update.message.reply_text("Невірний формат посилання. Спробуйте ще раз.")

def list_subscriptions(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return

    conn = sqlite3.connect("subscriptions.db")
    subscriptions = conn.execute("SELECT url FROM subscriptions").fetchall()
    conn.close()

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
    conn = sqlite3.connect("subscriptions.db")
    conn.execute("DELETE FROM subscriptions WHERE url = ?", (link,))
    conn.commit()
    conn.close()
    query.answer()
    query.edit_message_text("Підписка видалена.")

def check_updates():
    conn = sqlite3.connect("subscriptions.db")
    subscriptions = conn.execute("SELECT * FROM subscriptions").fetchall()
    conn.close()

    for url, last_pub_date in subscriptions:
        topic_id = url.split("/t")[-1]
        track_url = f"https://toloka.to/rss.php?t=1&login&topic={topic_id}&toronly=1"

        try:
            session = requests.Session()
            response = requests.get(track_url, auth=(LOGIN, PASSWORD), timeout=10)
            response.raise_for_status()
            new_pub_date = extract_pub_date(response.text)

            if new_pub_date != last_pub_date:
                bot.send_message(chat_id=ADMIN_ID, text=f"Оновлення {url}.")
                conn = sqlite3.connect("subscriptions.db")
                conn.execute("UPDATE subscriptions SET pub_date = ? WHERE url = ?", (new_pub_date, url))
                conn.commit()
                conn.close()

        except requests.exceptions.RequestException:
            time.sleep(300)

def extract_pub_date(xml_data):
    start = xml_data.find("<pubDate>") + len("<pubDate>")
    return xml_data[start:xml_data.find("</pubDate>")]

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

keyboard = ReplyKeyboardMarkup([["Список"]], resize_keyboard=True, one_time_keyboard=False)

def start(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return

    update.message.reply_text("Використовуйте кнопку для перегляду списку.", reply_markup=keyboard)

def handle_text(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if text == "Список":
        list_subscriptions(update, context)
    else:
        add_subscription(update, context)

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("list", list_subscriptions))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
dp.add_handler(CallbackQueryHandler(remove_subscription))

updater.start_polling()
check_updates()
schedule.every(1).hours.do(check_updates)

while True:
    schedule.run_pending()
    time.sleep(60)
  
