from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram import F
from database import update_purchase_balance, update_referral_balance, transfer_referral_to_purchase_balance, get_user
from shared import bot, dp
from messages import get_profile_text, get_subscription_info_text
from datetime import datetime
from config import ROOT_ADMIN_ID, TIMEZONE
from error_handler import error_handler, sync_error_handler
import re
import asyncio

# Минимальная сумма для вывода реферальных средств
MIN_REFERRAL_WITHDRAWAL = 10

# Хранение состояния пользователей
user_states = {}

# Хранение информации о платежах для автоматической проверки
payment_checks = {}  # {payment_id: {user_id: int, message_id: int, chat_id: int}}

# Хранение активных сообщений для каждого пользователя
active_user_messages = {}  # {user_id: message_id}


@sync_error_handler
def get_profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Пополнить баланс",
                              callback_data="deposit")],
        [InlineKeyboardButton(
            text="💎 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton(text="👥 Реферальная программа",
                              callback_data="referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@error_handler
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
            keyboard_buttons.append([InlineKeyboardButton(
                text="💱 Обменять на баланс покупок", callback_data="exchange_referral_balance")])

        # Добавляем кнопку вывода средств (проверка будет при нажатии)
        keyboard_buttons.append([InlineKeyboardButton(
            text="💸 Вывод средств", callback_data="referral_withdrawal")])

        keyboard_buttons.append([InlineKeyboardButton(
            text="🔙 Назад", callback_data="back_to_profile")])

        msg = await callback.message.edit_text(
            text=get_referral_message(callback.from_user.id),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )

        # Сохраняем ID активного сообщения
        active_user_messages[callback.from_user.id] = msg.message_id

        await callback.answer()
    except Exception as e:
        print(f"Ошибка в show_referral_program: {e}")
        await callback.answer("Произошла ошибка при загрузке реферальной программы")


@error_handler
async def handle_exchange_referral_balance(callback: CallbackQuery):
    """Обработчик обмена реферального баланса на баланс покупок"""
    from database import get_user, transfer_referral_to_purchase_balance
    from messages import get_referral_message

    user_id = callback.from_user.id

    # Проверяем, является ли это сообщение активным
    if user_id in active_user_messages and active_user_messages[user_id] != callback.message.message_id:
        # Удаляем старое сообщение пользователя, если оно существует
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer("Пожалуйста, используйте актуальное меню. Повторите действие.", show_alert=True)
        return

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
            keyboard_buttons = []
            if referral_balance > 0:
                keyboard_buttons.append([InlineKeyboardButton(
                    text="💱 Обменять на баланс покупок", callback_data="exchange_referral_balance")])
            keyboard_buttons.append([InlineKeyboardButton(
                text="💸 Вывод средств", callback_data="referral_withdrawal")])
            keyboard_buttons.append([InlineKeyboardButton(
                text="🔙 Назад", callback_data="back_to_profile")])

            msg = await callback.message.edit_text(
                text=get_referral_message(user_id),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=keyboard_buttons)
            )

            # Обновляем ID активного сообщения
            active_user_messages[user_id] = msg.message_id
        else:
            await callback.answer("❌ Ошибка при переводе средств", show_alert=True)

    except Exception as e:
        print(f"Ошибка при обмене баланса: {e}")
        await callback.answer("❌ Ошибка при обмене баланса", show_alert=True)


@error_handler
async def show_clean_profile_menu(callback: CallbackQuery):
    """Показывает чистое меню профиля"""
    # Проверяем, является ли это сообщение активным
    if callback.from_user.id in active_user_messages and active_user_messages[callback.from_user.id] != callback.message.message_id:
        # Удаляем старое сообщение пользователя, если оно существует
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer("Пожалуйста, используйте актуальное меню. Повторите действие.", show_alert=True)
        return

    user = get_user(callback.from_user.id)
    if not user:
        try:
            msg = await callback.message.edit_text(
                "❌ Профиль не найден. Пожалуйста, запустите бота командой /start",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_main")]
                ])
            )
            active_user_messages[callback.from_user.id] = msg.message_id
        except Exception:
            msg = await callback.message.answer(
                "❌ Профиль не найден. Пожалуйста, запустите бота командой /start",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_main")]
                ])
            )
            try:
                await callback.message.delete()
            except:
                pass
            active_user_messages[callback.from_user.id] = msg.message_id
        await callback.answer()
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
            [InlineKeyboardButton(
                text="🔙 Назад", callback_data="back_to_main")]
        ])

    # Пытаемся отредактировать сообщение
    try:
        msg = await callback.message.edit_text(
            text=full_text,
            reply_markup=keyboard
        )
        active_user_messages[callback.from_user.id] = msg.message_id
    except Exception:
        # Если не удалось отредактировать, отправляем новое сообщение
        msg = await callback.message.answer(
            text=full_text,
            reply_markup=keyboard
        )
        try:
            await callback.message.delete()
        except:
            pass
        active_user_messages[callback.from_user.id] = msg.message_id

    await callback.answer()


@error_handler
async def show_profile(callback: CallbackQuery):
    await show_clean_profile_menu(callback)


@error_handler
async def deposit_balance(callback: CallbackQuery):
    """Обработчик кнопки пополнения баланса"""
    # Проверяем, является ли это сообщение активным
    if callback.from_user.id in active_user_messages and active_user_messages[callback.from_user.id] != callback.message.message_id:
        # Удаляем старое сообщение пользователя, если оно существует
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer("Пожалуйста, используйте актуальное меню. Повторите действие.", show_alert=True)
        return

    user_id = callback.from_user.id
    user_states[user_id] = "waiting_for_amount"  # Устанавливаем состояние
    from bot import message_history, last_bot_messages
    # Очищаем и показываем меню пополнения
    try:
        msg = await callback.message.edit_text(
            "💰 <b>Пополнение баланса</b>\n\n"
            "Введите сумму пополнения в рублях (минимум 100 руб.):\n\n"
            "Или нажмите 'Отмена' для возврата в профиль.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Отмена", callback_data="profile")]
            ])
        )

        # Сохраняем сообщение в историю
        chat_id = callback.message.chat.id
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        # Добавляем в начало списка, чтобы потом легко удалить
        message_history[chat_id]['bot_msgs'].insert(0, msg)

        # Сохраняем ID активного сообщения
        active_user_messages[user_id] = msg.message_id

    except Exception:
        msg = await callback.message.answer(
            "💰 <b>Пополнение баланса</b>\n\n"
            "Введите сумму пополнения в рублях (минимум 100 руб.):\n\n"
            "Или нажмите 'Отмена' для возврата в профиль.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Отмена", callback_data="profile")]
            ])
        )
        try:
            await callback.message.delete()
        except:
            pass

        # Сохраняем сообщение в историю
        chat_id = callback.message.chat.id
        if chat_id not in message_history:
            message_history[chat_id] = {'user_msgs': [], 'bot_msgs': []}
        # Добавляем в начало списка, чтобы потом легко удалить
        message_history[chat_id]['bot_msgs'].insert(0, msg)
        if chat_id in last_bot_messages:
            last_bot_messages[chat_id] = msg

        # Сохраняем ID активного сообщения
        active_user_messages[user_id] = msg.message_id

    await callback.answer()


@error_handler
async def process_deposit_amount(message: Message):
    """Обработка введенной суммы пополнения"""
    user_id = message.from_user.id

    # Проверяем, ожидаем ли мы ввод суммы от этого пользователя
    if user_id not in user_states or user_states[user_id] != "waiting_for_amount":
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except:
            pass
        return  # Если не ожидаем, пропускаем обработку

    # Очищаем сообщения пополнения баланса
    await clean_deposit_messages(message.chat.id)

    # Убираем состояние пользователя
    if user_id in user_states:
        del user_states[user_id]

    # Удаляем сообщение пользователя с суммой
    try:
        await message.delete()
    except:
        pass

    try:
        # Проверяем формат ввода
        amount_text = message.text.strip()

        # Проверяем, является ли ввод отменой
        if amount_text.lower() in ['отмена', 'cancel', 'назад']:
            # Возвращаем пользователя в профиль
            await show_clean_profile_menu_from_message(message)
            return

        # Извлекаем числовое значение
        amount_match = re.search(r'\d+', amount_text)
        if not amount_match:
            error_msg = await message.answer(
                "❌ Пожалуйста, введите корректную сумму (только цифры)\n\n"
                "Пример: 500"
            )
            user_states[user_id] = "waiting_for_amount"  # Возвращаем состояние
            # Удаляем сообщение об ошибке через 3 секунды
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
            except:
                pass
            return

        amount = int(amount_match.group())

        # Проверяем минимальную сумму
        if amount < 100:
            error_msg = await message.answer(
                "❌ Минимальная сумма пополнения: 100 руб.\n\n"
                "Введите другую сумму или нажмите 'Отмена'"
            )
            user_states[user_id] = "waiting_for_amount"  # Возвращаем состояние
            # Удаляем сообщение об ошибке через 3 секунды
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
            except:
                pass
            return

        if amount > 15000:
            error_msg = await message.answer(
                "❌ Максимальная сумма пополнения: 15000 руб.\n\n"
                "Введите другую сумму или нажмите 'Отмена'"
            )
            user_states[user_id] = "waiting_for_amount"  # Возвращаем состояние
            # Удаляем сообщение об ошибке через 3 секунды
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
            except:
                pass
            return

        # Создаем платеж через ЮKassa
        from yookassa_integration import create_payment
        payment_url, payment_id = await create_payment(
            user_id=user_id,
            amount=amount,
            description=f"Пополнение баланса на {amount} руб."
        )

        if payment_url:
            # Отправляем сообщение о платеже с автообновлением
            try:
                payment_msg = await message.answer(
                    f"💳 <b>Платёж создан</b>\n\n"
                    f"Сумма: <b>{amount} руб.</b>\n\n"
                    f"Нажмите кнопку ниже для оплаты:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="💳 Оплатить", url=payment_url)]
                    ])
                )

                # Сохраняем информацию для автообновления
                payment_checks[payment_id] = {
                    'user_id': user_id,
                    'message_id': payment_msg.message_id,  # Сохраняем ID сообщения о платеже
                    'chat_id': message.chat.id,
                    'amount': amount,
                    'check_count': 0,
                    'handled': False
                }

                # Запускаем задачу для автообновления статуса
                asyncio.create_task(auto_check_payment(payment_id))

            except Exception as e:
                print(f"Ошибка при отправке сообщения о платеже: {e}")
                payment_msg = await message.answer(
                    "❌ Ошибка при создании платежа. Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="👤 Профиль", callback_data="profile")]
                    ])
                )
        else:
            payment_msg = await message.answer(
                "❌ Произошла ошибка при создании платежа. Попробуйте позже или обратитесь в поддержку.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="👤 Профиль", callback_data="profile")]
                ])
            )

        # Сохраняем ID активного сообщения
        active_user_messages[user_id] = payment_msg.message_id

    except ValueError:
        error_msg = await message.answer(
            "❌ Пожалуйста, введите корректную сумму (только цифры)\n\n"
            "Пример: 500"
        )
        user_states[user_id] = "waiting_for_amount"  # Возвращаем состояние
        # Удаляем сообщение об ошибке через 3 секунды
        await asyncio.sleep(3)
        try:
            await error_msg.delete()
        except:
            pass
    except Exception as e:
        print(f"Ошибка при обработке суммы пополнения: {e}")
        error_msg = await message.answer(
            "❌ Произошла ошибка при обработке запроса. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="👤 Профиль", callback_data="profile")]
            ])
        )
        # Сохраняем ID активного сообщения
        active_user_messages[user_id] = error_msg.message_id


@error_handler
async def clean_deposit_messages(chat_id: int):
    """Очищает сообщения, связанные с пополнением баланса"""
    try:
        from state import message_history, last_bot_messages
        if chat_id in message_history:
            bot_msgs = message_history[chat_id]['bot_msgs']
            for msg in bot_msgs[:]:  # Копируем список для безопасного удаления
                if msg and hasattr(msg, 'message_id'):
                    try:
                        text = msg.text if hasattr(msg, 'text') else ""
                        if "💰 Пополнение баланса" in text or "Введите сумму пополнения" in text:
                            await bot.delete_message(chat_id, msg.message_id)
                            if msg in message_history[chat_id]['bot_msgs']:
                                message_history[chat_id]['bot_msgs'].remove(
                                    msg)
                    except:
                        pass
    except Exception as e:
        print(f"Ошибка при очистке сообщений пополнения: {e}")


@error_handler
async def auto_check_payment(payment_id: str):
    """Автоматическая проверка статуса платежа"""
    try:
        # Ждем немного перед первой проверкой
        await asyncio.sleep(5)

        payment_info = payment_checks.get(payment_id)
        if not payment_info:
            return

        max_checks = 12
        check_interval = 5  # секунд

        for _ in range(max_checks):
            try:
                # Используем существующую функцию проверки статуса
                from yookassa_integration import check_payment_status, processed_payments

                # Проверяем, не обработан ли уже платеж
                if payment_id in processed_payments:
                    print(
                        f"Авто-проверка: платеж {payment_id} уже обработан глобально, прекращаем проверку")
                    break

                status = await check_payment_status(payment_id)

                print(f"Авто-проверка {payment_id}: статус = {status}")

                if status == "succeeded":
                    print(
                        f"Авто-проверка: платеж {payment_id} успешен, прекращаем проверку")
                    break

                elif status == "canceled":
                    print(
                        f"Авто-проверка: платеж {payment_id} отменен, прекращаем проверку")
                    break

                elif status == "pending":
                    # Продолжаем проверку
                    await asyncio.sleep(check_interval)
                    continue
                else:
                    await asyncio.sleep(check_interval)
                    continue

            except Exception as e:
                print(
                    f"Ошибка при автоматической проверке платежа {payment_id}: {e}")
                await asyncio.sleep(check_interval)
                continue

        # Очищаем информацию о платеже
        if payment_id in payment_checks:
            del payment_checks[payment_id]

    except Exception as e:
        print(f"Ошибка в auto_check_payment: {e}")


@error_handler
async def handle_successful_payment(payment_info: dict, payment_id: str):
    """Обработка успешного платежа"""
    try:
        user_id = payment_info['user_id']
        chat_id = payment_info['chat_id']
        payment_message_id = payment_info.get(
            'message_id')  # ID сообщения о платеже
        amount = payment_info['amount']

        # Обновляем баланс пользователя
        update_purchase_balance(user_id, amount)

        # 1. Удаляем сообщение о платеже (если знаем его ID)
        if payment_message_id:
            try:
                await bot.delete_message(chat_id, payment_message_id)
                print(f"Сообщение о платеже {payment_message_id} удалено")
            except Exception as e:
                print(f"Не удалось удалить сообщение о платеже: {e}")

        # 2. Отправляем временное уведомление об успехе
        success_msg = None
        try:
            success_msg = await bot.send_message(
                chat_id,
                f"✅ Баланс успешно пополнен на {amount} руб.!"
            )
        except Exception as e:
            print(f"Ошибка при отправке уведомления об успехе: {e}")

        # 3. Сразу показываем профиль
        try:
            user = get_user(user_id)
            if user:
                from messages import get_profile_text, get_subscription_info_text
                profile_text = get_profile_text(user)
                sub_text = get_subscription_info_text(user)
                full_text = f"{profile_text}\n\n{sub_text}"

                profile_msg = await bot.send_message(
                    chat_id,
                    full_text,
                    reply_markup=get_profile_keyboard(user_id)
                )

                # Сохраняем ID сообщения профиля
                from bot import profile_message_ids
                profile_message_ids[user_id] = profile_msg.message_id

                # Сохраняем ID активного сообщения
                active_user_messages[user_id] = profile_msg.message_id
        except Exception as e:
            print(f"Ошибка при показе профиля: {e}")

        # 4. Удаляем уведомление об успехе через 3 секунды (если оно было отправлено)
        if success_msg:
            await asyncio.sleep(3)
            try:
                await success_msg.delete()
                print("Уведомление об успехе удалено")
            except Exception as e:
                print(f"Не удалось удалить уведомление об успехе: {e}")

        # Удаляем информацию о платеже
        if payment_id in payment_checks:
            del payment_checks[payment_id]

    except Exception as e:
        print(f"Ошибка при обработке успешного платежа: {e}")


@error_handler
async def handle_canceled_payment(payment_info: dict, payment_id: str):
    """Обработка отмененного платежа"""
    try:
        user_id = payment_info['user_id']
        chat_id = payment_info['chat_id']
        message_id = payment_info['message_id']

        # Обновляем сообщение о платеже
        try:
            msg = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Платеж был отменен или истек.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="💳 Повторить", callback_data="deposit")]
                ])
            )
            # Сохраняем ID активного сообщения
            active_user_messages[user_id] = msg.message_id
        except:
            pass

        # Удаляем информацию о платеже через 30 секунд
        await asyncio.sleep(30)
        if payment_id in payment_checks:
            del payment_checks[payment_id]

    except Exception as e:
        print(f"Ошибка при обработке отмененного платежа: {e}")


@error_handler
async def handle_referral_withdrawal_request(callback: CallbackQuery):
    """Обработчик запроса на вывод реферальных средств"""
    from database import get_user

    # Проверяем, является ли это сообщение активным
    if callback.from_user.id in active_user_messages and active_user_messages[callback.from_user.id] != callback.message.message_id:
        # Удаляем старое сообщение пользователя, если оно существует
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer("Пожалуйста, используйте актуальное меню. Повторите действие.", show_alert=True)
        return

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
    user_states[user_id] = 'waiting_for_withdrawal_amount'

    msg = await callback.message.edit_text(
        f"Введите сумму для вывода (баланс: {referral_balance} руб.):\n"
        f"Минимальная сумма: {MIN_REFERRAL_WITHDRAWAL} руб.\n\n"
        f"Или отправьте 'отмена' для отмены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="referral")]
        ])
    )

    # Сохраняем ID активного сообщения
    active_user_messages[user_id] = msg.message_id
    await callback.answer()


@error_handler
async def process_referral_withdrawal_amount(message: Message):
    """Обработка введенной суммы для вывода"""
    user_id = message.from_user.id

    # Проверяем, ожидаем ли мы ввод суммы от этого пользователя
    if user_id not in user_states or user_states[user_id] != 'waiting_for_withdrawal_amount':
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except:
            pass
        return

    # Убираем состояние пользователя
    if user_id in user_states:
        del user_states[user_id]

    try:
        amount_text = message.text.strip().lower()

        # Проверяем, является ли ввод отменой
        if amount_text in ['отмена', 'cancel', 'назад']:
            # Возвращаем пользователя в реферальную программу
            from profile import show_referral_program
            callback_data = type('CallbackData', (), {
                'from_user': type('FromUser', (), {'id': user_id}),
                'message': message
            })()
            await show_referral_program(callback_data)
            return

        # Извлекаем числовое значение
        amount_match = re.search(r'\d+', amount_text)
        if not amount_match:
            error_msg = await message.answer(
                "❌ Пожалуйста, введите корректную сумму (только цифры)\n\n"
                "Пример: 500"
            )
            user_states[user_id] = 'waiting_for_withdrawal_amount'
            # Удаляем сообщение об ошибке через 3 секунды
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
            except:
                pass
            return

        amount = int(amount_match.group())

        # Получаем баланс пользователя
        from database import get_user
        user = get_user(user_id)
        if not user:
            error_msg = await message.answer("Пользователь не найден")
            # Сохраняем ID активного сообщения
            active_user_messages[user_id] = error_msg.message_id
            return

        referral_balance = user.get('referral_balance', 0)

        # Проверяем минимальную сумму
        if amount < MIN_REFERRAL_WITHDRAWAL:
            error_msg = await message.answer(
                f"❌ Минимальная сумма для вывода: {MIN_REFERRAL_WITHDRAWAL} руб.\n\n"
                "Введите другую сумму или отправьте 'отмена'"
            )
            user_states[user_id] = 'waiting_for_withdrawal_amount'
            # Удаляем сообщение об ошибке через 3 секунды
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
            except:
                pass
            return

        # Проверяем, достаточно ли средств
        if amount > referral_balance:
            error_msg = await message.answer(
                f"❌ Недостаточно средств на реферальном балансе.\n"
                f"Ваш баланс: {referral_balance} руб.\n\n"
                "Введите другую сумму или отправьте 'отмена'"
            )
            user_states[user_id] = 'waiting_for_withdrawal_amount'
            # Удаляем сообщение об ошибке через 3 секунды
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
            except:
                pass
            return

        # Здесь должна быть логика вывода средств
        # Пока просто вычтем сумму из реферального баланса
        from database import update_referral_balance
        update_referral_balance(user_id, -amount)

        # Отправляем уведомление администратору (здесь должна быть реальная логика вывода)
        try:
            from config import ROOT_ADMIN_ID
            from shared import bot
            await bot.send_message(
                ROOT_ADMIN_ID,
                f"Пользователь {user_id} запросил вывод реферальных средств:\n"
                f"Сумма: {amount} руб.\n"
                f"Username: @{message.from_user.username if message.from_user.username else 'не указан'}"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления админу: {e}")

        # Уведомляем пользователя
        success_msg = await message.answer(
            f"✅ Заявка на вывод {amount} руб. отправлена на обработку!\n"
            f"Администратор свяжется с вами в ближайшее время."
        )

        # Возвращаем в реферальную программу через 3 секунды
        await asyncio.sleep(3)
        from profile import show_referral_program
        callback_data = type('CallbackData', (), {
            'from_user': type('FromUser', (), {'id': user_id}),
            'message': message
        })()
        await show_referral_program(callback_data)

    except ValueError:
        error_msg = await message.answer(
            "❌ Пожалуйста, введите корректную сумму (только цифры)\n\n"
            "Пример: 500"
        )
        user_states[user_id] = 'waiting_for_withdrawal_amount'
        # Удаляем сообщение об ошибке через 3 секунды
        await asyncio.sleep(3)
        try:
            await error_msg.delete()
        except:
            pass
    except Exception as e:
        print(f"Ошибка при обработке суммы вывода: {e}")
        error_msg = await message.answer(
            "❌ Произошла ошибка при обработке запроса. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="👥 Реферальная программа", callback_data="referral")]
            ])
        )
        # Сохраняем ID активного сообщения
        active_user_messages[user_id] = error_msg.message_id


@error_handler
async def show_clean_profile_menu_from_message(message: Message):
    """Показать чистое меню профиля из текстового сообщения"""
    from messages import get_profile_text, get_subscription_info_text
    user = get_user(message.from_user.id)
    if not user:
        error_msg = await message.answer("Сначала запустите бота командой /start")
        # Сохраняем ID активного сообщения
        active_user_messages[message.from_user.id] = error_msg.message_id
        return

    try:
        profile_text = get_profile_text(user)
        sub_text = get_subscription_info_text(user)
        full_text = f"{profile_text}\n\n{sub_text}"
    except Exception as e:
        print(f"Ошибка формирования текста профиля: {str(e)}")
        full_text = "❌ Не удалось загрузить данные профиля"

    try:
        keyboard = get_profile_keyboard(message.from_user.id)
    except Exception as e:
        print(f"Ошибка создания клавиатуры: {str(e)}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 Назад", callback_data="back_to_main")]
        ])

    # Очищаем чат и показываем профиль
    try:
        from bot import clean_previous_messages
        await clean_previous_messages(message.chat.id)
        msg = await message.answer(full_text, reply_markup=keyboard)

        # Обновляем историю сообщений
        from state import message_history, last_bot_messages
        if message.chat.id not in message_history:
            message_history[message.chat.id] = {
                'user_msgs': [], 'bot_msgs': []}
        message_history[message.chat.id]['bot_msgs'].append(msg)
        last_bot_messages[message.chat.id] = msg

        # Сохраняем ID активного сообщения
        active_user_messages[message.from_user.id] = msg.message_id

    except Exception as e:
        print(f"Ошибка при показе профиля: {e}")
        msg = await message.answer(full_text, reply_markup=keyboard)
        # Сохраняем ID активного сообщения
        active_user_messages[message.from_user.id] = msg.message_id

__all__ = ['get_profile_keyboard', 'show_referral_program', 'handle_exchange_referral_balance',
           'show_clean_profile_menu', 'show_profile', 'deposit_balance', 'process_deposit_amount',
           'handle_referral_withdrawal_request', 'process_referral_withdrawal_amount']
