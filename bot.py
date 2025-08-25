# bot.py
import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Получаем токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")

# Читаем контекст школы
def load_school_context():
    try:
        with open("school_context.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("❌ Файл school_context.txt не найден!")
        return "Информация о школе не найдена."

SCHOOL_CONTEXT = load_school_context()

# Глобальный словарь для истории чатов
CHAT_HISTORY = {}

# Функция для запроса к YandexGPT с историей
async def ask_yandex_gpt(user_question: str, chat_history: list) -> str:
    # 🔴 ИСПРАВЛЕНО: убран лишний пробел в конце URL
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    # Создаём полный список сообщений
    messages = [
        {
            "role": "system",
            "text": f"Ты — помощник детской языковой школы. "
                    f"Отвечай только на основе этой информации:\n{SCHOOL_CONTEXT}\n"
                    f"Если вопрос не по теме — скажи, что можешь помочь только с вопросами о школе. "
                    f"Не выдумывай. Отвечай кратко, по делу."
        }
    ]

    # Добавляем историю
    for msg in chat_history:
        messages.append({
            "role": "user",
            "text": msg["question"]
        })
        messages.append({
            "role": "assistant",
            "text": msg["answer"]
        })

    # Добавляем новый вопрос
    messages.append({
        "role": "user",
        "text": user_question
    })

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
        result = response.json()
        return result["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        print(f"❌ Ошибка при запросе к YandexGPT: {e}")
        return "Извините, сейчас не могу ответить."

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    print(f"👋 /start от: {user.full_name} (@{user.username}, ID: {user.id})")
    await update.message.reply_text(
        "👋 Здравствуйте! Я — бот языковой школы Today.\n"
        "Я помогу вам узнать о занятиях, преподавателях, ценах и записаться на пробное занятие.\n"
        "Задайте ваш вопрос!"
    )

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text.strip()
    
    # 🔥 ЛОГИРУЕМ ВХОДЯЩЕЕ СООБЩЕНИЕ
    print(f"💬 Пользователь {user.full_name} (@{user.username}): {user_text}")

    user_id = user.id
    if user_id not in CHAT_HISTORY:
        CHAT_HISTORY[user_id] = []

    # Получаем ответ
    history = CHAT_HISTORY[user_id]
    answer = await ask_yandex_gpt(user_text, history)

    # Сохраняем в историю
    history.append({
        "question": user_text,
        "answer": answer
    })
    if len(history) > 5:
        history.pop(0)

    # 🔥 ЛОГИРУЕМ ОТВЕТ БОТА
    print(f"🤖 Бот: {answer}")

    await update.message.reply_text(answer)

# Запуск бота
def main():
    if not all([TELEGRAM_TOKEN, YANDEX_API_KEY, FOLDER_ID]):
        print("❌ Ошибка: не все токены указаны в .env")
        return

    print("✅ Бот запускается...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Бот запущен и слушает сообщения...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()