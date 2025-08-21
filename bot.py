from aiogram import F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command
import aiohttp
import asyncio

from config import OPENROUTER_API_KEY, AI_NAME
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
    handle_exchange_referral_balance,
    handle_referral_withdrawal_request,
    show_referral_program,
    process_deposit_amount,
    process_referral_withdrawal_amount
)
from messages import get_welcome_message
from state import message_history, chat_histories, last_bot_messages
from shared import bot, dp
from admin import register_admin_handlers, handle_admin_text_message
from error_handler import error_handler, sync_error_handler
from typing import Dict


# === Константы ===
BASE_SYSTEM_PROMPT = "Ты умный, дружелюбный ассистент. Отвечай кратко, на русском языке."

MODEL_PROMPTS = {
    "teacher": "Ты опытный учитель с 20-летним стажем...",
    "content_manager": "Ты профессиональный контент-менеджер...",
    "editor": "Ты профессиональный редактор текстов...",
    "chat": "Ты дружелюбный собеседник..."
}

MAX_HISTORY_LENGTH = 21
chat_modes: Dict[int, str] = {}   # {chat_id: "menu" | "chat"}


# === Главное меню ===
@sync_error_handler
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


# === Режимы ===
@error_handler
async def handle_modes(callback: CallbackQuery):
    await callback.message.edit_text(
        text="Выберите режим работы:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍🏫 Учитель",
                                  callback_data="mode_teacher")],
            [InlineKeyboardButton(text="📝 Контент-менеджер",
                                  callback_data="mode_content_manager")],
            [InlineKeyboardButton(text="✍️ Редактор",
                                  callback_data="mode_editor")],
            [InlineKeyboardButton(text="💬 Свободный чат",
                                  callback_data="mode_chat")],
            [InlineKeyboardButton(
                text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


@error_handler
async def handle_set_mode(callback: CallbackQuery):
    user_id = callback.from_user.id
    mode = callback.data.replace("mode_", "")
    update_user_mode(user_id, mode)
    await callback.answer(f"✅ Режим изменён на {mode}")


# === Чат ===
@error_handler
async def handle_start_chat(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    chat_modes[chat_id] = "chat"

    try:
        await callback.message.delete()
    except:
        pass

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
        await bot.pin_chat_message(chat_id, pinned.message_id, disable_notification=True)
    except:
        pass

    await callback.answer()


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


# === Сообщения пользователя в чате ===
@error_handler
async def handle_message(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Если пользователь не в режиме чата
    if chat_modes.get(chat_id) != "chat":
        # Проверяем, не ожидаем ли мы от пользователя ввод (например, сумму для пополнения)
        from state import user_states
        if user_id in user_states and user_states[user_id] in [
            "waiting_for_amount",           # Ожидание суммы пополнения
            "waiting_for_withdrawal_amount",  # Ожидание суммы вывода
            'waiting_for_admin_id_to_add',
            'waiting_for_admin_username_to_add',
            'waiting_for_admin_id_to_remove',
            'waiting_for_discount_params',
            'waiting_for_discount_code_to_delete'
        ]:
            # Это ожидаемый ввод, обрабатываем его соответствующей функцией
            from profile import process_deposit_amount, process_referral_withdrawal_amount
            from admin import handle_admin_text_message

            if user_states[user_id] == "waiting_for_amount":
                await process_deposit_amount(message)
            elif user_states[user_id] == "waiting_for_withdrawal_amount":
                await process_referral_withdrawal_amount(message)
            else:
                await handle_admin_text_message(message)
            return

        # Если это не ожидаемый ввод, то показываем информацию о режиме чата
        try:
            # Удаляем сообщение пользователя
            await message.delete()
        except:
            pass

        # Отправляем информационное сообщение
        info_msg = await message.answer(
            "Для общения с Zenith используйте отдельный режим чата.\n"
            "Нажмите кнопку ниже, чтобы перейти в режим чата:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="💬 Чат с Zenith", callback_data="start_chat")]
            ])
        )

        # Удаляем информационное сообщение через 10 секунд
        await asyncio.sleep(10)
        try:
            await info_msg.delete()
        except:
            pass

        # Удаляем уведомление о закреплении через 10 секунд
        await asyncio.sleep(10)
        try:
            # Получаем последние сообщения в чате и ищем уведомление о закреплении
            async for msg in bot.get_chat_history(chat_id, limit=5):
                if msg.text and "закрепил(а) удалённое сообщение" in msg.text.lower():
                    await msg.delete()
                    break
        except:
            pass

        return

    # Основная логика общения с AI (ваша существующая логика)
    await message.answer("⚡ Чат с ИИ пока заглушка, добавь сюда логику общения.")


# === Регистрация хендлеров ===
@sync_error_handler
def register_handlers():
    dp.message.register(handle_start, Command("start"))
    dp.message.register(handle_message, F.text & ~F.text.startswith("/"))

    dp.callback_query.register(handle_modes, F.data == "modes")
    dp.callback_query.register(handle_set_mode, F.data.startswith("mode_"))
    dp.callback_query.register(handle_start_chat, F.data == "start_chat")
    dp.callback_query.register(handle_back_to_main, F.data == "back_to_main")

    # profile.py обёртки с bot_instance
    dp.callback_query.register(show_profile, F.data == "profile")
    dp.callback_query.register(deposit_balance, F.data == "deposit")
    dp.callback_query.register(
        handle_exchange_referral_balance, F.data == "exchange_referral_balance")
    dp.callback_query.register(
        handle_referral_withdrawal_request, F.data == "referral_withdrawal")
    dp.callback_query.register(show_referral_program, F.data == "referral")
    # subscriptions.py handlers
    from subscriptions import show_subscriptions_menu, handle_subscription_selection, handle_back_to_profile
    dp.callback_query.register(
        show_subscriptions_menu, F.data == "subscriptions")
    dp.callback_query.register(
        handle_subscription_selection, F.data.startswith("sub_"))
    dp.callback_query.register(
        handle_back_to_profile, F.data == "back_to_profile")


# === Запуск ===
@error_handler
async def main():
    init_db()
    register_handlers()
    register_admin_handlers()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
