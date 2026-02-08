#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from random import shuffle, choice
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackQueryHandler
)
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GUESSING, CHOOSING_PLAYER = range(2)
MONETES = {}  # Єдиний рахунок між чатами
daily_messages = {}  # Повідомлення за день у кожному чаті

# ---------- WORDS ----------
WORDS = []
with open("words.txt", "r", encoding="utf-8") as f:
    WORDS = [w.strip().lower() for w in f.readlines()]
shuffle(WORDS)

GROUP_ID = 5214033440  # Група, де нараховуємо 50 монет за #

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

    # 🔥 Реакція на ключові слова
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
        # Додаємо монети за вгадане слово
        MONETES[user.id] = MONETES.get(user.id, 0) + 5

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
    user = update.message.from_user
    chat_id = update.message.chat.id  # Виправлено!
    text = update.message.text.lower()

    # 🔥 Реакція на ключові слова
    if "гетеро" in text:
        update.message.reply_text("🍽️")
    if "мальви" in text:
        update.message.reply_text("👀")
    if "кішпари" in text:
        update.message.reply_text("🍽️")

    # 🔥 Тільки для конкретного чату: # нарахування 50 монет
    if chat_id == GROUP_ID and "#" in text:
        MONETES[user.id] = MONETES.get(user.id, 0) + 50

    # Рахуємо повідомлення для щоденного топу
    daily_messages.setdefault(chat_id, {})
    daily_messages[chat_id][user.id] = daily_messages[chat_id].get(user.id, 0) + 1

# ---------- TOP / WALLET ----------
def top(update, context):
    chat_id = update.message.chat.id  # Виправлено!
    if chat_id not in daily_messages or not daily_messages[chat_id]:
        update.message.reply_text("Ще немає повідомлень для топу сьогодні.")
        return

    sorted_users = sorted(daily_messages[chat_id].items(), key=lambda x: x[1], reverse=True)
    text = "Поточний топ за день:\n"
    for i, (user_id, count) in enumerate(sorted_users[:3]):
        try:
            user = context.bot.get_chat_member(chat_id, user_id).user
            username = user.first_name if user.first_name else "Unknown"
        except:
            username = "Unknown"
        text += f"{i+1}. {username}: {count} повідомлень\n"
    update.message.reply_text(text)

def wallet(update, context):
    user_id = update.message.from_user.id
    balance = MONETES.get(user_id, 0)
    update.message.reply_text(f"Твій баланс: {balance} монет")

# ---------- DAILY RESET ----------
def daily_reset():
    global daily_messages
    for chat_id, messages in daily_messages.items():
        sorted_users = sorted(messages.items(), key=lambda x: x[1], reverse=True)
        rewards = [20, 10, 5]  # 1,2,3 місце
        for i, (user_id, _) in enumerate(sorted_users[:3]):
            MONETES[user_id] = MONETES.get(user_id, 0) + rewards[i]
        # очищаємо лічильники після нарахування
        daily_messages[chat_id] = {}

# ---------- MAIN ----------
def main():
    token = os.environ["TOKEN"]
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    # Обробка тексту
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

    # Команди топ та гаманець
    dp.add_handler(CommandHandler("top", top))
    dp.add_handler(CommandHandler("wallet", wallet))

    # Налаштування APScheduler для щоденного reset о 00:00 Київ
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Kiev"))
    scheduler.add_job(daily_reset, trigger="cron", hour=0, minute=0)
    scheduler.start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
