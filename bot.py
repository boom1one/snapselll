import os
import time
import threading
import requests
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "8977186531:AAFwl7w9GWT7zDPBWHmTF4KQzD6npHQ8i5U"
CHANNEL_ID = "@SnapSell350"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)

# Хранилище данных
user_data = {}
user_states = {}
scheduled_replacements = []

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Отправка сообщения"""
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    response = requests.post(url, json=payload)
    return response.json()

def edit_message(chat_id, message_id, text, parse_mode="HTML"):
    """Редактирование сообщения"""
    url = f"{BASE_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    response = requests.post(url, json=payload)
    return response.json()

def delete_message(chat_id, message_id):
    """Удаление сообщения"""
    url = f"{BASE_URL}/deleteMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    response = requests.post(url, json=payload)
    return response.json()

def get_main_keyboard():
    """Главное меню"""
    return {
        "inline_keyboard": [
            [{"text": "📤 Выложить публикацию", "callback_data": "publish"}],
            [{"text": "✏️ Изменить шаблон автозамены", "callback_data": "change_template"}]
        ]
    }

# ========== ОБРАБОТЧИКИ КОМАНД ==========
def handle_start(chat_id):
    """Команда /start"""
    text = (
        "👋 *Добро пожаловать в бота управления публикациями!*\n\n"
        "Здесь вы можете:\n"
        "• *Выложить публикацию* в канал с автоматической заменой\n"
        "• *Изменить шаблон* для автозамены\n\n"
        "Выберите действие ниже 👇"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_publish_callback(chat_id):
    """Начало публикации"""
    user_states[chat_id] = "waiting_for_text"
    send_message(
        chat_id,
        "📝 *Отправьте текст публикации*, который вы хотите выложить в канал.\n\n"
        "Это может быть любой текст, ссылки, или форматирование."
    )

def handle_change_template_callback(chat_id):
    """Начало изменения шаблона"""
    current_template = user_data.get(chat_id, {}).get("template", "Не установлен")
    
    user_states[chat_id] = "waiting_for_template"
    send_message(
        chat_id,
        f"📝 *Текущий шаблон автозамены:*\n"
        f"`{current_template}`\n\n"
        f"✍️ *Отправьте новый текст шаблона*, на который будут заменяться публикации.\n\n"
        f"Вы можете использовать *HTML-теги* для форматирования:\n"
        f"`<b>жирный</b>`, `<i>курсив</i>`, `<a href='url'>ссылка</a>`"
    )

def handle_text_message(chat_id, text):
    """Обработка текстовых сообщений"""
    state = user_states.get(chat_id)
    
    if state == "waiting_for_text":
        user_data[chat_id] = user_data.get(chat_id, {})
        user_data[chat_id]["publish_text"] = text
        
        user_states[chat_id] = "waiting_for_time"
        send_message(
            chat_id,
            "⏱ *Укажите время в минутах*, через которое публикация заменится на шаблон.\n\n"
            "Пример: `120` — замена через 2 часа.\n"
            "Отправьте *только число*."
        )
    
    elif state == "waiting_for_time":
        try:
            delay_minutes = int(text.strip())
            if delay_minutes <= 0:
                raise ValueError("Время должно быть положительным")
        except ValueError:
            send_message(chat_id, "❌ Пожалуйста, отправьте *положительное целое число* (количество минут).")
            return
        
        publish_text = user_data.get(chat_id, {}).get("publish_text")
        if not publish_text:
            send_message(chat_id, "❌ Ошибка: текст публикации не найден. Начните заново /start")
            user_states.pop(chat_id, None)
            return
        
        # Публикуем в канал
        try:
            url = f"{BASE_URL}/sendMessage"
            payload = {
                "chat_id": CHANNEL_ID,
                "text": publish_text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload).json()
            
            if response.get("ok"):
                message_id = response["result"]["message_id"]
                
                # Сохраняем данные для замены
                if chat_id not in user_data:
                    user_data[chat_id] = {}
                
                user_data[chat_id]["last_post"] = {
                    "message_id": message_id,
                    "replace_at": datetime.now() + timedelta(minutes=delay_minutes),
                    "template": user_data.get(chat_id, {}).get("template", "⚠️ Этот пост был автоматически заменён по шаблону.")
                }
                
                # Планируем замену
                schedule_replacement(chat_id, delay_minutes)
                
                send_message(
                    chat_id,
                    f"✅ *Публикация успешно выложена!*\n\n"
                    f"🔹 Текст опубликован в канале.\n"
                    f"🔹 Замена произойдет через *{delay_minutes} минут*.\n\n"
                    f"⏳ Таймер запущен!",
                    reply_markup=get_main_keyboard()
                )
                
                user_states.pop(chat_id, None)
            else:
                send_message(
                    chat_id,
                    "❌ *Ошибка при публикации!*\n"
                    "Проверьте, что бот является администратором канала и имеет права на отправку сообщений.",
                    reply_markup=get_main_keyboard()
                )
        except Exception as e:
            send_message(
                chat_id,
                f"❌ Ошибка: {str(e)}",
                reply_markup=get_main_keyboard()
            )
    
    elif state == "waiting_for_template":
        if chat_id not in user_data:
            user_data[chat_id] = {}
        
        user_data[chat_id]["template"] = text
        
        send_message(
            chat_id,
            "✅ *Шаблон успешно обновлен!*\n\n"
            f"📌 Новый шаблон:\n"
            f"`{text}`\n\n"
            "Теперь все будущие публикации будут заменяться на этот шаблон.",
            reply_markup=get_main_keyboard()
        )
        user_states.pop(chat_id, None)

def schedule_replacement(chat_id, delay_minutes):
    """Планирование замены в отдельном потоке"""
    def replace_post():
        time.sleep(delay_minutes * 60)
        
        try:
            if chat_id not in user_data:
                return
            
            post_data = user_data[chat_id].get("last_post")
            if not post_data:
                return
            
            template = user_data[chat_id].get("template", "⚠️ Этот пост был автоматически заменён по шаблону.")
            
            # Редактируем сообщение
            edit_message(CHANNEL_ID, post_data["message_id"], template)
            
            # Удаляем данные о посте
            del user_data[chat_id]["last_post"]
            
        except Exception as e:
            print(f"Ошибка замены поста: {e}")
    
    thread = threading.Thread(target=replace_post)
    thread.daemon = True
    thread.start()

# ========== ВЕБХУК ==========
@app.route("/", methods=["GET", "POST"])
def webhook():
    """Обработка входящих обновлений"""
    if request.method == "GET":
        return "Bot is running!"
    
    try:
        update = request.get_json()
        if not update:
            return jsonify({"status": "ok"})
        
        # Обработка сообщений
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            
            if "text" in message:
                text = message["text"]
                
                if text.startswith("/start"):
                    handle_start(chat_id)
                else:
                    handle_text_message(chat_id, text)
        
        # Обработка callback'ов
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            
            # Ответ на callback
            url = f"{BASE_URL}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback["id"]})
            
            # Удаляем сообщение с кнопками
            delete_message(chat_id, callback["message"]["message_id"])
            
            if data == "publish":
                handle_publish_callback(chat_id)
            elif data == "change_template":
                handle_change_template_callback(chat_id)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Устанавливаем вебхук
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
    set_webhook_url = f"{BASE_URL}/setWebhook?url={webhook_url}"
    requests.get(set_webhook_url)
    
    print("🚀 Бот запущен!")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
