import sqlite3
import logging
from typing import List, Tuple, Optional
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

DB_NAME = 'hot_news_bot.db'


def get_db_connection():
    """Создает соединение с базой данных."""
    return sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES)


def create_db():
    """Создает необходимые таблицы в базе данных."""
    with get_db_connection() as conn:
        c = conn.cursor()

        # Таблица для статей
        c.execute('''CREATE TABLE IF NOT EXISTS articles
                     (id TEXT PRIMARY KEY, 
                     title TEXT, 
                     pub_date TEXT)''')

        # Таблица для событий
        c.execute('''CREATE TABLE IF NOT EXISTS events
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     name TEXT,
                     date DATE,
                     keywords TEXT)''')

        # Таблица для статистики постов
        c.execute('''CREATE TABLE IF NOT EXISTS post_stats
                     (message_id INTEGER PRIMARY KEY,
                     post_time DATETIME,
                     views INTEGER,
                     forwards INTEGER,
                     reactions INTEGER)''')

        conn.commit()
    logger.info("База данных успешно инициализирована")


def is_article_published(article_id: str) -> bool:
    """Проверяет, была ли статья уже опубликована."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM articles WHERE id=?", (article_id,))
        return c.fetchone() is not None


def add_published_article(article_id: str, title: str, pub_date: str):
    """Добавляет опубликованную статью в базу данных."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO articles VALUES (?, ?, ?)", (article_id, title, pub_date))
        conn.commit()
    logger.info(f"Статья добавлена в базу данных: {title}")


def get_last_publication_time() -> Optional[datetime]:
    """Возвращает время последней публикации."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(pub_date) FROM articles")
        result = c.fetchone()[0]
        return datetime.strptime(result, '%Y-%m-%d %H:%M:%S') if result else None


def initialize_events():
    """
    Инициализирует таблицу событий в базе данных.
    Эта функция должна вызываться при запуске бота.
    """
    with get_db_connection() as conn:
        c = conn.cursor()

        # Создаем таблицу событий, если она еще не существует
        c.execute('''CREATE TABLE IF NOT EXISTS events
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     name TEXT,
                     date DATE,
                     keywords TEXT)''')

        # Очищаем существующие события
        c.execute("DELETE FROM events")
        conn.commit()

    logger.info("Таблица событий инициализирована")


def add_event(name: str, event_date: date, keywords: List[str]):
    """Добавляет новое событие в базу данных."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO events (name, date, keywords) VALUES (?, ?, ?)",
                  (name, event_date, ','.join(keywords)))
        conn.commit()
    logger.info(f"Событие добавлено в базу данных: {name}")


def get_today_events() -> List[Tuple[int, str, date, str]]:
    """Возвращает события на сегодня."""
    today = date.today()
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM events WHERE date = ?", (today,))
        return c.fetchall()


def log_post_stats(message_id: int, post_time: datetime, views: int = 0, forwards: int = 0, reactions: int = 0):
    """Логирует или обновляет статистику поста."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO post_stats 
                     (message_id, post_time, views, forwards, reactions) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (message_id, post_time, views, forwards, reactions))
        conn.commit()
    logger.info(
        f"Статистика поста обновлена: message_id={message_id}, views={views}, forwards={forwards}, reactions={reactions}")


def get_post_stats(days: int = 7) -> List[Tuple[int, datetime, int, int, int]]:
    """Возвращает статистику постов за указанное количество дней."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''SELECT * FROM post_stats 
                     WHERE post_time >= datetime('now', '-' || ? || ' days') 
                     ORDER BY post_time DESC''', (days,))
        return c.fetchall()


def get_publications_in_last_hour() -> int:
    """Возвращает количество публикаций за последний час."""
    with get_db_connection() as conn:
        c = conn.cursor()
        one_hour_ago = datetime.now() - timedelta(hours=1)
        c.execute("SELECT COUNT(*) FROM articles WHERE pub_date > ?", (one_hour_ago.strftime('%Y-%m-%d %H:%M:%S'),))
        return c.fetchone()[0]


def clear_old_data(days: int = 30):
    """Очищает старые данные из базы данных."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM articles WHERE pub_date < datetime('now', '-? days')", (days,))
        c.execute("DELETE FROM events WHERE date < date('now', '-? days')", (days,))
        c.execute("DELETE FROM post_stats WHERE post_time < datetime('now', '-? days')", (days,))
        conn.commit()
    logger.info(f"Старые данные (старше {days} дней) удалены из базы данных")

def get_last_publication_time() -> Optional[datetime]:
    """Возвращает время последней публикации."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(pub_date) FROM articles")
        result = c.fetchone()[0]
        return datetime.strptime(result, '%Y-%m-%d %H:%M:%S') if result else None

def get_publications_in_last_hour() -> int:
    """Возвращает количество публикаций за последний час."""
    with get_db_connection() as conn:
        c = conn.cursor()
        one_hour_ago = datetime.now() - timedelta(hours=1)
        c.execute("SELECT COUNT(*) FROM articles WHERE pub_date > ?", (one_hour_ago.strftime('%Y-%m-%d %H:%M:%S'),))
        return c.fetchone()[0]

def get_top_articles(limit: int = 10) -> List[Tuple[str, str, int, int, int]]:
    """Возвращает топ статей по просмотрам и реакциям."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''SELECT articles.title, articles.pub_date, 
                     post_stats.views, post_stats.forwards, post_stats.reactions
                     FROM articles
                     JOIN post_stats ON articles.id = post_stats.message_id
                     ORDER BY (post_stats.views + post_stats.forwards * 5 + post_stats.reactions * 2) DESC
                     LIMIT ?''', (limit,))
        return c.fetchall()


if __name__ == "__main__":
    # Тестовый код для проверки работы модуля
    logging.basicConfig(level=logging.INFO)

    create_db()

    # Тестирование функций
    add_published_article("test1", "Test Article", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("Is article published:", is_article_published("test1"))

    add_event("Test Event", date.today(), ["test", "event"])
    print("Today's events:", get_today_events())

    log_post_stats(1, datetime.now(), 100, 10, 5)
    print("Post stats:", get_post_stats(1))

    print("Top articles:", get_top_articles(5))

    clear_old_data(1)  # Очистка данных старше 1 дня для теста

    logger.info("Тестирование database.py завершено")