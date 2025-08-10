from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import update_subscription, get_user, update_balance, is_subscription_active  
from messages import get_subscription_menu_text
from profile import get_profile_keyboard, show_profile
from state import last_bot_messages, message_history, chat_histories
from shared import get_bot

PRICES = {
    'tier1': 300,
    'tier2': 500,
    'tier3': 700
}

DURATIONS = {
    'tier1': 30,
    'tier2': 30,
    'tier3': 30
}

REFERRAL_PERCENTS = {
    1: 0.15,  # 15% для реферера 1 уровня
    2: 0.10,  # 10% для реферера 2 уровня
    3: 0.05   # 5% для реферера 3 уровня
}

def get_subscriptions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    from database import get_user, is_subscription_active
    
    user = get_user(user_id)
    if not user:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ])
    
    current_sub = user.get('subscription_type', 'free')
    active = is_subscription_active(user_id)
    buttons = []
    
    # Если это максимальная подписка (Eclipse)
    if current_sub == 'tier3':
        pass
    # Если это Nova
    elif current_sub == 'tier2':
        if active:
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
        else:
            # Истекшая Nova - показываем улучшение
            buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽", callback_data="sub_tier2")])
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
    # Если это Pulse
    elif current_sub == 'tier1':
        if active:
            buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽", callback_data="sub_tier2")])
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
        else:
            # Истекший Pulse - показываем улучшения
            buttons.append([InlineKeyboardButton(text="Zenith Pulse - 300₽", callback_data="sub_tier1")])
            buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽", callback_data="sub_tier2")])
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
    # Если бесплатная (Spark)
    else:
        buttons.append([InlineKeyboardButton(text="Zenith Pulse - 300₽", callback_data="sub_tier1")])
        buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽", callback_data="sub_tier2")])
        buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def show_subscriptions_menu(callback: CallbackQuery):
    try:
        keyboard = get_subscriptions_keyboard(callback.from_user.id)
        await callback.message.edit_text(
            text=get_subscription_menu_text(callback.from_user.id),
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в show_subscriptions_menu: {e}")
        await callback.answer()

async def handle_subscription_selection(callback: CallbackQuery):
    try:
        sub_type = callback.data.split("_")[1]
        user_id = callback.from_user.id
        user = get_user(user_id)

        if sub_type in PRICES:
            # ... существующая проверка подписки и баланса ...

            # Списываем средства
            update_balance(user_id, -final_price)
            
            # Отмечаем скидку как использованную, если она была применена
            if discount:
                from database import mark_discount_as_used
                mark_discount_as_used(user_id, discount['discount_code'])

            # Обновляем подписку
            update_subscription(user_id, sub_type, DURATIONS[sub_type])

            # Начисляем реферальные бонусы
            await process_referral_bonuses(user_id, original_price, sub_type)

            # Формируем сообщение о покупке
            price_info = f"💳 Списано {final_price} руб."
            if discount_percent > 0:
                price_info += f" (скидка {discount_percent}%: -{discount_amount} руб.)"
            
            await callback.message.edit_text(
                text=f"✅ Подписка активирована: {get_subscription_name(sub_type)}.\n"
                     f"{price_info}\n"
                     f"📅 Истекает: {(datetime.now() + timedelta(days=DURATIONS[sub_type])).strftime('%d.%m.%Y')}",
                reply_markup=get_profile_keyboard(user_id)
            )
            await callback.answer()
    except Exception as e:
        print(f"Ошибка в handle_subscription_selection: {e}")
        await callback.answer("Произошла ошибка при обработке подписки")

def get_subscription_name(sub_type: str) -> str:
    names = {
        'free': 'Zenith Spark',
        'tier1': 'Zenith Pulse',
        'tier2': 'Zenith Nova',
        'tier3': 'Zenith Eclipse'
    }
    return names.get(sub_type, 'Zenith Spark')

async def handle_back_to_profile(callback: CallbackQuery):
    bot = get_bot()
    try:
        await callback.answer()
        await callback.message.delete()
        await show_profile(callback, bot)
    except Exception as e:
        print(f"Ошибка в handle_back_to_profile: {e}")
        await callback.answer()

async def process_referral_bonuses(user_id: int, amount: float, sub_type: str):
    """Обрабатывает реферальные бонусы для цепочки рефереров"""
    from database import get_referrer_id, add_referral_payment, update_balance
    
    current_id = user_id
    for level in range(1, 4):  # Обрабатываем 3 уровня
        referrer_id = get_referrer_id(current_id)
        if not referrer_id:
            break
            
        # Рассчитываем бонус
        bonus = amount * REFERRAL_PERCENTS[level]
        
        # Начисляем бонус рефереру
        update_balance(referrer_id, bonus)
        
        # Записываем транзакцию
        add_referral_payment(user_id, referrer_id, bonus, level, sub_type)
        
        # Переходим к следующему уровню
        current_id = referrer_id