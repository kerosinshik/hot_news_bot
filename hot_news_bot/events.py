import logging
from typing import List, Dict, Any
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup
from .database import add_event, get_today_events, clear_old_data

logger = logging.getLogger(__name__)

# Обновим URL на более подходящий для новостей о знаменитостях
CELEBRITY_EVENTS_URL = "https://www.imdb.com/calendar/"


def fetch_upcoming_events() -> List[Dict[str, Any]]:
    """
    Получает предстоящие события, связанные со знаменитостями.
    """
    events = []
    try:
        response = requests.get(CELEBRITY_EVENTS_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Парсинг страницы IMDb для получения предстоящих премьер фильмов и сериалов
        event_elements = soup.select('.ipc-metadata-list-item__content-container')

        for event in event_elements:
            try:
                date_elem = event.find_previous('h3')
                if date_elem:
                    date_str = date_elem.text.strip()
                    event_date = datetime.strptime(date_str, '%B %d').replace(year=datetime.now().year).date()

                    title = event.select_one('.ipc-metadata-list-item__list-content-item').text.strip()
                    stars = [star.text.strip() for star in event.select('.ipc-inline-list__item')]

                    events.append({
                        'name': f"Премьера: {title}",
                        'date': event_date,
                        'keywords': stars + [title, "премьера", "фильм", "сериал"]
                    })
            except Exception as e:
                logger.error(f"Ошибка при обработке события: {e}")

        logger.info(f"Получено {len(events)} предстоящих событий")
    except Exception as e:
        logger.error(f"Ошибка при получении событий с {CELEBRITY_EVENTS_URL}: {e}")

    return events


def update_events():
    """Обновляет базу данных событий."""
    logger.info("Начало обновления базы данных событий")

    # Очистка старых событий
    clear_old_data(days=30)  # Удаляем события старше 30 дней

    # Получение новых событий
    new_events = fetch_upcoming_events()

    # Добавление новых событий в базу данных
    for event in new_events:
        add_event(event['name'], event['date'], event['keywords'])

    logger.info("Обновление базы данных событий завершено")


def get_relevant_events(article_content: str) -> List[Dict[str, Any]]:
    """
    Находит релевантные события для данной статьи.
    """
    today_events = get_today_events()
    relevant_events = []

    for event in today_events:
        event_keywords = event[3].split(',')
        if any(keyword.lower() in article_content.lower() for keyword in event_keywords):
            relevant_events.append({
                'id': event[0],
                'name': event[1],
                'date': event[2],
                'keywords': event_keywords
            })

    return relevant_events


def generate_events_digest() -> str:
    """
    Генерирует дайджест предстоящих событий.
    """
    upcoming_events = fetch_upcoming_events()

    if not upcoming_events:
        return "На ближайшее время нет запланированных событий в мире знаменитостей."

    digest = "🎬 Предстоящие премьеры и события в мире знаменитостей:\n\n"

    for i, event in enumerate(upcoming_events[:10], 1):  # Ограничиваем 10 событиями
        digest += f"{i}. <b>{event['name']}</b>\n"
        digest += f"   📆 {event['date'].strftime('%d.%m.%Y')}\n"
        digest += f"   🌟 В ролях: {', '.join(event['keywords'][:-3])}\n\n"

    digest += "\nСледите за обновлениями и не пропустите громкие премьеры! 🍿🎥"

    return digest


if __name__ == "__main__":
    # Тестовый код для проверки работы модуля
    logging.basicConfig(level=logging.INFO)

    print("Обновление событий...")
    update_events()

    print("\nТекущие события:")
    today_events = get_today_events()
    for event in today_events:
        print(f"- {event[1]} ({event[2]})")

    print("\nГенерация дайджеста событий:")
    digest = generate_events_digest()
    print(digest)

    logger.info("Тестирование events.py завершено")