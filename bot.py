import os
import time
import threading
import requests
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

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
    # Инициализируем пользователя
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
        f"⚠️ *Важно:* Изменение шаблона не повлияет на уже опубликованные посты - они заменятся на тот шаблон, который был активен в момент их публикации.\n\n"
        f"Вы можете использовать *HTML-теги* для форматирования:\n"
        f"`<b>жирный</b>`, `<i>курсив</i>`, `<a href='url'>ссылка</a>`"
    )

def handle_text_message(chat_id, text):
    """Обработка текстовых сообщений"""
    state = user_states.get(chat_id)
    
    if state == "waiting_for_text":
        # Инициализируем пользователя если нужно
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
                
                # СОХРАНЯЕМ ТЕКУЩИЙ ШАБЛОН ДЛЯ ЭТОЙ ПУБЛИКАЦИИ
                current_template = user_data[chat_id].get("template", "⚠️ Этот пост был автоматически заменён по шаблону.")
                
                # Создаём запись о публикации с ЗАФИКСИРОВАННЫМ шаблоном
                publication = {
                    "message_id": message_id,
                    "replace_at": datetime.now() + timedelta(minutes=delay_minutes),
                    "template": current_template,  # Шаблон фиксируется в момент публикации
                    "chat_id": CHANNEL_ID,
                    "created_at": datetime.now().isoformat()
                }
                
                # Добавляем в список публикаций
                if "publications" not in user_data[chat_id]:
                    user_data[chat_id]["publications"] = []
                
                user_data[chat_id]["publications"].append(publication)
                
                # Планируем замену для этой конкретной публикации
                schedule_replacement(chat_id, publication)
                
                send_message(
                    chat_id,
                    f"✅ *Публикация успешно выложена!*\n\n"
                    f"🔹 Текст опубликован в канале.\n"
                    f"🔹 Замена произойдет через *{delay_minutes} минут*.\n"
                    f"🔹 Шаблон для замены ЗАФИКСИРОВАН:\n"
                    f"`{current_template[:50]}{'...' if len(current_template) > 50 else ''}`\n\n"
                    f"⏳ Таймер запущен!\n"
                    f"📊 Всего активных публикаций: *{len(user_data[chat_id]['publications'])}*",
                    reply_markup=get_main_keyboard()
                )
                
                user_states.pop(chat_id, None)
                # Удаляем временный текст
                user_data[chat_id].pop("publish_text", None)
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
            user_data[chat_id] = {
                "publications": [],
                "template": "⚠️ Этот пост был автоматически заменён по шаблону."
            }
        
        # Сохраняем НОВЫЙ шаблон для БУДУЩИХ публикаций
        user_data[chat_id]["template"] = text
        
        # Показываем список активных публикаций с их шаблонами
        active_publications = user_data[chat_id].get("publications", [])
        active_count = len(active_publications)
        
        response_text = (
            "✅ *Шаблон успешно обновлен!*\n\n"
            f"📌 Новый шаблон (для будущих публикаций):\n"
            f"`{text}`\n\n"
            f"⚠️ *Важно:*\n"
            f"• Уже опубликованные посты (*{active_count} шт.*) заменятся на СВОИ шаблоны,\n"
            f"  которые были зафиксированы в момент их публикации.\n"
            f"• Новый шаблон будет применяться только к *НОВЫМ* публикациям.\n\n"
            "Теперь все будущие публикации будут заменяться на этот шаблон."
        )
        
        send_message(
            chat_id,
            response_text,
            reply_markup=get_main_keyboard()
        )
        user_states.pop(chat_id, None)

def schedule_replacement(chat_id, publication):
    """Планирование замены конкретной публикации в отдельном потоке"""
    def replace_post():
        # Ждём указанное время
        wait_seconds = (publication["replace_at"] - datetime.now()).total_seconds()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        
        try:
            # Проверяем, существует ли ещё эта публикация в списке
            if chat_id not in user_data:
                return
            
            publications = user_data[chat_id].get("publications", [])
            
            # Ищем эту публикацию по message_id
            found_pub = None
            for pub in publications:
                if pub["message_id"] == publication["message_id"]:
                    found_pub = pub
                    break
            
            if not found_pub:
                return  # Публикация уже была заменена или удалена
            
            # Используем шаблон, который был ЗАФИКСИРОВАН при публикации
            template = found_pub["template"]
            
            # Редактируем сообщение
            edit_message(CHANNEL_ID, publication["message_id"], template)
            
            # Удаляем эту публикацию из списка
            user_data[chat_id]["publications"] = [
                pub for pub in publications 
                if pub["message_id"] != publication["message_id"]
            ]
            
            print(f"✅ Пост {publication['message_id']} заменён на шаблон для пользователя {chat_id}")
            print(f"📝 Использован шаблон: {template[:50]}...")
            
        except Exception as e:
            print(f"❌ Ошибка замены поста {publication['message_id']}: {e}")
            
            # В случае ошибки всё равно удаляем публикацию из списка, чтобы избежать повторных попыток
            if chat_id in user_data:
                publications = user_data[chat_id].get("publications", [])
                user_data[chat_id]["publications"] = [
                    pub for pub in publications 
                    if pub["message_id"] != publication["message_id"]
                ]
    
    thread = threading.Thread(target=replace_post)
    thread.daemon = True
    thread.start()

# ========== КОМАНДА ДЛЯ ПРОСМОТРА АКТИВНЫХ ПУБЛИКАЦИЙ ==========
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
                elif text.startswith("/my_posts"):
                    handle_my_posts(chat_id)
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
        print(f"❌ Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def handle_my_posts(chat_id):
    """Показывает все активные публикации пользователя"""
    if chat_id not in user_data or not user_data[chat_id].get("publications"):
        send_message(
            chat_id,
            "📭 У вас нет активных публикаций, ожидающих замены.",
            reply_markup=get_main_keyboard()
        )
        return
    
    publications = user_data[chat_id]["publications"]
    text = f"📊 *Ваши активные публикации:* ({len(publications)} шт.)\n\n"
    
    for i, pub in enumerate(publications, 1):
        time_left = (pub["replace_at"] - datetime.now()).total_seconds()
        minutes_left = int(time_left / 60)
        hours_left = minutes_left // 60
        mins_left = minutes_left % 60
        
        if hours_left > 0:
            time_str = f"{hours_left}ч {mins_left}м"
        else:
            time_str = f"{mins_left}м"
        
        text += f"*{i}.* ID: `{pub['message_id']}`\n"
        text += f"   ⏱ Замена через: *{time_str}*\n"
        text += f"   📝 Шаблон: `{pub['template'][:30]}{'...' if len(pub['template']) > 30 else ''}`\n\n"
    
    send_message(chat_id, text, reply_markup=get_main_keyboard())

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Устанавливаем вебхук
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
    set_webhook_url = f"{BASE_URL}/setWebhook?url={webhook_url}"
    response = requests.get(set_webhook_url)
    print(f"✅ Вебхук установлен: {webhook_url}")
    print(f"📊 Ответ: {response.json()}")
    
    print("🚀 Бот запущен!")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
