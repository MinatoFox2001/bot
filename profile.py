from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from database import update_purchase_balance, update_referral_balance, transfer_referral_to_purchase_balance
from shared import bot
from messages import get_profile_text, get_subscription_info_text

# Обновим функцию get_profile_keyboard()
def get_profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Пополнить баланс (+100 руб.)", callback_data="deposit")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton(text="👥 Реферальная программа", callback_data="referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Добавим обработчик реферальной программы
async def show_referral_program(callback: CallbackQuery):
    from messages import get_referral_message
    from database import get_user
    
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
            
        referral_balance = user.get('referral_balance', 0)
        
        keyboard_buttons = [
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ]
        
        # Добавляем кнопку обмена, если есть средства на реферальном балансе
        if referral_balance > 0:
            keyboard_buttons.insert(0, [InlineKeyboardButton(text="💱 Обменять на баланс покупок", callback_data="exchange_referral_balance")])
        
        await callback.message.edit_text(
            text=get_referral_message(callback.from_user.id),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в show_referral_program: {e}")
        await callback.answer("Произошла ошибка при загрузке реферальной программы")

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

__all__ = ['get_profile_keyboard', 'show_profile', 'deposit_balance', 'show_referral_program']