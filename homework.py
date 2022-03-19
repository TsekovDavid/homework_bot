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
TOKEN_IS_MISSING = "Переменная окружения - {token} - отсутствует."
SEND_MESSAGE = "Сообщение - {message} - отправлено."
BAD_STATUS_CODE = (
    "Код-возврата <{status_code}> не соответсвует ожиданиям\n{url}\n"
    "Параметры запроса:\n{headers}\n{params}")
API_TROUBLE = ("Ответ API не соответсвует ожидаемому.\n"
               "По ключу <{key}> получено значение <{value}>\n"
               "Запрос к {url}\nПараметры:\n{headers}\n{params}")
API_NOT_A_DICT = "Тип ответа API {type_api} -- ожидается словарь"
HOMEWORKS_NOT_A_LIST = "Домашки получены не в виде списка, а {homeworks_type}"
INVALID_STATUS = "{status} - нет в списке статусов домашней работы"
STATUS_CHANGE = 'Изменился статус проверки работы "{name}". {verdict}'
MISSING_KEY = "В словаре нет ключа {key}"
PROGRAM_FAILURE = "Сбой в работе программы: {error}"

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания."}
TOKENS = ("PRACTICUM_TOKEN", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")


class CustomBotException(Exception):
    """Универсальное исключение для бота."""


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.
    Определяемый переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения
    """
    return bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def get_api_answer(current_timestamp):
    """Делает запрос к сервису API с информацией о проверке домашней работы.
    Параметр переданный в функцию - временная метка.
    В случае успешного запроса должна вернуть ответ API, преобразовав его
    из формата JSON к типам данных Python
    """
    params = {"from_date": current_timestamp}
    keys = ("code", "error")
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.RequestException as error:
        raise CustomBotException(
            CONNECTION_PROBLEM.format(
                error=error, url=ENDPOINT, params=params, headers=HEADERS))
    if response.status_code != HTTPStatus.OK:
        raise ValueError(BAD_STATUS_CODE.format(
            params=params,
            url=ENDPOINT,
            headers=HEADERS,
            status_code=response.status_code))
    logging.info("Получен ответ от сервера")
    api_json = response.json()
    for key in keys:
        if key in api_json:
            raise ValueError(API_TROUBLE.format(
                url=ENDPOINT,
                params=params,
                headers=HEADERS,
                key=key,
                value=api_json.get(key)))
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
        raise TypeError(API_NOT_A_DICT.format(type_api=type(response)))
    if "homeworks" not in response:
        raise KeyError("В API ответе нет ключа 'homeworks'")
    homeworks = response.get("homeworks")
    if not isinstance(homeworks, list):
        raise TypeError(HOMEWORKS_NOT_A_LIST.format(
            homeworks_type=type(homeworks)))
    logging.debug("ответ API корректен")
    return homeworks


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную
    для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_STATUSES
    """
    if len(homework) == 0:
        return None
    for key in ("homework_name", "status"):
        if key not in homework:
            raise KeyError(MISSING_KEY.format(key=key))
    status = homework.get("status")
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(INVALID_STATUS.format(status=status))
    verdict = HOMEWORK_VERDICTS[status]
    return STATUS_CHANGE.format(
        name=homework.get("homework_name"), verdict=verdict)


def check_tokens():
    """Проверка переменных окружения."""
    is_error = True
    for name in TOKENS:
        if globals()[name] is None:
            logging.critical(TOKEN_IS_MISSING.format(token=name))
            is_error = False
    return is_error


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = "Отсутствуют переменные окружения"
        logging.critical(message)
        raise ValueError(message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - ONE_MONTH
    previous_message = None
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework = check_response(response)[0]
            message = parse_status(homework)
            if message != previous_message:
                send_message(bot, message)
                current_timestamp = response.get(
                    "current_date", current_timestamp)
                logging.info(SEND_MESSAGE.format(message=message))
                previous_message = message

        except Exception as error:
            message = PROGRAM_FAILURE.format(error=error)
            if message != previous_message:
                logging.error(message)
                try:
                    send_message(bot, message)
                except CustomBotException as error:
                    logging.error(PROGRAM_FAILURE.format(error=error))
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
