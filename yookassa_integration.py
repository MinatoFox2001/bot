import uuid
import asyncio
from yookassa import Payment, Configuration  # type: ignore
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
from database import update_purchase_balance
from shared import bot
from error_handler import error_handler

# Инициализация yookassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Хранение состояния платежей
active_payments = {}

processed_payments = set()

# Блокировки для предотвращения параллельных обработок
payment_locks = {}


@error_handler
async def create_payment(user_id: int, amount: float, description: str = "Пополнение баланса"):
    """
    Создает платеж через ЮKassa
    :param user_id: ID пользователя
    :param amount: Сумма платежа
    :param description: Описание платежа
    :return: Ссылка на оплату или None
    """
    try:
        # Генерируем уникальный ID для платежа
        payment_id = str(uuid.uuid4())

        # Создаем платеж
        payment = Payment.create({
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/zenith_ii_bot"
            },
            "description": description,
            "capture": True,
            "metadata": {
                "user_id": str(user_id),
                "payment_id": payment_id
            }
        })

        # Сохраняем информацию о платеже
        active_payments[payment_id] = {
            "user_id": user_id,
            "amount": amount,
            "status": "pending",
            "yookassa_payment_id": payment.id,
            "processed": False
        }

        # Создаем lock для этого платежа
        payment_locks[payment_id] = asyncio.Lock()

        # Возвращаем ссылку для оплаты
        return payment.confirmation.confirmation_url, payment_id

    except Exception as e:
        print(f"Ошибка создания платежа: {e}")
        return None, None


@error_handler
async def check_payment_status(payment_id: str):
    """
    Проверяет статус платежа (ручная проверка)
    :param payment_id: ID платежа в нашей системе
    :return: Статус платежа
    """
    try:
        if payment_id not in active_payments:
            print(f"Платеж {payment_id} не найден в active_payments")
            return "not_found"

        # Проверяем, не обработан ли уже этот платеж
        if payment_id in processed_payments:
            print(
                f"Платеж {payment_id} уже обработан глобально, возвращаем статус")
            return active_payments[payment_id]["status"]

        # Получаем lock для этого платежа
        lock = payment_locks.get(payment_id)
        if not lock:
            lock = asyncio.Lock()
            payment_locks[payment_id] = lock

        # Ждем освобождения lock
        async with lock:
            # Двойная проверка после получения блокировки
            if payment_id in processed_payments:
                print(
                    f"Платеж {payment_id} уже обработан глобально (после блокировки)")
                return active_payments[payment_id]["status"]

            # Проверяем, не был ли платеж уже обработан
            if active_payments[payment_id].get("processed", False):
                print(
                    f"Платеж {payment_id} уже обработан, возвращаем статус {active_payments[payment_id]['status']}")
                # Добавляем в глобальный набор
                processed_payments.add(payment_id)
                return active_payments[payment_id]["status"]

            print(f"НАЧАЛО ОБРАБОТКИ ПЛАТЕЖА: {payment_id}")

            yookassa_payment_id = active_payments[payment_id]["yookassa_payment_id"]

            # Получаем информацию о платеже из ЮKassa
            payment_info = Payment.find_one(yookassa_payment_id)

            status = payment_info.status
            print(f"Статус платежа {payment_id}: {status}")

            # Обновляем статус в нашей системе
            active_payments[payment_id]["status"] = status

            if status == "succeeded":
                # Только если платеж еще не обработан
                if not active_payments[payment_id].get("processed", False):
                    user_id = active_payments[payment_id]["user_id"]
                    amount = int(active_payments[payment_id]["amount"])

                    print(
                        f"НАЧИСЛЕНИЕ БАЛАНСА: пользователь {user_id}, сумма {amount}")
                    update_purchase_balance(user_id, amount)

                    # Помечаем как обработанный
                    active_payments[payment_id]["processed"] = True
                    # Добавляем в глобальный набор
                    processed_payments.add(payment_id)
                    print(f"Платеж {payment_id} помечен как обработанный")

                    # Получаем информацию о сообщении платежа из payment_checks
                    from profile import payment_checks
                    payment_message_id = None
                    if payment_id in payment_checks:
                        payment_message_id = payment_checks[payment_id].get(
                            'message_id')

                    # Отправляем уведомление через handle_successful_payment
                    from profile import handle_successful_payment
                    payment_data = {
                        'user_id': user_id,
                        'chat_id': user_id,  # Для личных сообщений chat_id = user_id
                        'message_id': payment_message_id,  # Передаем ID сообщения о платеже
                        'amount': amount
                    }
                    await handle_successful_payment(payment_data, payment_id)

                else:
                    print(f"Платеж {payment_id} уже был обработан ранее")

            elif status in ["canceled", "expired"]:
                # Помечаем отмененные/истекшие платежи как обработанные
                active_payments[payment_id]["processed"] = True
                # Добавляем в глобальный набор
                processed_payments.add(payment_id)
                print(
                    f"Платеж {payment_id} отменен/истек, помечен как обработанный")

            return status

    except Exception as e:
        print(f"Ошибка проверки статуса платежа: {e}")
        return "error"


@error_handler
async def handle_payment_webhook(request_data: dict):
    """
    Обрабатывает вебхуки от ЮKassa (автоматически)
    :param request_data: Данные вебхука
    """
    try:
        print("ПОЛУЧЕН ВЕБХУК:", request_data)

        # Проверяем тип события
        if request_data.get("event") == "payment.succeeded":
            # Получаем метаданные платежа
            metadata = request_data.get("object", {}).get("metadata", {})
            payment_id = metadata.get("payment_id")
            yookassa_payment_id = request_data.get("object", {}).get("id")

            print(
                f"ВЕБХУК: обработка платежа {payment_id}, yookassa_id: {yookassa_payment_id}")

            # Проверяем, не обработан ли уже этот платеж
            if payment_id in processed_payments:
                print(f"ВЕБХУК: платеж {payment_id} уже обработан, пропускаем")
                return {"status": "already_processed"}

            if payment_id and payment_id in active_payments:
                # Получаем lock для этого платежа
                lock = payment_locks.get(payment_id)
                if not lock:
                    lock = asyncio.Lock()
                    payment_locks[payment_id] = lock

                # Ждем освобождения lock
                async with lock:
                    # Двойная проверка после получения блокировки
                    if payment_id in processed_payments:
                        print(
                            f"ВЕБХУК: платеж {payment_id} уже обработан (после блокировки), пропускаем")
                        return {"status": "already_processed"}

                    # Проверяем, не был ли уже обработан
                    if not active_payments[payment_id].get("processed", False):
                        print(
                            f"ВЕБХУК: начисление баланса для платежа {payment_id}")

                        # Обновляем статус платежа
                        active_payments[payment_id]["status"] = "succeeded"

                        # Пополняем баланс пользователя ТОЛЬКО ОДИН РАЗ
                        user_id = active_payments[payment_id]["user_id"]
                        amount = int(active_payments[payment_id]["amount"])

                        print(
                            f"ВЕБХУК НАЧИСЛЕНИЕ: пользователь {user_id}, сумма {amount}")
                        update_purchase_balance(user_id, amount)

                        # Помечаем как обработанный
                        active_payments[payment_id]["processed"] = True
                        # Добавляем в глобальный набор
                        processed_payments.add(payment_id)
                        print(
                            f"ВЕБХУК: платеж {payment_id} помечен как обработанный")

                        # Получаем информацию о сообщении платежа из payment_checks
                        from profile import payment_checks
                        payment_message_id = None
                        if payment_id in payment_checks:
                            payment_message_id = payment_checks[payment_id].get(
                                'message_id')

                        # Отправляем уведомление через handle_successful_payment
                        from profile import handle_successful_payment
                        payment_data = {
                            'user_id': user_id,
                            'chat_id': user_id,  # Для личных сообщений chat_id = user_id
                            'message_id': payment_message_id,  # Передаем ID сообщения о платеже
                            'amount': amount
                        }
                        await handle_successful_payment(payment_data, payment_id)

                    else:
                        print(
                            f"ВЕБХУК: платеж {payment_id} уже обработан, пропускаем")
                        # Все равно добавляем
                        processed_payments.add(payment_id)
            else:
                print(
                    f"ВЕБХУК: платеж {payment_id} не найден в active_payments")

        return {"status": "success"}

    except Exception as e:
        print(f"Ошибка обработки вебхука: {e}")
        return {"status": "error"}


@error_handler
async def cleanup_old_payments():
    """Очищает устаревшие платежи и locks"""
    try:
        import time
        current_time = time.time()

        # Удаляем обработанные платежи старше 24 часов из глобального набора
        global processed_payments
        # Здесь можно добавить логику для очистки старых записей, если нужно

        # Удаляем обработанные платежи старше 1 часа из active_payments
        to_remove = []
        for payment_id, payment_data in active_payments.items():
            if payment_data.get("processed", False):
                # Здесь можно добавить проверку времени создания платежа
                to_remove.append(payment_id)

        for payment_id in to_remove:
            if payment_id in active_payments:
                del active_payments[payment_id]
            if payment_id in payment_locks:
                del payment_locks[payment_id]

    except Exception as e:
        print(f"Ошибка очистки старых платежей: {e}")
