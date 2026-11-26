# Поліна — голосовий асистент / Polina — Voice Assistant

Поліна — настільний асистент, який приймає текстові й голосові команди українською мовою, керує програмами та файлами й може відповідати голосом.

Polina is a desktop assistant that accepts Ukrainian text and voice commands, manages applications and files, and can respond with speech.

## Зміст / Contents

- [Поліна — голосовий асистент / Polina — Voice Assistant](#поліна--голосовий-асистент--polina--voice-assistant)
  - [Зміст / Contents](#зміст--contents)
  - [Встановлення / Installation](#встановлення--installation)
  - [Запуск / Launch](#запуск--launch)
  - [Користування / Usage](#користування--usage)
  - [Приклади команд / Command examples](#приклади-команд--command-examples)
  - [Структура проєкту / Project structure](#структура-проєкту--project-structure)
  - [Документація / Documentation](#документація--documentation)
  - [Висновок / Conclusion](#висновок--conclusion)

## Встановлення / Installation

Потрібен Python 3.12. У PowerShell з каталогу проєкту виконайте:

Python 3.12 is required. In PowerShell, from the project directory, run:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
```

## Запуск / Launch

Графічний інтерфейс / Graphical interface:

```powershell
python -m gui
```

Голосовий режим у терміналі / Voice mode in the terminal:

```powershell
python manage.py run_assistant
```

Локальний HTTP API (не потрібен для GUI) / Local HTTP API (not required by the GUI):

```powershell
python manage.py runserver 127.0.0.1:8000
```

GUI автоматично ініціалізує асистента у власному процесі й не запускає HTTP-сервер.

The GUI initializes the assistant in its own process and does not start the HTTP server.

## Користування / Usage

- **Текстова команда / Text command:** введіть команду в чаті й натисніть Enter. Для нового рядка натисніть Shift+Enter. / Enter a command in the chat and press Enter. Press Shift+Enter for a new line.
- **Голосова команда / Voice command:** натисніть кнопку мікрофона або Ctrl+M. Повторне натискання зупиняє прослуховування. / Click the microphone button or press Ctrl+M. Press again to stop listening.
- **Аудіопристрої / Audio devices:** у налаштуваннях виберіть мікрофон і вихідний пристрій та налаштуйте гучність. / In Settings, choose a microphone and output device, and adjust the volume.
- **Моделі ШІ / AI models:** відкрийте «Персоналізацію», щоб налаштувати провайдера й API-ключ. / Open Personalization to configure a provider and API key.
- **Запит до ШІ / AI request:** у текстовому чаті починайте повідомлення з `/ai`, наприклад `/ai що таке REST API`. Без цього префікса повідомлення обробляється як команда асистента. / In text chat, start a message with `/ai`, for example `/ai what is a REST API`. Without this prefix, the message is handled as an assistant command.
- **Уточнення / Follow-up:** введіть номер потрібного варіанта. Для підтвердження відповідайте «так» або «ні», для скасування — «скасувати». / Enter the number of the desired option. Reply yes or no to confirm, or cancel to stop.

## Приклади команд / Command examples

| Команда / Command | Дія / Action |
| --- | --- |
| `Відкрий Steam` | Відкрити програму / Open an application |
| `Закрий Telegram` | Закрити програму / Close an application |
| `Відкрий папку Завантаження` | Відкрити папку / Open a folder |
| `Знайди файл звіт.docx` | Знайти файл / Find a file |
| `Покажи відкриті папки` | Показати вікна Провідника / Show File Explorer windows |
| `Пауза` / `Продовж` | Призупинити або відновити обробку команд / Pause or resume command processing |
| `Зупини` | Завершити роботу асистента / Stop the assistant |

## Структура проєкту / Project structure

```text
Assistant/
├── Assistant/                 # Django settings and URL configuration
├── core/
│   ├── management/commands/   # Assistant command handling
│   └── response_analysis/     # Response and confirmation analysis
├── gui/
│   ├── assets/                # Icons and styles
│   └── widgets/               # GUI components
├── utils/                     # Audio, applications, files, and LLM utilities
├── tests/                     # Automated tests
├── manage.py                  # Django command-line entry point
├── requirements.txt           # Python dependencies
├── README.md                  # Usage guide (Ukrainian and English)
└── DOC.md                     # Technical documentation
```

## Документація / Documentation

- [Технічна документація / Technical documentation](./DOC.md)
- [Модуль аналізу відповідей / Response analyzer](./core/response_analysis/DOC.md)

## Висновок / Conclusion

Поліна поєднує голосове й текстове керування зручним настільним інтерфейсом. Асистент допомагає працювати з програмами та файлами, а інтеграція ШІ доступна за запитом через `/ai`.

Polina combines voice and text control in a desktop interface. It helps manage applications and files, with AI integration available on demand through `/ai`.
