import os
import time
import threading
import requests
import json
import pickle
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

# ========== АДМИНИСТРАТОРЫ ==========
# Список ID пользователей, которым разрешен доступ
ALLOWED_USERS = [
    1524345644,  # @piggass - ГЛАВНЫЙ АДМИНИСТРАТОР
]

# Файл для хранения данных
DATA_FILE = "bot_data.pkl"

app = Flask(__name__)

# Хранилище данных
user_data = {}
user_states = {}

# ========== РАБОТА С ДАННЫМИ ==========
def save_data():
    """Сохранение данных в файл"""
    try:
        data_to_save = {
            "user_data": user_data,
            "user_states": user_states,
            "allowed_users": ALLOWED_USERS
        }
        with open(DATA_FILE, "wb") as f:
            pickle.dump(data_to_save, f)
        logger.info("💾 Данные сохранены")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")

def load_data():
    """Загрузка данных из файла"""
    global user_data, user_states, ALLOWED_USERS
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "rb") as f:
                data = pickle.load(f)
                user_data = data.get("user_data", {})
                user_states = data.get("user_states", {})
                ALLOWED_USERS = data.get("allowed_users", ALLOWED_USERS)
            logger.info(f"📂 Данные загружены: {len(user_data)} пользователей")
            logger.info(f"👥 Разрешено пользователей: {len(ALLOWED_USERS)}")
            
            # Восстанавливаем таймеры
            restore_timers()
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
    return False

def restore_timers():
    """Восстановление таймеров после перезагрузки"""
    restored_count = 0
    for chat_id, data in user_data.items():
        # Восстанавливаем автопубликации
        for pub in data.get("auto_publications", []):
            if pub.get("active", False):
                schedule_auto_publication(chat_id, pub)
                restored_count += 1
                logger.info(f"🔄 Восстановлена автопубликация {pub['id']}")
        
        # Восстанавливаем обычные публикации
        for pub in data.get("publications", []):
            if datetime.now() < pub["replace_at"]:
                schedule_replacement(chat_id, pub)
                restored_count += 1
                logger.info(f"🔄 Восстановлен таймер для поста {pub['message_id']}")
            else:
                logger.info(f"⏰ Пост {pub['message_id']} просрочен, заменяем")
                replace_post_immediately(chat_id, pub)
    
    if restored_count > 0:
        logger.info(f"🔄 Восстановлено {restored_count} задач")

def replace_post_immediately(chat_id, publication):
    """Немедленная замена поста"""
    try:
        template = publication["template"]
        result = edit_message(CHANNEL_ID, publication["message_id"], template)
        
        if result.get("ok"):
            logger.info(f"✅ Пост {publication['message_id']} заменён")
        else:
            logger.error(f"❌ Ошибка замены: {result}")
        
        if chat_id in user_data:
            user_data[chat_id]["publications"] = [
                pub for pub in user_data[chat_id]["publications"]
                if pub["message_id"] != publication["message_id"]
            ]
            save_data()
    except Exception as e:
        logger.error(f"❌ Ошибка немедленной замены: {e}")

# ========== ПРОВЕРКА ДОСТУПА ==========
def is_allowed_user(chat_id):
    """Проверка, имеет ли пользователь доступ"""
    return chat_id in ALLOWED_USERS

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
            [{"text": "🔄 Автопубликации", "callback_data": "auto_publish"}]
        ]
    }

def get_back_keyboard():
    """Клавиатура с кнопкой Назад"""
    return {
        "inline_keyboard": [
            [{"text": "🔙 Назад", "callback_data": "back_to_menu"}]
        ]
    }

# ========== ОБРАБОТЧИКИ КОМАНД ==========
def handle_start(chat_id):
    """Команда /start с проверкой доступа"""
    if not is_allowed_user(chat_id):
        send_message(
            chat_id,
            "🚫 *У вас нет панели администратора для пользования данным ботом*\n\n"
            "Доступ разрешен только администраторам."
        )
        logger.warning(f"⚠️ Неавторизованный доступ: {chat_id}")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
        logger.info(f"👤 Новый администратор: {chat_id}")
    
    text = (
        "👋 *Добро пожаловать в бота управления публикациями!*\n\n"
        "Здесь вы можете:\n"
        "• *Выложить публикацию* в канал с автоматической заменой\n"
        "• *Изменить шаблон* для автозамены\n"
        "• *Настроить автопубликации* - периодическая публикация постов\n\n"
        "Выберите действие ниже 👇"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_publish_callback(chat_id):
    """Начало публикации"""
    if not is_allowed_user(chat_id):
        send_message(chat_id, "🚫 У вас нет доступа к этому боту.")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_states[chat_id] = "waiting_for_text"
    send_message(
        chat_id,
        "📝 *Отправьте текст публикации*, который вы хотите выложить в канал.\n\n"
        "Это может быть любой текст, ссылки, или форматирование.",
        reply_markup=get_back_keyboard()
    )

def handle_change_template_callback(chat_id):
    """Начало изменения шаблона"""
    if not is_allowed_user(chat_id):
        send_message(chat_id, "🚫 У вас нет доступа к этому боту.")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    current_template = user_data[chat_id].get("template", "Не установлен")
    
    user_states[chat_id] = "waiting_for_template"
    send_message(
        chat_id,
        f"📝 *Текущий шаблон автозамены:*\n"
        f"`{current_template}`\n\n"
        f"✍️ *Отправьте новый текст шаблона*, на который будут заменяться *НОВЫЕ* публикации.\n\n"
        f"⚠️ *Важно:* Изменение шаблона не повлияет на уже опубликованные посты.\n\n"
        f"Вы можете использовать *HTML-теги* для форматирования:\n"
        f"`<b>жирный</b>`, `<i>курсив</i>`, `<a href='url'>ссылка</a>`",
        reply_markup=get_back_keyboard()
    )

def handle_auto_publish_callback(chat_id):
    """Начало настройки автопубликации"""
    if not is_allowed_user(chat_id):
        send_message(chat_id, "🚫 У вас нет доступа к этому боту.")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_states[chat_id] = "waiting_for_auto_text"
    send_message(
        chat_id,
        "🔄 *Настройка автопубликации*\n\n"
        "📝 *Отправьте текст поста*, который будет публиковаться автоматически.\n\n"
        "Это может быть любой текст, ссылки, или форматирование.",
        reply_markup=get_back_keyboard()
    )

def handle_back_to_menu(chat_id):
    """Возврат в главное меню"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_states.pop(chat_id, None)
    send_message(
        chat_id,
        "🔙 *Возврат в главное меню*\n\nВыберите действие:",
        reply_markup=get_main_keyboard()
    )

def handle_text_message(chat_id, text):
    """Обработка текстовых сообщений"""
    if not is_allowed_user(chat_id):
        send_message(chat_id, "🚫 У вас нет доступа к этому боту.")
        return
    
    state = user_states.get(chat_id)
    
    if state == "waiting_for_text":
        handle_publish_text(chat_id, text)
    elif state == "waiting_for_time":
        handle_publish_time(chat_id, text)
    elif state == "waiting_for_template":
        handle_template_save(chat_id, text)
    elif state == "waiting_for_auto_text":
        handle_auto_text(chat_id, text)
    elif state == "waiting_for_auto_interval":
        handle_auto_interval(chat_id, text)
    elif state == "waiting_for_auto_count":
        handle_auto_count(chat_id, text)

# ========== ОБЫЧНЫЕ ПУБЛИКАЦИИ ==========
def handle_publish_text(chat_id, text):
    """Обработка текста публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_data[chat_id]["publish_text"] = text
    user_states[chat_id] = "waiting_for_time"
    
    send_message(
        chat_id,
        "⏱ *Укажите время в минутах*, через которое публикация заменится на шаблон.\n\n"
        "Пример: `120` — замена через 2 часа.\n"
        "Отправьте *только число*.",
        reply_markup=get_back_keyboard()
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
            save_data()
            
            schedule_replacement(chat_id, publication)
            
            send_message(
                chat_id,
                f"✅ *Публикация успешно выложена!*\n\n"
                f"🔹 Текст опубликован в канале.\n"
                f"🔹 Замена произойдет через *{delay_minutes} минут*.\n"
                f"🔹 Шаблон зафиксирован:\n"
                f"`{current_template[:50]}{'...' if len(current_template) > 50 else ''}`\n\n"
                f"⏳ Таймер запущен!",
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
        send_message(chat_id, f"❌ Ошибка: {str(e)}", reply_markup=get_main_keyboard())

def handle_template_save(chat_id, text):
    """Сохранение нового шаблона"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_data[chat_id]["template"] = text
    save_data()
    
    send_message(
        chat_id,
        f"✅ *Шаблон успешно обновлен!*\n\n"
        f"📌 Новый шаблон:\n`{text}`",
        reply_markup=get_main_keyboard()
    )
    user_states.pop(chat_id, None)

# ========== АВТОПУБЛИКАЦИИ ==========
def handle_auto_text(chat_id, text):
    """Обработка текста автопубликации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "auto_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_data[chat_id]["auto_text"] = text
    user_states[chat_id] = "waiting_for_auto_interval"
    
    send_message(
        chat_id,
        "⏱ *Укажите интервал в минутах* между публикациями.\n\n"
        "Пример: `60` — публикация каждый час.\n"
        "Отправьте *только число*.",
        reply_markup=get_back_keyboard()
    )

def handle_auto_interval(chat_id, text):
    """Обработка интервала автопубликации"""
    try:
        interval_minutes = int(text.strip())
        if interval_minutes <= 0:
            raise ValueError("Интервал должен быть положительным")
    except ValueError:
        send_message(chat_id, "❌ Пожалуйста, отправьте *положительное целое число* (количество минут).")
        return
    
    user_data[chat_id]["auto_interval"] = interval_minutes
    user_states[chat_id] = "waiting_for_auto_count"
    
    send_message(
        chat_id,
        f"🔢 *Укажите количество публикаций*\n\n"
        f"Сколько раз должен опубликоваться пост?\n"
        f"Интервал: *{interval_minutes} минут*\n\n"
        f"Пример: `5` — опубликуется 5 раз.",
        reply_markup=get_back_keyboard()
    )

def handle_auto_count(chat_id, text):
    """Обработка количества автопубликаций"""
    try:
        count = int(text.strip())
        if count <= 0:
            raise ValueError("Количество должно быть положительным")
    except ValueError:
        send_message(chat_id, "❌ Пожалуйста, отправьте *положительное целое число*.")
        return
    
    auto_text = user_data[chat_id].get("auto_text")
    interval = user_data[chat_id].get("auto_interval")
    
    if not auto_text or not interval:
        send_message(chat_id, "❌ Ошибка: данные не найдены. Начните заново /start")
        user_states.pop(chat_id, None)
        return
    
    # Создаем задачу автопубликации
    auto_pub = {
        "id": int(time.time()),
        "text": auto_text,
        "interval_minutes": interval,
        "total_count": count,
        "published_count": 0,
        "active": True,
        "created_at": datetime.now().isoformat()
    }
    
    if "auto_publications" not in user_data[chat_id]:
        user_data[chat_id]["auto_publications"] = []
    
    user_data[chat_id]["auto_publications"].append(auto_pub)
    save_data()
    
    # Запускаем автопубликацию
    schedule_auto_publication(chat_id, auto_pub)
    
    send_message(
        chat_id,
        f"✅ *Автопубликация настроена!*\n\n"
        f"📝 Текст: `{auto_text[:50]}{'...' if len(auto_text) > 50 else ''}`\n"
        f"⏱ Интервал: *{interval} минут*\n"
        f"🔢 Количество: *{count} раз*\n\n"
        f"🔄 Первая публикация будет отправлена сейчас!",
        reply_markup=get_main_keyboard()
    )
    
    user_states.pop(chat_id, None)
    user_data[chat_id].pop("auto_text", None)
    user_data[chat_id].pop("auto_interval", None)
    
    # Отправляем первую публикацию сразу
    send_auto_publication(chat_id, auto_pub)

def send_auto_publication(chat_id, auto_pub):
    """Отправка одной автопубликации"""
    try:
        result = send_to_channel(auto_pub["text"])
        
        if result.get("ok"):
            auto_pub["published_count"] += 1
            logger.info(f"✅ Автопубликация {auto_pub['id']} отправлена ({auto_pub['published_count']}/{auto_pub['total_count']})")
            save_data()
            
            # Проверяем, достигнуто ли нужное количество
            if auto_pub["published_count"] >= auto_pub["total_count"]:
                auto_pub["active"] = False
                save_data()
                logger.info(f"✅ Автопубликация {auto_pub['id']} завершена")
                
                # Уведомляем пользователя
                send_message(
                    chat_id,
                    f"✅ *Автопубликация завершена!*\n\n"
                    f"Все *{auto_pub['total_count']}* публикаций отправлены.\n"
                    f"📝 Текст: `{auto_pub['text'][:50]}{'...' if len(auto_pub['text']) > 50 else ''}`"
                )
        else:
            logger.error(f"❌ Ошибка автопубликации: {result}")
    except Exception as e:
        logger.error(f"❌ Ошибка при автопубликации: {e}")

def schedule_auto_publication(chat_id, auto_pub):
    """Планирование следующей автопубликации"""
    def auto_publish_loop():
        while auto_pub.get("active", False) and auto_pub["published_count"] < auto_pub["total_count"]:
            # Ждем интервал
            time.sleep(auto_pub["interval_minutes"] * 60)
            
            # Проверяем, активна ли еще задача
            if not auto_pub.get("active", False):
                break
            
            # Отправляем следующую публикацию
            send_auto_publication(chat_id, auto_pub)
    
    thread = threading.Thread(target=auto_publish_loop, daemon=False)
    thread.start()
    logger.info(f"🔄 Запущена автопубликация {auto_pub['id']}")

# ========== ФОНОВЫЕ ЗАДАЧИ ==========
def schedule_replacement(chat_id, publication):
    """Планирование замены конкретной публикации"""
    def replace_post():
        wait_seconds = (publication["replace_at"] - datetime.now()).total_seconds()
        if wait_seconds > 0:
            while wait_seconds > 0:
                time.sleep(min(60, wait_seconds))
                wait_seconds -= 60
                if chat_id in user_data:
                    found = any(
                        pub["message_id"] == publication["message_id"]
                        for pub in user_data[chat_id].get("publications", [])
                    )
                    if not found:
                        logger.info(f"⏹️ Пост {publication['message_id']} отменён")
                        return
        
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
            save_data()
            
        except Exception as e:
            logger.error(f"❌ Ошибка замены поста {publication['message_id']}: {e}")
    
    thread = threading.Thread(target=replace_post, daemon=False)
    thread.start()
    logger.info(f"⏱️ Запланирована замена поста {publication['message_id']}")

# ========== ФУНКЦИЯ ПИНГА ==========
def ping_bot():
    """Функция для пинга бота (не отправляет сообщения)"""
    def ping_loop():
        while True:
            try:
                url = f"{BASE_URL}/getMe"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"🔄 Пинг бота выполнен в {datetime.now()}")
            except Exception as e:
                logger.error(f"❌ Ошибка при пинге бота: {e}")
            time.sleep(300)
    
    ping_thread = threading.Thread(target=ping_loop, daemon=True)
    ping_thread.start()
    logger.info("🔄 Запущен автоматический пинг бота (каждые 5 минут)")

# ========== ВЕБХУК ==========
@app.route("/", methods=["GET", "HEAD", "POST"])
def webhook():
    if request.method == "HEAD":
        return "", 200
    
    if request.method == "GET":
        return "Bot is running!"
    
    try:
        if request.headers.get('Content-Type') != 'application/json':
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
            elif data == "auto_publish":
                handle_auto_publish_callback(chat_id)
            elif data == "back_to_menu":
                handle_back_to_menu(chat_id)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    load_data()
    
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
    set_webhook_url = f"{BASE_URL}/setWebhook?url={webhook_url}"
    response = requests.get(set_webhook_url)
    
    if response.status_code == 200:
        logger.info(f"✅ Вебхук установлен: {webhook_url}")
    else:
        logger.error(f"❌ Ошибка установки вебхука: {response.status_code}")
    
    ping_bot()
    
    logger.info(f"🚀 Бот запущен! Разрешено пользователей: {len(ALLOWED_USERS)}")
    logger.info(f"👥 ID администраторов: {ALLOWED_USERS}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
