from database import is_subscription_active, is_user_admin, get_subscription_info


def get_welcome_message(user_id=None):
    # Если user_id не передан, возвращаем общее приветствие
    if user_id is None:
        return (
            "🤖 Zenith — лучший друг, специалист и просто AI помощник\n"
            "⚠️ У вас подписка: Zenith Spark (20 пар токенов/день)\n"
            "🔄 Версия: Zenith Beta v1.0"
        )
    
    # Получаем информацию о пользователе
    from database import get_user
    user = get_user(user_id)
    
    if not user:
        return (
            "🤖 Zenith — лучший друг, специалист и просто AI помощник\n"
            "⚠️ У вас подписка: Zenith Spark (20 пар токенов/день)\n"
            "🔄 Версия: Zenith Beta v1.0"
        )
    
    # Определяем название подписки и лимиты
    sub_type = user.get("subscription_type", "free")
    sub_names = {
        'free': 'Zenith Spark',
        'tier1': 'Zenith Pulse',
        'tier2': 'Zenith Nova',
        'tier3': 'Zenith Eclipse'
    }
    sub_limits = {
        'free': '20 пар токенов/день',
        'tier1': '20k пар токенов/день',
        'tier2': '40k пар токенов/день',
        'tier3': '100k пар токенов/день'
    }
    
    sub_name = sub_names.get(sub_type, 'Zenith Spark')
    sub_limit = sub_limits.get(sub_type, '20 пар токенов/день')
    
    # Проверяем, является ли пользователь админом
    is_admin = is_user_admin(user_id)
    admin_text = "\n👑 У вас права администратора" if is_admin else ""
    
    return (
        "🤖 Zenith — лучший друг, специалист и просто AI помощник\n"
        f"⚠️ У вас подписка: {sub_name} ({sub_limit}){admin_text}\n"
        "🔄 Версия: Zenith Beta v1.0"
    )


def get_profile_text(user: dict) -> str:
    try:
        # Проверяем обязательные поля
        if not isinstance(user, dict):
            return "❌ Ошибка данных профиля"
            
        # Устанавливаем значения по умолчанию
        user_id = user.get('user_id', 'N/A')
        full_name = user.get('full_name', 'Не указано')
        username = user.get('username', 'N/A')
        balance = user.get('balance', 0)
        
        # Формируем текст профиля без информации о подписке
        result = (
            f"👤 Личный кабинет \n\n"
            f"🆔 {user_id}\n"
            f"📛Имя : {full_name}\n"
            f"🪪 Логин : @{username}\n"
            f"💰Баланс : {balance} руб."
        )
            
        return result
        
    except Exception as e:
        print(f"Ошибка в get_profile_text: {e}")
        return "❌ Не удалось загрузить данные профиля"

def get_mode_changed_message(mode_type: str):
    messages = {
        "teacher": "Режим учителя активирован!",
        "content_manager": "Режим контент-менеджера активирован!",
        "editor": "Режим редактора активирован!",
        "chat": "Режим чата активирован!"
    }
    return messages.get(mode_type, "Режим изменен!")

def get_subscription_info_text(user: dict) -> str:
    try:
        if not user or not isinstance(user, dict):
            return "🔔 Подписка: данные не загружены"
        
        # Получаем user_id безопасным способом
        user_id = user.get('user_id')
        if not user_id:
            return "🔔 Подписка: неверные данные пользователя"
            
        sub_type = user.get('subscription_type', 'free')
        expires = user.get('subscription_expires')
        tokens_used = user.get('tokens_used_today', 0)
        
        sub_names = {
            'free': 'Zenith Spark',
            'tier1': 'Zenith Pulse',
            'tier2': 'Zenith Nova', 
            'tier3': 'Zenith Eclipse'
        }
        
        sub_limits = {
            'free': 20,
            'tier1': 20000,
            'tier2': 40000,
            'tier3': 100000
        }
        
        sub_name = sub_names.get(sub_type, 'Zenith Spark')
        limit = sub_limits.get(sub_type, 20)
        
        # Форматируем значения
        def format_tokens(value):
            if value >= 1000:
                return f"{value//1000}k"
            return str(value)
        
        # Дата истечения
        expires_text = ""
        if expires and sub_type != 'free':
            try:
                if isinstance(expires, str):
                    from datetime import datetime
                    expires_date = datetime.fromisoformat(expires.split('+')[0])  # Убираем часовой пояс если есть
                    expires_text = f"📅 Истекает : {expires_date.strftime('%d.%m.%Y')}"
            except Exception as e:
                print(f"Ошибка обработки даты: {e}")
                expires_text = "📅 Истекает : ошибка"
        elif sub_type != 'free':
            expires_text = "📅 Истекает : не указана"

        # Формируем текст в формате как в примере
        result = (
            f"📶 Подписка : {sub_name}\n\n"
            f"⚡️ Лимит : {format_tokens(limit//2)}k пар токенов/день\n"
        )
        
        # Добавляем дату истечения только если подписка не бесплатная
        if sub_type != 'free' and expires_text:
            result += f"{expires_text}"
        elif sub_type != 'free':
            result += "📅 Истекает : не указана"
            
        return result
        
    except Exception as e:
        print(f"Критическая ошибка в get_subscription_info_text: {str(e)}")
        return "🔔 Подписка: ошибка загрузки"
    
def get_subscription_menu_text(user_id: int = None) -> str:
    from database import get_user, is_subscription_active, get_user_active_discount
    from datetime import datetime
    
    # Проверяем наличие скидки у пользователя
    discount_info = ""
    if user_id:
        discount = get_user_active_discount(user_id)
        if discount:
            discount_info = f"\n🎁 Активная скидка: {discount['discount_percent']}%"

    if user_id:
        user = get_user(user_id)
        if user:
            current_sub = user.get('subscription_type', 'free')
            active = is_subscription_active(user_id)
            
            # Если это максимальная подписка (Eclipse)
            if current_sub == 'tier3':
                expires = user.get('subscription_expires', '')
                expires_text = ""
                if expires:
                    try:
                        if isinstance(expires, str):
                            # Удаляем информацию о часовом поясе если есть
                            expires_clean = expires.split('+')[0]
                            expires_date = datetime.fromisoformat(expires_clean)
                            expires_text = f" до {expires_date.strftime('%d.%m.%Y')}"
                    except Exception as e:
                        print(f"Ошибка обработки даты: {e}")
                        expires_text = ""
                return (
                    "💰 <b>У вас максимальный уровень подписки</b>\n\n"
                    f"💫 Zenith Eclipse - 100k токенов/день{expires_text}{discount_info}\n"
                    "Вы можете продлить подписку после истечения срока."
                )
            # Если это Nova
            elif current_sub == 'tier2':
                if active:
                    return (
                        "💰 <b>Доступные улучшения подписки</b>\n\n"
                        "💫 У вас активна: Zenith Nova (40k токенов/день)\n\n"
                        "1. Zenith Eclipse - 700₽ (100k токенов/день)\n\n"
                        "Текущая подписка отображается в вашем профиле."
                        f"{discount_info}"
                    )
                else:
                    # Истекшая Nova
                    return (
                        "💰 <b>Выберите подписку</b>\n\n"
                        "1. Zenith Pulse - 300₽ (20k токенов/день)\n"
                        "2. Zenith Nova - 500₽ (40k токенов/день)\n"
                        "3. Zenith Eclipse - 700₽ (100k токенов/день)\n\n"
                        "Текущая подписка отображается в вашем профиле."
                        f"{discount_info}"
                    )
            # Если это Pulse
            elif current_sub == 'tier1':
                if active:
                    return (
                        "💰 <b>Доступные улучшения подписки</b>\n\n"
                        "💫 У вас активна: Zenith Pulse (20k токенов/день)\n\n"
                        "1. Zenith Nova - 500₽ (40k токенов/день)\n"
                        "2. Zenith Eclipse - 700₽ (100k токенов/день)\n\n"
                        "Текущая подписка отображается в вашем профиле."
                        f"{discount_info}"
                    )
                else:
                    # Истекший Pulse
                    return (
                        "💰 <b>Выберите подписку</b>\n\n"
                        "1. Zenith Pulse - 300₽ (20k токенов/день)\n"
                        "2. Zenith Nova - 500₽ (40k токенов/день)\n"
                        "3. Zenith Eclipse - 700₽ (100k токенов/день)\n\n"
                        "Текущая подписка отображается в вашем профиле."
                        f"{discount_info}"
                    )
            # Если бесплатная (Spark)
            else:
                return (
                    "💰 <b>Выберите подписку</b>\n\n"
                    "1. Zenith Pulse - 300₽ (20k токенов/день)\n"
                    "2. Zenith Nova - 500₽ (40k токенов/день)\n"
                    "3. Zenith Eclipse - 700₽ (100k токенов/день)\n\n"
                    "Текущая подписка отображается в вашем профиле."
                    f"{discount_info}"
                )
    
    return (
        "💰 <b>Выберите подписку</b>\n\n"
        "1. Zenith Pulse - 300₽ (20k токенов/день)\n"
        "2. Zenith Nova - 500₽ (40k токенов/день)\n"
        "3. Zenith Eclipse - 700₽ (100k токенов/день)\n\n"
        "Текущая подписка отображается в вашем профиле."
    )

def get_return_to_main_message():
    return (
        "🔙 Пожалуйста, вернитесь в главное меню, чтобы задать вопрос ИИ\n\n"
        "Используйте команду /start или кнопку ниже"
    )

def get_referral_message(user_id: int) -> str:
    """Возвращает сообщение с реферальной ссылкой и статистикой"""
    from database import get_referral_stats
    
    stats = get_referral_stats(user_id)
    
    return (
        "👥 <b>Реферальная программа</b>\n\n"
        f"🔗 Ваша реферальная ссылка:\n"
        f"<code>https://t.me/zenith_ii_bot?start=ref{user_id}</code>\n\n"
        f"📊 Статистика:\n"
        f"👥 Всего рефералов: {stats['total_referrals']}\n"
        f"💎 Активных рефералов: {stats['active_referrals']}\n"
        f"💰 Всего заработано: {stats['total_earned']:.2f} руб.\n\n"
        "💸 <b>Как это работает?</b>\n"
        "1. Вы приглашаете друзей по своей ссылке\n"
        "2. Когда они покупают подписку, вы получаете:\n"
        "   - 15% с покупки прямого реферала\n"
        "   - 10% с покупки реферала 2 уровня\n"
        "   - 5% с покупки реферала 3 уровня\n"
        "3. Вывод средств доступен при достижении 500 руб."
    )

