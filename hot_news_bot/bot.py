import telebot
import schedule
import time
import threading
import sqlite3
import random
from datetime import datetime, timedelta
import logging
from .rss_parser import fetch_articles
from .article_processor import process_articles, select_interesting_articles
from .publisher import publish_to_telegram
from .database import get_db_connection, create_db, initialize_events, is_article_published, add_published_article
from .telegram_handlers import setup_bot_commands, send_initial_message
from .events import update_events
from .utils import setup_logging, to_moscow_time
from .telegram_handlers import register_handlers
from config import PUBLISH_INTERVAL, MIN_PUBLICATION_INTERVAL, MAX_PUBLICATIONS_PER_HOUR, MIN_INTEREST_SCORE, PUBLICATION_DELAY_INCREASE

class NewsBot:
    def __init__(self, token, admin_chat_id, channel_id):
        self.bot = telebot.TeleBot(token)
        self.admin_chat_id = admin_chat_id
        self.channel_id = channel_id
        self.pause_until = None
        self.pause_timer = None
        self.logger = logging.getLogger(__name__)
        self.publication_delay = PUBLISH_INTERVAL  # Инициализация задержки публикации
        create_db()
        self.optimal_publishing_hours = self.analyze_optimal_publishing_time()

    def send_log(self, message):
        self.logger.info(message)
        moscow_time = to_moscow_time(datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
        self.bot.send_message(self.admin_chat_id, f"LOG [{moscow_time}]: {message}")

    def analyze_optimal_publishing_time(self):
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) FROM post_stats
            """)
            count = c.fetchone()[0]

            if count == 0:
                self.logger.info("Таблица post_stats пуста. Используем значения по умолчанию.")
                return [9, 12, 15, 18, 21]  # Значения по умолчанию

            c.execute("""
                SELECT strftime('%H', post_time) as hour,
                       AVG(views + forwards * 5 + reactions * 2) as engagement_score
                FROM post_stats
                WHERE post_time >= datetime('now', '-30 days')
                GROUP BY hour
                ORDER BY engagement_score DESC
                LIMIT 5
            """)
            result = c.fetchall()

        if not result:
            return [9, 12, 15, 18, 21]  # Значения по умолчанию

        return [int(hour) for hour, _ in result if hour is not None]

    def update_optimal_publishing_time(self):
        self.optimal_publishing_hours = self.analyze_optimal_publishing_time()
        self.send_log(f"Обновлено оптимальное время публикации: {self.optimal_publishing_hours}")

    def should_publish_now(self):
        current_hour = datetime.now().hour
        if current_hour in self.optimal_publishing_hours:
            return True
        else:
            closest_optimal = min(self.optimal_publishing_hours, key=lambda x: abs(x - current_hour))
            time_difference = abs(closest_optimal - current_hour)
            publish_chance = max(0.2 - (time_difference * 0.01), 0.05)
            return random.random() < publish_chance



    def run(self):
        self.send_log("Бот запускается...")
        create_db()
        initialize_events()
        setup_bot_commands(self.bot)
        send_initial_message(self.bot, self.admin_chat_id)

        self.bot.newsbot = self
        register_handlers(self.bot)

        schedule.every(PUBLISH_INTERVAL).minutes.do(self.run_scheduled_job)
        schedule.every().day.at("00:00").do(self.update_optimal_publishing_time)

        polling_thread = threading.Thread(target=self.bot.polling, kwargs={"none_stop": True})
        polling_thread.start()

        self.send_log("Бот успешно запущен и готов к работе!")

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.send_log("Получен сигнал завершения. Останавливаем бота...")
        finally:
            self.stop()

    def stop(self):
        self.send_log("Останавливаем бота...")
        if self.pause_timer:
            self.pause_timer.cancel()
        self.bot.stop_polling()
        self.send_log("Бот остановлен.")

    def run_scheduled_job(self):
        if self.is_paused():
            self.send_log(f"Запланированная задача пропущена. Публикации на паузе до {self.pause_until}")
            return
        self.process_and_publish()

    def is_paused(self):
        return self.pause_until and datetime.now() < self.pause_until

    def process_and_publish(self):
        if not self.should_publish_now():
            self.send_log("Текущее время не оптимально для публикации. Пропуск цикла.")
            return

        self.send_log("Начало цикла обработки и публикации")
        articles = fetch_articles()
        if not articles:
            self.send_log("Нет новых статей для обработки. Пропуск цикла.")
            return

        processed_articles = process_articles(articles)
        interesting_articles = [article for article in processed_articles if
                                article['interest_score'] >= MIN_INTEREST_SCORE]

        if not interesting_articles:
            self.send_log("Нет достаточно интересных статей для публикации. Увеличение задержки.")
            self.increase_publication_delay(PUBLICATION_DELAY_INCREASE)
            return

        self.send_log(f"Отобрано {len(interesting_articles)} интересных статей")

        published_count = 0
        last_publication_time = None

        for article in interesting_articles:
            if published_count >= MAX_PUBLICATIONS_PER_HOUR:
                self.send_log(
                    f"Достигнут лимит публикаций в час ({MAX_PUBLICATIONS_PER_HOUR}). Ожидание следующего цикла.")
                break

            current_time = datetime.now()
            if last_publication_time and (
                    current_time - last_publication_time).total_seconds() < MIN_PUBLICATION_INTERVAL * 60:
                wait_time = (last_publication_time + timedelta(
                    minutes=MIN_PUBLICATION_INTERVAL) - current_time).total_seconds()
                self.send_log(f"Ожидание {wait_time:.0f} секунд до следующей публикации...")
                time.sleep(wait_time)

            if not is_article_published(article['id']):
                try:
                    message_id = publish_to_telegram(self.bot, article, self.channel_id)
                    if message_id:
                        add_published_article(article['id'], article['title'],
                                              current_time.strftime('%Y-%m-%d %H:%M:%S'))
                        published_count += 1
                        last_publication_time = current_time
                        self.send_log(f"Статья опубликована: {article['title']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при публикации статьи: {e}")

        self.send_log(f"Цикл обработки завершен. Опубликовано {published_count} статей.")

    def increase_publication_delay(self, increase_minutes):
        self.publication_delay += increase_minutes
        self.send_log(f"Задержка публикации увеличена. Новая задержка: {self.publication_delay} минут")

    def pause_publications(self, hours):
        self.pause_until = to_moscow_time(datetime.now() + timedelta(hours=hours))
        if self.pause_timer:
            self.pause_timer.cancel()
        self.pause_timer = threading.Timer(hours * 3600, self.resume_publications)
        self.pause_timer.start()
        self.send_log(f"Публикации остановлены на {hours} часов до {self.pause_until.strftime('%Y-%m-%d %H:%M:%S')}")

    def resume_publications(self):
        self.pause_until = None
        if self.pause_timer:
            self.pause_timer.cancel()
            self.pause_timer = None
        self.send_log("Публикации возобновлены")

    # Здесь можно добавить дополнительные методы для обработки команд Telegram


def main():
    setup_logging()
    bot = NewsBot()
    bot.run()


if __name__ == "__main__":
    main()