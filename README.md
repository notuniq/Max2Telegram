# Max2Telegram
Бот для пересылки сообщений из чата **MAX** в **Telegram**.  

---

Функционал пересылки:
- Текстовые сообщения  
- Голосовые сообщения
- Видео сообщения
- Видео
- Фото
- Файлы
- Обработка нескольких сообщений
- GIF файлы

В разработке:
- Контакты MAX

---

## 🚀 Установка

1. Клонируйте репозиторий:  

    ```bash
    git clone https://github.com/notuniq/Max2Telegram.git
    cd Max2Telegram
    ```
2. Создайте виртуальное окружение и установите зависимости:
    ```bash
    python -m venv venv
    # Linux/macOS
    source venv/bin/activate
    # Windows
    venv\Scripts\activate
    pip install -r requirements.txt
    ```
3. Установите ffmpeg для конвертации аудио в формат OGG (Telegram требует этот формат для голосовых сообщений):
- Linux (Ubuntu/Debian):
    ```bash
    sudo apt update
    sudo apt install ffmpeg
    ```
- macOS (Homebrew):
    ```
    brew install ffmpeg
    ```
- Windows:
    1. Скачайте сборку с [официального сайта](https://ffmpeg.org/download.html)
    2. Добавьте ffmpeg/bin в системный PATH

4. Создайте файл .env с вашими настройками:
    ```
    MAX_AUTH_TOKEN=<Ваш токен из MAX>
    MAX_CHAT_ID=<ID чата MAX>
    TG_TOKEN=<Telegram Bot Token>
    TG_CHAT_ID=<ID чата Telegram>
    USER_FILTER_IDS=[<ID пользователей, от которых нужно пересылать сообщения, через запятую>]
    ```

## Получение MAX_AUTH_TOKEN

1. Перейдите в [веб-версию MAX](https://web.max.ru)
2. Откройте DevTools (F12 или Ctrl+Shift+I)
3. Перейдите на вкладку Application → Local Storage
4. Найдите ключ __oneme_auth
5. Скопируйте значение token и вставьте его в .env как MAX_AUTH_TOKEN

## Получение MAX_CHAT_ID
1. Зайдите в ваш чат через [веб-версию MAX](https://web.max.ru)
2. Скопируйте ссылку на чат в адресной строке браузера

    ```
    https://web.max.ru/-12345678
    ```
3. Скопируйте из ссылки -12345678 и вставьте в MAX_CHAT_ID

## Получение TG_TOKEN

1. Создайте бота с помощью [BotFather](https://t.me/BotFather)
2. После создания скопируйте токен бота и вставьте его в TG_TOKEN
    ```
    Use this token to access the HTTP API:
    12345678:ADdaJLKAAdjalJDeadjaoiIIP
    Keep your token secure and store it safely, it can be used by anyone to control your bot.
    ```

## [Получение TG_CHAT_ID (клик)](https://habr.com/ru/companies/amvera/articles/996686/)

## Получение USER_FILTER_IDs
1. Настройте файл .env, указав параметры:

- MAX_CHAT_ID
- MAX_AUTH_TOKEN
2. Запустите скрипт:
    ```bash
    python src/utils/get_group_participants.py
    ```
3. В консоли отобразятся ID и имена всех участников беседы, например:
    ```
    1234 - Евгений
    4513 - Мария
    313354 - Андрей
    ```
4. Добавьте нужные ID в переменную USER_FILTER_IDS в .env:
    ```
    USER_FILTER_IDs=[4513, 313354]
    ```
### Примечание
- Если USER_FILTER_IDS указан, бот будет пересылать сообщения только от этих пользователей.

- Если нужно пересылать сообщения от всех участников беседы, оставьте список пустым:
    ```
    USER_FILTER_IDS=[]
    ```

## Запуск бота
```bash
python src/main.py
```
Бот подключится к MAX, будет проверять новые сообщения и пересылать их в Telegram.

## Лицензия
Проект лицензирован под MIT License.

MIT License позволяет:
- Свободно использовать код
- Форкать и дорабатывать
- Распространять любые изменения

```
Сохранение лицензии обязательно при любых изменениях или распространении.
```