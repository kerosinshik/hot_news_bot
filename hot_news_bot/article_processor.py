import logging
from typing import List, Dict, Any
from datetime import datetime
import re
import random
from collections import defaultdict
from nltk.sentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from googletrans import Translator
from .database import get_today_events
from .events import get_relevant_events
from .utils import clean_html, truncate_summary
from config import (
    TARGET_LANGUAGE, SUMMARY_LENGTH,
    BREAKING_NEWS_KEYWORDS, PRIORITY_SOURCES,
    category_keywords, category_weights,
    PRIORITY_CATEGORIES, BLACKLIST_KEYWORDS,
    TOP_ARTICLES_PERCENTAGE, DIVERSITY_PERCENTAGE
)

logger = logging.getLogger(__name__)

# Инициализация необходимых объектов
sia = SentimentIntensityAnalyzer()
translator = Translator()


def process_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Обрабатывает список статей: переводит, очищает, категоризирует и оценивает.

    Args:
        articles (List[Dict[str, Any]]): Список необработанных статей.

    Returns:
        List[Dict[str, Any]]: Список обработанных статей.
    """
    processed_articles = []
    for article in articles:
        try:
            processed = process_single_article(article)
            if processed:
                processed_articles.append(processed)
        except Exception as e:
            logger.error(f"Ошибка при обработке статьи {article.get('title', 'Unknown')}: {e}")

    logger.info(f"Обработано {len(processed_articles)} статей")
    return processed_articles


def process_single_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обрабатывает отдельную статью.

    Args:
        article (Dict[str, Any]): Необработанная статья.

    Returns:
        Dict[str, Any]: Обработанная статья или None, если статья не прошла фильтрацию.
    """
    # Перевод
    title = translate_text(clean_html(article['title']))
    summary = translate_text(clean_html(article['summary']))

    # Обрезка summary до заданной длины
    summary = truncate_summary(summary, SUMMARY_LENGTH)

    # Категоризация
    category = categorize_article(title + " " + summary)

    # Оценка интересности
    interest_score = calculate_interest_score(article, title, summary)

    # Проверка на срочные новости
    is_breaking = is_breaking_news(article, title, summary)

    return {
        'id': article['id'],
        'title': title,
        'summary': summary,
        'link': article['link'],
        'pub_date': article['pub_date'],
        'source': article['source'],
        'category': category,
        'interest_score': interest_score,
        'is_breaking': is_breaking,
        'image_url': article.get('image_url')  # Сохраняем URL изображения
    }


def translate_text(text: str) -> str:
    """
    Переводит текст на целевой язык.

    Args:
        text (str): Исходный текст.

    Returns:
        str: Переведенный текст.
    """
    try:
        return translator.translate(text, dest=TARGET_LANGUAGE).text
    except Exception as e:
        logger.error(f"Ошибка при переводе текста: {e}")
        return text  # Возвращаем исходный текст в случае ошибки


def categorize_article(content: str) -> str:
    """
    Определяет категорию статьи на основе ключевых слов.

    Args:
        content (str): Содержание статьи (заголовок + краткое содержание).

    Returns:
        str: Определенная категория или None, если статья содержит слова из черного списка.
    """
    content = content.lower()

    # Проверка на наличие слов из черного списка
    if any(word.lower() in content for word in BLACKLIST_KEYWORDS):
        return None

    category_scores = {}

    for cat, keywords in category_keywords.items():
        category_scores[cat] = sum(content.count(keyword.lower()) for keyword in keywords)

    if not any(category_scores.values()):
        return None  # Если не найдено ни одного совпадения, возвращаем None

    return max(category_scores, key=category_scores.get)


def calculate_interest_score(article: Dict[str, Any], title: str, summary: str) -> float:
    content = title + " " + summary
    category = categorize_article(content)

    if category is None:
        return 0  # Статья не соответствует ни одной категории

    # Начинаем с веса категории
    score = category_weights.get(category, 0.0)

    # Анализ настроений (используем небольшой вес, чтобы это не было определяющим фактором)
    sentiment_score = sia.polarity_scores(content)['compound']
    score += sentiment_score * 0.1

    # Проверка связи с предстоящими событиями
    relevant_events = get_relevant_events(content)
    score += len(relevant_events) * 0.5  # Добавляем бонус за каждое релевантное событие

    # Временная актуальность
    time_diff = datetime.now() - article['pub_date']
    if time_diff.days == 0:
        score += 0.3  # Небольшой бонус для статей, опубликованных сегодня
    elif time_diff.days <= 2:
        score += 0.1  # Совсем небольшой бонус для статей не старше 2 дней

    # Приоритетные источники
    if any(source in article['source'] for source in PRIORITY_SOURCES):
        score += 0.2

    # Наличие ключевых слов, указывающих на важность или новизну
    importance_keywords = ["скандал", "сенсация", "эксклюзив", "шокирующий", "неожиданно"]
    if any(keyword in content.lower() for keyword in importance_keywords):
        score += 0.3

    return score


def is_breaking_news(article: Dict[str, Any], title: str, summary: str) -> bool:
    """
    Определяет, является ли новость срочной.

    Args:
        article (Dict[str, Any]): Исходная статья.
        title (str): Переведенный заголовок.
        summary (str): Переведенное краткое содержание.

    Returns:
        bool: True, если новость срочная, иначе False.
    """
    text_to_check = (title + " " + summary).lower()

    # Проверка ключевых слов
    if any(keyword.lower() in text_to_check for keyword in BREAKING_NEWS_KEYWORDS):
        return True

    # Проверка приоритетных источников
    if any(source in article['source'] for source in PRIORITY_SOURCES):
        return True

    return False


def select_interesting_articles(articles: List[Dict[str, Any]], num_to_select: int = 5) -> List[Dict[str, Any]]:
    # Сортировка статей по оценке интереса
    sorted_articles = sorted(articles, key=lambda x: x['interest_score'], reverse=True)

    # Выбор топовых статей
    top_count = int(num_to_select * TOP_ARTICLES_PERCENTAGE)
    selected = sorted_articles[:top_count]

    # Добавление разнообразия
    other_articles = [a for a in sorted_articles if a not in selected]
    diversity_count = num_to_select - top_count

    # Группировка оставшихся статей по категориям
    category_articles = defaultdict(list)
    for article in other_articles:
        category_articles[article['category']].append(article)

    # Приоритизация категорий
    prioritized_categories = PRIORITY_CATEGORIES + [cat for cat in category_articles.keys() if cat not in PRIORITY_CATEGORIES]

    # Выбор статей для разнообразия
    while len(selected) < num_to_select and prioritized_categories:
        category = prioritized_categories.pop(0)
        if category_articles[category]:
            article = max(category_articles[category], key=lambda x: x['interest_score'])
            selected.append(article)
            category_articles[category].remove(article)

    # Если все еще не хватает статей, добавляем случайные
    if len(selected) < num_to_select:
        remaining = [a for cat in category_articles.values() for a in cat]
        selected += random.sample(remaining, min(len(remaining), num_to_select - len(selected)))

    # Добавление признака "горячей новости"
    for article in selected:
        article['is_hot'] = article['interest_score'] > 2.0 or article['category'] in PRIORITY_CATEGORIES[:3]

    return selected


def ensure_diversity(articles: List[Dict[str, Any]], num_diverse: int = 3) -> List[Dict[str, Any]]:
    """
    Обеспечивает разнообразие в выбранных статьях.

    Args:
        articles (List[Dict[str, Any]]): Список статей для обеспечения разнообразия.
        num_diverse (int): Желаемое количество разнообразных статей.

    Returns:
        List[Dict[str, Any]]: Список разнообразных статей.
    """
    if len(articles) <= num_diverse:
        return articles

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([article['title'] + " " + article['summary'] for article in articles])

    diverse_articles = [articles[0]]  # Начинаем с самой интересной статьи
    for _ in range(num_diverse - 1):
        if len(diverse_articles) == len(articles):
            break

        candidate_scores = []
        for article in articles:
            if article not in diverse_articles:
                article_index = articles.index(article)
                max_similarity = max(
                    cosine_similarity(tfidf_matrix[article_index], tfidf_matrix[articles.index(div_article)])
                    for div_article in diverse_articles
                )[0][0]
                score = article['interest_score'] * (1 - max_similarity)
                candidate_scores.append((article, score))

        if candidate_scores:
            diverse_articles.append(max(candidate_scores, key=lambda x: x[1])[0])

    return diverse_articles


def expand_keywords(initial_keywords, corpus, top_n=5):
    # Создание корпуса текстов из статей
    texts = [article['title'] + ' ' + article['summary'] for article in corpus]

    # Создание и обучение TF-IDF векторизатора
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(texts)

    # Получение всех слов из векторизатора
    feature_names = vectorizer.get_feature_names_out()

    expanded_keywords = set(initial_keywords)
    for keyword in initial_keywords:
        # Найти индекс ключевого слова
        if keyword in feature_names:
            keyword_index = list(feature_names).index(keyword)

            # Вычислить косинусное сходство между ключевым словом и всеми другими словами
            keyword_vector = tfidf_matrix[:, keyword_index].toarray().reshape(1, -1)
            cosine_similarities = cosine_similarity(keyword_vector, tfidf_matrix.transpose()).flatten()

            # Получить топ N наиболее похожих слов
            similar_word_indices = cosine_similarities.argsort()[:-top_n - 1:-1]
            similar_words = [feature_names[index] for index in similar_word_indices if feature_names[index] != keyword]

            expanded_keywords.update(similar_words)

    return list(expanded_keywords)


def update_category_keywords(articles):
    for category, keywords in category_keywords.items():
        category_keywords[category] = expand_keywords(keywords, articles)

# Эту функцию нужно вызывать периодически, например, раз в день или неделю
def process_and_update_keywords(articles):
    update_category_keywords(articles)
    # Здесь можно добавить код для сохранения обновленных ключевых слов в файл или базу данных


def get_article_scores(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Возвращает детальную информацию об оценках статей.

    Args:
        articles (List[Dict[str, Any]]): Список обработанных статей.

    Returns:
        List[Dict[str, Any]]: Список словарей с детальной информацией об оценках.
    """
    scored_articles = []
    for article in articles:
        content = article['title'] + " " + article['summary']
        sentiment_score = sia.polarity_scores(content)['compound']

        time_relevance = 1 if (datetime.now() - article['pub_date']).days == 0 else 0

        source_priority = 1 if any(source in article['source'] for source in PRIORITY_SOURCES) else 0

        category_weight = category_weights.get(article['category'], 1.0)

        scored_articles.append({
            'title': article['title'][:50] + '...' if len(article['title']) > 50 else article['title'],
            'sentiment': sentiment_score,
            'time_relevance': time_relevance,
            'source_priority': source_priority,
            'category_weight': category_weight,
            'total_score': article['interest_score']
        })

    return sorted(scored_articles, key=lambda x: x['total_score'], reverse=True)

if __name__ == "__main__":
    # Тестовый код для проверки работы модуля
    logging.basicConfig(level=logging.INFO)
    test_articles = [
        {
            'id': '1',
            'title': 'Breaking news: New AI breakthrough',
            'summary': 'Scientists have made a significant advancement in artificial intelligence...',
            'link': 'http://example.com/1',
            'pub_date': datetime.now(),
            'source': 'http://techcrunch.com'
        },
        {
            'id': '2',
            'title': 'SpaceX launches new satellite',
            'summary': 'SpaceX successfully launched a new communication satellite into orbit...',
            'link': 'http://example.com/2',
            'pub_date': datetime.now(),
            'source': 'http://space.com'
        },
        # Добавьте еще несколько тестовых статей
    ]

    processed = process_articles(test_articles)
    interesting = select_interesting_articles(processed)

    for article in interesting:
        print(f"Title: {article['title']}")
        print(f"Category: {article['category']}")
        print(f"Interest Score: {article['interest_score']}")
        print(f"Is Breaking: {article['is_breaking']}")
        print("---")