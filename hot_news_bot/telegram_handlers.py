import logging
from telebot import TeleBot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telebot.apihelper import ApiTelegramException
from datetime import datetime, timedelta
from typing import List, Dict, Any
from .database import get_post_stats, get_top_articles, get_last_publication_time, get_publications_in_last_hour
from .publisher import publish_digest
from .article_processor import get_article_scores, process_articles
from .rss_parser import fetch_articles
from .utils import to_moscow_time
from config import ADMIN_CHAT_ID

logger = logging.getLogger(__name__)


def setup_bot_commands(bot: TeleBot):
    """Устанавливает команды бота."""
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("help", "Показать справку"),
        BotCommand("status", "Проверить статус бота"),
        BotCommand("stats", "Показать статистику публикаций"),
        BotCommand("top", "Показать топ статей"),
        BotCommand("hot", "Показать самые горячие новости"),  # Заменили "events" на "hot"
        BotCommand("pause", "Приостановить публикации"),
        BotCommand("resume", "Возобновить публикации"),
        BotCommand("scores", "Показать таблицу оценок статей"),
        BotCommand("optimal_time", "Показать оптимальное время публикаций")
    ]
    bot.set_my_commands(commands)


def send_initial_message(bot: TeleBot, admin_chat_id: str):
    """Отправляет начальное сообщение администратору при запуске бота."""
    message = (
        "🤖 Бот запущен и готов к работе!\n\n"
        "Доступные команды:\n"
        "/status - Проверить статус бота\n"
        "/stats - Показать статистику публикаций\n"
        "/top - Показать топ статей\n"
        "/hot - Показать самые горячие новости\n"  # Заменили "events" на "hot"
        "/pause - Приостановить публикации\n"
        "/resume - Возобновить публикации\n"
        "/scores - Показать таблицу оценок статей\n"
        "/optimal_time - Показать оптимальное время публикаций\n"
        "/help - Показать эту справку"
    )
    bot.send_message(admin_chat_id, message)


def register_handlers(bot: TeleBot):
    """Регистрирует обработчики команд и сообщений."""
    logger.info("Начало регистрации обработчиков команд")

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message: Message):
        bot.reply_to(message, "Привет! Я бот для публикации новостей. Используй /help для получения списка команд.")

    @bot.message_handler(commands=['status'])
    def send_status(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return

        newsbot = bot.newsbot
        status = "🤖 Статус бота:\n\n"

        if newsbot.is_paused():
            status += "📴 Бот на паузе\n"
            status += f"⏳ Пауза до: {to_moscow_time(newsbot.pause_until).strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            status += "✅ Бот активен и публикует новости\n"

        last_publication = get_last_publication_time()
        if last_publication:
            status += f"🕒 Последняя публикация: {to_moscow_time(last_publication).strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            status += "🕒 Публикаций еще не было\n"

        publications_last_hour = get_publications_in_last_hour()
        status += f"📊 Публикаций за последний час: {publications_last_hour}\n"

        bot.reply_to(message, status)

    @bot.message_handler(commands=['stats'])
    def send_stats(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return
        stats = get_post_stats(7)  # Статистика за последнюю неделю
        response = "📊 Статистика публикаций за последнюю неделю:\n\n"

        # Разделяем статистику на части
        chunk_size = 50  # Количество записей в одном сообщении
        for i in range(0, len(stats), chunk_size):
            chunk = stats[i:i + chunk_size]
            chunk_response = response if i == 0 else ""  # Добавляем заголовок только к первому сообщению
            for stat in chunk:
                chunk_response += f"ID: {stat[0]}, Время: {stat[1]}, Просмотры: {stat[2]}, Репосты: {stat[3]}, Реакции: {stat[4]}\n"

            try:
                bot.reply_to(message, chunk_response)
            except ApiTelegramException as e:
                if "message is too long" in str(e):
                    # Если сообщение все еще слишком длинное, разделим его на еще меньшие части
                    lines = chunk_response.split('\n')
                    sub_chunk = ""
                    for line in lines:
                        if len(sub_chunk) + len(line) > 4000:  # Оставляем небольшой запас
                            bot.reply_to(message, sub_chunk)
                            sub_chunk = line + "\n"
                        else:
                            sub_chunk += line + "\n"
                    if sub_chunk:
                        bot.reply_to(message, sub_chunk)
                else:
                    # Если возникла другая ошибка, просто логируем её
                    logger.error(f"Ошибка при отправке статистики: {e}")

        bot.reply_to(message, "Статистика отправлена.")

    @bot.message_handler(commands=['top'])
    def send_top_articles(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return
        top_articles = get_top_articles(5)  # Топ-5 статей
        response = "🏆 Топ-5 статей:\n\n"
        for article in top_articles:
            response += f"Заголовок: {article[0]}\nДата: {article[1]}\nПросмотры: {article[2]}, Репосты: {article[3]}, Реакции: {article[4]}\n\n"
        bot.reply_to(message, response)


    @bot.message_handler(commands=['pause'])
    def pause_publications(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton("1 час", callback_data="pause_1"),
                     InlineKeyboardButton("2 часа", callback_data="pause_2"),
                     InlineKeyboardButton("4 часа", callback_data="pause_4"))
        bot.reply_to(message, "На сколько часов приостановить публикации?", reply_markup=keyboard)

    @bot.message_handler(commands=['resume'])
    def resume_publications(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return
        bot.newsbot.resume_publications()
        bot.reply_to(message, "Публикации возобновлены.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pause_'))
    def callback_pause(call: CallbackQuery):
        if str(call.message.chat.id) != ADMIN_CHAT_ID:
            bot.answer_callback_query(call.id, "У вас нет прав для выполнения этой команды.")
            return
        hours = int(call.data.split('_')[1])
        bot.newsbot.pause_publications(hours)
        bot.answer_callback_query(call.id, f"Публикации приостановлены на {hours} час(а/ов).")
        bot.edit_message_text(
            f"Публикации приостановлены на {hours} час(а/ов) до {(datetime.now() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')}",
            call.message.chat.id, call.message.message_id)

    @bot.message_handler(commands=['scores'])
    def send_article_scores(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return

        bot.reply_to(message, "Подготовка таблицы оценок статей...")

        articles = fetch_articles()
        processed_articles = process_articles(articles)
        scored_articles = get_article_scores(processed_articles)

        table = "🏆 Таблица оценок статей:\n\n"
        table += "<pre>"
        table += f"{'Заголовок':<50} | {'Общ.':<5} | {'Настр.':<6} | {'Врем.':<5} | {'Ист.':<4} | {'Кат.':<4}\n"
        table += "-" * 85 + "\n"

        for article in scored_articles[:10]:  # Показываем топ-10 статей
            table += f"{article['title']:<50} | {article['total_score']:<5.2f} | {article['sentiment']:<6.2f} | {article['time_relevance']:<5d} | {article['source_priority']:<4d} | {article['category_weight']:<4.2f}\n"

        table += "</pre>"

        bot.reply_to(message, table, parse_mode='HTML')

    @bot.message_handler(commands=['hot'])
    def send_hot_news(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return

        # Получаем топ-5 самых популярных статей за последнюю неделю
        hot_articles = get_top_articles(5)  # Эта функция уже существует в database.py

        response = "🔥 Самые горячие новости за последнее время:\n\n"
        for article in hot_articles:
            title, pub_date, views, forwards, reactions = article
            score = views + forwards * 5 + reactions * 2  # Простая формула для расчета "горячести"
            response += f"🔥 {title}\n"
            response += f"📅 {pub_date}\n"
            response += f"📊 Рейтинг: {score}\n\n"

        bot.reply_to(message, response)

    @bot.message_handler(commands=['optimal_time'])
    def send_optimal_time(message: Message):
        if str(message.chat.id) != ADMIN_CHAT_ID:
            bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
            return

        newsbot = bot.newsbot
        optimal_hours = sorted(newsbot.analyze_optimal_publishing_time())

        response = "🕰 Оптимальное время для публикаций:\n\n"
        for hour in optimal_hours:
            response += f"• {hour:02d}:00 - {(hour + 1) % 24:02d}:00\n"

        response += "\nЭти данные основаны на анализе вовлеченности аудитории за последние 30 дней."

        bot.reply_to(message, response)


    @bot.message_handler(func=lambda message: True)
    def echo_all(message: Message):
        bot.reply_to(message,
                     "Извините, я не понимаю эту команду. Используйте /help для получения списка доступных команд.")


    logger.info("Регистрация обработчиков команд завершена")



if __name__ == "__main__":
    # Тестовый код для проверки работы модуля
    from telebot import TeleBot
    from config import TELEGRAM_BOT_TOKEN

    logging.basicConfig(level=logging.INFO)

    bot = TeleBot(TELEGRAM_BOT_TOKEN)
    setup_bot_commands(bot)
    register_handlers(bot)

    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    bot.polling(none_stop=True)