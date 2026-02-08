#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from random import shuffle, choice
from datetime import datetime, timedelta
from pytz import timezone
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

# ---------- GLOBAL DATA ----------
MONETES = {}  # Баланс монет
DAILY_MESSAGES = {}  # Повідомлення за день
CHAT_ID_HASHTAG = 5214033440  # чат для нарахування монет за #
TOP_CHAT_ID = 5214033440  # чат для топу

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

    # 🔥 РЕАКЦІЯ НА "ГЕТЕРО" та "МАЛЬВИ"
    if "гетеро" in text:
        update.message.reply_text("🍽️")
        return GUESSING
    if "мальви" in text:
        update.message.reply_text("👀")
        return GUESSING

    # Основна логіка гри
    if (
        context.chat_data.get("is_playing")
        and user.id != context.chat_data.get("current_player")
        and text == context.chat_data.get("current_word")
    ):
        update.message.reply_text(f"{user.first_name} вгадав слово!")

        # Нарахування 5 монет за вгадане слово
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
    text = update.message.text.lower()
    user = update.message.from_user
    chat_id = update.message.chat.id

    # Реакція на гетеро/мальви
    if "гетеро" in text:
        update.message.reply_text("🍽️")
    if "мальви" in text:
        update.message.reply_text("👀")

    # Нарахування монет за #
    if "#" in text and chat_id == CHAT_ID_HASHTAG:
        MONETES[user.id] = MONETES.get(user.id, 0) + 50

    # Нараховуємо повідомлення для топу
    if chat_id == TOP_CHAT_ID:
        DAILY_MESSAGES[user.id] = DAILY_MESSAGES.get(user.id, 0) + 1

# ---------- SHOW BALANCE ----------
def my_wallet(update, context):
    user = update.message.from_user
    balance = MONETES.get(user.id, 0)
    update.message.reply_text(f"{user.first_name}, у тебе {balance} монет 💰")

# ---------- DAILY TOP ----------
def daily_top(update, context):
    if not DAILY_MESSAGES:
        update.message.reply_text("Ще немає повідомлень за сьогодні")
        return
    sorted_top = sorted(DAILY_MESSAGES.items(), key=lambda x: x[1], reverse=True)
    text_lines = []
    rewards = [20, 10, 5]
    for i, (uid, count) in enumerate(sorted_top[:3]):
        user_mention = f"[{context.bot.get_chat_member(TOP_CHAT_ID, uid).user.first_name}](tg://user?id={uid})"
        text_lines.append(f"{i+1}. {user_mention}: {count} повідомлень")
        MONETES[uid] = MONETES.get(uid, 0) + (rewards[i] if i < len(rewards) else 0)
    update.message.reply_text("🔥 Топ учасників за день:\n" + "\n".join(text_lines), parse_mode="Markdown")
    # Очищуємо рахунок на наступний день
    DAILY_MESSAGES.clear()

# ---------- ADMIN BALANCE COMMANDS ----------
def add_coins(update, context):
    user = update.message.from_user
    chat_id = update.message.chat.id

    member = context.bot.get_chat_member(chat_id, user.id)
    if member.status not in ("administrator", "creator"):
        update.message.reply_text("Тільки адміністратори можуть змінювати баланс!")
        return

    try:
        amount = int(context.args[0])
        target_id = int(context.args[1])
    except (IndexError, ValueError):
        update.message.reply_text("Синтаксис: /add <кількість> <id користувача>")
        return

    MONETES[target_id] = MONETES.get(target_id, 0) + amount
    update.message.reply_text(f"Додано {amount} монет користувачу {target_id}.")

def deduct_coins(update, context):
    user = update.message.from_user
    chat_id = update.message.chat.id

    member = context.bot.get_chat_member(chat_id, user.id)
    if member.status not in ("administrator", "creator"):
        update.message.reply_text("Тільки адміністратори можуть змінювати баланс!")
        return

    try:
        amount = int(context.args[0])
        target_id = int(context.args[1])
    except (IndexError, ValueError):
        update.message.reply_text("Синтаксис: /deduct <кількість> <id користувача>")
        return

    MONETES[target_id] = max(MONETES.get(target_id, 0) - amount, 0)
    update.message.reply_text(f"Віднято {amount} монет користувачу {target_id}.")

# ---------- MAIN ----------
def main():
    token = os.environ["TOKEN"]
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    # 🔥 Обробка тексту глобально
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

    # Команди балансу
    dp.add_handler(CommandHandler("my_wallet", my_wallet))
    dp.add_handler(CommandHandler("daily_top", daily_top))
    dp.add_handler(CommandHandler("add", add_coins, pass_args=True))
    dp.add_handler(CommandHandler("deduct", deduct_coins, pass_args=True))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
