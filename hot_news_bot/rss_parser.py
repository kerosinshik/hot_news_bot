import feedparser
import requests
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from config import RSS_FEEDS, ARTICLES_PER_FEED
from .database import is_article_published
from .utils import clean_html, remove_img_tags

logger = logging.getLogger(__name__)


def fetch_articles() -> List[Dict[str, Any]]:
    """
    Получает статьи из всех RSS-фидов, определенных в конфигурации.

    Returns:
        List[Dict[str, Any]]: Список словарей, каждый из которых представляет статью.
    """
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed_articles = fetch_feed(feed_url)
            articles.extend(feed_articles)
        except Exception as e:
            logger.error(f"Ошибка при получении статей из {feed_url}: {e}")

    logger.info(f"Всего получено {len(articles)} статей")
    return articles


def fetch_feed(feed_url: str) -> List[Dict[str, Any]]:
    """
    Получает статьи из одного RSS-фида.

    Args:
        feed_url (str): URL RSS-фида.

    Returns:
        List[Dict[str, Any]]: Список словарей, каждый из которых представляет статью.
    """
    logger.info(f"Получение статей из {feed_url}")

    feed = feedparser.parse(feed_url)

    if feed.bozo:
        logger.warning(f"Ошибка при парсинге {feed_url}: {feed.bozo_exception}")

    articles = []
    for entry in feed.entries[:ARTICLES_PER_FEED]:
        article = parse_entry(entry, feed_url)
        if article and not is_article_published(article['id']):
            articles.append(article)

    logger.info(f"Получено {len(articles)} новых статей из {feed_url}")
    return articles


def parse_entry(entry: feedparser.FeedParserDict, feed_url: str) -> Dict[str, Any]:
    """
    Парсит отдельную запись из RSS-фида.

    Args:
        entry (feedparser.FeedParserDict): Запись из RSS-фида.
        feed_url (str): URL RSS-фида.

    Returns:
        Dict[str, Any]: Словарь, представляющий статью, или None, если статья не валидна.
    """
    try:
        article_id = entry.get('id', entry.link)
        title = clean_html(entry.title)
        summary = clean_html(remove_img_tags(entry.summary)) if 'summary' in entry else ''

        # Получаем дату публикации
        pub_date = entry.get('published_parsed') or entry.get('updated_parsed')
        if pub_date:
            pub_date = datetime(*pub_date[:6])
        else:
            pub_date = datetime.now()

        # Проверяем, что статья не старше 7 дней
        if datetime.now() - pub_date > timedelta(days=7):
            return None

        return {
            'id': article_id,
            'title': title,
            'summary': summary,
            'link': entry.link,
            'pub_date': pub_date,
            'source': feed_url
        }
    except Exception as e:
        logger.error(f"Ошибка при парсинге статьи из {feed_url}: {e}")
        return None


def fetch_full_article(url: str) -> str:
    """
    Получает полный текст статьи по URL.

    Args:
        url (str): URL статьи.

    Returns:
        str: Полный текст статьи или пустая строка в случае ошибки.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        # Здесь можно добавить код для извлечения основного содержимого статьи
        # Например, использовать библиотеку newspaper3k или BeautifulSoup
        return response.text
    except requests.RequestException as e:
        logger.error(f"Ошибка при получении полного текста статьи {url}: {e}")
        return ""


if __name__ == "__main__":
    # Тестовый код для проверки работы модуля
    logging.basicConfig(level=logging.INFO)
    articles = fetch_articles()
    for article in articles[:5]:  # Выводим первые 5 статей для проверки
        print(f"Title: {article['title']}")
        print(f"Summary: {article['summary'][:100]}...")
        print(f"Link: {article['link']}")
        print(f"Published: {article['pub_date']}")
        print("---")