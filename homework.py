import json
import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_TOKEN')

RETRY_TIME = 600
ONE_MONTH = 2592000
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}


HOMEWORK_STATUSES = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания."
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


class CustomBotException(Exception):
    """Универсальное исключение для бота."""


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.
    Определяемый переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    return bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def get_api_answer(current_timestamp):
    """Получает список домашних работ за определенный промежуток времени.
    Делает запрос к сервису API с информацией о проверке домашней работы.
    Параметр переданный в функцию - временная метка.
    В случае успешного запроса должна вернуть ответ API, преобразовав его
    из формата JSON к типам данных Python
    """
    timestamp = current_timestamp or int(time.time())
    logging.debug(timestamp)
    params = {"from_date": timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.RequestException as e:
        logging.error(e, exc_info=True)
    if response.status_code != HTTPStatus.OK:
        message = f"{ENDPOINT} недоступен."
        logging.error(message)
        raise ConnectionError(message)
    logging.info("Получен ответ от сервера")
    try:
        response_json = response.json()
    except json.JSONDecodeError as e:
        logging.error(e)
    return response_json


def check_response(response):
    """Проверяет ответ API на корректность.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям,
    то функция должна вернуть список домашних работ (он может быть и пустым),
    доступный в ответе API по ключу 'homeworks'
    """
    if not isinstance(response, dict):
        raise TypeError("response не является словарем")
    if "homeworks" not in response:
        raise KeyError("В API ответе нет ключа 'homeworks'")
    homeworks_list = response.get("homeworks")
    if not isinstance(homeworks_list, list):
        raise TypeError("homeworks_list не является списком")
    logging.debug("ответ API корректен")
    return homeworks_list[0]


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную
    для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_STATUSES
    """
    keys = ["homework_name", "status"]
    for key in keys:
        if key not in homework:
            raise KeyError(f"В словаре нет ключа {key}")
    homework_status = homework[keys[1]]
    if homework_status not in HOMEWORK_STATUSES:
        message = f"{homework_status} - нет в списке статусов домашней работы"
        logging.error(message)
        raise CustomBotException(message)
    homework_name = homework[keys[0]]
    verdict = HOMEWORK_STATUSES[homework_status]
    logging.debug(f"Статус домашней работы: {verdict}")
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка переменных окружения."""
    set = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    if None in set:
        return False
    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = "Отсутствуют переменные окружения"
        logging.critical(message)
        raise CustomBotException(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - ONE_MONTH
    previous_message = None
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response["current_date"]
            homework = check_response(response)
            message = parse_status(homework)
            if message != previous_message:
                send_message(bot, message)
                logging.info("Сообщение о статусе домашней работы отправлено")
                previous_message = message
            logging.debug(
                "Статус проверки последней домашней работы не изменился")
            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            send_message(bot, message)
            time.sleep(RETRY_TIME)
        else:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
