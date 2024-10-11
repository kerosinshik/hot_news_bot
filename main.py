import logging
from hot_news_bot.bot import NewsBot
from hot_news_bot.utils import setup_logging
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение значений переменных
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')

# Проверка наличия обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден в файле .env")
if not TELEGRAM_CHANNEL_ID:
    raise ValueError("TELEGRAM_CHANNEL_ID не найден в файле .env")
if not ADMIN_CHAT_ID:
    raise ValueError("ADMIN_CHAT_ID не найден в файле .env")

def main():
    setup_logging()
    newsbot = NewsBot(TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, TELEGRAM_CHANNEL_ID)
    newsbot.bot.newsbot = newsbot

    try:
        newsbot.run()
    except KeyboardInterrupt:
        logging.info("Получен сигнал завершения. Останавливаем бота...")
    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка: {e}")
        logging.exception("Полный стек вызовов:")
    finally:
        newsbot.stop()

if __name__ == '__main__':
    main()