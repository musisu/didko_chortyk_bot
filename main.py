#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
from random import shuffle, choice
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackQueryHandler
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GUESSING, CHOOSING_PLAYER = range(2)

# ---------- WORDS ----------
WORDS = []
with open("words.txt", "r", encoding="utf-8") as f:
    WORDS = [w.strip().lower() for w in f.readlines()]
shuffle(WORDS)

# ---------- DAILY STATS ----------
STATS_FILE = "daily_stats.json"

def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"date": datetime.now().strftime("%Y-%m-%d"), "messages": {}}
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def check_new_day(data):
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("date") != today:
        # Новий день → скидаємо лічильники
        data = {"date": today, "messages": {}}
    return data

def count_message(update):
    user = update.effective_user
    data = load_stats()
    data = check_new_day(data)
    uid = str(user.id)
    if uid not in data["messages"]:
        data["messages"][uid] = {"name": user.first_name, "count": 0}
    data["messages"][uid]["count"] += 1
    save_stats(data)

def show_top(update, context):
    data = load_stats()
    users = sorted(
        data["messages"].values(),
        key=lambda x: x["count"],
        reverse=True
    )
    if not users:
        update.message.reply_text("Сьогодні ще ніхто нічого не писав 🙂")
        return
    text = "🏆 Топ активності за сьогодні:\n\n"
    for i, u in enumerate(users[:10], 1):
        text += f"{i}. {u['name']} — {u['count']} повідомлень\n"
    update.message.reply_text(text)

# ---------- GAME ----------
def start(update, context):
    if context.chat_data.get("is_playing"):
        update.message.reply_text("Гра вже почалась")
        return GUESSING

    user = update.message.from_user
    context.chat_data["is_playing"] = True
    context.chat_data["current_player"] = user.id
    context.chat_data["current_word"] = choice(WORDS)

    keyboard = [[
        InlineKeyboardButton("Подивитись слово", callback_data="look"),
        InlineKeyboardButton("Наступне слово", callback_data="next")
    ]]

    update.message.reply_text(
        f"[{user.first_name}](tg://user?id={user.id}) пояснює слово!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return GUESSING


def stop(update, context):
    context.chat_data.clear()
    update.message.reply_text("Гру зупинено")
    return ConversationHandler.END


def guesser(update, context):
    text = update.message.text.lower()
    user = update.message.from_user

    # 🔥 РЕАКЦІЯ НА "ГЕТЕРО", "МАЛЬВИ", "КІШПАРИ"
    if "гетеро" in text:
        update.message.reply_text("🍽️")
        return GUESSING
    if "мальви" in text:
        update.message.reply_text("👀")
        return GUESSING
    if "кішпари" in text:
        update.message.reply_text("🍽️")
        return GUESSING

    # Основна логіка гри
    if (
        context.chat_data.get("is_playing")
        and user.id != context.chat_data.get("current_player")
        and text == context.chat_data.get("current_word")
    ):
        update.message.reply_text(f"{user.first_name} вгадав слово!")
        context.chat_data["winner"] = user.id
        context.chat_data["win_time"] = datetime.now()
        return CHOOSING_PLAYER

    return GUESSING


def next_player(update, context):
    query = update.callback_query
    query.answer()
    user = query.from_user
    context.chat_data["current_player"] = user.id
    context.chat_data["current_word"] = choice(WORDS)

    keyboard = [[
        InlineKeyboardButton("Подивитись слово", callback_data="look"),
        InlineKeyboardButton("Наступне слово", callback_data="next")
    ]]

    query.edit_message_text(
        f"[{user.first_name}](tg://user?id={user.id}) пояснює слово!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return GUESSING


def see_word(update, context):
    query = update.callback_query
    if query.from_user.id == context.chat_data.get("current_player"):
        query.answer(context.chat_data.get("current_word"), show_alert=True)
    else:
        query.answer("Не можна 👀", show_alert=True)
    return GUESSING


def next_word(update, context):
    query = update.callback_query
    if query.from_user.id == context.chat_data.get("current_player"):
        context.chat_data["current_word"] = choice(WORDS)
        query.answer(context.chat_data["current_word"], show_alert=True)
    else:
        query.answer("Не можна", show_alert=True)
    return GUESSING


# ---------- GLOBAL TEXT HANDLER ----------
def global_text(update, context):
    text = update.message.text.lower()

    # 🔥 Підрахунок повідомлень
    count_message(update)

    # 🔥 Ключові слова
    if "гетеро" in text:
        update.message.reply_text("🍽️")
    if "мальви" in text:
        update.message.reply_text("👀")
    if "кішпари" in text:
        update.message.reply_text("🍽️")


# ---------- MAIN ----------
def main():
    token = os.environ["TOKEN"]
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    # Обробник тексту (топ + ключові слова)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, global_text))

    # Conversation handler для гри
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GUESSING: [
                MessageHandler(Filters.text & ~Filters.command, guesser),
                CallbackQueryHandler(see_word, pattern="^look$"),
                CallbackQueryHandler(next_word, pattern="^next$")
            ],
            CHOOSING_PLAYER: [
                CallbackQueryHandler(next_player)
            ],
        },
        fallbacks=[CommandHandler("stop", stop)],
        per_user=False
    )

    dp.add_handler(conv)
    dp.add_handler(CommandHandler("top", show_top))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
