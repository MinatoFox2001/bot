from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand
)
from aiogram.filters import Command
import aiohttp
import asyncio

from config import API_TOKEN, OPENROUTER_API_KEY, AI_NAME
from database import (
    init_db,
    get_user,
    create_user,
    update_user_mode,
    reset_daily_tokens_if_needed,
    increment_token_usage,
    get_subscription_info,
    log_message,
    get_last_messages,
    is_subscription_active,
    is_user_admin
)
from profile import (
    show_profile,
    deposit_balance,
    get_profile_keyboard,
    handle_exchange_referral_balance,
    handle_referral_withdrawal_request,
    process_deposit_amount,
    process_referral_withdrawal_amount,
    show_referral_program,
    payment_checks
)
from messages import (
    get_welcome_message,
    get_profile_text,
    get_return_to_main_message,
    get_subscription_info_text
)
from state import message_history, chat_histories, last_bot_messages, admin_states, user_states
from shared import bot, dp
from admin import register_admin_handlers
from error_handler import error_handler, sync_error_handler
from typing import Optional


# === Константы ===
BASE_SYSTEM_PROMPT = "Ты умный, дружелюбный ассистент. Отвечай кратко, на русском языке."

MODEL_PROMPTS = {
    "teacher": "Ты опытный учитель с 20-летним стажем...",
    "content_manager": "Ты профессиональный контент-менеджер...",
    "editor": "Ты профессиональный редактор текстов...",
    "chat": "Ты дружелюбный собеседник..."
}

MAX_HISTORY_LENGTH = 21
chat_modes = {}   # {chat_id: "menu" | "chat"}


# === Главное меню ===
def get_main_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="🛠 Режимы", callback_data="modes")
        ],
        [InlineKeyboardButton(text="💬 Чат", callback_data="start_chat")]
    ]
    if user_id and is_user_admin(user_id):
        buttons.append([InlineKeyboardButton(
            text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# === Старт ===
@error_handler
async def handle_start(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    chat_modes[chat_id] = "menu"

    try:
        await message.delete()
    except:
        pass

    if not get_user(user_id):
        create_user(user_id, message.from_user.username,
                    message.from_user.full_name)

    welcome_text = get_welcome_message(user_id)
    keyboard = get_main_keyboard(user_id)

    msg = await message.answer(welcome_text, reply_markup=keyboard)
    message_history[chat_id] = {"user_msgs": [], "bot_msgs": [msg]}
    last_bot_messages[chat_id] = msg


# === Вход в чат с ИИ ===
@error_handler
async def handle_start_chat(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    chat_modes[chat_id] = "chat"

    # Убираем меню
    try:
        await callback.message.delete()
    except:
        pass

    # Отправляем закреплёнку
    pinned = await bot.send_message(
        chat_id,
        "💬 Вы находитесь в диалоговом чате.\n\n"
        "Чтобы выйти в меню, нажмите кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 В меню", callback_data="back_to_main")]
        ])
    )
    try:
        await bot.pin_chat_message(chat_id, pinned.message_id)
    except:
        pass

    await callback.answer()


# === Выход из чата ===
@error_handler
async def handle_back_to_main(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    chat_modes[chat_id] = "menu"

    try:
        await bot.unpin_all_chat_messages(chat_id)
    except:
        pass

    welcome_text = get_welcome_message(user_id)
    keyboard = get_main_keyboard(user_id)

    msg = await callback.message.answer(welcome_text, reply_markup=keyboard)
    message_history[chat_id] = {"user_msgs": [], "bot_msgs": [msg]}
    last_bot_messages[chat_id] = msg

    try:
        await callback.message.delete()
    except:
        pass

    await callback.answer()


# === Сообщения пользователя ===
@error_handler
async def handle_message(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_modes.get(chat_id) != "chat":
        return  # в меню сообщения не обрабатываем

    # Сохраняем
    if chat_id not in message_history:
        message_history[chat_id] = {"user_msgs": [], "bot_msgs": []}
    message_history[chat_id]["user_msgs"].append(message)
    log_message(user_id, "user", message.text)

    reset_daily_tokens_if_needed(user_id)
    user = get_user(user_id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return

    if "mode" not in user:
        await message.answer("Пожалуйста, сначала выберите режим работы")
        return

    sub_info = get_subscription_info(user_id)
    tokens_needed = len(message.text.split()) * 2
    if sub_info["tokens_used_today"] + tokens_needed > get_daily_limit(sub_info["subscription_type"]):
        await message.answer("⚠️ Превышен дневной лимит токенов для вашей подписки!")
        return

    increment_token_usage(user_id, tokens_needed)

    # История
    mode = user.get("mode", "chat")
    system_prompt = MODEL_PROMPTS.get(mode, BASE_SYSTEM_PROMPT)

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [
            {"role": "system", "content": system_prompt}]
        past = get_last_messages(user_id, limit=20)
        for msg in past:
            chat_histories[chat_id].append(
                {"role": msg["role"], "content": msg["message"]})

    chat_histories[chat_id].append({"role": "user", "content": message.text})

    if len(chat_histories[chat_id]) > MAX_HISTORY_LENGTH:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + \
            chat_histories[chat_id][-MAX_HISTORY_LENGTH + 1:]

    # Запрос к AI
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {"model": AI_NAME, "messages": chat_histories[chat_id]}
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    answer = data["choices"][0]["message"]["content"]
                    chat_histories[chat_id].append(
                        {"role": "assistant", "content": answer})
                    log_message(user_id, "assistant", answer)
                    await message.answer(answer)
                else:
                    error = await response.text()
                    await message.answer(f"⚠️ Ошибка: {error}")
    except Exception as e:
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")


# === Лимиты ===
def get_daily_limit(sub_type: str) -> int:
    limits = {"free": 20, "tier1": 20000, "tier2": 40000, "tier3": 100000}
    return limits.get(sub_type, 20)


# === Регистрация хендлеров ===
def register_handlers():
    dp.message.register(handle_start, Command("start"))
    dp.message.register(handle_message, F.text & ~F.text.startswith("/"))

    dp.callback_query.register(handle_start_chat, F.data == "start_chat")
    dp.callback_query.register(handle_back_to_main, F.data == "back_to_main")
    dp.callback_query.register(show_profile, F.data == "profile")
    dp.callback_query.register(deposit_balance, F.data == "deposit")
    dp.callback_query.register(
        handle_exchange_referral_balance, F.data == "exchange_referral_balance")
    dp.callback_query.register(
        handle_referral_withdrawal_request, F.data == "referral_withdrawal")
    dp.callback_query.register(show_referral_program, F.data == "referral")


# === Запуск ===
async def main():
    init_db()
    register_handlers()
    register_admin_handlers()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
