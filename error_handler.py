import traceback
import asyncio
from functools import wraps
from error_logger import log_error
from config import ROOT_ADMIN_ID
from shared import bot


def error_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Игнорируем предупреждения о неизмененном сообщении
            if "message is not modified" in str(e).lower():
                # Просто отвечаем callback'ом и выходим
                for arg in args:
                    if hasattr(arg, 'answer'):
                        try:
                            await arg.answer()
                        except:
                            pass
                        break
                return  # Не логируем эту "ошибку"

            # Логируем все остальные ошибки
            error_type = type(e).__name__
            error_message = str(e)
            tb = traceback.format_exc()

            # Определяем user_id из аргументов если возможно
            user_id = None
            for arg in args:
                if hasattr(arg, 'from_user') and hasattr(arg.from_user, 'id'):
                    user_id = arg.from_user.id
                    break

            log_error(error_type, error_message, tb, user_id)

            # Отправляем уведомление главному админу
            if ROOT_ADMIN_ID:
                try:
                    admin_message = (
                        f"🔴 <b>Произошла ошибка в боте</b>\n\n"
                        f"❌ <b>Функция:</b> {func.__name__}\n"
                        f"👤 <b>Пользователь:</b> {user_id or 'N/A'}\n"
                        f"❗ <b>Тип ошибки:</b> {error_type}\n"
                        f"📄 <b>Сообщение:</b> {error_message[:200]}...\n"
                        f"🔍 <b>Traceback:</b>\n<code>{tb[:500]}...</code>"
                    )
                    await bot.send_message(ROOT_ADMIN_ID, admin_message)
                except Exception:
                    pass  # Игнорируем ошибки при отправке уведомления

            # Пытаемся ответить пользователю
            try:
                # Определяем объект сообщения или callback из аргументов
                msg_obj = None
                for arg in args:
                    if hasattr(arg, 'message'):
                        msg_obj = arg
                        break
                    elif hasattr(arg, 'answer'):
                        msg_obj = arg
                        break

                if msg_obj:
                    if hasattr(msg_obj, 'answer'):
                        await msg_obj.answer("⚠️ Произошла ошибка. Администраторы уведомлены.")
                    elif hasattr(msg_obj, 'edit_text'):
                        await msg_obj.edit_text("⚠️ Произошла ошибка. Администраторы уведомлены.")
            except Exception:
                pass  # Игнорируем ошибки при отправке сообщения пользователю

    return wrapper


def sync_error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Логируем ошибку
            error_type = type(e).__name__
            error_message = str(e)
            tb = traceback.format_exc()

        # Определяем user_id из аргументов если возможно
        user_id = None
        for arg in args:
            if hasattr(arg, 'from_user') and hasattr(arg.from_user, 'id'):
                user_id = arg.from_user.id
                break

        log_error(error_type, error_message, tb, user_id)

        # Отправляем уведомление главному админу (используем asyncio.create_task)
        if ROOT_ADMIN_ID:
            try:
                admin_message = (
                    f"🔴 <b>Произошла ошибка в боте</b>\n\n"
                    f"❌ <b>Функция:</b> {func.__name__}\n"
                    f"👤 <b>Пользователь:</b> {user_id or 'N/A'}\n"
                    f"❗ <b>Тип ошибки:</b> {error_type}\n"
                    f"📄 <b>Сообщение:</b> {error_message[:200]}...\n"
                    f"🔍 <b>Traceback:</b>\n<code>{tb[:500]}...</code>"
                )
                # Используем create_task вместо threading.Thread
                asyncio.create_task(bot.send_message(
                    ROOT_ADMIN_ID, admin_message))
            except Exception:
                pass  # Игнорируем ошибки при отправке уведомления

    return wrapper
