СИСТЕМНЫЕ ЗАВИСИМОСТИ ОКО

Если при запуске появляется ошибка Qt xcb:

    xcb-cursor0 or libxcb-cursor0 is needed
    Could not load the Qt platform plugin "xcb"

значит в системе не хватает системного пакета libxcb-cursor0.

Установщик Око не запускает sudo автоматически.
Команду должен выполнить администратор:

    sudo apt update
    sudo apt install -y libxcb-cursor0 python3-venv python3-pip libnss3 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2t64

Примечание:
на новых Ubuntu пакет libasound2 заменён на libasound2t64.
Проверочный скрипт принимает оба варианта: libasound2 и libasound2t64.

Проверка выполняется файлом:

    CHECK_SYSTEM_DEPS.sh
