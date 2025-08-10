from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from database import update_purchase_balance, update_referral_balance, transfer_referral_to_purchase_balance
from shared import bot
from messages import get_profile_text, get_subscription_info_text
from datetime import datetime
from config import ROOT_ADMIN_ID, TIMEZONE

# Минимальная сумма для вывода реферальных средств
MIN_REFERRAL_WITHDRAWAL = 10

# Обновим функцию get_profile_keyboard()
def get_profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Пополнить баланс (+100 руб.)", callback_data="deposit")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton(text="👥 Реферальная программа", callback_data="referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def show_profile(callback: CallbackQuery, bot_instance):
    user = get_user(callback.from_user.id)
    if not user:
        # Пытаемся отредактировать сообщение
        try:
            await callback.message.edit_text(
                "❌ Профиль не найден. Пожалуйста, запустите бота командой /start",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
                ])
            )
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            await callback.message.answer(
                "❌ Профиль не найден. Пожалуйста, запустите бота командой /start",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
                ])
            )
            try:
                await callback.message.delete()
            except:
                pass
        return

    
    try:
        profile_text = get_profile_text(user)
        sub_text = get_subscription_info_text(user)
        full_text = f"{profile_text}\n\n{sub_text}"
    except Exception as e:
        print(f"Ошибка формирования текста профиля: {str(e)}")
        full_text = "❌ Не удалось загрузить данные профиля"

    try:
        keyboard = get_profile_keyboard(callback.from_user.id)
    except Exception as e:
        print(f"Ошибка создания клавиатуры: {str(e)}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])

    # Пытаемся отредактировать сообщение
    try:
        await callback.message.edit_text(
            text=full_text,
            reply_markup=keyboard
        )
    except Exception:
        # Если не удалось отредактировать, отправляем новое сообщение
        await callback.message.answer(
            text=full_text,
            reply_markup=keyboard
        )
        try:
            await callback.message.delete()
        except:
            pass

async def deposit_balance(callback: CallbackQuery):
    """Обработчик кнопки пополнения баланса на 100 рублей"""
    from database import update_purchase_balance, get_user
    from messages import get_profile_text, get_subscription_info_text
    
    user_id = callback.from_user.id
    
    try:
        # Пополняем баланс для покупок на 100 рублей
        update_purchase_balance(user_id, 100)
        
        # Получаем обновленную информацию о пользователе
        user = get_user(user_id)
        
        if user:
            # Обновляем сообщение профиля с подтверждением пополнения
            profile_text = get_profile_text(user)
            sub_text = get_subscription_info_text(user)
            full_text = f"{profile_text}\n\n{sub_text}"
            
            # Добавляем уведомление о пополнении
            full_text += "\n\n✅ Баланс для покупок успешно пополнен на 100 руб.!"
            
            await callback.message.edit_text(
                text=full_text,
                reply_markup=get_profile_keyboard(user_id)
            )
        else:
            await callback.answer("❌ Ошибка при обновлении профиля", show_alert=True)
            
    except Exception as e:
        print(f"Ошибка при пополнении баланса: {e}")
        await callback.answer("❌ Ошибка при пополнении баланса", show_alert=True)
        return
    
    await callback.answer("💳 Баланс для покупок успешно пополнен на 100 руб.!")

async def handle_exchange_referral_balance(callback: CallbackQuery):
    """Обработчик обмена реферального баланса на баланс покупок"""
    from database import get_user, transfer_referral_to_purchase_balance
    from messages import get_referral_message
    
    user_id = callback.from_user.id
    
    try:
        user = get_user(user_id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
            
        referral_balance = user.get('referral_balance', 0)
        
        if referral_balance <= 0:
            await callback.answer("У вас нет средств на реферальном балансе для обмена", show_alert=True)
            return
        
        # Переводим все средства с реферального баланса на баланс покупок
        if transfer_referral_to_purchase_balance(user_id, referral_balance):
            await callback.answer(f"✅ Успешно переведено {referral_balance} руб. с реферального баланса на баланс покупок!", show_alert=True)
            
            # Обновляем сообщение реферальной программы
            user = get_user(user_id)  # Получаем обновленные данные
            await callback.message.edit_text(
                text=get_referral_message(user_id),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💱 Обменять на баланс покупок", callback_data="exchange_referral_balance")],
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
                ])
            )
        else:
            await callback.answer("❌ Ошибка при переводе средств", show_alert=True)
            
    except Exception as e:
        print(f"Ошибка при обмене баланса: {e}")
        await callback.answer("❌ Ошибка при обмене баланса", show_alert=True)

async def handle_referral_withdrawal_request(callback: CallbackQuery):
    """Обработчик запроса на вывод средств"""
    from database import get_user
    
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    referral_balance = user.get('referral_balance', 0)
    
    if referral_balance < MIN_REFERRAL_WITHDRAWAL:
        await callback.answer(f"Минимальная сумма для вывода: {MIN_REFERRAL_WITHDRAWAL} руб.", show_alert=True)
        return
    
    # Установим состояние ожидания ввода суммы
    from state import admin_states
    admin_states[user_id] = 'waiting_for_withdrawal_amount'
    
    await callback.message.edit_text(
        f"Введите сумму для вывода (максимум: {referral_balance} руб.):\n"
        f"Минимальная сумма: {MIN_REFERRAL_WITHDRAWAL} руб.\n\n"
        f"Или введите 'cancel' для отмены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="referral")]
        ])
    )
    await callback.answer()

async def process_withdrawal_amount(message: Message):
    """Обработка введенной суммы вывода"""
    from database import get_user, update_referral_balance
    from state import admin_states
    from shared import bot
    from datetime import datetime, timedelta
    from config import ROOT_ADMIN_ID, TIMEZONE
    
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.answer("Пользователь не найден")
        return
    
    referral_balance = user.get('referral_balance', 0)
    
    try:
        amount = float(message.text)
        
        # Проверки
        if amount < MIN_REFERRAL_WITHDRAWAL:
            await message.answer(f"Минимальная сумма для вывода: {MIN_REFERRAL_WITHDRAWAL} руб.")
            return
            
        if amount > referral_balance:
            await message.answer(f"Недостаточно средств. Доступно: {referral_balance} руб.")
            return
            
        if amount <= 0:
            await message.answer("Сумма должна быть положительной")
            return
        
        # Снимаем средства с реферального баланса
        update_referral_balance(user_id, -int(amount))
        
        # Удаляем состояние
        if user_id in admin_states:
            del admin_states[user_id]
        
        # Получаем текущее время с учетом часового пояса
        current_time = (datetime.now() + timedelta(hours=TIMEZONE)).strftime('%d.%m.%Y %H:%M')
        
        # Отправляем уведомление главному админу
        try:
            admin_message = (
                f"💰 <b>Новая заявка на вывод средств!</b>\n\n"
                f"👤 Пользователь: <code>{user_id}</code>\n"
                f"👤 Имя: {user.get('full_name', 'Не указано')}\n"
                f"{'👤 Username: @' + str(user.get('username', 'Не указан')) if user.get('username') else '👤 Username: Не указан'}\n"
                f"💸 Сумма: <b>{amount} руб.</b>\n"
                f"📅 Время: {current_time}\n\n"
                f"Для обработки заявки используйте команду:\n"
                f"<code>/user {user_id} balance {int(amount)}</code> - для зачисления средств\n"
                f"или вручной перевод через платежную систему"
            )
            
            # Отправляем уведомление главному админу
            if ROOT_ADMIN_ID:
                await bot.send_message(
                    chat_id=ROOT_ADMIN_ID,
                    text=admin_message,
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"Ошибка отправки уведомления админу: {e}")
        
        await message.answer(
            f"✅ Заявка на вывод средств принята!\n\n"
            f"Сумма: {amount} руб.\n"
            f"Статус: В обработке\n\n"
            f"Средства будут переведены в течение 3 рабочих дней.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
            ])
        )
        
        # Обновляем профиль пользователя
        from messages import get_profile_text, get_subscription_info_text
        from profile import get_profile_keyboard
        
        updated_user = get_user(user_id)
        profile_text = get_profile_text(updated_user)
        sub_text = get_subscription_info_text(updated_user)
        full_text = f"{profile_text}\n\n{sub_text}"
        
        # Обновляем последнее сообщение профиля
        from bot import profile_message_ids
        if user_id in profile_message_ids:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=profile_message_ids[user_id],
                    text=full_text,
                    reply_markup=get_profile_keyboard(user_id)
                )
            except:
                pass
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректную сумму (число)")
    except Exception as e:
        # Возвращаем состояние в случае ошибки
        if user_id in admin_states:
            admin_states[user_id] = 'waiting_for_withdrawal_amount'
        await message.answer("Произошла ошибка при обработке заявки. Пожалуйста, попробуйте еще раз.")
        print(f"Ошибка в process_withdrawal_amount: {e}")

async def show_referral_program(callback: CallbackQuery):
    from messages import get_referral_message
    from database import get_user
    
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
            
        referral_balance = user.get('referral_balance', 0)
        
        keyboard_buttons = []
        
        # Добавляем кнопку обмена, если есть средства на реферальном балансе
        if referral_balance > 0:
            keyboard_buttons.append([InlineKeyboardButton(text="💱 Обменять на баланс покупок", callback_data="exchange_referral_balance")])
        
        # Добавляем кнопку вывода средств (проверка будет при нажатии)
        keyboard_buttons.append([InlineKeyboardButton(text="💸 Вывод средств", callback_data="referral_withdrawal")])
        
        keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")])
        
        await callback.message.edit_text(
            text=get_referral_message(callback.from_user.id),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в show_referral_program: {e}")
        await callback.answer("Произошла ошибка при загрузке реферальной программы")

__all__ = ['get_profile_keyboard', 'show_profile', 'deposit_balance', 'show_referral_program', 
           'handle_exchange_referral_balance', 'handle_referral_withdrawal_request', 'process_withdrawal_amount']
