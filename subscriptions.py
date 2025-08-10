from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import update_purchase_balance, update_referral_balance
from messages import get_subscription_menu_text, get_profile_text, get_subscription_info_text
from profile import get_profile_keyboard

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
    
    # Показываем только доступные для апгрейда подписки
    if current_sub == 'tier3':
        # Максимальная подписка - можно только продлить
        buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽ (продление)", callback_data="sub_tier3")])
    elif current_sub == 'tier2':
        if active:
            # Nova активна - можно апгрейд до Eclipse
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
        else:
            # Nova истекла - можно продлить или апгрейд
            buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽ (продление)", callback_data="sub_tier2")])
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
    elif current_sub == 'tier1':
        if active:
            # Pulse активна - можно апгрейд до Nova или Eclipse
            buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽", callback_data="sub_tier2")])
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
        else:
            # Pulse истекла - можно продлить или апгрейд
            buttons.append([InlineKeyboardButton(text="Zenith Pulse - 300₽ (продление)", callback_data="sub_tier1")])
            buttons.append([InlineKeyboardButton(text="Zenith Nova - 500₽", callback_data="sub_tier2")])
            buttons.append([InlineKeyboardButton(text="Zenith Eclipse - 700₽", callback_data="sub_tier3")])
    else:
        # Бесплатная - можно купить любую
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
    """Обработчик выбора подписки"""
    try:
        user_id = callback.from_user.id
        sub_type = callback.data.replace("sub_", "")
        
        print(f"Обработка подписки {sub_type} для пользователя {user_id}")
        
        # Проверяем, что это допустимый тип подписки
        if sub_type not in ['tier1', 'tier2', 'tier3']:
            await callback.answer("Неверный тип подписки", show_alert=True)
            return
        
        # Получаем информацию о пользователе
        user = get_user(user_id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Определяем стоимость подписки
        prices = {
            'tier1': 300,
            'tier2': 500,
            'tier3': 700
        }
        
        sub_names = {
            'tier1': 'Zenith Pulse',
            'tier2': 'Zenith Nova',
            'tier3': 'Zenith Eclipse'
        }
        
        price = prices.get(sub_type, 0)
        sub_name = sub_names.get(sub_type, 'Неизвестная подписка')
        
        # Проверяем наличие скидки
        discount_info = get_user_active_discount(user_id)
        discount_percent = 0
        if discount_info:
            discount_percent = discount_info['discount_percent']
            final_price = price * (100 - discount_percent) / 100
        else:
            final_price = price
        
        # Проверяем баланс для покупок пользователя
        purchase_balance = user.get('balance', 0)
        if purchase_balance < final_price:
            await callback.answer(f"Недостаточно средств на балансе для покупок. Требуется {int(final_price)} руб.", show_alert=True)
            return
        
        # Списываем средства с баланса покупок
        update_purchase_balance(user_id, -int(final_price))
        
        # Отмечаем скидку как использованную (если была)
        if discount_info:
            mark_discount_as_used(user_id, discount_info['discount_code'])
        
        # Активируем подписку на 30 дней
        update_subscription(user_id, sub_type, 30)
        
        # Обрабатываем реферальные бонусы
        await process_referral_bonuses(user_id, final_price, sub_type)
        
        # Отправляем уведомление об успешной покупке
        success_text = (
            f"✅ Подписка успешно оформлена!\n\n"
            f"📶 Подписка: {sub_name}\n"
            f"💰 Списано: {int(final_price)} руб. с баланса покупок"
        )
        if discount_percent > 0:
            success_text += f"\n🎁 Применена скидка: {discount_percent}%"
        
        await callback.answer(success_text, show_alert=True)
        
        # Возвращаемся в профиль
        from messages import get_profile_text, get_subscription_info_text
        from profile import get_profile_keyboard
        
        user = get_user(user_id)
        profile_text = get_profile_text(user) if user else "❌ Профиль не найден"
        sub_text = get_subscription_info_text(user) if user else ""
        full_text = f"{profile_text}\n\n{sub_text}"
        full_text += f"\n\n✅ Подписка {sub_name} успешно оформлена!"
        
        await callback.message.edit_text(
            text=full_text,
            reply_markup=get_profile_keyboard(user_id)
        )
        
    except Exception as e:
        print(f"Ошибка при оформлении подписки: {e}")
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("Ошибка при оформлении подписки. Попробуйте позже.", show_alert=True)
        except:
            pass
        
def get_subscription_name(sub_type: str) -> str:
    names = {
        'free': 'Zenith Spark',
        'tier1': 'Zenith Pulse',
        'tier2': 'Zenith Nova',
        'tier3': 'Zenith Eclipse'
    }
    return names.get(sub_type, 'Zenith Spark')

async def handle_back_to_profile(callback: CallbackQuery):
    """Возврат в профиль"""
    try:
        from database import get_user as db_get_user
        from messages import get_profile_text, get_subscription_info_text
        from profile import get_profile_keyboard
        
        user_id = callback.from_user.id
        user = db_get_user(user_id)
        
        if user:
            profile_text = get_profile_text(user)
            sub_text = get_subscription_info_text(user)
            full_text = f"{profile_text}\n\n{sub_text}"
            
            # Проверяем, отличается ли текст от текущего
            try:
                current_text = callback.message.text
                if current_text != full_text:
                    await callback.message.edit_text(
                        text=full_text,
                        reply_markup=get_profile_keyboard(user_id)
                    )
                else:
                    # Если текст не изменился, просто обновляем клавиатуру если нужно
                    try:
                        await callback.message.edit_reply_markup(
                            reply_markup=get_profile_keyboard(user_id)
                        )
                    except:
                        pass
            except:
                await callback.message.edit_text(
                    text=full_text,
                    reply_markup=get_profile_keyboard(user_id)
                )
            
            # Не вызываем callback.answer(), если он уже был вызван ранее
            try:
                await callback.answer()
            except:
                pass  # Игнорируем ошибку, если callback уже истек
        else:
            await callback.answer("Пользователь не найден", show_alert=True)
    except Exception as e:
        print(f"Ошибка в handle_back_to_profile: {e}")
        # Не пытаемся вызвать callback.answer(), если время истекло
        pass

async def process_referral_bonuses(user_id: int, amount: float, sub_type: str):
    """Обрабатывает реферальные бонусы для цепочки рефереров"""
    from database import get_referrer_id, add_referral_payment, update_referral_balance
    
    current_id = user_id
    print(f"Начало обработки реферальных бонусов для пользователя {user_id}, сумма: {amount}")
    
    for level in range(1, 4):  # Обрабатываем 3 уровня
        referrer_id = get_referrer_id(current_id)
        if not referrer_id:
            print(f"Нет реферера уровня {level} для пользователя {current_id}")
            break
            
        # Рассчитываем бонус
        bonus = amount * REFERRAL_PERCENTS[level]
        
        print(f"Начисление бонуса уровня {level}: {bonus} руб. рефереру {referrer_id}")
        
        # Начисляем бонус на реферальный баланс рефереру
        update_referral_balance(referrer_id, bonus)
        
        # Записываем транзакцию
        add_referral_payment(user_id, referrer_id, bonus, level, sub_type)
        
        # Переходим к следующему уровню
        current_id = referrer_id

__all__ = ['show_subscriptions_menu', 'handle_subscription_selection', 'handle_back_to_profile', 'get_subscriptions_keyboard']