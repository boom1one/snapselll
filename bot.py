import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.getenv("8977186531:AAFwl7w9GWT7zDPBWHmTF4KQzD6npHQ8i5U")  # Токен бота
CHANNEL_ID = "@SnapSell350"     # ID канала

# ========== ИНИЦИАЛИЗАЦИЯ ==========
logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# Хранилище данных пользователя (в реальном проекте используйте БД)
user_data = {}

# ========== FSM (МАШИНЫ СОСТОЯНИЙ) ==========
class PublishStates(StatesGroup):
    waiting_for_text = State()       # Ждем текст публикации
    waiting_for_time = State()       # Ждем время до замены

class TemplateStates(StatesGroup):
    waiting_for_new_template = State()  # Ждем новый шаблон

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    """Главное меню с двумя кнопками"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Выложить публикацию", callback_data="publish")],
            [InlineKeyboardButton(text="✏️ Изменить шаблон автозамены", callback_data="change_template")]
        ]
    )
    return keyboard

# ========== ХЭНДЛЕРЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветствие и главное меню"""
    welcome_text = (
        "👋 *Добро пожаловать в бота управления публикациями!*\n\n"
        "Здесь вы можете:\n"
        "• *Выложить публикацию* в канал с автоматической заменой\n"
        "• *Изменить шаблон* для автозамены\n\n"
        "Выберите действие ниже 👇"
    )
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "publish")
async def start_publish(callback: types.CallbackQuery, state: FSMContext):
    """Начинаем процесс публикации"""
    await callback.message.delete()
    await callback.answer()
    
    await state.set_state(PublishStates.waiting_for_text)
    await callback.message.answer(
        "📝 *Отправьте текст публикации*, который вы хотите выложить в канал.\n\n"
        "Это может быть любой текст, ссылки, или форматирование.",
        parse_mode="Markdown"
    )

@dp.message(PublishStates.waiting_for_text)
async def get_publish_text(message: types.Message, state: FSMContext):
    """Получаем текст публикации"""
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте текст сообщением.")
        return
    
    # Сохраняем текст в состояние
    await state.update_data(publish_text=message.text)
    await state.set_state(PublishStates.waiting_for_time)
    
    await message.answer(
        "⏱ *Укажите время в минутах*, через которое публикация заменится на шаблон.\n\n"
        "Пример: `120` — замена через 2 часа.\n"
        "Отправьте *только число*.",
        parse_mode="Markdown"
    )

@dp.message(PublishStates.waiting_for_time)
async def get_publish_time(message: types.Message, state: FSMContext):
    """Получаем время и публикуем пост"""
    try:
        delay_minutes = int(message.text.strip())
        if delay_minutes <= 0:
            raise ValueError("Время должно быть положительным")
    except ValueError:
        await message.answer("❌ Пожалуйста, отправьте *положительное целое число* (количество минут).")
        return
    
    # Получаем текст публикации из состояния
    data = await state.get_data()
    publish_text = data.get("publish_text")
    
    if not publish_text:
        await message.answer("❌ Ошибка: текст публикации не найден. Начните заново /start")
        await state.clear()
        return
    
    # Публикуем пост в канал
    try:
        sent_message = await bot.send_message(
            chat_id=CHANNEL_ID,
            text=publish_text,
            parse_mode="HTML"  # Поддерживает базовое форматирование
        )
        
        # Сохраняем данные для автозамены
        user_id = message.from_user.id
        if user_id not in user_data:
            user_data[user_id] = {}
        
        user_data[user_id]["last_post"] = {
            "chat_id": CHANNEL_ID,
            "message_id": sent_message.message_id,
            "replace_at": datetime.now() + timedelta(minutes=delay_minutes),
            "template": user_data.get(user_id, {}).get("template", "⚠️ Этот пост был автоматически заменён по шаблону.")
        }
        
        # Уведомляем пользователя
        await message.answer(
            f"✅ *Публикация успешно выложена!*\n\n"
            f"🔹 Текст опубликован в канале.\n"
            f"🔹 Замена произойдет через *{delay_minutes} минут*.\n\n"
            f"⏳ Таймер запущен!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        
        # Запускаем задачу на замену
        asyncio.create_task(schedule_post_replacement(user_id, delay_minutes))
        
    except Exception as e:
        logging.error(f"Ошибка публикации: {e}")
        await message.answer(
            "❌ *Ошибка при публикации!*\n"
            "Проверьте, что бот является администратором канала и имеет права на отправку сообщений.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    await state.clear()

@dp.callback_query(F.data == "change_template")
async def change_template_start(callback: types.CallbackQuery, state: FSMContext):
    """Начинаем изменение шаблона"""
    await callback.message.delete()
    await callback.answer()
    
    current_template = user_data.get(callback.from_user.id, {}).get("template", "Не установлен")
    
    await state.set_state(TemplateStates.waiting_for_new_template)
    await callback.message.answer(
        f"📝 *Текущий шаблон автозамены:*\n"
        f"`{current_template}`\n\n"
        f"✍️ *Отправьте новый текст шаблона*, на который будут заменяться публикации.\n\n"
        f"Вы можете использовать *HTML-теги* для форматирования:\n"
        f"`<b>жирный</b>`, `<i>курсив</i>`, `<a href='url'>ссылка</a>`",
        parse_mode="Markdown"
    )

@dp.message(TemplateStates.waiting_for_new_template)
async def save_new_template(message: types.Message, state: FSMContext):
    """Сохраняем новый шаблон"""
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте текст шаблона.")
        return
    
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]["template"] = message.text
    
    await message.answer(
        "✅ *Шаблон успешно обновлен!*\n\n"
        f"📌 Новый шаблон:\n"
        f"`{message.text}`\n\n"
        "Теперь все будущие публикации будут заменяться на этот шаблон.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    await state.clear()

# ========== ФОНОВАЯ ЗАДАЧА ЗАМЕНЫ ==========
async def schedule_post_replacement(user_id: int, delay_minutes: int):
    """Отложенная замена поста на шаблон"""
    await asyncio.sleep(delay_minutes * 60)  # Переводим минуты в секунды
    
    try:
        # Проверяем, есть ли данные о посте
        if user_id not in user_data:
            return
        
        post_data = user_data[user_id].get("last_post")
        if not post_data:
            return
        
        # Получаем шаблон
        template = user_data[user_id].get("template", "⚠️ Этот пост был автоматически заменён по шаблону.")
        
        # Редактируем сообщение в канале
        await bot.edit_message_text(
            chat_id=post_data["chat_id"],
            message_id=post_data["message_id"],
            text=template,
            parse_mode="HTML"
        )
        
        logging.info(f"Пост {post_data['message_id']} заменён на шаблон для пользователя {user_id}")
        
        # Очищаем данные, чтобы не заменить повторно
        del user_data[user_id]["last_post"]
        
    except Exception as e:
        logging.error(f"Ошибка замены поста: {e}")

# ========== ЗАПУСК БОТА ==========
async def main():
    print("🚀 Бот запущен на Render!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
