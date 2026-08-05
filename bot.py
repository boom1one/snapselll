import os
import time
import threading
import requests
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import logging

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "8857819530:AAF_XClRgpje6cZ08HDZMEVGyXqMnVUyqNE"
CHANNEL_ID = "@testiktiks"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)

# Хранилище данных
user_data = {}
user_states = {}

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
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return {"ok": False, "error": str(e)}

def edit_message(chat_id, message_id, text, parse_mode="HTML"):
    """Редактирование сообщения"""
    url = f"{BASE_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        return {"ok": False, "error": str(e)}

def delete_message(chat_id, message_id):
    """Удаление сообщения"""
    url = f"{BASE_URL}/deleteMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка удаления сообщения: {e}")
        return {"ok": False, "error": str(e)}

def send_to_channel(text, parse_mode="HTML"):
    """Отправка сообщения в канал с проверкой"""
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()
        if result.get("ok"):
            logger.info(f"✅ Сообщение отправлено в канал")
        else:
            logger.error(f"❌ Ошибка отправки в канал: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в канал: {e}")
        return {"ok": False, "error": str(e)}

def get_main_keyboard():
    """Главное меню"""
    return {
        "inline_keyboard": [
            [{"text": "📤 Выложить публикацию", "callback_data": "publish"}],
            [{"text": "✏️ Изменить шаблон автозамены", "callback_data": "change_template"}],
            [{"text": "📋 Мои публикации", "callback_data": "my_posts"}]
        ]
    }

# ========== ОБРАБОТЧИКИ КОМАНД ==========
def handle_start(chat_id):
    """Команда /start"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        logger.info(f"👤 Новый пользователь: {chat_id}")
    
    text = (
        "👋 *Добро пожаловать в бота управления публикациями!*\n\n"
        "Здесь вы можете:\n"
        "• *Выложить публикацию* в канал с автоматической заменой\n"
        "• *Изменить шаблон* для автозамены\n"
        "• *Просмотреть свои публикации*\n\n"
        "Выберите действие ниже 👇"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_publish_callback(chat_id):
    """Начало публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    user_states[chat_id] = "waiting_for_text"
    send_message(
        chat_id,
        "📝 *Отправьте текст публикации*, который вы хотите выложить в канал.\n\n"
        "Это может быть любой текст, ссылки, или форматирование."
    )

def handle_change_template_callback(chat_id):
    """Начало изменения шаблона"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    current_template = user_data[chat_id].get("template", "Не установлен")
    
    user_states[chat_id] = "waiting_for_template"
    send_message(
        chat_id,
        f"📝 *Текущий шаблон автозамены:*\n"
        f"`{current_template}`\n\n"
        f"✍️ *Отправьте новый текст шаблона*, на который будут заменяться *НОВЫЕ* публикации.\n\n"
        f"⚠️ *Важно:* Изменение шаблона не повлияет на уже опубликованные посты.\n\n"
        f"Вы можете использовать *HTML-теги* для форматирования:\n"
        f"`<b>жирный</b>`, `<i>курсив</i>`, `<a href='url'>ссылка</a>`"
    )

def handle_my_posts_callback(chat_id):
    """Показывает все активные публикации пользователя"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    publications = user_data[chat_id].get("publications", [])
    
    if not publications:
        send_message(
            chat_id,
            "📭 *У вас нет активных публикаций*\n\n"
            "Создайте новую публикацию!",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "📊 *Ваши активные публикации*\n\n"
    
    for i, pub in enumerate(publications, 1):
        time_left = (pub["replace_at"] - datetime.now()).total_seconds()
        if time_left > 0:
            minutes_left = int(time_left / 60)
            hours_left = minutes_left // 60
            mins_left = minutes_left % 60
            
            if hours_left > 0:
                time_str = f"{hours_left}ч {mins_left}м"
            else:
                time_str = f"{mins_left}м"
        else:
            time_str = "⏳ Скоро"
        
        text += f"*{i}.* ID: `{pub['message_id']}`\n"
        text += f"   ⏱ Замена через: *{time_str}*\n"
        text += f"   📝 Шаблон: `{pub['template'][:40]}{'...' if len(pub['template']) > 40 else ''}`\n\n"
    
    text += f"\n📊 Всего активных публикаций: *{len(publications)}*"
    
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_text_message(chat_id, text):
    """Обработка текстовых сообщений"""
    state = user_states.get(chat_id)
    
    if state == "waiting_for_text":
        handle_publish_text(chat_id, text)
    elif state == "waiting_for_time":
        handle_publish_time(chat_id, text)
    elif state == "waiting_for_template":
        handle_template_save(chat_id, text)

def handle_publish_text(chat_id, text):
    """Обработка текста публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    user_data[chat_id]["publish_text"] = text
    user_states[chat_id] = "waiting_for_time"
    
    send_message(
        chat_id,
        "⏱ *Укажите время в минутах*, через которое публикация заменится на шаблон.\n\n"
        "Пример: `120` — замена через 2 часа.\n"
        "Отправьте *только число*."
    )

def handle_publish_time(chat_id, text):
    """Обработка времени публикации"""
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
    
    try:
        # Отправляем в канал
        result = send_to_channel(publish_text)
        
        if result.get("ok"):
            message_id = result["result"]["message_id"]
            
            current_template = user_data[chat_id].get("template", "⚠️ Этот пост был автоматически заменён по шаблону.")
            
            publication = {
                "message_id": message_id,
                "replace_at": datetime.now() + timedelta(minutes=delay_minutes),
                "template": current_template,
                "chat_id": CHANNEL_ID,
                "created_at": datetime.now().isoformat()
            }
            
            if "publications" not in user_data[chat_id]:
                user_data[chat_id]["publications"] = []
            
            user_data[chat_id]["publications"].append(publication)
            
            schedule_replacement(chat_id, publication)
            
            send_message(
                chat_id,
                f"✅ *Публикация успешно выложена!*\n\n"
                f"🔹 Текст опубликован в канале.\n"
                f"🔹 Замена произойдет через *{delay_minutes} минут*.\n"
                f"🔹 Шаблон зафиксирован:\n"
                f"`{current_template[:50]}{'...' if len(current_template) > 50 else ''}`\n\n"
                f"⏳ Таймер запущен!\n"
                f"📊 Всего активных публикаций: *{len(user_data[chat_id]['publications'])}*",
                reply_markup=get_main_keyboard()
            )
            
            user_states.pop(chat_id, None)
            user_data[chat_id].pop("publish_text", None)
        else:
            error_msg = result.get('description', 'Неизвестная ошибка')
            send_message(
                chat_id,
                f"❌ *Ошибка при публикации!*\n\n"
                f"Причина: {error_msg}\n\n"
                f"Проверьте, что бот является администратором канала.",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        send_message(
            chat_id,
            f"❌ Ошибка: {str(e)}",
            reply_markup=get_main_keyboard()
        )

def handle_template_save(chat_id, text):
    """Сохранение нового шаблона"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    user_data[chat_id]["template"] = text
    
    active_publications = user_data[chat_id].get("publications", [])
    active_count = len(active_publications)
    
    response_text = (
        "✅ *Шаблон успешно обновлен!*\n\n"
        f"📌 Новый шаблон (для будущих публикаций):\n"
        f"`{text}`\n\n"
        f"⚠️ *Важно:*\n"
        f"• Уже опубликованные посты (*{active_count} шт.*) заменятся на СВОИ шаблоны.\n"
        f"• Новый шаблон будет применяться только к *НОВЫМ* публикациям."
    )
    
    send_message(
        chat_id,
        response_text,
        reply_markup=get_main_keyboard()
    )
    user_states.pop(chat_id, None)

# ========== ФОНОВЫЕ ЗАДАЧИ ==========
def schedule_replacement(chat_id, publication):
    """Планирование замены конкретной публикации"""
    def replace_post():
        wait_seconds = (publication["replace_at"] - datetime.now()).total_seconds()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        
        try:
            if chat_id not in user_data:
                return
            
            publications = user_data[chat_id].get("publications", [])
            
            found_pub = None
            for pub in publications:
                if pub["message_id"] == publication["message_id"]:
                    found_pub = pub
                    break
            
            if not found_pub:
                return
            
            template = found_pub["template"]
            result = edit_message(CHANNEL_ID, publication["message_id"], template)
            
            if result.get("ok"):
                logger.info(f"✅ Пост {publication['message_id']} заменён на шаблон")
            else:
                logger.error(f"❌ Ошибка замены поста: {result}")
            
            user_data[chat_id]["publications"] = [
                pub for pub in publications 
                if pub["message_id"] != publication["message_id"]
            ]
            
        except Exception as e:
            logger.error(f"❌ Ошибка замены поста {publication['message_id']}: {e}")
            if chat_id in user_data:
                publications = user_data[chat_id].get("publications", [])
                user_data[chat_id]["publications"] = [
                    pub for pub in publications 
                    if pub["message_id"] != publication["message_id"]
                ]
    
    thread = threading.Thread(target=replace_post, daemon=True)
    thread.start()
    logger.info(f"⏱️ Запланирована замена поста {publication['message_id']}")

# ========== ВЕБХУК ==========
@app.route("/", methods=["GET", "HEAD", "POST"])
def webhook():
    """Обработка входящих обновлений"""
    # Обработка HEAD запросов (проверка здоровья от Render)
    if request.method == "HEAD":
        return "", 200
    
    # Обработка GET запросов
    if request.method == "GET":
        return "Bot is running!"
    
    # Обработка POST запросов (только для Telegram)
    try:
        # Проверяем Content-Type
        if request.headers.get('Content-Type') != 'application/json':
            logger.warning(f"Неверный Content-Type: {request.headers.get('Content-Type')}")
            return jsonify({"status": "ok"}), 200
        
        update = request.get_json()
        if not update:
            return jsonify({"status": "ok"}), 200
        
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            
            if "text" in message:
                text = message["text"]
                
                if text.startswith("/start"):
                    handle_start(chat_id)
                else:
                    handle_text_message(chat_id, text)
        
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            
            url = f"{BASE_URL}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback["id"]})
            
            delete_message(chat_id, callback["message"]["message_id"])
            
            if data == "publish":
                handle_publish_callback(chat_id)
            elif data == "change_template":
                handle_change_template_callback(chat_id)
            elif data == "my_posts":
                handle_my_posts_callback(chat_id)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Устанавливаем вебхук
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
    set_webhook_url = f"{BASE_URL}/setWebhook?url={webhook_url}"
    response = requests.get(set_webhook_url)
    
    if response.status_code == 200:
        logger.info(f"✅ Вебхук установлен: {webhook_url}")
        logger.info(f"📊 Ответ: {response.json()}")
    else:
        logger.error(f"❌ Ошибка установки вебхука: {response.status_code}")
        logger.error(f"Текст ошибки: {response.text}")
    
    logger.info("🚀 Бот запущен!")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
