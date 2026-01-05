import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import g4f
from duckduckgo_search import DDGS
from collections import defaultdict
import json
import os
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = "8248012302:AAEjFHs5yyb-CF4i08__FhxwP8DHsG_MN9s"
ADMIN_IDS = [8329783163]

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

user_history = defaultdict(list)
MAX_HISTORY = 20
SYSTEM_PROMPT = "Ты умный AI-ассистент с доступом к интернету. Используй предоставленную информацию из интернета для ответа. Отвечай подробно на русском языке."

CHANNELS_FILE = "channels.json"
USERS_FILE = "users.json"
STATS_FILE = "stats.json"

class BroadcastStates(StatesGroup):
    waiting_message = State()

class ChannelStates(StatesGroup):
    waiting_channel = State()

def load_channels():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_channels(channels):
    with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(users), f, ensure_ascii=False, indent=2)

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"last_activity": {}, "blocked": []}

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def update_user_activity(user_id):
    stats = load_stats()
    stats["last_activity"][str(user_id)] = datetime.now().isoformat()
    save_stats(stats)

def add_user(user_id):
    users = load_users()
    users.add(user_id)
    save_users(users)
    update_user_activity(user_id)

def get_active_users(days=7):
    stats = load_stats()
    last_activity = stats.get("last_activity", {})
    now = datetime.now()
    active = 0
    
    for user_id, last_time in last_activity.items():
        try:
            last_dt = datetime.fromisoformat(last_time)
            if (now - last_dt).days <= days:
                active += 1
        except:
            pass
    
    return active

def add_blocked_user(user_id):
    stats = load_stats()
    if str(user_id) not in stats["blocked"]:
        stats["blocked"].append(str(user_id))
        save_stats(stats)

def get_blocked_count():
    stats = load_stats()
    return len(stats.get("blocked", []))

async def check_subscription(user_id: int) -> tuple[bool, list]:
    channels = load_channels()
    if not channels:
        return True, []
    
    not_subscribed = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel['chat_id'], user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed

def get_subscription_keyboard(channels):
    keyboard = []
    for channel in channels:
        keyboard.append([InlineKeyboardButton(
            text=channel['button_text'], 
            url=channel['link']
        )])
    keyboard.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def search_web(query: str) -> str:
    try:
        results = DDGS().text(query, max_results=5)
        if not results:
            return ""
        search_context = "\n\n".join([
            f"📌 {r['title']}\n{r['body']}\n🔗 {r['href']}" 
            for r in results
        ])
        return search_context
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return ""

async def ask_gpt(user_id: int, question: str) -> str:
    try:
        search_results = await asyncio.to_thread(search_web, question)
        
        if search_results:
            full_question = f"Вопрос: {question}\n\n🌐 Актуальная информация из интернета:\n\n{search_results}\n\nОтветь на вопрос используя эту информацию."
        else:
            full_question = question
        
        user_history[user_id].append({"role": "user", "content": full_question})
        
        if len(user_history[user_id]) > MAX_HISTORY:
            user_history[user_id] = user_history[user_id][-MAX_HISTORY:]
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_history[user_id]
        
        response = await g4f.ChatCompletion.create_async(
            model="gpt-4",
            messages=messages
        )
        
        answer = response
        user_history[user_id].append({"role": "assistant", "content": answer})
        
        return answer
    except Exception as e:
        logger.error(f"Ошибка GPT: {e}")
        return f"⚠️ Ошибка: {str(e)}"

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    
    is_subscribed, channels = await check_subscription(user_id)
    
    if not is_subscribed:
        await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наши каналы:",
            reply_markup=get_subscription_keyboard(channels)
        )
        return
    
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 Я AI-бот с поиском в интернете 🌐\n\n"
        "Я ищу актуальную информацию для каждого вопроса!\n\n"
        "📋 Команды:\n"
        "/start - Начать\n"
        "/clear - Очистить историю\n"
        "/help - Помощь\n"
        "/stats - Статистика"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed, channels = await check_subscription(user_id)
    
    if not is_subscribed:
        await callback.answer("❌ Вы еще не подписались на все каналы!", show_alert=True)
    else:
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Отлично! Теперь можешь пользоваться ботом.\n\n"
            "🤖 Просто напиши вопрос и я найду информацию в интернете!"
        )
        await callback.answer()

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    
    users = load_users()
    channels = load_channels()
    active_users = get_active_users(7)
    blocked_users = get_blocked_count()
    
    await message.answer(
        f"👨‍💼 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        f"📊 <b>Статистика пользователей:</b>\n"
        f"👥 Всего пользователей: {len(users)}\n"
        f"✅ Активных (за 7 дней): {active_users}\n"
        f"🚫 Заблокировали бота: {blocked_users}\n"
        f"📢 Обязательных каналов: {len(channels)}\n\n"
        f"<b>Команды:</b>\n"
        f"/broadcast - Сделать рассылку\n"
        f"/add_channel - Добавить канал\n"
        f"/remove_channel - Удалить канал\n"
        f"/list_channels - Список каналов\n"
        f"/detailed_stats - Детальная статистика",
        parse_mode="HTML"
    )

@dp.message(Command("detailed_stats"))
async def cmd_detailed_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    users = load_users()
    active_1d = get_active_users(1)
    active_7d = get_active_users(7)
    active_30d = get_active_users(30)
    blocked = get_blocked_count()
    channels = load_channels()
    
    inactive = len(users) - active_30d - blocked
    
    await message.answer(
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {len(users)}\n"
        f"• Активных за 24 часа: {active_1d}\n"
        f"• Активных за 7 дней: {active_7d}\n"
        f"• Активных за 30 дней: {active_30d}\n"
        f"• Неактивных (30+ дней): {inactive}\n"
        f"• Заблокировали бота: {blocked}\n\n"
        f"📢 <b>Каналы:</b>\n"
        f"• Обязательных каналов: {len(channels)}\n\n"
        f"💬 <b>Активность:</b>\n"
        f"• Активных диалогов: {len(user_history)}\n"
        f"• Процент удержания: {round((active_7d / len(users) * 100) if users else 0, 1)}%",
        parse_mode="HTML"
    )

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer("📝 Отправь сообщение для рассылки (текст, фото, видео):")
    await state.set_state(BroadcastStates.waiting_message)

@dp.message(BroadcastStates.waiting_message)
async def process_broadcast(message: Message, state: FSMContext):
    users = load_users()
    
    status_msg = await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    failed = 0
    blocked = 0
    
    for user_id in users:
        try:
            await message.copy_to(user_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            if "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
                blocked += 1
                add_blocked_user(user_id)
    
    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {failed}\n"
        f"🚫 Заблокировали бота: {blocked}"
    )
    await state.clear()

@dp.message(Command("add_channel"))
async def cmd_add_channel(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer(
        "📢 Отправь данные канала в формате (3 строки):\n\n"
        "Строка 1: Ссылка на канал\n"
        "Строка 2: ID канала\n"
        "Строка 3: Текст кнопки\n\n"
        "Пример:\n"
        "https://t.me/mychannel\n"
        "-1001234567890\n"
        "📢 Наш канал"
    )
    await state.set_state(ChannelStates.waiting_channel)

@dp.message(ChannelStates.waiting_channel)
async def process_add_channel(message: Message, state: FSMContext):
    try:
        lines = message.text.strip().split('\n')
        
        if len(lines) < 3:
            await message.answer("❌ Нужно отправить 3 строки: ссылка, ID канала и текст кнопки")
            return
        
        link = lines[0].strip()
        chat_id = lines[1].strip()
        button_text = lines[2].strip()
        
        if not link.startswith('http'):
            await message.answer("❌ Ссылка должна начинаться с http:// или https://")
            return
        
        try:
            chat_id_int = int(chat_id)
        except:
            await message.answer("❌ ID канала должен быть числом (например: -1001234567890)")
            return
        
        channels = load_channels()
        channels.append({
            "link": link,
            "chat_id": chat_id_int,
            "button_text": button_text
        })
        save_channels(channels)
        
        await message.answer(
            f"✅ Канал добавлен!\n\n"
            f"🔗 Ссылка: {link}\n"
            f"🆔 ID: {chat_id_int}\n"
            f"📝 Кнопка: {button_text}"
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

@dp.message(Command("list_channels"))
async def cmd_list_channels(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    channels = load_channels()
    
    if not channels:
        await message.answer("📢 Обязательных каналов пока нет")
        return
    
    text = "📢 <b>Список обязательных каналов:</b>\n\n"
    for i, channel in enumerate(channels, 1):
        text += f"{i}. {channel['button_text']}\n"
        text += f"   🔗 {channel['link']}\n"
        text += f"   🆔 {channel['chat_id']}\n\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("remove_channel"))
async def cmd_remove_channel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    channels = load_channels()
    
    if not channels:
        await message.answer("📢 Обязательных каналов пока нет")
        return
    
    text = "📢 Отправь номер канала для удаления:\n\n"
    for i, channel in enumerate(channels, 1):
        text += f"{i}. {channel['button_text']} ({channel['chat_id']})\n"
    
    await message.answer(text)

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    user_id = message.from_user.id
    user_history[user_id].clear()
    await message.answer("🗑 История очищена!")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ <b>Инструкция:</b>\n\n"
        "Пиши любые вопросы - бот ищет информацию в интернете и дает ответ! 🌐\n\n"
        "<b>Команды:</b>\n"
        "/clear - Очистить историю\n"
        "/stats - Статистика\n"
        "/help - Помощь",
        parse_mode="HTML"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    msgs = len([m for m in user_history[user_id] if m["role"] == "user"])
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"💬 Сообщений: {msgs}\n"
        f"📝 В истории: {len(user_history[user_id])}\n"
        f"🌐 Поиск: DuckDuckGo (всегда включен)",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    is_subscribed, channels = await check_subscription(user_id)
    
    if not is_subscribed:
        await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наши каналы:",
            reply_markup=get_subscription_keyboard(channels)
        )
        return
    
    if message.text.isdigit():
        if message.from_user.id in ADMIN_IDS:
            channels_list = load_channels()
            channel_num = int(message.text) - 1
            if 0 <= channel_num < len(channels_list):
                removed = channels_list.pop(channel_num)
                save_channels(channels_list)
                await message.answer(f"✅ Канал {removed['button_text']} удален!")
                return
    
    question = message.text
    
    wait_msg = await message.answer("🌐 Ищу информацию в интернете...")
    
    answer = await ask_gpt(user_id, question)
    
    await wait_msg.delete()
    
    if len(answer) > 4096:
        for i in range(0, len(answer), 4096):
            await message.answer(answer[i:i+4096])
    else:
        await message.answer(answer)

async def main():
    logger.info("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
