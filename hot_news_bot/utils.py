import re
import logging
from typing import Optional
from html import escape
from googletrans import Translator
from config import TARGET_LANGUAGE, MOSCOW_TZ
from datetime import datetime
from pytz import UTC

logger = logging.getLogger(__name__)

translator = Translator()


def setup_logging():
    """Настраивает логирование для бота."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot.log', encoding='utf-8')
        ]
    )
    # Отключаем логи для некоторых библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('telebot').setLevel(logging.WARNING)


def clean_html(raw_html: str) -> str:
    """
    Очищает HTML-теги из текста.

    Args:
        raw_html (str): Исходный текст с HTML-тегами.

    Returns:
        str: Очищенный текст.
    """
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()


def remove_img_tags(text: str) -> str:
    """
    Удаляет теги изображений из текста.

    Args:
        text (str): Исходный текст с тегами изображений.

    Returns:
        str: Текст без тегов изображений.
    """
    return re.sub(r'<img[^>]*>', '', text)


def truncate_summary(summary: str, max_length: int = 200) -> str:
    """
    Обрезает текст до заданной длины, сохраняя целостность слов.

    Args:
        summary (str): Исходный текст.
        max_length (int): Максимальная длина текста.

    Returns:
        str: Обрезанный текст.
    """
    if len(summary) <= max_length:
        return summary
    truncated = summary[:max_length]
    last_space = truncated.rfind(' ')
    if last_space != -1:
        truncated = truncated[:last_space]
    return truncated + '...'


def translate_text(text: str, target_language: str = TARGET_LANGUAGE) -> str:
    """
    Переводит текст на целевой язык.

    Args:
        text (str): Исходный текст.
        target_language (str): Код целевого языка.

    Returns:
        str: Переведенный текст.
    """
    try:
        return translator.translate(text, dest=target_language).text
    except Exception as e:
        logger.error(f"Ошибка при переводе текста: {e}")
        return text


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы для Markdown.

    Args:
        text (str): Исходный текст.

    Returns:
        str: Текст с экранированными специальными символами.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


def escape_html(text: str) -> str:
    """
    Экранирует специальные символы для HTML.

    Args:
        text (str): Исходный текст.

    Returns:
        str: Текст с экранированными специальными символами.
    """
    return escape(text)


def format_number(number: int) -> str:
    """
    Форматирует число для удобного отображения (например, 1000 -> 1K).

    Args:
        number (int): Исходное число.

    Returns:
        str: Отформатированное число.
    """
    if number < 1000:
        return str(number)
    elif number < 1000000:
        return f"{number / 1000:.1f}K"
    else:
        return f"{number / 1000000:.1f}M"


def is_valid_url(url: str) -> bool:
    """
    Проверяет, является ли строка действительным URL.

    Args:
        url (str): Проверяемая строка.

    Returns:
        bool: True, если строка является действительным URL, иначе False.
    """
    regex = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None


def extract_domain(url: str) -> Optional[str]:
    """
    Извлекает домен из URL.

    Args:
        url (str): URL для обработки.

    Returns:
        Optional[str]: Домен или None, если URL невалиден.
    """
    if not is_valid_url(url):
        return None
    domain = re.findall(r'://(?:www\.)?([\w\-\.]+)/', url)
    return domain[0] if domain else None


if __name__ == "__main__":
    # Тестовый код для проверки работы модуля
    setup_logging()
    logger.info("Тестирование модуля utils.py")

    test_html = "<p>Это <b>тестовый</b> HTML.</p>"
    print(f"Очищенный HTML: {clean_html(test_html)}")

    test_summary = "Это очень длинный текст, который нужно обрезать до разумной длины."
    print(f"Обрезанный текст: {truncate_summary(test_summary, 30)}")

    test_translate = "Hello, world!"
    print(f"Переведенный текст: {translate_text(test_translate, 'ru')}")

    test_markdown = "This is *bold* and _italic_ text with [link](http://example.com)."
    print(f"Экранированный Markdown: {escape_markdown(test_markdown)}")

    test_number = 1234567
    print(f"Отформатированное число: {format_number(test_number)}")

    test_url = "https://www.example.com/page?param=value"
    print(f"Валидный URL: {is_valid_url(test_url)}")
    print(f"Извлеченный домен: {extract_domain(test_url)}")

    logger.info("Тестирование модуля utils.py завершено")

def to_moscow_time(dt: datetime) -> datetime:
    """
    Конвертирует время в московское.

    Args:
        dt (datetime): Исходное время (предполагается, что оно в UTC).

    Returns:
        datetime: Время, преобразованное в московский часовой пояс.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(MOSCOW_TZ)
