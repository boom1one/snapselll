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
    1524345644,  # Замените на реальный ID
    987654321,  # Добавьте других администраторов
]

# ========== ГЛАВНЫЕ АДМИНИСТРАТОРЫ (могут добавлять других) ==========
MASTER_ADMINS = [
    "piggass",      # Юзернейм без @
    "Gdjfcj28573"   # Юзернейм без @
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
        for pub in data.get("publications", []):
            # Проверяем, не истекло ли время
            if datetime.now() < pub["replace_at"]:
                schedule_replacement(chat_id, pub)
                restored_count += 1
                logger.info(f"🔄 Восстановлен таймер для поста {pub['message_id']}")
            else:
                # Если время уже прошло, заменяем сразу
                logger.info(f"⏰ Пост {pub['message_id']} просрочен, заменяем")
                replace_post_immediately(chat_id, pub)
    
    if restored_count > 0:
        logger.info(f"🔄 Восстановлено {restored_count} таймеров")

def replace_post_immediately(chat_id, publication):
    """Немедленная замена поста"""
    try:
        template = publication["template"]
        result = edit_message(CHANNEL_ID, publication["message_id"], template)
        
        if result.get("ok"):
            logger.info(f"✅ Пост {publication['message_id']} заменён")
        else:
            logger.error(f"❌ Ошибка замены: {result}")
        
        # Удаляем из списка
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

def is_master_admin(chat_id):
    """Проверка, является ли пользователь главным администратором"""
    try:
        # Получаем username пользователя
        url = f"{BASE_URL}/getChat"
        response = requests.get(url, params={"chat_id": chat_id})
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                username = data["result"].get("username", "").lower()
                # Проверяем, есть ли username в списке мастер-админов
                return username in [admin.lower() for admin in MASTER_ADMINS]
    except Exception as e:
        logger.error(f"Ошибка проверки мастер-админа: {e}")
    return False

def get_username_by_id(chat_id):
    """Получить username пользователя по ID"""
    try:
        url = f"{BASE_URL}/getChat"
        response = requests.get(url, params={"chat_id": chat_id})
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return data["result"].get("username")
    except Exception as e:
        logger.error(f"Ошибка получения username: {e}")
    return None

def get_user_id_from_username(username):
    """Получить ID пользователя по username"""
    if username.startswith("@"):
        username = username[1:]
    
    url = f"{BASE_URL}/getChat"
    try:
        response = requests.get(url, params={"chat_id": f"@{username}"})
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return data["result"]["id"]
    except Exception as e:
        logger.error(f"Ошибка получения ID для @{username}: {e}")
    return None

def add_admin_by_username(username, added_by):
    """Добавить администратора по username"""
    if username.startswith("@"):
        username = username[1:]
    
    # Проверяем, существует ли пользователь
    user_id = get_user_id_from_username(username)
    if not user_id:
        return False, "❌ Пользователь не найден. Проверьте правильность username."
    
    # Проверяем, не добавлен ли уже
    if user_id in ALLOWED_USERS:
        return False, f"❌ Пользователь @{username} уже является администратором."
    
    # Добавляем
    ALLOWED_USERS.append(user_id)
    save_data()
    
    # Уведомляем нового администратора
    try:
        send_message(
            user_id,
            f"🎉 *Вас добавили в администраторы бота!*\n\n"
            f"Теперь вы можете использовать бота для управления публикациями в канале {CHANNEL_ID}.\n"
            f"Для начала работы отправьте команду /start"
        )
    except:
        pass
    
    return True, f"✅ Администратор @{username} успешно добавлен!"

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
    """Главное меню (с кнопкой Добавить администратора для мастер-админов)"""
    keyboard = [
        [{"text": "📤 Выложить публикацию", "callback_data": "publish"}],
        [{"text": "✏️ Изменить шаблон автозамены", "callback_data": "change_template"}]
    ]
    
    # Проверяем, является ли пользователь мастер-админом
    # (это будет проверяться при нажатии кнопки, но для красоты показываем всем)
    keyboard.append([{"text": "👑 Добавить администратора", "callback_data": "add_admin"}])
    
    return {"inline_keyboard": keyboard}

# ========== ОБРАБОТЧИКИ КОМАНД ==========
def handle_start(chat_id):
    """Команда /start с проверкой доступа"""
    # Проверяем, есть ли у пользователя доступ
    if not is_allowed_user(chat_id):
        send_message(
            chat_id,
            "🚫 *У вас нет панели администратора для пользования данным ботом*\n\n"
            "Доступ разрешен только администраторам."
        )
        logger.warning(f"⚠️ Неавторизованный доступ: {chat_id}")
        return
    
    # Для авторизованных пользователей
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
        logger.info(f"👤 Новый администратор: {chat_id}")
    
    text = (
        "👋 *Добро пожаловать в бота управления публикациями!*\n\n"
        "Здесь вы можете:\n"
        "• *Выложить публикацию* в канал с автоматической заменой\n"
        "• *Изменить шаблон* для автозамены\n"
        "• *Добавить нового администратора* (только для главных админов)\n\n"
        "Выберите действие ниже 👇"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_publish_callback(chat_id):
    """Начало публикации"""
    # Проверка доступа
    if not is_allowed_user(chat_id):
        send_message(chat_id, "🚫 У вас нет доступа к этому боту.")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
    user_states[chat_id] = "waiting_for_text"
    send_message(
        chat_id,
        "📝 *Отправьте текст публикации*, который вы хотите выложить в канал.\n\n"
        "Это может быть любой текст, ссылки, или форматирование."
    )

def handle_change_template_callback(chat_id):
    """Начало изменения шаблона"""
    # Проверка доступа
    if not is_allowed_user(chat_id):
        send_message(chat_id, "🚫 У вас нет доступа к этому боту.")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
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
        f"`<b>жирный</b>`, `<i>курсив</i>`, `<a href='url'>ссылка</a>`"
    )

def handle_add_admin_callback(chat_id):
    """Обработка нажатия кнопки Добавить администратора"""
    # Проверяем, является ли пользователь мастер-админом
    if not is_master_admin(chat_id):
        send_message(
            chat_id,
            "🚫 *У вас нет доступа к панели*\n\n"
            "Только главные администраторы могут добавлять новых."
        )
        logger.warning(f"⚠️ Попытка добавить админа без прав: {chat_id}")
        return
    
    user_states[chat_id] = "waiting_for_admin_username"
    send_message(
        chat_id,
        "👑 *Добавление нового администратора*\n\n"
        "Отправьте *username* пользователя, которого хотите добавить.\n\n"
        "Пример: `@username` или просто `username`\n\n"
        "❗️ Пользователь должен существовать в Telegram."
    )

def handle_text_message(chat_id, text):
    """Обработка текстовых сообщений"""
    # Проверка доступа для всех текстовых сообщений
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
    elif state == "waiting_for_admin_username":
        handle_add_admin_username(chat_id, text)

def handle_publish_text(chat_id, text):
    """Обработка текста публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        save_data()
    
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
            save_data()  # Сохраняем после добавления
            
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
        save_data()
    
    user_data[chat_id]["template"] = text
    save_data()  # Сохраняем шаблон
    
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

def handle_add_admin_username(chat_id, text):
    """Обработка username для добавления администратора"""
    username = text.strip()
    
    # Убираем @ если есть
    if username.startswith("@"):
        username = username[1:]
    
    # Проверяем, что это не пустая строка
    if not username:
        send_message(chat_id, "❌ Пожалуйста, отправьте корректный username.")
        return
    
    # Добавляем администратора
    success, message = add_admin_by_username(username, chat_id)
    
    send_message(
        chat_id,
        message,
        reply_markup=get_main_keyboard()
    )
    user_states.pop(chat_id, None)

# ========== ФУНКЦИЯ ПИНГА ==========
def ping_bot():
    """Функция для пинга бота командой /start"""
    def ping_loop():
        while True:
            try:
                # Отправляем команду /start в канал
                send_message(CHANNEL_ID, "/start")
                logger.info(f"🔄 Пинг бота выполнен в {datetime.now()}")
            except Exception as e:
                logger.error(f"❌ Ошибка при пинге бота: {e}")
            
            # Ждем 5 минут
            time.sleep(300)  # 300 секунд = 5 минут
    
    # Запускаем пинг в отдельном потоке
    ping_thread = threading.Thread(target=ping_loop, daemon=True)
    ping_thread.start()
    logger.info("🔄 Запущен автоматический пинг бота (каждые 5 минут)")

# ========== ФОНОВЫЕ ЗАДАЧИ ==========
def schedule_replacement(chat_id, publication):
    """Планирование замены конкретной публикации"""
    def replace_post():
        wait_seconds = (publication["replace_at"] - datetime.now()).total_seconds()
        if wait_seconds > 0:
            # Разбиваем ожидание на интервалы по 60 секунд
            while wait_seconds > 0:
                time.sleep(min(60, wait_seconds))
                wait_seconds -= 60
                # Проверяем, не отменили ли публикацию
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
            
            # Удаляем из списка
            user_data[chat_id]["publications"] = [
                pub for pub in publications 
                if pub["message_id"] != publication["message_id"]
            ]
            save_data()  # Сохраняем изменения
            
        except Exception as e:
            logger.error(f"❌ Ошибка замены поста {publication['message_id']}: {e}")
            if chat_id in user_data:
                publications = user_data[chat_id].get("publications", [])
                user_data[chat_id]["publications"] = [
                    pub for pub in publications 
                    if pub["message_id"] != publication["message_id"]
                ]
                save_data()
    
    thread = threading.Thread(target=replace_post, daemon=False)
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
            elif data == "add_admin":
                handle_add_admin_callback(chat_id)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Загружаем сохраненные данные
    load_data()
    
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
    
    # Запускаем пинг бота
    ping_bot()
    
    logger.info(f"🚀 Бот запущен! Разрешено пользователей: {len(ALLOWED_USERS)}")
    logger.info(f"👥 ID администраторов: {ALLOWED_USERS}")
    logger.info(f"👑 Главные администраторы: {MASTER_ADMINS}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
