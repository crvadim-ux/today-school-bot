import os
import sys
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверка версии Python
print(f"🐍 Python version: {sys.version}")
print(f"📦 Python executable: {sys.executable}")

# Загружаем переменные из .env
load_dotenv()

# Получаем токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")

# Глобальная инициализация приложения
application = None

# Читаем контекст школы
def load_school_context():
    try:
        with open("school_context.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("❌ Файл school_context.txt не найден!")
        return "Информация о школе не найдена."

SCHOOL_CONTEXT = load_school_context()

# Глобальный словарь для истории чатов
CHAT_HISTORY = {}

# Функция для запроса к YandexGPT с историей
async def ask_yandex_gpt(user_question: str, chat_history: list) -> str:
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [
        {
            "role": "system",
            "text": f"Ты — помощник детской языковой школы. "
                    f"Отвечай только на основе этой информации:\n{SCHOOL_CONTEXT}\n"
                    f"Если вопрос не по теме — скажи, что могу помочь только с вопросами о школе. "
                    f"Не выдумывай. Отвечай кратко, по делу."
        }
    ]

    for msg in chat_history:
        messages.append({"role": "user", "text": msg["question"]})
        messages.append({"role": "assistant", "text": msg["answer"]})

    messages.append({"role": "user", "text": user_question})

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "temperature": 0.6,
            "maxTokens": 500
        },
        "messages": messages
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        logger.error(f"❌ Ошибка при запросе к YandexGPT: {e}")
        return "Извините, сейчас не могу ответить. Попробуйте позже."

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"👋 /start от: {user.full_name} (@{user.username}, ID: {user.id})")
    await update.message.reply_text(
        "👋 Здравствуйте! Я — бот языковой школы Today.\n"
        "Я помогу вам узнать о занятиях, преподавателях, ценах и записаться на пробное занятие.\n"
        "Задайте ваш вопрос!"
    )

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text.strip()
    logger.info(f"💬 Пользователь {user.full_name} (@{user.username}): {user_text}")

    user_id = user.id
    if user_id not in CHAT_HISTORY:
        CHAT_HISTORY[user_id] = []

    history = CHAT_HISTORY[user_id]
    answer = await ask_yandex_gpt(user_text, history)

    history.append({"question": user_text, "answer": answer})
    if len(history) > 5:
        history.pop(0)

    logger.info(f"🤖 Бот: {answer}")
    await update.message.reply_text(answer)

# Обработка ошибки
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

# Создаем FastAPI приложение
app = FastAPI()

# Обработка вебхука с фиксированным путем
WEBHOOK_PATH = "/webhook"
@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    global application
    if application is None:
        logger.error("❌ Application не инициализировано")
        return {"error": "Application not initialized"}, 500
    update_data = await request.json()
    update = Update.de_json(update_data, application)
    logger.info(f"Получен вебхук: {update}")
    await application.process_update(update)
    return {"ok": True}

# Диагностический маршрут
@app.get("/")
async def root():
    return {"message": "Бот запущен, вебхук настроен на /webhook"}

# Запуск бота
def main():
    global application
    if not all([TELEGRAM_TOKEN, YANDEX_API_KEY, FOLDER_ID]):
        logger.error("❌ Ошибка: не все токены указаны в .env")
        return

    asyncio.run(start_bot())

async def start_bot():
    global application
    logger.info("✅ Бот запускается...")

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    await application.initialize()  # Инициализация приложения с await

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    PORT = int(os.environ.get("PORT", 10000))

    # Формируем URL вебхука с фиксированным путем
    service_name = os.getenv('RENDER_SERVICE_NAME', 'today-school-bot-2')
    webhook_url = f"https://{service_name}.onrender.com{WEBHOOK_PATH}"

    logger.info(f"🚀 Запуск бота на порту {PORT}")
    logger.info(f"🌐 Webhook URL: {webhook_url}")

    # Устанавливаем вебхук
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            data={"url": webhook_url}
        )
        response.raise_for_status()
        logger.info("✅ Webhook успешно установлен")
    except Exception as e:
        logger.error(f"❌ Ошибка при установке вебхука: {e}")
        return

    # Запускаем вебхук
    import uvicorn
    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    except KeyboardInterrupt:
        application.shutdown()  # Завершение работы приложения
        logger.info("✅ Бот завершил работу")

if __name__ == "__main__":
    main()
