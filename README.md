# BlackManagerLite

## Запуск локально

1. Установите Python 3.11 или новее.
2. Установите зависимости: `python -m pip install -r requirements.txt`.
3. Укажите токен сообщества VK в `config.json` в поле `bot-token`.
4. Запустите: `python main.py`.

## Запуск на Railway

Railway собирает приложение через `Dockerfile`.

1. Подключите репозиторий к Railway.
2. В **Variables** добавьте `VK_TOKEN` со значением токена сообщества VK.
3. Для сохранения базы данных между пересборками подключите Railway Volume и задайте `DATABASE_PATH=/data/database.db`, смонтировав Volume в `/data`.
4. Запустите Deploy.

Токен не нужно публиковать в репозитории или отправлять в открытые чаты.

## База данных

По умолчанию SQLite использует `database.db` рядом с `main.py`. Для постоянного хранения на Railway рекомендуется Volume и переменная `DATABASE_PATH`.

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0). See `LICENSE`.
