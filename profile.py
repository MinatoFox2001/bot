from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from database import get_user
from shared import bot
from messages import get_profile_text, get_subscription_info_text

# Обновим функцию get_profile_keyboard()
def get_profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton(text="👥 Реферальная программа", callback_data="referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Добавим обработчик реферальной программы
async def show_referral_program(callback: CallbackQuery):
    from messages import get_referral_message
    
    try:
        await callback.message.edit_text(
            text=get_referral_message(callback.from_user.id),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
            ])
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
    await callback.answer("💳 Функция пополнения баланса будет реализована позже")

__all__ = ['get_profile_keyboard', 'show_profile', 'deposit_balance', 'show_referral_program']