# shared.py
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from config import API_TOKEN
from aiogram.enums import ParseMode

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Глобальные состояния
user_modes = {}
last_bot_messages = {}
message_history = {}
chat_histories = {}

def get_bot():
    return bot