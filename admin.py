from aiogram import F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from database import is_user_admin, add_admin, remove_admin, get_all_admins, get_user_info, update_balance, update_subscription, get_user_id_by_username, dict_factory
from config import ROOT_ADMIN_ID
from shared import dp, bot
import sqlite3
from datetime import datetime, timedelta
from state import admin_states, last_bot_messages, message_history
from error_logger import get_recent_errors, clear_error_logs
from error_handler import error_handler, sync_error_handler


@sync_error_handler
def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру админ панели"""
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика",
                              callback_data="admin_stats")],
        [InlineKeyboardButton(text="👨‍💼 Администраторы",
                              callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="👥 Пользователи",
                              callback_data="admin_users")],
        [InlineKeyboardButton(
            text="🎟 Скидки", callback_data="admin_discounts")],
        # Добавлена кнопка настроек
        [InlineKeyboardButton(text="⚙️ Настройки",
                              callback_data="admin_settings")],
        [InlineKeyboardButton(
            text="🔙 Назад", callback_data="admin_back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@sync_error_handler
def get_admins_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру управления админами"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить админа",
                              callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="➖ Удалить админа",
                              callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="📋 Список админов",
                              callback_data="admin_list_admins")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@error_handler
async def handle_admin_command(message: Message):
    """Обработчик команды /admin"""
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    await message.answer(
        "🎛 Панель администратора",
        reply_markup=get_admin_keyboard()
    )


@error_handler
async def handle_admin_stats(callback: CallbackQuery):
    """Показывает статистику"""
    from database import get_user

    # Получаем общую статистику
    with sqlite3.connect("users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM admins")
        total_admins = cursor.fetchone()[0] + 1  # +1 для root админа

        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0

    stats_text = (
        "📊 <b>Статистика системы</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"👨‍💼 Администраторов: {total_admins}\n"
        f"💰 Общий баланс: {total_balance} руб."
    )

    buttons = [[InlineKeyboardButton(
        text="🔙 Назад", callback_data="admin_back")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(stats_text, reply_markup=keyboard)
    await callback.answer()


@error_handler
async def handle_add_admin_start(callback: CallbackQuery):
    """Начало добавления администратора"""
    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(
        "Выберите способ добавления администратора:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🆔 По ID", callback_data="admin_add_by_id")],
            [InlineKeyboardButton(text="👤 По Username",
                                  callback_data="admin_add_by_username")],
            [InlineKeyboardButton(
                text="🔙 Назад", callback_data="admin_manage_admins")]
        ])
    )
    await callback.answer()


@error_handler
async def handle_remove_admin_start(callback: CallbackQuery):
    """Начало удаления администратора"""
    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(
        "Введите ID пользователя, которого хотите удалить из администраторов:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🔙 Назад", callback_data="admin_manage_admins")
        ]])
    )
    await callback.answer()


@error_handler
async def handle_list_admins(callback: CallbackQuery):
    """Показывает список администраторов"""
    from config import ROOT_ADMIN_ID

    admins = get_all_admins()

    # Добавляем root админа в список
    all_admins = [{'user_id': ROOT_ADMIN_ID,
                   'added_by': 'ROOT', 'added_at': 'ROOT'}]

    # Добавляем остальных админов из БД
    for admin in admins:
        if admin['user_id'] != ROOT_ADMIN_ID:  # Избегаем дубликатов
            all_admins.append(admin)

    if len(all_admins) <= 1 and all_admins[0]['user_id'] == ROOT_ADMIN_ID:
        admins_text = "👨‍💼 <b>Администраторы</b>\n\nСписок администраторов пуст."
    else:
        admins_text = "👨‍💼 <b>Администраторы</b>\n\n"
        for admin in all_admins:
            user_id = admin['user_id']
            added_by = admin['added_by']
            added_at = admin['added_at']

            if user_id == ROOT_ADMIN_ID:
                admins_text += f"👑 {user_id} (ROOT)\n"
            else:
                admins_text += f"👤 {user_id} (добавил: {added_by})\n"

    buttons = [[InlineKeyboardButton(
        text="🔙 Назад", callback_data="admin_manage_admins")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(admins_text, reply_markup=keyboard)
    await callback.answer()


@error_handler
async def handle_user_info(message: Message, user_id: int):
    """Получает информацию о пользователе"""
    user_info = get_user_info(user_id)
    if not user_info:
        await message.answer("❌ Пользователь не найден")
        return

    sub_names = {
        'free': 'Zenith Spark',
        'tier1': 'Zenith Pulse',
        'tier2': 'Zenith Nova',
        'tier3': 'Zenith Eclipse'
    }

    subscription_name = sub_names.get(
        user_info['subscription_type'], 'Zenith Spark')

    info_text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: {user_info['user_id']}\n"
        f"👤 Username: @{user_info['username']}\n"
        f"📛 Имя: {user_info['full_name']}\n"
        f"💰 Баланс для покупок: {user_info['balance']} руб.\n"
        f"💸 Реферальный баланс: {user_info.get('referral_balance', 0)} руб.\n"
        f"📶 Подписка: {subscription_name}"
    )

    await message.answer(info_text)


@error_handler
async def handle_user_balance(message: Message, user_id: int, amount: int):
    """Изменяет баланс пользователя"""
    user_info = get_user_info(user_id)
    if not user_info:
        await message.answer("❌ Пользователь не найден")
        return

    update_balance(user_id, amount)

    new_balance = user_info['balance'] + \
        amount if 'balance' in user_info else amount
    await message.answer(
        f"✅ Баланс пользователя {user_id} успешно изменен!\n"
        f"💰 Новый баланс: {new_balance} руб.\n"
        f"📈 Изменение: {amount:+} руб."
    )


@error_handler
async def handle_user_subscription(message: Message, user_id: int, sub_type: str):
    """Изменяет подписку пользователя"""
    user_info = get_user_info(user_id)
    if not user_info:
        await message.answer("❌ Пользователь не найден")
        return

    if sub_type not in ['tier1', 'tier2', 'tier3', 'free']:
        await message.answer("❌ Неверный тип подписки. Доступные: tier1, tier2, tier3, free")
        return

    # Устанавливаем подписку на 30 дней
    update_subscription(user_id, sub_type, 30)

    sub_names = {
        'free': 'Zenith Spark',
        'tier1': 'Zenith Pulse',
        'tier2': 'Zenith Nova',
        'tier3': 'Zenith Eclipse'
    }

    subscription_name = sub_names.get(sub_type, 'Zenith Spark')

    await message.answer(
        f"✅ Подписка пользователя {user_id} успешно изменена!\n"
        f"📶 Новая подписка: {subscription_name}\n"
        f"📅 Срок действия: 30 дней"
    )


@sync_error_handler
def get_discounts_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру управления скидками"""
    buttons = [
        [InlineKeyboardButton(text="➕ Создать скидку",
                              callback_data="admin_create_discount")],
        [InlineKeyboardButton(text="📋 Список скидок",
                              callback_data="admin_list_discounts")],
        [InlineKeyboardButton(text="🗑 Удалить скидку",
                              callback_data="admin_delete_discount")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@error_handler
async def handle_admin_users(callback: CallbackQuery):
    """Управление пользователями"""
    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    # Обновляем текст с информацией о новой команде
    await callback.message.edit_text(
        "👥 <b>Управление пользователями</b>\n\n"
        "Введите команду в формате:\n"
        "<code>/user [ID] [команда] [параметры]</code>\n\n"
        "Доступные команды:\n"
        "- <code>/user [ID] info</code> - информация\n"
        "- <code>/user [ID] balance [сумма]</code> - изменить баланс\n"
        "- <code>/user [ID] subscription [tier1/tier2/tier3/free]</code> - изменить подписку\n"
        "- <code>/user [ID] discount [процент] [кол-во использований]</code> - создать скидку для пользователя",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                          [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]])
    )
    await callback.answer()


@error_handler
async def handle_user_command(message: Message):
    """Обработчик команды /user"""
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("❌ Неверный формат команды. Используйте: /user [ID] [команда] [параметры]")
            return

        user_id = int(parts[1])
        command = parts[2].lower()

        if command == "info":
            await handle_user_info(message, user_id)
        elif command == "balance" and len(parts) >= 4:
            amount = int(parts[3])
            await handle_user_balance(message, user_id, amount)
        elif command == "subscription" and len(parts) >= 4:
            sub_type = parts[3]
            await handle_user_subscription(message, user_id, sub_type)
        elif command == "discount" and len(parts) >= 5:
            # Новая команда для создания скидки
            discount_percent = int(parts[3])
            max_uses = int(parts[4])
            target_subscription = parts[5] if len(parts) > 5 else None
            await handle_create_discount_for_user(message, user_id, discount_percent, max_uses, target_subscription)
        else:
            await message.answer("❌ Неизвестная команда или недостаточно параметров")
    except ValueError:
        await message.answer("❌ Неверный формат ID или числового параметра")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@error_handler
async def handle_create_discount_for_user(message: Message, user_id: int, discount_percent: int, max_uses: int, target_subscription: str = None):
    """Создает скидочный код для конкретного пользователя"""
    from database import create_discount_code
    import hashlib
    import time

    # Генерируем уникальный код
    code = f"DISC_{user_id}_{int(time.time())}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:6]}".upper(
    )

    # Добавляем информацию о целевой подписке в код (если указана)
    if target_subscription:
        code = f"{code}_{target_subscription.upper()}"

    # Создаем скидку
    if create_discount_code(code, discount_percent, max_uses, message.from_user.id):
        target_info = f" для подписки {target_subscription}" if target_subscription else ""
        await message.answer(
            f"✅ Скидочный код успешно создан для пользователя {user_id}!\n\n"
            f"📊 Скидка: {discount_percent}%\n"
            f"🔢 Максимум использований: {max_uses}\n"
            f"🎯 Назначение: {target_info if target_info else 'любая подписка'}\n"
            f"🎫 Код: <code>{code}</code>\n\n"
            f"Перешлите этот код пользователю для использования."
        )
    else:
        await message.answer("❌ Не удалось создать скидочный код")


@error_handler
async def handle_admin_callback(callback: CallbackQuery):
    """Обработчик callback'ов админ панели"""
    if not is_user_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора!", show_alert=True)
        return

    action = callback.data

    if action == "admin_panel":
        await handle_admin_panel_callback(callback)
    elif action == "admin_stats":
        await handle_admin_stats(callback)
    elif action == "admin_manage_admins":
        # Редактируем сообщение вместо отправки нового
        await callback.message.edit_text(
            "👨‍💼 Управление администраторами",
            reply_markup=get_admins_keyboard()
        )
        await callback.answer()
    elif action == "admin_users":
        await handle_admin_users(callback)
    elif action == "admin_discounts":
        # Редактируем сообщение вместо отправки нового
        await callback.message.edit_text(
            "🎟 <b>Управление скидками</b>\n\n"
            "Выберите действие:",
            reply_markup=get_discounts_keyboard()
        )
        await callback.answer()
    elif action == "admin_settings":  # Добавлен обработчик настроек
        await handle_admin_settings(callback)
    elif action == "admin_view_errors":  # Добавлен обработчик просмотра ошибок
        await handle_view_errors(callback)
    elif action == "admin_clear_errors":  # Добавлен обработчик очистки ошибок
        await handle_clear_errors(callback)
    elif action == "admin_create_discount":
        admin_states[callback.from_user.id] = 'waiting_for_discount_params'
        await handle_create_discount_start(callback)
    elif action == "admin_list_discounts":
        await handle_list_discounts(callback)
    elif action == "admin_delete_discount":
        admin_states[callback.from_user.id] = 'waiting_for_discount_code_to_delete'
        await handle_delete_discount_start(callback)
    elif action == "admin_add_admin":
        await handle_add_admin_start(callback)
    elif action == "admin_add_by_id":
        admin_states[callback.from_user.id] = 'waiting_for_admin_id_to_add'
        # Редактируем сообщение вместо отправки нового
        await callback.message.edit_text(
            "Введите ID пользователя, которого хотите назначить администратором:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="🔙 Назад", callback_data="admin_manage_admins")]])
        )
        await callback.answer()
    elif action == "admin_add_by_username":
        admin_states[callback.from_user.id] = 'waiting_for_admin_username_to_add'
        # Редактируем сообщение вместо отправки нового
        await callback.message.edit_text(
            "Введите username пользователя, которого хотите назначить администратором:\n"
            "Пример: @username\n\n"
            "Или просто username без @",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="🔙 Назад", callback_data="admin_manage_admins")]])
        )
        await callback.answer()
    elif action == "admin_remove_admin":
        admin_states[callback.from_user.id] = 'waiting_for_admin_id_to_remove'
        await handle_remove_admin_start(callback)
    elif action == "admin_list_admins":
        await handle_list_admins(callback)
    elif action == "admin_back":
        # Очищаем состояние админа
        if callback.from_user.id in admin_states:
            del admin_states[callback.from_user.id]

        # Редактируем сообщение вместо отправки нового
        await callback.message.edit_text(
            "🎛 Панель администратора",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
    elif action == "admin_back_to_main":
        # Очищаем состояние админа
        if callback.from_user.id in admin_states:
            del admin_states[callback.from_user.id]

        # Получаем приветственное сообщение
        from messages import get_welcome_message
        from bot import get_main_keyboard

        welcome_text = get_welcome_message(callback.from_user.id)
        keyboard = get_main_keyboard(callback.from_user.id)

        # Редактируем сообщение вместо отправки нового
        try:
            await callback.message.edit_text(
                welcome_text,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Не удалось отредактировать сообщение: {e}")
            # Если не удалось отредактировать, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass

            await callback.message.answer(
                welcome_text,
                reply_markup=keyboard
            )

        await callback.answer()


@error_handler
async def handle_create_discount_start(callback: CallbackQuery):
    """Начало создания скидки"""
    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(
        "Введите параметры скидки в формате:\n"
        "<code>[код] [процент скидки] [максимум использований]</code>\n\n"
        "Пример: <code>NEW2024 15 100</code>\n"
        "Это создаст код NEW2024 со скидкой 15% и 100 использований.\n\n"
        "Или введите 'cancel' для отмены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                          [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_discounts")]])
    )
    await callback.answer()


@error_handler
async def handle_delete_discount_start(callback: CallbackQuery):
    """Начало удаления скидки"""
    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(
        "Введите код скидки, который хотите удалить:\n\n"
        "Или введите 'cancel' для отмены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                          [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_discounts")]])
    )
    await callback.answer()


@error_handler
async def handle_list_discounts(callback: CallbackQuery):
    """Показывает список всех скидок"""
    from database import get_all_discount_codes

    discounts = get_all_discount_codes()

    if not discounts:
        discounts_text = "🎟 <b>Скидочные коды</b>\n\nСписок скидок пуст."
    else:
        discounts_text = "🎟 <b>Скидочные коды</b>\n\n"
        for discount in discounts:
            code = discount['code']
            percent = discount['discount_percent']
            max_uses = discount['max_uses']
            used = discount['used_count']
            active = "✅" if discount['is_active'] else "❌"
            creator = discount['created_by']

            discounts_text += (
                f"🎫 <code>{code}</code> {active}\n"
                f"📊 {percent}% | Использовано: {used}/{max_uses}\n"
                f"👤 Создал: {creator}\n\n"
            )

    buttons = [[InlineKeyboardButton(
        text="🔙 Назад", callback_data="admin_discounts")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(discounts_text, reply_markup=keyboard)
    await callback.answer()


@error_handler
async def handle_admin_text_message(message: Message):
    """Обработчик текстовых сообщений от админов"""
    if not is_user_admin(message.from_user.id):
        return

    user_id = message.from_user.id

    # Проверяем, ждем ли мы от этого админа какой-то информации
    if user_id in admin_states:
        state = admin_states[user_id]
        if message.text.lower() == 'cancel':
            # Очищаем состояние
            del admin_states[user_id]
            await message.answer(
                "❌ Операция отменена",
                reply_markup=get_admin_keyboard()
            )
            return

        try:
            if state == 'waiting_for_discount_params':
                # Обработка создания скидки
                parts = message.text.split()
                if len(parts) != 3:
                    await message.answer("❌ Неверный формат. Введите: [код] [процент] [максимум использований]")
                    return

                code = parts[0].upper()
                discount_percent = int(parts[1])
                max_uses = int(parts[2])

                if discount_percent < 1 or discount_percent > 100:
                    await message.answer("❌ Процент скидки должен быть от 1 до 100")
                    return

                if max_uses < 1:
                    await message.answer("❌ Максимум использований должен быть больше 0")
                    return

                from database import create_discount_code
                if create_discount_code(code, discount_percent, max_uses, user_id):
                    await message.answer(
                        f"✅ Скидочный код успешно создан!\n\n"
                        f"🎫 Код: {code}\n"
                        f"📊 Скидка: {discount_percent}%\n"
                        f"🔢 Максимум использований: {max_uses}",
                        reply_markup=get_discounts_keyboard()
                    )
                else:
                    await message.answer(
                        "❌ Не удалось создать скидочный код. Возможно, такой код уже существует.",
                        reply_markup=get_discounts_keyboard()
                    )

                # Очищаем состояние
                del admin_states[user_id]

            elif state == 'waiting_for_discount_code_to_delete':
                # Обработка удаления скидки
                code = message.text.upper()

                from database import delete_discount_code
                if delete_discount_code(code):
                    await message.answer(
                        f"✅ Скидочный код {code} успешно удален!",
                        reply_markup=get_discounts_keyboard()
                    )
                else:
                    await message.answer(
                        f"❌ Не удалось удалить скидочный код {code}. Возможно, он не существует.",
                        reply_markup=get_discounts_keyboard()
                    )

                # Очищаем состояние
                del admin_states[user_id]

            elif state == 'waiting_for_admin_id_to_add':
                # Добавляем администратора по ID
                target_user_id = int(message.text)
                if add_admin(target_user_id, user_id):
                    await message.answer(
                        f"✅ Пользователь {target_user_id} успешно назначен администратором!",
                        reply_markup=get_admins_keyboard()
                    )
                else:
                    await message.answer(
                        f"❌ Не удалось назначить пользователя {target_user_id} администратором.\n"
                        f"Возможно, он уже является администратором.",
                        reply_markup=get_admins_keyboard()
                    )

                # Очищаем состояние
                del admin_states[user_id]

            elif state == 'waiting_for_admin_username_to_add':
                # Добавляем администратора по username
                username = message.text.strip().lstrip('@')

                # Ищем пользователя по username в базе данных
                from database import get_user_id_by_username
                target_user_id = get_user_id_by_username(username)
                if target_user_id:
                    if add_admin(target_user_id, user_id):
                        await message.answer(
                            f"✅ Пользователь @{username} (ID: {target_user_id}) успешно назначен администратором!",
                            reply_markup=get_admins_keyboard()
                        )
                    else:
                        await message.answer(
                            f"❌ Не удалось назначить пользователя @{username} администратором.\n"
                            f"Возможно, он уже является администратором.",
                            reply_markup=get_admins_keyboard()
                        )
                else:
                    await message.answer(
                        f"❌ Пользователь @{username} не найден в базе данных.\n"
                        f"Попросите пользователя сначала запустить бота.",
                        reply_markup=get_admins_keyboard()
                    )

                # Очищаем состояние
                del admin_states[user_id]

            elif state == 'waiting_for_admin_id_to_remove':
                # Удаляем администратора
                target_user_id = int(message.text)
                if remove_admin(target_user_id):
                    await message.answer(
                        f"✅ Пользователь {target_user_id} успешно удален из администраторов!",
                        reply_markup=get_admins_keyboard()
                    )
                else:
                    await message.answer(
                        f"❌ Не удалось удалить пользователя {target_user_id} из администраторов.\n"
                        f"Возможно, он не является администратором или это ROOT админ.",
                        reply_markup=get_admins_keyboard()
                    )

                # Очищаем состояние
                del admin_states[user_id]

        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректные данные.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
            # Очищаем состояние в случае ошибки
            if user_id in admin_states:
                del admin_states[user_id]


@error_handler
async def handle_admin_panel_callback(callback: CallbackQuery):
    """Обработчик кнопки админ-панели в главном меню"""
    # Проверяем, является ли пользователь админом
    if not is_user_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора!", show_alert=True)
        return

    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(
        "🎛 Панель администратора",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


@error_handler
async def handle_referral_stats(callback: CallbackQuery):
    """Показывает статистику реферальной системы"""
    with sqlite3.connect("users.db") as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute("SELECT COUNT(*) as count FROM referrals")
        total_referrals = cursor.fetchone()['count']

        cursor.execute("SELECT SUM(amount) as total FROM referral_payments")
        total_payments = cursor.fetchone()['total'] or 0

        cursor.execute("""
            SELECT u.user_id, u.username, COUNT(r.user_id) as referrals_count, 
                   SUM(rp.amount) as earned_total
            FROM users u
            LEFT JOIN referrals r ON u.user_id = r.referrer_id
            LEFT JOIN referral_payments rp ON u.user_id = rp.referrer_id
            GROUP BY u.user_id
            ORDER BY earned_total DESC
            LIMIT 10
        """)
        top_referrers = cursor.fetchall()

    stats_text = (
        "📊 <b>Реферальная статистика</b>\n\n"
        f"👥 Всего рефералов: {total_referrals}\n"
        f"💰 Всего выплачено: {total_payments:.2f} руб.\n\n"
        "🏆 <b>Топ рефереров</b>:\n"
    )

    for i, referrer in enumerate(top_referrers, 1):
        stats_text += (
            f"{i}. @{referrer['username']} (ID: {referrer['user_id']})\n"
            f"   👥 Рефералов: {referrer['referrals_count']}\n"
            f"   💰 Заработано: {referrer['earned_total'] or 0:.2f} руб.\n\n"
        )

    buttons = [[InlineKeyboardButton(
        text="🔙 Назад", callback_data="admin_back")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(stats_text, reply_markup=keyboard)
    await callback.answer()


@error_handler
async def handle_referral_withdrawal(callback: CallbackQuery):
    """Обработчик вывода реферальных средств"""
    from database import get_user

    user_id = callback.from_user.id
    user = get_user(user_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    referral_balance = user.get('referral_balance', 0)

    if referral_balance < 500:  # Минимальная сумма для вывода
        await callback.answer("Минимальная сумма для вывода: 500 руб.", show_alert=True)
        return

    # Установим состояние ожидания ввода суммы
    from state import admin_states
    admin_states[user_id] = 'waiting_for_withdrawal_amount'

    await callback.message.edit_text(
        f"Введите сумму для вывода (максимум: {referral_balance} руб.):\n"
        f"Минимальная сумма: 500 руб.\n\n"
        f"Или введите 'cancel' для отмены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="referral")]
        ])
    )
    await callback.answer()


@error_handler
async def handle_withdrawal_request(message: Message):
    """Обработчик команды для подтверждения вывода средств"""
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.answer(
                "❌ Неверный формат команды. Используйте: /withdraw [ID_пользователя] [сумма] [комментарий]\n"
                "Пример: /withdraw 123456789 500 Обработано"
            )
            return

        user_id = int(parts[1])
        amount = float(parts[2])
        comment = " ".join(parts[3:]) if len(parts) > 3 else "Обработано"

        # Здесь можно добавить логику для реальной отправки средств
        # Например, обновление статуса заявки в БД

        # Для примера просто отправляем уведомление пользователю
        try:
            from shared import bot
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваша заявка на вывод средств в размере {amount} руб. обработана!\n"
                f"Комментарий: {comment}\n\n"
                f"Средства поступят в течение 3 рабочих дней."
            )
            await message.answer(f"✅ Уведомление отправлено пользователю {user_id}")
        except Exception as e:
            await message.answer(f"⚠️ Заявка обработана, но не удалось уведомить пользователя: {e}")

    except ValueError:
        await message.answer("❌ Неверный формат ID или суммы")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@sync_error_handler
def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру настроек"""
    buttons = [
        [InlineKeyboardButton(text="📝 Просмотр ошибок",
                              callback_data="admin_view_errors")],
        [InlineKeyboardButton(text="🗑 Очистить логи ошибок",
                              callback_data="admin_clear_errors")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@error_handler
async def handle_admin_settings(callback: CallbackQuery):
    """Обработчик настроек админ панели"""
    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(
        "⚙️ <b>Настройки админ панели</b>\n\n"
        "Выберите действие:",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()


@error_handler
async def handle_view_errors(callback: CallbackQuery):
    """Просмотр последних ошибок"""
    errors = get_recent_errors(20)  # Получаем последние 20 ошибок

    if not errors:
        errors_text = "📝 <b>Журнал ошибок</b>\n\nНет записей об ошибках."
    else:
        errors_text = "📝 <b>Журнал ошибок</b>\n\n"
        for error in errors:
            errors_text += (
                f"🔴 <b>ID:</b> {error['id']}\n"
                f"🕐 <b>Время:</b> {error['timestamp']}\n"
                f"👤 <b>Пользователь:</b> {error['user_id'] or 'N/A'}\n"
                f"❗ <b>Тип:</b> {error['error_type']}\n"
                f"📄 <b>Сообщение:</b> {error['error_message']}\n"
            )
            if error['traceback']:
                errors_text += f"🔍 <b>Traceback:</b>\n<code>{error['traceback'][:200]}...</code>\n"
            errors_text += "\n" + "-"*30 + "\n\n"

    buttons = [[InlineKeyboardButton(
        text="🔙 Назад", callback_data="admin_settings")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Сохраняем сообщение в истории
    chat_id = callback.message.chat.id
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

    # Обновляем последнее сообщение бота
    from state import last_bot_messages
    last_bot_messages[chat_id] = callback.message

    await callback.message.edit_text(errors_text, reply_markup=keyboard)
    await callback.answer()


@error_handler
async def handle_clear_errors(callback: CallbackQuery):
    """Очистка логов ошибок"""
    if clear_error_logs():
        await callback.answer("✅ Логи ошибок успешно очищены!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка при очистке логов", show_alert=True)

    # Возвращаем к настройкам
    await handle_admin_settings(callback)


@error_handler
async def handle_console_command(message: Message):
    """Обработчик консольных команд администратора"""
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    try:
        command_text = message.text[9:].strip()  # Убираем "/console "

        if not command_text:
            await message.answer(
                "🔧 <b>Консоль администратора</b>\n\n"
                "Доступные команды:\n"
                "<code>/console stats</code> - статистика системы\n"
                "<code>/console errors</code> - последние ошибки\n"
                "<code>/console clear_errors</code> - очистить логи ошибок\n"
                "<code>/console users count</code> - количество пользователей\n"
                "<code>/console user [ID] info</code> - информация о пользователе\n"
                "<code>/console broadcast [сообщение]</code> - рассылка всем пользователям"
            )
            return

        parts = command_text.split()
        command = parts[0].lower()

        if command == "stats":
            await handle_console_stats(message)
        elif command == "errors":
            await handle_console_errors(message)
        elif command == "clear_errors":
            if clear_error_logs():
                await message.answer("✅ Логи ошибок успешно очищены!")
            else:
                await message.answer("❌ Ошибка при очистке логов")
        elif command == "users" and len(parts) > 1 and parts[1] == "count":
            await handle_console_users_count(message)
        elif command == "user" and len(parts) >= 3 and parts[2] == "info":
            try:
                user_id = int(parts[1])
                await handle_user_info(message, user_id)
            except ValueError:
                await message.answer("❌ Неверный формат ID")
        elif command == "broadcast" and len(parts) > 1:
            await handle_console_broadcast(message, " ".join(parts[1:]))
        else:
            await message.answer("❌ Неизвестная команда. Используйте /console для помощи.")

    except Exception as e:
        from error_logger import log_error
        import traceback
        log_error("ConsoleCommandError", str(e),
                  traceback.format_exc(), message.from_user.id)
        await message.answer(f"❌ Ошибка выполнения команды: {str(e)}")


@error_handler
async def handle_console_stats(message: Message):
    """Консольная команда статистики"""
    from database import get_user

    with sqlite3.connect("users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM admins")
        total_admins = cursor.fetchone()[0] + 1

        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0

    stats_text = (
        "📊 <b>Статистика системы (консоль)</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"👨‍💼 Администраторов: {total_admins}\n"
        f"💰 Общий баланс: {total_balance} руб."
    )

    await message.answer(stats_text)


@error_handler
async def handle_console_errors(message: Message):
    """Консольная команда просмотра ошибок"""
    errors = get_recent_errors(10)

    if not errors:
        await message.answer("📝 Нет записей об ошибках.")
        return

    errors_text = "📝 <b>Последние ошибки:</b>\n\n"
    for error in errors[:5]:  # Показываем только первые 5
        errors_text += (
            f"[{error['timestamp']}] {error['error_type']}: {error['error_message'][:100]}...\n"
        )

    await message.answer(errors_text)


@error_handler
async def handle_console_users_count(message: Message):
    """Консольная команда подсчета пользователей"""
    with sqlite3.connect("users.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

    await message.answer(f"👥 Общее количество пользователей: {total_users}")


@error_handler
async def handle_console_broadcast(message: Message, broadcast_text: str):
    """Консольная команда рассылки сообщений"""
    from database import get_all_users_ids
    from shared import bot

    try:
        # Получаем все ID пользователей
        with sqlite3.connect("users.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            user_ids = [row[0] for row in cursor.fetchall()]

        success_count = 0
        failed_count = 0

        for user_id in user_ids:
            try:
                await bot.send_message(chat_id=user_id, text=broadcast_text)
                success_count += 1
            except Exception:
                failed_count += 1

        await message.answer(
            f"📢 Рассылка завершена!\n\n"
            f"✅ Успешно отправлено: {success_count}\n"
            f"❌ Не отправлено: {failed_count}"
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при рассылке: {str(e)}")


@sync_error_handler
def register_admin_handlers():
    # Регистрируем обработчики команд первыми
    dp.message.register(handle_admin_command, Command("admin"))
    dp.message.register(handle_user_command, Command("user"))
    dp.message.register(handle_withdrawal_request, Command("withdraw"))
    dp.message.register(handle_console_command, Command("console"))

    # Затем регистрируем callback обработчики
    dp.callback_query.register(
        handle_admin_callback, F.data.startswith("admin_"))

    # И только потом - обработчик текстовых сообщений
    dp.message.register(handle_admin_text_message, F.text)
