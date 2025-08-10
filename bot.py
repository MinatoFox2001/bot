from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiogram.filters import Command
from subscriptions import show_subscriptions_menu, handle_subscription_selection, handle_back_to_profile
from config import API_TOKEN, OPENROUTER_API_KEY
from database import (
    init_db,
    get_user,
    create_user,
    update_balance,
    update_user_mode,
    reset_daily_tokens_if_needed,
    increment_token_usage,
    get_subscription_info,
    log_message,
    get_last_messages, 
    is_subscription_active,
    get_user_active_discount, 
    mark_discount_as_used,
    is_user_admin
)
from profile import show_profile, deposit_balance, get_profile_keyboard, show_referral_program
from messages import get_welcome_message, get_profile_text, get_return_to_main_message, get_subscription_info_text
import aiohttp
import asyncio
from aiogram.types import BotCommand
from state import last_bot_messages, message_history, chat_histories, admin_states
from functools import partial
from shared import bot, dp
import logging
from admin import register_admin_handlers

# Глобальные переменные для хранения состояния
user_modes = {}
last_bot_messages = {}  # {chat_id: {'user_msgs': [], 'bot_msgs': []}}
profile_message_ids = {}
chat_modes = {}

init_db()

async def set_main_menu(bot: Bot):
    # Базовые команды для всех пользователей
    commands = [
        BotCommand(command='start', description='Перезапустить бота'),
        BotCommand(command='profile', description='Личный кабинет'),
        BotCommand(command='mode', description='Сменить режим работы'),
        BotCommand(command='discount', description='Применить скидочный код')
    ]
    
    # Команды для админов (будут установлены отдельно для админов)
    admin_commands = commands.copy()
    admin_commands.extend([
        BotCommand(command='admin', description='Панель администратора'),
        BotCommand(command='user', description='Управление пользователями')
    ])
    
    # Устанавливаем базовые команды для всех
    await bot.set_my_commands(commands)


#logging.basicConfig(level=logging.INFO)
BASE_SYSTEM_PROMPT = "Ты умный, дружелюбный ассистент. Отвечай кратко, на русском языке."

MODEL_PROMPTS = {
    "teacher": "Ты опытный учитель с 20-летним стажем...",
    "content_manager": "Ты профессиональный контент-менеджер...",
    "editor": "Ты профессиональный редактор текстов...",
    "chat": "Ты дружелюбный собеседник..."
}

MODEL = "deepseek/deepseek-chat-v3-0324:free"
MAX_HISTORY_LENGTH = 21

def get_models_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Учитель", callback_data="mode_teacher")],
        [InlineKeyboardButton(text="Контент-менеджер", callback_data="mode_content_manager")],
        [InlineKeyboardButton(text="Редактор", callback_data="mode_editor")],
        [InlineKeyboardButton(text="Чатовод", callback_data="mode_chat")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_main_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🛠 Режимы", callback_data="modes")]
    ]
    
    # Добавляем кнопку админ-панели, если пользователь админ
    if user_id and is_user_admin(user_id):
        buttons.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def cleanup_chat(chat_id: int):
    try:
        if chat_id in message_history:
            # Удаляем только существующие сообщения, кроме последнего приветствия и админ панели
            for msg in message_history[chat_id]['bot_msgs']:
                try:
                    if msg and hasattr(msg, 'message_id'):  # Проверка на None и наличие message_id
                        # Не удаляем приветственное сообщение и админ панель
                        if not (hasattr(msg, 'text') and msg.text and 
                               ("🤖 Zenith — лучший друг" in msg.text or 
                                "🎛 Панель администратора" in msg.text or
                                "👥 Управление пользователями" in msg.text or
                                "👨‍💼 Управление администраторами" in msg.text or
                                "📊 Статистика системы" in msg.text or
                                "🎟 Скидочные коды" in msg.text or
                                "🎟 Управление скидками" in msg.text)):
                            await bot.delete_message(chat_id, msg.message_id)
                except:
                    pass
            
            message_history[chat_id]['bot_msgs'] = []
            
    except Exception as e:
        print(f"Ошибка при очистке чата: {e}")

async def handle_start(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    chat_modes[chat_id] = 'inline'
    
    # Удаляем команду пользователя
    try:
        await message.delete()
    except Exception as e:
        print(f"Не удалось удалить сообщение команды: {e}")

    # Обработка реферальной ссылки
    referrer_id = None
    if len(message.text.split()) > 1 and message.text.split()[1].startswith('ref'):
        try:
            referrer_id = int(message.text.split()[1][3:])
            if referrer_id != user_id:  # Нельзя ссылаться на себя
                from database import add_referral
                add_referral(user_id, referrer_id)
        except ValueError:
            pass

    if not get_user(user_id):
        create_user(user_id, message.from_user.username, message.from_user.full_name)

    await cleanup_chat(chat_id)

    # Загружаем историю из БД
    history = get_last_messages(user_id, limit=20)
    system_prompt = MODEL_PROMPTS.get("chat", BASE_SYSTEM_PROMPT)

    chat_histories[chat_id] = [{"role": "system", "content": system_prompt}]
    for msg in history:
        chat_histories[chat_id].append({"role": msg["role"], "content": msg["message"]})

    # Получаем новое приветственное сообщение
    welcome_text = get_welcome_message(user_id)
    welcome_keyboard = get_main_keyboard(user_id)

    # Проверяем, есть ли последнее сообщение бота и содержит ли оно приветствие
    last_msg = last_bot_messages.get(chat_id)
    
    try:
        if (last_msg and 
            hasattr(last_msg, 'text') and 
            last_msg.text and 
            "🤖 Zenith — лучший друг" in last_msg.text):
            # Просто удаляем старое сообщение и отправляем новое
            try:
                await last_msg.delete()
            except:
                pass
        
        # Удаляем текущее сообщение если оно существует
        if last_msg and last_msg != message:
            try:
                await last_msg.delete()
            except:
                pass
        
    except Exception as e:
        print(f"Ошибка при удалении старого сообщения: {e}")

    # Отправляем новое сообщение
    try:
        msg = await message.answer(
            welcome_text,
            reply_markup=welcome_keyboard
        )
        
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        message_history[chat_id]['bot_msgs'].append(msg)
        last_bot_messages[chat_id] = msg
        
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

async def handle_profile_command(message: Message):
    await cleanup_chat(message.chat.id)
    
    user = get_user(message.from_user.id)
    if not user:
        msg = await message.answer("Сначала запустите бота командой /start")
        message_history[message.chat.id]['bot_msgs'].append(msg)
        return
    
    try:
        await message.delete()
    except Exception:
        pass

    # Получаем текст профиля
    profile_text = get_profile_text(user)
    
    # Получаем информацию о подписке
    sub_text = get_subscription_info_text(user)
    full_text = f"{profile_text}\n\n{sub_text}"

    # Пытаемся отредактировать предыдущее сообщение профиля
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id in profile_message_ids:
        try:
            # Пытаемся отредактировать существующее сообщение
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=profile_message_ids[user_id],
                text=full_text,
                reply_markup=get_profile_keyboard(user_id)
            )
            return
        except Exception as e:
            # Если не удалось отредактировать, удаляем запись об ID сообщения
            if user_id in profile_message_ids:
                del profile_message_ids[user_id]
    
    # Если редактирование не удалось, отправляем новое сообщение
    msg = await message.answer(
        text=full_text,
        reply_markup=get_profile_keyboard(user_id)
    )
    
    # Сохраняем ID нового сообщения
    profile_message_ids[user_id] = msg.message_id
    message_history[chat_id]['bot_msgs'].append(msg)

async def handle_message(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Если это команда, игнорируем
    if message.text.startswith('/'):
        return
    
    # Переключаем режим чата в диалоговый
    chat_modes[chat_id] = 'dialog'
    
    print(f"Получено сообщение от user_id={user_id}, admin_states={admin_states}")  
    
    # Инициализируем историю сообщений
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
    message_history[chat_id]['user_msgs'].append(message)

    # Если админ вводит данные для управления, не обрабатываем как сообщение ИИ
    if user_id in admin_states:
        print(f"Сообщение от админа в состоянии {admin_states[user_id]}, передаем админскому обработчику")   
        # Это сообщение для админских операций, админский обработчик сам с ним разберется
        return
    
    # Проверяем, находится ли пользователь в админ панели
    last_msg = last_bot_messages.get(chat_id) if chat_id in last_bot_messages else None
    is_in_admin_panel = False
    
    if last_msg and hasattr(last_msg, 'text') and last_msg.text:
        admin_texts = [
            "🎛 Панель администратора",
            "👥 Управление пользователями", 
            "👨‍💼 Управление администраторами",
            "📊 Статистика системы",
            "🎟 Скидочные коды",
            "🎟 Управление скидками"
        ]
        is_in_admin_panel = any(admin_text in last_msg.text for admin_text in admin_texts)
    
    # Если пользователь в админ панели, не очищаем чат
    if not is_in_admin_panel:
        await cleanup_chat(chat_id)
    
    print(f"Обрабатываем как обычное сообщение ИИ от user_id={user_id}")
    
    log_message(user_id, "user", message.text)  # 💾 лог пользователя

    # Более надежная проверка наличия приветственного сообщения
    has_welcome_message = False
    
    if last_msg and hasattr(last_msg, 'text') and last_msg.text:
        has_welcome_message = "🤖 Zenith — лучший друг" in last_msg.text
    
    if not has_welcome_message:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
        ])
        msg = await message.answer(
            text=get_return_to_main_message(),
            reply_markup=keyboard
        )
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        message_history[chat_id]['bot_msgs'].append(msg)
        if chat_id not in last_bot_messages:
            last_bot_messages[chat_id] = msg
        return

    reset_daily_tokens_if_needed(user_id)
    user = get_user(user_id)
    if not user:
        msg = await message.answer("Сначала запустите бота командой /start")
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        message_history[chat_id]['bot_msgs'].append(msg)
        return
    
    if 'mode' not in user:
        msg = await message.answer("Пожалуйста, сначала выберите режим работы")
        return

    sub_info = get_subscription_info(user_id)
    tokens_needed = len(message.text.split()) * 2
    if sub_info['tokens_used_today'] + tokens_needed > get_daily_limit(sub_info['subscription_type']):
        msg = await message.answer("⚠️ Превышен дневной лимит токенов для вашей подписки!")
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        message_history[chat_id]['bot_msgs'].append(msg)
        return

    increment_token_usage(user_id, tokens_needed)
    await message.chat.do("typing")

    try:
        mode = user.get('mode', 'chat')
        system_prompt = MODEL_PROMPTS.get(mode, BASE_SYSTEM_PROMPT)

        if chat_id not in chat_histories:
            chat_histories[chat_id] = [{"role": "system", "content": system_prompt}]
            past = get_last_messages(user_id, limit=20)
            for msg in past:
                chat_histories[chat_id].append({"role": msg["role"], "content": msg["message"]})

        chat_histories[chat_id].append({"role": "user", "content": message.text})

        if len(chat_histories[chat_id]) > MAX_HISTORY_LENGTH:
            chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-MAX_HISTORY_LENGTH+1:]

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": MODEL,
                "messages": chat_histories[chat_id]
            }

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    answer = data['choices'][0]['message']['content']
                    chat_histories[chat_id].append({"role": "assistant", "content": answer})
                    log_message(user_id, "assistant", answer)  # 💾 лог бота
                    msg = await message.answer(answer)
                    message_history[chat_id]['bot_msgs'].append(msg)
                else:
                    error = await response.text()
                    msg = await message.answer(f"⚠️ Ошибка при обработке запроса: {error}")
                    message_history[chat_id]['bot_msgs'].append(msg)

    except Exception as e:
        msg = await message.answer(f"⚠️ Произошла ошибка: {str(e)}")
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        message_history[chat_id]['bot_msgs'].append(msg)
        
async def handle_modes_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    await cleanup_chat(chat_id)
    
    msg = await callback.message.answer(
        text="Выберите режим работы:",
        reply_markup=get_models_keyboard()
    )
    
    if chat_id not in message_history:
        message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
    message_history[chat_id]['bot_msgs'].append(msg)
    
    await callback.answer()

async def handle_profile_callback(callback: CallbackQuery):
    try:
        await callback.answer()
        chat_id = callback.message.chat.id
        user_id = callback.from_user.id
        
        # После пополнения баланса проверим состояние подписки
        user = get_user(user_id)
        if not user:
            # код обработки отсутствующего пользователя
            return

        # Получаем текст профиля и подписки
        try:
            profile_text = get_profile_text(user)
            sub_text = get_subscription_info_text(user)
            full_text = f"{profile_text}\n\n{sub_text}"
        except Exception as e:
            print(f"Ошибка формирования текста профиля: {str(e)}")
            full_text = "❌ Не удалось загрузить данные профиля"

        # Получаем клавиатуру с актуальными данными
        try:
            keyboard = get_profile_keyboard(user_id)
        except Exception as e:
            print(f"Ошибка создания клавиатуры: {str(e)}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
            ])

        # Обновляем сообщение
        try:
            await callback.message.edit_text(
                text=full_text,
                reply_markup=keyboard
            )
            profile_message_ids[user_id] = callback.message.message_id
        except Exception as e:
            print(f"Не удалось отредактировать сообщение: {e}")

    except Exception as e:
        print(f"Критическая ошибка в handle_profile_callback: {str(e)}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

async def handle_back_to_main(callback: CallbackQuery):
    try:
        # Сразу отвечаем на callback
        await callback.answer()
        
        chat_id = callback.message.chat.id
        chat_modes[chat_id] = 'inline'
        user_id = callback.from_user.id
        
        # Получаем новое приветственное сообщение
        welcome_text = get_welcome_message(user_id)
        welcome_keyboard = get_main_keyboard(user_id)

        # Пытаемся отредактировать текущее сообщение
        try:
            await callback.message.edit_text(
                welcome_text,
                reply_markup=welcome_keyboard
            )
        except Exception as e:
            print(f"Не удалось отредактировать сообщение: {e}")
            # Если не удалось отредактировать, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass
            
            new_msg = await callback.message.answer(
                welcome_text,
                reply_markup=welcome_keyboard
            )
            
            # Обновляем историю сообщений
            if chat_id not in message_history:
                message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
            message_history[chat_id]['bot_msgs'].append(new_msg)
            last_bot_messages[chat_id] = new_msg

        await cleanup_chat(chat_id)

    except Exception as e:
        print(f"Ошибка в handle_back_to_main: {e}")

def get_daily_limit(sub_type: str) -> int:
    limits = {
        'free': 20,
        'tier1': 20000,
        'tier2': 40000,
        'tier3': 100000
    }
    return limits.get(sub_type, 20)

async def handle_mode_selection(callback: CallbackQuery):
    try:
        await callback.answer()
        chat_id = callback.message.chat.id
        mode = callback.data.replace("mode_", "")
        user_id = callback.from_user.id

        # Инициализируем историю
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}

        # Удаляем предыдущие сообщения
        for msg in message_history[chat_id]['bot_msgs']:
            try:
                await bot.delete_message(chat_id, msg.message_id)
            except:
                pass

        update_user_mode(user_id, mode)

        # Отправляем сообщение о смене режима
        mode_msg = await callback.message.answer(
            f"✅ Режим работы изменён на: <b>{mode}</b>"
        )

        # Отправляем главное меню (удаляем старое приветствие если есть)
        last_msg = last_bot_messages.get(chat_id)
        if (last_msg and 
            hasattr(last_msg, 'text') and 
            last_msg.text and 
            "🤖 Zenith — лучший друг" in last_msg.text):
            try:
                await last_msg.delete()
            except:
                pass

        menu_msg = await callback.message.answer(
            get_welcome_message(user_id),
            reply_markup=get_main_keyboard(user_id)
        )

        # Обновляем историю
        message_history[chat_id]['bot_msgs'] = [mode_msg, menu_msg]
        last_bot_messages[chat_id] = menu_msg

        # Обновляем системный промпт
        system_prompt = MODEL_PROMPTS.get(mode, BASE_SYSTEM_PROMPT)
        chat_histories[chat_id] = [{"role": "system", "content": system_prompt}]

    except Exception as e:
        print(f"Ошибка в handle_mode_selection: {e}")

async def handle_admin_panel_callback(callback: CallbackQuery):
    """Обработчик кнопки админ-панели в главном меню"""
    from admin import get_admin_keyboard
    
    # Проверяем, является ли пользователь админом
    if not is_user_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав администратора!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎛 Панель администратора",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

async def handle_discount_command(message: Message):
    """Обработчик команды /discount"""
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Неверный формат команды. Используйте: /discount [код]")
            return
        
        code = parts[1].upper()
        
        # Проверяем, есть ли уже примененная скидка у пользователя
        existing_discount = get_user_active_discount(message.from_user.id)
        if existing_discount:
            await message.answer("❌ У вас уже есть активная скидка. Используйте её при покупке подписки.")
            return
        
        # Получаем информацию о скидке
        from database import get_discount_code
        discount = get_discount_code(code)
        
        if not discount:
            await message.answer("❌ Неверный или неактивный скидочный код")
            return
        
        # Проверяем, не использован ли код полностью
        if discount['used_count'] >= discount['max_uses']:
            await message.answer("❌ Этот скидочный код уже полностью использован")
            return
        
        # Применяем скидку к пользователю (сохраняем для последующего использования)
        from database import apply_discount_to_user
        if apply_discount_to_user(message.from_user.id, code):
            # Увеличиваем счетчик использований кода
            from database import use_discount_code
            use_discount_code(code)
            
            await message.answer(
                f"✅ Скидка успешно применена!\n\n"
                f"🎫 Код: {code}\n"
                f"📊 Скидка: {discount['discount_percent']}%\n\n"
                f"Используйте эту скидку при покупке подписки."
            )
        else:
            await message.answer("❌ Не удалось применить скидку. Попробуйте позже.")
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

async def handle_mode_command(message: Message):
    await cleanup_chat(message.chat.id)
    
    msg = await message.answer(
        "Выберите режим работы:",
        reply_markup=get_models_keyboard()
    )

    try:
        await message.delete()
    except Exception:
        pass

    message_history[message.chat.id]['bot_msgs'].append(msg)

async def handle_admin_command(message: Message):
    """Обработчик команды /admin"""
    if not is_user_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора!")
        return
    
    # Пытаемся отредактировать последнее сообщение, если оно есть
    chat_id = message.chat.id
    last_msg = last_bot_messages.get(chat_id)
    
    welcome_text = "🎛 Панель администратора"
    
    # Создаем клавиатуру администратора
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👨‍💼 Администраторы", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🎟 Скидки", callback_data="admin_discounts")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_main")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if (last_msg and 
        hasattr(last_msg, 'text') and 
        last_msg.text and 
        "🎛 Панель администратора" in last_msg.text):
        # Пытаемся отредактировать существующее сообщение
        try:
            await last_msg.edit_text(welcome_text, reply_markup=keyboard)
            try:
                await message.delete()
            except:
                pass
            return
        except Exception as e:
            print(f"Не удалось отредактировать сообщение администратора: {e}")
            # Если не удалось отредактировать, удаляем старое сообщение
            try:
                await last_msg.delete()
            except:
                pass
    
    # Удаляем сообщение пользователя с командой
    try:
        await message.delete()
    except Exception:
        pass
    
    # Отправляем новое сообщение
    try:
        msg = await message.answer(welcome_text, reply_markup=keyboard)
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        message_history[chat_id]['bot_msgs'].append(msg)
        last_bot_messages[chat_id] = msg
    except Exception as e:
        print(f"Ошибка при отправке сообщения администратора: {e}")

async def handle_inline_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    # Если предыдущий режим был диалоговый, очищаем историю сообщений для инлайн режима
    if chat_modes.get(chat_id) == 'dialog':
        if chat_id in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
    
    # Устанавливаем инлайн режим
    chat_modes[chat_id] = 'inline'
    
    # Если это админская кнопка, передаем обработку админскому модулю
    if callback.data.startswith("admin_"):
        from admin import handle_admin_callback
        return await handle_admin_callback(callback)
    
    # Получаем последнее сообщение бота
    last_msg = last_bot_messages.get(chat_id)
    
    # Если есть сообщение для редактирования и оно в инлайн режиме
    if (last_msg and 
        hasattr(last_msg, 'message_id') and 
        chat_modes.get(chat_id) == 'inline'):
        
        try:
            # Определяем новый текст и клавиатуру в зависимости от callback.data
            if callback.data == "profile":
                user = get_user(user_id)
                new_text = get_profile_text(user) if user else "❌ Профиль не найден"
                new_keyboard = get_profile_keyboard(user_id)
            elif callback.data == "modes":
                new_text = "Выберите режим работы:"
                new_keyboard = get_models_keyboard()
            elif callback.data == "back_to_main":
                new_text = get_welcome_message(user_id)
                new_keyboard = get_main_keyboard(user_id)
            elif callback.data == "admin_panel":
                from admin import handle_admin_panel_callback
                return await handle_admin_panel_callback(callback)
            elif callback.data == "subscriptions":
                # Для подписок передаем обработку специальному обработчику
                return await show_subscriptions_menu(callback)
            elif callback.data == "deposit":
                # Для пополнения баланса передаем обработку специальному обработчику
                return await deposit_balance(callback)
            elif callback.data.startswith("mode_"):
                # Для выбора режимов передаем обработку специальному обработчику
                return await handle_mode_selection(callback)
            elif callback.data == "back_to_profile":
                # Для возврата к профилю передаем обработку специальному обработчику
                return await handle_back_to_profile(callback)
            elif callback.data == "referral":
                # Для реферальной программы передаем обработку специальному обработчику
                from profile import show_referral_program
                return await show_referral_program(callback)
            else:
                # Если callback не обрабатывается здесь, передаем другим обработчикам
                return await handle_other_callbacks(callback)
            
            # Редактируем сообщение
            try:
                current_text = last_msg.text if hasattr(last_msg, 'text') else ""
                if current_text != new_text:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=last_msg.message_id,
                        text=new_text,
                        reply_markup=new_keyboard
                    )
                else:
                    # Если текст не изменился, обновляем только клавиатуру
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=last_msg.message_id,
                        reply_markup=new_keyboard
                    )
            except Exception as e:
                print(f"Не удалось отредактировать сообщение: {e}")
                # Если не удалось отредактировать, отправляем новое сообщение
                try:
                    await last_msg.delete()
                except:
                    pass
                new_msg = await callback.message.answer(
                    text=new_text,
                    reply_markup=new_keyboard
                )
                message_history[chat_id]['bot_msgs'].append(new_msg)
                last_bot_messages[chat_id] = new_msg
            
            await callback.answer()
            return
        except Exception as e:
            print(f"Не удалось отредактировать сообщение: {e}")
    
    # Если не удалось редактировать, вызываем соответствующий обработчик
    try:
        if callback.data == "profile":
            await handle_profile_callback(callback)
        elif callback.data == "modes":
            await handle_modes_callback(callback)
        elif callback.data == "back_to_main":
            await handle_back_to_main(callback)
        elif callback.data == "admin_panel":
            from admin import handle_admin_panel_callback
            await handle_admin_panel_callback(callback)
        elif callback.data == "subscriptions":
            await show_subscriptions_menu(callback)
        elif callback.data == "deposit":
            await deposit_balance(callback)
        elif callback.data.startswith("mode_"):
            await handle_mode_selection(callback)
        elif callback.data.startswith("sub_"):
            await handle_subscription_selection(callback)
        elif callback.data == "back_to_profile":
            await handle_back_to_profile(callback)
        elif callback.data == "referral":
            from profile import show_referral_program
            await show_referral_program(callback)
        else:
            await handle_other_callbacks(callback)
    except Exception as e:
        print(f"Ошибка в handle_inline_callback: {e}")
        try:
            await callback.answer("Произошла ошибка при обработке запроса")
        except:
            pass

async def handle_other_callbacks(callback: CallbackQuery):
    """Обработчик для всех остальных callback'ов"""
    try:
        print(f"Unhandled callback data: {callback.data}")
        
        # Проверим, начинается ли с sub_
        if callback.data.startswith("sub_"):
            print(f"Обнаружена подписка: {callback.data}")
            # Попробуем обработать здесь
            from subscriptions import handle_subscription_selection
            return await handle_subscription_selection(callback)
            
        await callback.answer("Действие не распознано")
    except Exception as e:
        print(f"Ошибка в handle_other_callbacks: {e}")
        try:
            await callback.answer("Произошла ошибка при обработке запроса")
        except:
            pass
        
def register_handlers():
    # Обработчики команд
    dp.message.register(handle_start, Command("start"))
    dp.message.register(handle_profile_command, Command("profile"))
    dp.message.register(handle_mode_command, Command("mode"))  
    dp.message.register(handle_discount_command, Command("discount"))
    
    # Обработчик текстовых сообщений
    dp.message.register(handle_message, F.text)
    
    # Общий обработчик инлайн кнопок
    dp.callback_query.register(handle_inline_callback)
    
    # Специфические обработчики кнопок
    dp.callback_query.register(handle_modes_callback, F.data == "modes")
    dp.callback_query.register(handle_profile_callback, F.data == "profile")
    dp.callback_query.register(deposit_balance, F.data == "deposit")
    dp.callback_query.register(handle_mode_selection, F.data.startswith("mode_"))
    dp.callback_query.register(handle_back_to_main, F.data == "back_to_main")
    dp.callback_query.register(show_subscriptions_menu, F.data == "subscriptions")
    dp.callback_query.register(handle_subscription_selection, F.data.startswith("sub_"))
    dp.callback_query.register(handle_back_to_profile, F.data == "back_to_profile")
    dp.callback_query.register(handle_admin_panel_callback, F.data == "admin_panel")
    dp.callback_query.register(show_referral_program, F.data == "referral")
    dp.callback_query.register(handle_exchange_referral_balance, F.data == "exchange_referral_balance")

async def main():
    init_db()
    register_handlers()
    register_admin_handlers()
    await set_main_menu(bot)
    await dp.start_polling(bot)
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())