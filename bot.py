# bot.py
import os
import sys
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

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

# Получаем токены (удаляем пробелы)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN").strip()
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY").strip()
FOLDER_ID = os.getenv("FOLDER_ID").strip()

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
    # ✅ Исправлено: убраны пробелы в URL
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
                    f"Если вопрос не по теме — скажи, что можешь помочь только с вопросами о школе. "
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

# Обработка ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

# Запуск бота
def main():
    if not all([TELEGRAM_TOKEN, YANDEX_API_KEY, FOLDER_ID]):
        logger.error("❌ Ошибка: не все токены указаны в .env")
        return

    logger.info("✅ Бот запускается...")

    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)

        PORT = int(os.environ.get("PORT", 10000))

        # 🚀 Формируем URL вебхука
        service_name = os.getenv('RENDER_SERVICE_NAME')
        if service_name:
            webhook_url = f"https://{service_name}.onrender.com/{TELEGRAM_TOKEN}"
        else:
            # ✅ Исправлено: убраны пробелы
            webhook_url = f"https://your-domain.com/{TELEGRAM_TOKEN}"  # для локальной разработки

        logger.info(f"🚀 Запуск бота на порту {PORT}")
        logger.info(f"🌐 Webhook URL: {webhook_url}")

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=webhook_url,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")
        # Fallback на polling для разработки
        if not os.getenv('RENDER_SERVICE_NAME'):
            logger.info("🔄 Попытка запуска в режиме polling...")
            app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
