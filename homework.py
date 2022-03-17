import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_TOKEN")

RETRY_TIME = 600
ONE_MONTH = 3600 * 24 * 30
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}
CONNECTION_PROBLEM = (
    "Ошибка {error}\nпри попытке запроса к{url}\nс параметрами:"
    "\n{params}\n{headers}")
TOKEN_IS_MISSING = "Переменная окружения -{token}- отсутствует."
SEND_MESSAGE = "Сообщение - {message} - отправлено."

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания."}


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
    params = {"from_date": current_timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.RequestException as error:
        raise CustomBotException(
            CONNECTION_PROBLEM.format(
                error=error, url=ENDPOINT, params=params, headers=HEADERS))
    if response.status_code != HTTPStatus.OK:
        raise requests.exceptions.HTTPError(
            f"{ENDPOINT} недоступен.\nПараметры запроса: {HEADERS}\n{params}")
    logging.info("Получен ответ от сервера")
    api_json = response.json()
    if "error" and "code" not in api_json:
        return api_json


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
    homeworks = response.get("homeworks")
    if not isinstance(homeworks, list):
        raise TypeError("Значение по ключу 'homeworks' не является списком")
    if len(homeworks) == 0:
        raise KeyError("В ответе API нет домашних работ")
    homework = homeworks[0]
    logging.debug("ответ API корректен")
    return homework


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
    status = homework[keys[1]]
    verdict = HOMEWORK_VERDICTS[status]
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f"{status} - нет в списке статусов домашней работы")
    name = homework[keys[0]]
    logging.debug(f"Статус домашней работы: {verdict}")
    return f'Изменился статус проверки работы "{name}". {verdict}'


def check_tokens():
    """Проверка переменных окружения."""
    set = ["PRACTICUM_TOKEN", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    for name in set:
        if globals()[name] is None:
            logging.critical(TOKEN_IS_MISSING.format(token=name))
            return False
    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = "Отсутствуют переменные окружения"
        logging.critical(message)
        raise Exception(message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - ONE_MONTH
    previous_message = None
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework = check_response(response)
            message = parse_status(homework)
            if message != previous_message:
                send_message(bot, message)
                current_timestamp = response.get(
                    "current_date", current_timestamp)
                logging.info(SEND_MESSAGE.format(message=message))
                previous_message = message

        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            if message != previous_message:
                logging.error(message)
                send_message(bot, message)
                previous_message = message
        time.sleep(RETRY_TIME)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(__file__ + ".log", encoding="UTF-8")],
        format=("%(asctime)s <%(funcName)s %(lineno)d> "
                "[%(levelname)s] %(message)s")
    )
    try:
        main()
    except KeyboardInterrupt:
        print("Бот отключен")
