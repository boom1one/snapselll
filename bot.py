import os
import time
import threading
import requests
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import re
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
            logger.info(f"✅ Сообщение отправлено в канал: {text[:50]}...")
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
            [{"text": "📅 Ежедневная публикация", "callback_data": "daily_publish"}],
            [{"text": "📋 Мои публикации", "callback_data": "my_posts"}]
        ]
    }

def get_daily_menu_keyboard():
    """Меню для ежедневных публикаций"""
    return {
        "inline_keyboard": [
            [{"text": "➕ Создать ежедневную публикацию", "callback_data": "create_daily"}],
            [{"text": "📋 Список ежедневных публикаций", "callback_data": "list_daily"}],
            [{"text": "🔙 Назад в меню", "callback_data": "back_to_menu"}]
        ]
    }

def get_confirm_keyboard():
    """Кнопки подтверждения удаления"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Да, удалить", "callback_data": "confirm_delete"},
                {"text": "❌ Нет, отмена", "callback_data": "cancel_delete"}
            ]
        ]
    }

# ========== ОБРАБОТЧИКИ КОМАНД ==========
def handle_start(chat_id):
    """Команда /start"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "daily_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
        logger.info(f"👤 Новый пользователь: {chat_id}")
    
    text = (
        "👋 *Добро пожаловать в бота управления публикациями!*\n\n"
        "Здесь вы можете:\n"
        "• *Выложить публикацию* в канал с автоматической заменой\n"
        "• *Изменить шаблон* для автозамены\n"
        "• *Настроить ежедневные публикации*\n"
        "• *Просмотреть свои публикации*\n\n"
        "Выберите действие ниже 👇"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_publish_callback(chat_id):
    """Начало публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "daily_publications": [],
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
            "daily_publications": [],
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

def handle_daily_publish_callback(chat_id):
    """Меню ежедневных публикаций"""
    send_message(
        chat_id,
        "📅 *Ежедневные публикации*\n\n"
        "Здесь вы можете:\n"
        "• Создать новую ежедневную публикацию\n"
        "• Просмотреть список всех ежедневных публикаций\n"
        "• Удалить ненужные публикации\n\n"
        "Выберите действие:",
        reply_markup=get_daily_menu_keyboard()
    )

def handle_my_posts_callback(chat_id):
    """Показывает все активные публикации пользователя"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "daily_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    publications = user_data[chat_id].get("publications", [])
    daily_publications = user_data[chat_id].get("daily_publications", [])
    
    if not publications and not daily_publications:
        send_message(
            chat_id,
            "📭 *У вас нет активных публикаций*\n\n"
            "Создайте новую публикацию или ежедневную публикацию!",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "📊 *Ваши публикации*\n\n"
    
    if publications:
        text += "🔹 *Обычные публикации (с автозаменой):*\n"
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
            
            text += f"  *{i}.* ID: `{pub['message_id']}` — ⏱ *{time_str}*\n"
        text += "\n"
    
    if daily_publications:
        text += "🔹 *Ежедневные публикации:*\n"
        for i, pub in enumerate(daily_publications, 1):
            last_pub = pub.get('last_published', 'Никогда')
            if last_pub != 'Никогда':
                try:
                    last_pub = datetime.fromisoformat(last_pub).strftime('%d.%m.%Y %H:%M')
                except:
                    pass
            text += f"  *{i}.* ⏰ *{pub['time']}* — `{pub['text'][:30]}{'...' if len(pub['text']) > 30 else ''}`\n"
            text += f"      📅 Последняя публикация: {last_pub}\n"
    
    send_message(chat_id, text, reply_markup=get_main_keyboard())

def handle_create_daily_callback(chat_id):
    """Создание новой ежедневной публикации"""
    user_states[chat_id] = "waiting_for_daily_text"
    send_message(
        chat_id,
        "📝 *Отправьте текст для ежедневной публикации*\n\n"
        "Этот текст будет публиковаться каждый день в указанное время.\n"
        "Вы можете использовать форматирование."
    )

def handle_list_daily_callback(chat_id):
    """Список ежедневных публикаций"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "daily_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    daily_pubs = user_data[chat_id].get("daily_publications", [])
    
    if not daily_pubs:
        send_message(
            chat_id,
            "📭 *У вас нет ежедневных публикаций*\n\n"
            "Создайте первую ежедневную публикацию!",
            reply_markup=get_daily_menu_keyboard()
        )
        return
    
    text = "📋 *Список ежедневных публикаций*\n\n"
    for i, pub in enumerate(daily_pubs, 1):
        last_pub = pub.get('last_published', 'Никогда')
        if last_pub != 'Никогда':
            try:
                last_pub = datetime.fromisoformat(last_pub).strftime('%d.%m.%Y %H:%M')
            except:
                pass
        text += f"*{i}.* ⏰ *{pub['time']}*\n"
        text += f"   📝 `{pub['text'][:50]}{'...' if len(pub['text']) > 50 else ''}`\n"
        text += f"   📅 Последняя: {last_pub}\n\n"
    
    text += "\n💡 *Чтобы удалить публикацию, отправьте её номер* (например: `1`)"
    
    send_message(
        chat_id,
        text,
        reply_markup={
            "inline_keyboard": [
                [{"text": "🔙 Назад", "callback_data": "daily_publish"}]
            ]
        }
    )
    
    user_states[chat_id] = "waiting_for_daily_delete"

def handle_text_message(chat_id, text):
    """Обработка текстовых сообщений"""
    state = user_states.get(chat_id)
    
    if state == "waiting_for_text":
        handle_publish_text(chat_id, text)
    elif state == "waiting_for_time":
        handle_publish_time(chat_id, text)
    elif state == "waiting_for_template":
        handle_template_save(chat_id, text)
    elif state == "waiting_for_daily_text":
        handle_daily_text(chat_id, text)
    elif state == "waiting_for_daily_time":
        handle_daily_time(chat_id, text)
    elif state == "waiting_for_daily_delete":
        handle_daily_delete(chat_id, text)

def handle_publish_text(chat_id, text):
    """Обработка текста публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "daily_publications": [],
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
            "daily_publications": [],
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

def handle_daily_text(chat_id, text):
    """Обработка текста для ежедневной публикации"""
    if chat_id not in user_data:
        user_data[chat_id] = {
            "publications": [],
            "daily_publications": [],
            "template": "⚠️ Этот пост был автоматически заменён по шаблону."
        }
    
    user_data[chat_id]["daily_text"] = text
    user_states[chat_id] = "waiting_for_daily_time"
    
    send_message(
        chat_id,
        "⏰ *Укажите время для ежедневной публикации*\n\n"
        "Отправьте время в формате *HH:MM* (например: `14:30`)\n"
        "Публикация будет выходить каждый день в это время."
    )

def handle_daily_time(chat_id, text):
    """Обработка времени для ежедневной публикации"""
    if not re.match(r'^\d{2}:\d{2}$', text):
        send_message(
            chat_id,
            "❌ *Неверный формат времени!*\n\n"
            "Пожалуйста, отправьте время в формате *HH:MM*\n"
            "Пример: `14:30`"
        )
        return
    
    try:
        hours, minutes = map(int, text.split(':'))
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            raise ValueError("Неверное время")
    except ValueError:
        send_message(
            chat_id,
            "❌ *Неверное время!*\n\n"
            "Часы должны быть от 0 до 23, минуты от 0 до 59."
        )
        return
    
    daily_text = user_data[chat_id].get("daily_text")
    if not daily_text:
        send_message(chat_id, "❌ Ошибка: текст не найден. Начните заново.")
        user_states.pop(chat_id, None)
        return
    
    # Создаём ежедневную публикацию с уникальным ID
    daily_pub = {
        "id": int(time.time()),  # Уникальный ID на основе времени
        "text": daily_text,
        "time": text,
        "created_at": datetime.now().isoformat(),
        "last_published": None,
        "active": True
    }
    
    if "daily_publications" not in user_data[chat_id]:
        user_data[chat_id]["daily_publications"] = []
    
    user_data[chat_id]["daily_publications"].append(daily_pub)
    
    # Запускаем задачу для этой публикации
    start_daily_task(chat_id, daily_pub)
    
    send_message(
        chat_id,
        f"✅ *Ежедневная публикация создана!*\n\n"
        f"📝 Текст:\n`{daily_text}`\n\n"
        f"⏰ Время: *{text}*\n"
        f"📊 Всего ежедневных публикаций: *{len(user_data[chat_id]['daily_publications'])}*\n\n"
        "Публикация будет выходить каждый день в указанное время! 🎉",
        reply_markup=get_main_keyboard()
    )
    
    user_states.pop(chat_id, None)
    user_data[chat_id].pop("daily_text", None)
    
    logger.info(f"📅 Создана ежедневная публикация для {chat_id} в {text}")

def handle_daily_delete(chat_id, text):
    """Удаление ежедневной публикации по номеру"""
    try:
        index = int(text.strip()) - 1
        daily_pubs = user_data[chat_id].get("daily_publications", [])
        
        if index < 0 or index >= len(daily_pubs):
            send_message(
                chat_id,
                f"❌ *Неверный номер!*\n\n"
                f"Пожалуйста, отправьте номер от 1 до {len(daily_pubs)}.",
                reply_markup=get_main_keyboard()
            )
            return
        
        user_data[chat_id]["delete_index"] = index
        pub_to_delete = daily_pubs[index]
        
        send_message(
            chat_id,
            f"⚠️ *Вы уверены, что хотите удалить эту публикацию?*\n\n"
            f"📝 Текст: `{pub_to_delete['text'][:50]}{'...' if len(pub_to_delete['text']) > 50 else ''}`\n"
            f"⏰ Время: *{pub_to_delete['time']}*\n\n"
            "Это действие нельзя отменить!",
            reply_markup=get_confirm_keyboard()
        )
        
        user_states[chat_id] = "waiting_for_delete_confirm"
        
    except ValueError:
        send_message(
            chat_id,
            "❌ *Пожалуйста, отправьте номер публикации!*\n\n"
            "Пример: `1`",
            reply_markup=get_main_keyboard()
        )

def confirm_delete_daily(chat_id):
    """Подтверждение удаления ежедневной публикации"""
    delete_index = user_data[chat_id].get("delete_index")
    if delete_index is None:
        return
    
    daily_pubs = user_data[chat_id].get("daily_publications", [])
    if delete_index < len(daily_pubs):
        deleted_pub = daily_pubs.pop(delete_index)
        deleted_pub['active'] = False  # Отмечаем как неактивную
        
        send_message(
            chat_id,
            f"✅ *Публикация успешно удалена!*\n\n"
            f"Удалена публикация:\n"
            f"⏰ *{deleted_pub['time']}*\n"
            f"📝 `{deleted_pub['text'][:50]}{'...' if len(deleted_pub['text']) > 50 else ''}`\n\n"
            f"📊 Осталось публикаций: *{len(daily_pubs)}*",
            reply_markup=get_main_keyboard()
        )
        
        logger.info(f"🗑️ Удалена ежедневная публикация {deleted_pub['id']} для {chat_id}")
    else:
        send_message(
            chat_id,
            "❌ *Ошибка при удалении!*",
            reply_markup=get_main_keyboard()
        )
    
    user_data[chat_id].pop("delete_index", None)
    user_states.pop(chat_id, None)

def cancel_delete_daily(chat_id):
    """Отмена удаления ежедневной публикации"""
    user_data[chat_id].pop("delete_index", None)
    user_states.pop(chat_id, None)
    
    daily_pubs = user_data[chat_id].get("daily_publications", [])
    
    if not daily_pubs:
        send_message(
            chat_id,
            "📭 *У вас нет ежедневных публикаций*",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "📋 *Список ежедневных публикаций*\n\n"
    for i, pub in enumerate(daily_pubs, 1):
        text += f"*{i}.* ⏰ *{pub['time']}*\n"
        text += f"   📝 `{pub['text'][:50]}{'...' if len(pub['text']) > 50 else ''}`\n\n"
    
    text += "\n💡 *Чтобы удалить публикацию, отправьте её номер*"
    
    send_message(
        chat_id,
        text,
        reply_markup={
            "inline_keyboard": [
                [{"text": "🔙 Назад в меню", "callback_data": "back_to_menu"}]
            ]
        }
    )
    user_states[chat_id] = "waiting_for_daily_delete"

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
    logger.info(f"⏱️ Запланирована замена поста {publication['message_id']} через {publication['replace_at']}")

def start_daily_task(chat_id, daily_pub):
    """Запуск задачи для ежедневной публикации"""
    def daily_job():
        pub_id = daily_pub['id']
        pub_time = daily_pub['time']
        
        logger.info(f"🔄 Запущена ежедневная задача для {pub_id} в {pub_time}")
        
        while True:
            try:
                # Проверяем, существует ли ещё эта публикация
                if chat_id not in user_data:
                    logger.info(f"🔄 Пользователь {chat_id} удалён, завершаем задачу {pub_id}")
                    break
                
                # Проверяем, активна ли публикация
                pub_exists = False
                for pub in user_data[chat_id].get("daily_publications", []):
                    if pub['id'] == pub_id and pub.get('active', True):
                        pub_exists = True
                        break
                
                if not pub_exists:
                    logger.info(f"🔄 Ежедневная публикация {pub_id} удалена, завершаем задачу")
                    break
                
                # Вычисляем следующее время публикации
                now = datetime.now()
                hours, minutes = map(int, pub_time.split(':'))
                
                next_publish = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                
                # Если время уже прошло сегодня, публикуем завтра
                if next_publish <= now:
                    next_publish += timedelta(days=1)
                
                wait_seconds = (next_publish - now).total_seconds()
                
                logger.info(f"⏳ Следующая публикация {pub_id} через {wait_seconds/60:.1f} минут (в {pub_time})")
                
                time.sleep(wait_seconds)
                
                # Проверяем ещё раз перед публикацией
                pub_still_exists = False
                for pub in user_data[chat_id].get("daily_publications", []):
                    if pub['id'] == pub_id and pub.get('active', True):
                        pub_still_exists = True
                        break
                
                if not pub_still_exists:
                    logger.info(f"🔄 Публикация {pub_id} удалена перед отправкой, завершаем")
                    break
                
                # Отправляем в канал
                result = send_to_channel(daily_pub['text'])
                
                if result.get("ok"):
                    # Обновляем время последней публикации
                    for pub in user_data[chat_id].get("daily_publications", []):
                        if pub['id'] == pub_id:
                            pub['last_published'] = datetime.now().isoformat()
                            break
                    
                    logger.info(f"✅ Ежедневная публикация {pub_id} отправлена в {pub_time}")
                else:
                    logger.error(f"❌ Ошибка отправки ежедневной публикации {pub_id}: {result}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка в ежедневной задаче {pub_id}: {e}")
                time.sleep(60)  # Ждём минуту перед повторной попыткой
    
    thread = threading.Thread(target=daily_job, daemon=True)
    thread.start()
    logger.info(f"📅 Запущена ежедневная задача для {chat_id} в {daily_pub['time']}")

def restart_all_daily_tasks():
    """Перезапуск всех ежедневных задач при старте бота"""
    logger.info("🔄 Перезапуск всех ежедневных задач...")
    
    for chat_id, data in user_data.items():
        daily_pubs = data.get("daily_publications", [])
        for pub in daily_pubs:
            if pub.get('active', True):
                start_daily_task(chat_id, pub)
                logger.info(f"✅ Восстановлена ежедневная задача для {chat_id} в {pub['time']}")

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
            elif data == "daily_publish":
                handle_daily_publish_callback(chat_id)
            elif data == "my_posts":
                handle_my_posts_callback(chat_id)
            elif data == "create_daily":
                handle_create_daily_callback(chat_id)
            elif data == "list_daily":
                handle_list_daily_callback(chat_id)
            elif data == "back_to_menu":
                handle_start(chat_id)
            elif data == "confirm_delete":
                confirm_delete_daily(chat_id)
            elif data == "cancel_delete":
                cancel_delete_daily(chat_id)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Восстанавливаем задачи при старте
    restart_all_daily_tasks()
    
    # Устанавливаем вебхук
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
    set_webhook_url = f"{BASE_URL}/setWebhook?url={webhook_url}"
    response = requests.get(set_webhook_url)
    
    if response.status_code == 200:
        logger.info(f"✅ Вебхук установлен: {webhook_url}")
        logger.info(f"📊 Ответ: {response.json()}")
    else:
        logger.error(f"❌ Ошибка установки веб
