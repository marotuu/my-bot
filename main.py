from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dp import (
    dp, bot, add_task, get_task, get_all_tasks, update_task, delete_task, 
    delete_all_tasks, add_pinned_message, get_pinned_message, delete_pinned_message,
    add_assignee, get_assignees, delete_assignees, add_bot_message, 
    get_bot_messages, delete_bot_message,
    init_db, close_db
)
from typing import Union
from dp import add_bot_message, get_bot_messages, delete_bot_message, get_group_timezone, set_group_timezone, is_message_pinned
from markups import group_menu, reminder_menu, task_actions_menu, confirmation_menu, private_menu, timezone_menu, timezone_confirmation_menu, cancel_timezone_menu
import asyncio
import sqlite3
from config import DB_NAME
import markups as mk
import aiosqlite

router = Router()

class TaskStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_edit_text = State()
    waiting_for_edit_date = State()
    confirm_edit_text = State()
    confirm_edit_date = State()
    waiting_for_new_date = State()
    waiting_for_assignee_choice = State()
    waiting_for_assignee = State()

class TimezoneStates(StatesGroup):
    waiting_for_custom_name = State()
    waiting_for_custom_hours = State()
    waiting_for_confirmation = State()

def escape_html(text):
    if not text:
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
                .replace("#", "&#35;"))

def check_chat_type(required_type: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            event = kwargs.get("event")
            if isinstance(event, types.CallbackQuery):
                chat_type = event.message.chat.type
                chat_id = event.message.chat.id
            elif isinstance(event, types.Message):
                chat_type = event.chat.type
                chat_id = event.chat.id
            else:
                return
            if required_type == "group":
                if chat_type not in ["group", "supergroup"]:
                    text = "Эта команда доступна только в группах!"
                    if isinstance(event, types.CallbackQuery):
                        await event.answer(text, show_alert=True)
                    else:
                        await send_and_track_message(chat_id, text, delete_after=5)
                    return
            elif required_type == "private":
                if chat_type != "private":
                    text = "Эта команда доступна только в личных сообщениях!"
                    if isinstance(event, types.CallbackQuery):
                        await event.answer(text, show_alert=True)
                    else:
                        await send_and_track_message(chat_id, text, delete_after=5)
                    return
            return await func(*args, **kwargs)
        return wrapper
    return decorator

async def cleanup_bot_messages(chat_id: int, task_id=None):
    if not await bot_has_permissions(chat_id):
        return
    message_ids = await get_bot_messages(chat_id, task_id)
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id, message_id)
            await delete_bot_message(chat_id, message_id)
            await asyncio.sleep(0.3)
        except:
            continue

async def cleanup_user_message(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def cleanup_user_and_bot_messages(chat_id: int, user_message_id: int = None, task_id=None):
    try:
        if user_message_id:
            await cleanup_user_message(chat_id, user_message_id)
        await cleanup_bot_messages(chat_id, task_id)
    except:
        pass

async def send_and_track_message(chat_id, text, reply_markup=None, task_id=None, delete_after=None, parse_mode=None):
    try:
        await cleanup_bot_messages(chat_id, task_id)
        msg = await bot.send_message(
            chat_id, 
            text, 
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        for attempt in range(3):
            try:
                await add_bot_message(chat_id, msg.message_id, task_id)
                break
            except:
                await asyncio.sleep(0.1 * (attempt + 1))
        if delete_after:
            await asyncio.sleep(delete_after)
            try:
                await msg.delete()
                await delete_bot_message(chat_id, msg.message_id)
            except:
                pass
        return msg
    except:
        return None

@router.message(Command(commands=["start", "help"]))
async def send_welcome(message: types.Message):
    try:
        if message.chat.type in ["group", "supergroup"]:
            try:
                await message.delete()
            except:
                pass
        await cleanup_bot_messages(message.chat.id)
        if message.chat.type == "private":
            welcome_text = (
                "👋 Привет! Я бот для управления задачами.\n\n"
                "📌 В группах я могу:\n"
                "- Создавать задачи с напоминаниями\n"
                "- Управлять списком задач\n"
                "- Отправлять уведомления о сроках\n\n"
                "⚙️ Для работы в группе мне нужны права:\n"
                "- Удаление сообщений\n"
                "- Закрепление сообщений\n\n"
                "Добавьте меня в группу и назначьте администратором!"
            )
            await send_and_track_message(
                message.chat.id,
                welcome_text,
                reply_markup=mk.private_menu()
            )
        else:
            if not await bot_has_permissions(message.chat.id):
                await send_and_track_message(
                    message.chat.id,
                    "⚠️ Мне нужны права администратора для работы!\n\n"
                    "Пожалуйста, назначьте меня администратором с правами:\n"
                    "- Удаление сообщений\n"
                    "- Закрепление сообщений",
                    delete_after=10
                )
                return
            await send_and_track_message(
                message.chat.id,
                "📋 Бот для управления задачами. Выберите действие:",
                reply_markup=mk.group_menu()
            )
    except:
        pass

async def get_chat_history(self, chat_id, limit=100):
    messages = []
    async for message in self.get_chat(chat_id).iter_history(limit=limit):
        messages.append(message)
    return messages

async def cleanup_all_start_messages(chat_id: int):
    try:
        messages = []
        async for message in bot.get_chat_history(chat_id, limit=100):
            if message.text and (message.text.startswith('/start') or message.text.startswith('/help')):
                messages.append(message)
        for message in messages:
            try:
                await bot.delete_message(chat_id, message.message_id)
                await asyncio.sleep(0.3)
            except:
                continue
    except:
        raise

async def bot_has_permissions(chat_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id, bot.id)
        return chat_member.can_delete_messages
    except:
        return False

@router.callback_query(F.data == "group_settings")
async def group_settings_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚙️ Настройки группы",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="group_menu")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_list")
async def back_to_list_handler(callback: types.CallbackQuery):
    tasks = await get_all_tasks(callback.message.chat.id)
    if tasks:
        await send_tasks_page(
            chat_id=callback.message.chat.id,
            tasks=tasks,
            edit_message_id=callback.message.message_id
        )
    else:
        await callback.message.edit_text(
            "📭 Нет активных задач",
            reply_markup=mk.group_menu()
        )
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📋 Главное меню",
        reply_markup=mk.group_menu()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("remind_"))
async def set_reminder_handler(callback: types.CallbackQuery):
    await cleanup_bot_messages(callback.message.chat.id)
    _, minutes, task_id = callback.data.split('_')
    minutes = int(minutes)
    await update_task(task_id, reminder_minutes=minutes)
    if minutes > 0:
        hours = minutes // 60
        mins = minutes % 60
        time_str = f"{hours} ч {mins} мин" if hours else f"{mins} мин"
        await send_and_track_message(
            callback.message.chat.id,
            f"⏰ Напоминание установлено: за {time_str} до события",
            task_id=task_id,
            delete_after=3
        )
    else:
        await send_and_track_message(
            callback.message.chat.id,
            "❌ Напоминание отключено",
            task_id=task_id,
            delete_after=3
        )

@router.callback_query(F.data == "list_tasks")
async def list_tasks_handler(callback: types.CallbackQuery):
    try:
        tasks = await get_all_tasks(callback.message.chat.id)
        if not tasks:
            await callback.message.edit_text(
                "📭 Нет активных задач",
                reply_markup=mk.group_menu(),
                parse_mode=None
            )
            return
        await send_tasks_page(
            chat_id=callback.message.chat.id,
            tasks=tasks,
            edit_message_id=callback.message.message_id
        )
    except:
        await callback.answer("Сталася помилка, спробуйте ще раз")

async def send_tasks_page(chat_id, tasks, page=0, edit_message_id=None):
    tz_info = await get_group_timezone(chat_id)
    if not tz_info:
        tz_offset = 5
        tz_name = "Екатеринбург (UTC+5)"
    else:
        tz_offset = tz_info[2] if tz_info[2] is not None else {
            'moscow': 3,
            'ekb': 5,
            'novosib': 7
        }.get(tz_info[0], 5)
        tz_name = tz_info[1] if tz_info[1] else {
            'moscow': 'Москва (UTC+3)',
            'ekb': 'Екатеринбург (UTC+5)',
            'novosib': 'Новосибирск (UTC+7)'
        }.get(tz_info[0], 'Екатеринбург (UTC+5)')

    now_utc = datetime.utcnow()
    local_now = now_utc + timedelta(hours=tz_offset)
    current_date_str = local_now.strftime('%d.%m.%Y %H:%M')

    tasks_per_page = 2
    total_tasks = len(tasks)
    page = min(page, max(0, (total_tasks + tasks_per_page - 1) // tasks_per_page - 1))
    start_idx = page * tasks_per_page
    end_idx = (page + 1) * tasks_per_page
    current_tasks = tasks[start_idx:end_idx]

    message_text = f"<b>🕒 Часовой пояс:</b> {escape_html(tz_name)} ({current_date_str})\n\n"
    message_text += f"<b>📅 Список задач</b>\n\n"

    for task in current_tasks:
        if len(task) < 4:
            task_id = task[0]
            text = task[1] if len(task) > 1 else "Нет описания"
            due_date = task[2] if len(task) > 2 else datetime.utcnow().isoformat()
            reminder = task[3] if len(task) > 3 else None
        else:
            task_id, text, due_date, reminder = task

        try:
            due_datetime = datetime.fromisoformat(due_date)
            local_due_datetime = due_datetime + timedelta(hours=tz_offset)
            due_date_str = local_due_datetime.strftime('%d.%m.%Y %H:%M')

            if local_due_datetime < local_now:
                status = "🔴 Просрочено"
            elif local_due_datetime - local_now < timedelta(hours=24):
                status = "🟡 Скоро срок"
            else:
                status = "🟢 Активно"

            reminder_text = ""
            if reminder and reminder > 0:
                hours = reminder // 60
                mins = reminder % 60
                reminder_text = f"\n⏰ Напоминание: за {hours} ч {mins} мин" if hours else f"\n⏰ Напоминание: за {mins} мин"

            assignees = await get_assignees(task_id)
            assignees_without_at = [a[1:] if a.startswith('@') else a for a in assignees]

            safe_text = escape_html(text)
            safe_assignees = escape_html(', '.join(assignees_without_at)) if assignees else ""

            message_text += (
                f"{status} <b>Задача #{task_id}</b>\n"
                f"📌 {safe_text}\n"
                f"🕒 <b>Срок:</b> {due_date_str}{reminder_text}\n"
                f"👥 <b>Исполнители:</b> {safe_assignees}\n\n"
            )
        except:
            continue

    message_text += f"<b>Страница {page+1} из {max(1, (total_tasks + tasks_per_page - 1) // tasks_per_page)}</b>"

    keyboard = mk.tasks_pagination_menu(tasks, page, tasks_per_page)
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🕒 Сменить часовой пояс", callback_data="change_timezone")])

    try:
        if edit_message_id:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return edit_message_id
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await add_bot_message(chat_id, msg.message_id)
            return msg.message_id
    except:
        pass


@router.callback_query(F.data.startswith("edit_"))
async def edit_task_handler(callback: types.CallbackQuery):
    task_id = callback.data.split("_")[1]
    await callback.message.edit_text(
        "Что вы хотите изменить?",
        reply_markup=edit_options_menu(task_id)
    )

@router.callback_query(F.data.startswith("edit_text_"))
async def edit_text_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return
    _, _, _, current_text, _, _, *_ = task
    await state.update_data({
        'task_id': task_id,
        'current_text': current_text,
        'edit_message_id': callback.message.message_id
    })
    await callback.message.answer(
        f"✏️ Введите новый текст задачи:\n\nТекущий текст: {current_text}"
    )
    await state.set_state(TaskStates.waiting_for_edit_text)

@router.callback_query(F.data == "group_menu")
async def main_menu_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    await send_and_track_message(
        callback.message.chat.id,
        "*📋 Головне меню*",
        reply_markup=mk.group_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_date_"))
async def edit_date_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return
    tz_info = await get_group_timezone(callback.message.chat.id)
    if tz_info:
        timezone, custom_name, custom_offset = tz_info
        tz_offset = custom_offset if custom_offset is not None else {
            'moscow': 3,
            'ekb': 5,
            'novosib': 7
        }.get(timezone, 3)
    else:
        tz_offset = 3
    _, _, _, _, due_date, _, *_ = task
    due_datetime = datetime.fromisoformat(due_date)
    local_due_datetime = due_datetime + timedelta(hours=tz_offset)
    current_date = local_due_datetime.strftime('%d.%m.%Y %H:%M')
    await state.update_data({
        'task_id': task_id,
        'current_date': current_date,
        'edit_message_id': callback.message.message_id,
        'tz_offset': tz_offset
    })
    await callback.message.delete()
    await send_and_track_message(
        callback.message.chat.id,
        f"📅 Введите новую дату в формате ДД.ММ.ГГГГ ЧЧ:ММ\n\nТекущая дата: {current_date}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_{task_id}")]
        ]),
        task_id=task_id
    )
    await state.set_state(TaskStates.waiting_for_edit_date)

@router.callback_query(F.data == "create_task")
async def create_task_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        await cleanup_user_and_bot_messages(callback.message.chat.id, callback.message.message_id)
        msg = await send_and_track_message(
            callback.message.chat.id,
            "Введите задачу в формате: Текст, ДД.ММ.ГГГГ ЧЧ:ММ\nНапример: Парикмахер, 20.07.2025 18:00",
            task_id=None,
            delete_after=None
        )
        await state.set_state(TaskStates.waiting_for_task)
    except:
        await callback.answer("Произошла ошибка, попробуйте еще раз")


@router.message(TaskStates.waiting_for_task)
async def process_task(message: types.Message, state: FSMContext):
    user_message_id = message.message_id
    chat_id = message.chat.id

    try:
        await cleanup_user_message(chat_id, user_message_id)

        try:
            text, date = message.text.rsplit(',', 1)
            text = text.strip()
            date = date.strip()
        except ValueError:
            await cleanup_bot_messages(chat_id)
            error_msg = await send_and_track_message(
                chat_id,
                "❌ Неверный формат. Введите через запятую:\n"
                "Например: Парикмахер, 10.07.2025 13:26",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Попробовать снова", callback_data="create_task")]
                ])
            )
            await state.update_data(error_message_id=error_msg.message_id)
            return

        tz_info = await get_group_timezone(chat_id)
        tz_offset = 3
        if tz_info:
            timezone, custom_name, custom_offset = tz_info
            if custom_offset is not None:
                tz_offset = custom_offset

        try:
            date_part, time_part = date.split()

            if '.' in date_part:
                parts = date_part.split('.')
                if len(parts) == 3:
                    day, month, year = parts
                else:
                    day = parts[0]
                    month = parts[1][:2]
                    year = parts[1][2:]
            elif '-' in date_part:
                day, month, year = date_part.split('-')
            else:
                day = date_part[:2]
                month = date_part[2:4]
                year = date_part[4:]

            time_part = time_part.replace(':', '').replace('.', '').replace('-', '')
            if len(time_part) == 3:
                time_part = '0' + time_part
            hour = time_part[:2]
            minute = time_part[2:4]

            if int(hour) > 23 or int(minute) > 59:
                raise ValueError("Некорректное время")

            local_due_date = datetime(
                int(year), int(month), int(day),
                int(hour), int(minute))

            utc_due_date = local_due_date - timedelta(hours=tz_offset)

            if utc_due_date < datetime.utcnow():
                raise ValueError("Дата не может быть в прошлом")

            await cleanup_bot_messages(chat_id)

            task_id = await add_task(chat_id, message.from_user.id, text, utc_due_date.isoformat())

            formatted_date = local_due_date.strftime('%d.%m.%Y %H:%M')

            confirm_msg = await send_and_track_message(
                chat_id,
                f"✅ Задача создана!\n\n"
                f"📌 Текст: {text}\n"
                f"🕒 Дата: {formatted_date}\n\n"
                "Хотите добавить исполнителей к задаче?",
                reply_markup=mk.assignee_choice_menu(task_id),
                task_id=task_id
            )

            await state.update_data({
                'task_id': task_id,
                'confirm_message_id': confirm_msg.message_id
            })
            await state.set_state(TaskStates.waiting_for_assignee_choice)

        except ValueError as e:
            await cleanup_bot_messages(chat_id)
            examples = [
                "1. Парикмахер, 10.07.2025 13:26",
                "2. Парикмахер, 10072025 1326",
                "3. Парикмахер, 10.072025 13.26",
                "4. Парикмахер, 10-07-2025 13-26"
            ]
            error_msg = await send_and_track_message(
                chat_id,
                f"❌ Ошибка: {str(e)}\n\nПравильные форматы даты и времени:\n" +
                "\n".join(examples) +
                "\n\nПопробуйте еще раз:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Ввести заново", callback_data="create_task")]
                ])
            )
            await state.update_data(error_message_id=error_msg.message_id)

    except:
        await cleanup_user_message(chat_id, user_message_id)
        await cleanup_bot_messages(chat_id)
        await send_and_track_message(
            chat_id,
            "❌ Произошла ошибка. Попробуйте еще раз",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Ввести заново", callback_data="create_task")]
            ]),
            delete_after=10
        )

@router.callback_query(F.data.startswith("with_assignee_"))
async def with_assignee_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    await state.update_data({'task_id': task_id})
    await cleanup_bot_messages(callback.message.chat.id)
    await send_and_track_message(
        callback.message.chat.id,
        "Введите имя исполнителя через @ (например: @username)",
        task_id=task_id
    )
    await state.set_state(TaskStates.waiting_for_assignee)

@router.callback_query(F.data.startswith("without_assignee_"))
async def without_assignee_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    await cleanup_bot_messages(callback.message.chat.id)
    await send_and_track_message(
        callback.message.chat.id,
        "✅ Задача создана! Добавить напоминание?",
        reply_markup=mk.reminder_menu(task_id),
        task_id=task_id
    )
    await state.clear()

@router.message(TaskStates.waiting_for_assignee)
async def process_assignee(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        task_id = data['task_id']
        assignee = message.text.strip()
        
        if not assignee.startswith('@'):
            raise ValueError("Имя исполнителя должно начинаться с @")
            
        await cleanup_user_message(message.chat.id, message.message_id)
        await add_assignee(task_id, assignee)
        
        assignees = await get_assignees(task_id)
        assignees_text = "\n".join(assignees) if assignees else "Нет исполнителей"
        
        await cleanup_bot_messages(message.chat.id)
        await send_and_track_message(
            message.chat.id,
            f"✅ Исполнитель добавлен:\n{assignee}\n\nТекущие исполнители:\n{assignees_text}",
            reply_markup=mk.assignee_menu(task_id),
            task_id=task_id
        )
        
    except ValueError as e:
        await send_and_track_message(
            message.chat.id,
            f"❌ Ошибка: {str(e)}\n\nВведите имя исполнителя через @ (например: @username)",
            delete_after=5
        )

@router.callback_query(F.data.startswith("continue_"))
async def continue_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[1]
    await cleanup_bot_messages(callback.message.chat.id)
    await send_and_track_message(
        callback.message.chat.id,
        "✅ Задача создана! Добавить напоминание?",
        reply_markup=mk.reminder_menu(task_id),
        task_id=task_id
    )
    await state.clear()

@router.callback_query(F.data.startswith("add_more_"))
async def add_more_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    await state.set_state(TaskStates.waiting_for_assignee)
    await cleanup_bot_messages(callback.message.chat.id)
    await send_and_track_message(
        callback.message.chat.id,
        "Введите имя исполнителя через @ (например: @username)",
        task_id=task_id
    )


def get_current_time_str(offset_hours):
    now_utc = datetime.utcnow()
    local_time = now_utc + timedelta(hours=offset_hours)
    return local_time.strftime("%H:%M")

# Добавляем обработчики
@router.callback_query(F.data == "change_timezone")
async def change_timezone_handler(callback: types.CallbackQuery):
    # Получаем текущее время для Екатеринбурга (UTC+5)
    ekb_time = get_current_time_str(5)
    
    await callback.message.edit_text(
        "🕒 Выберите ваш часовой пояс:",
        reply_markup=mk.timezone_menu(ekb_time)  # Передаем время Екатеринбурга
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tz_"))
async def timezone_selection_handler(callback: types.CallbackQuery, state: FSMContext):
    tz_data = callback.data.split("_")[1]
    
    if tz_data == "moscow":
        await state.update_data({
            'timezone': 'moscow',
            'offset': 3,
            'name': 'Москва (UTC+3)'
        })
        time_str = get_current_time_str(3)
    elif tz_data == "ekb":
        await state.update_data({
            'timezone': 'ekb',
            'offset': 5,
            'name': 'Екатеринбург (UTC+5)'
        })
        time_str = get_current_time_str(5)
    elif tz_data == "novosib":
        await state.update_data({
            'timezone': 'novosib',
            'offset': 7,
            'name': 'Новосибирск (UTC+7)'
        })
        time_str = get_current_time_str(7)
    elif tz_data == "custom":
        await callback.message.delete()  # Удаляем предыдущее сообщение
        await send_and_track_message(
            callback.message.chat.id,
            "📝 Введите название вашего региона (например: Москва):",
            reply_markup=mk.cancel_timezone_menu()
        )
        await state.set_state(TimezoneStates.waiting_for_custom_name)
        await callback.answer()
        return
    elif tz_data == "change":
        await change_timezone_handler(callback)
        return
    elif tz_data == "confirm":
        data = await state.get_data()
        await set_group_timezone(
            callback.message.chat.id,
            data['timezone'],
            data.get('custom_name'),
            data.get('custom_offset')
        )
        await callback.message.delete()  # Удаляем предыдущее сообщение
        await send_and_track_message(
            callback.message.chat.id,
            f"✅ Часовой пояс установлен: {data['name']}",
            reply_markup=mk.group_menu()
        )
        await state.clear()
        await callback.answer()
        return
    
    data = await state.get_data()
    await callback.message.edit_text(
        f"Установить часовой пояс: {data['name']} ({time_str})?",
        reply_markup=mk.timezone_confirmation_menu(data['name'], time_str)
    )
    await callback.answer()

@router.message(TimezoneStates.waiting_for_custom_name)
async def process_custom_name(message: types.Message, state: FSMContext):
    await state.update_data({'custom_name': message.text})
    await cleanup_user_message(message.chat.id, message.message_id)

    moscow_minutes = datetime.utcnow().minute
    await state.update_data({'minutes': moscow_minutes})

    await send_and_track_message(
        message.chat.id,
        f"⏰ Сейчас в Москве: {datetime.utcnow().hour}:{moscow_minutes:02d}\n"
        "Введите ваш текущий час (0-23):",
        reply_markup=mk.cancel_timezone_menu()
    )
    await state.set_state(TimezoneStates.waiting_for_custom_hours)

@router.message(TimezoneStates.waiting_for_custom_hours)
async def process_custom_hours(message: types.Message, state: FSMContext):
    try:
        hours = int(message.text.strip())
        if hours < 0 or hours > 23:
            raise ValueError
    except ValueError:
        await send_and_track_message(
            message.chat.id,
            "❌ Неверный формат. Введите число от 0 до 23:",
            reply_markup=mk.cancel_timezone_menu(),
            delete_after=5
        )
        return

    data = await state.get_data()
    minutes = data['minutes']
    current_time_str = f"{hours}:{minutes:02d}"

    utc_hours = datetime.utcnow().hour
    offset = hours - utc_hours
    if offset > 12:
        offset -= 24
    elif offset < -12:
        offset += 24

    await state.update_data({
        'timezone': 'custom',
        'offset': offset,
        'name': data['custom_name'],
        'custom_offset': offset
    })

    await cleanup_user_message(message.chat.id, message.message_id)
    await send_and_track_message(
        message.chat.id,
        f"⏳ Установить время: {current_time_str} ({data['custom_name']})?",
        reply_markup=mk.timezone_confirmation_menu(data['custom_name'], current_time_str)
    )
    await state.set_state(TimezoneStates.waiting_for_confirmation)


@router.message(TimezoneStates.waiting_for_custom_name)
async def process_custom_name(message: types.Message, state: FSMContext):
    await state.update_data({'custom_name': message.text})
    await cleanup_user_message(message.chat.id, message.message_id)

    moscow_minutes = datetime.utcnow().minute
    await state.update_data({'minutes': moscow_minutes})

    await send_and_track_message(
        message.chat.id,
        f"⏰ Сейчас в Москве: {datetime.utcnow().hour}:{moscow_minutes:02d}\n"
        "Введите ваш текущий час (0-23):",
        reply_markup=mk.cancel_timezone_menu()
    )
    await state.set_state(TimezoneStates.waiting_for_custom_hours)

@router.message(TimezoneStates.waiting_for_custom_hours)
async def process_custom_hours(message: types.Message, state: FSMContext):
    try:
        hours = int(message.text.strip())
        if hours < 0 or hours > 23:
            raise ValueError
    except ValueError:
        await send_and_track_message(
            message.chat.id,
            "❌ Неверный формат. Введите число от 0 до 23:",
            reply_markup=mk.cancel_timezone_menu(),
            delete_after=5
        )
        return

    data = await state.get_data()
    minutes = data['minutes']
    current_time_str = f"{hours}:{minutes:02d}"

    utc_hours = datetime.utcnow().hour
    offset = hours - utc_hours
    if offset > 12:
        offset -= 24
    elif offset < -12:
        offset += 24

    await state.update_data({
        'timezone': 'custom',
        'offset': offset,
        'name': data['custom_name'],
        'custom_offset': offset
    })

    await cleanup_user_message(message.chat.id, message.message_id)
    await send_and_track_message(
        message.chat.id,
        f"⏳ Установить время: {current_time_str} ({data['custom_name']})?",
        reply_markup=mk.timezone_confirmation_menu(data['custom_name'], current_time_str)
    )
    await state.set_state(TimezoneStates.waiting_for_confirmation)

@router.callback_query(F.data.startswith("reschedule_"))
async def reschedule_task_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[1]
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return

    tz_info = await get_group_timezone(callback.message.chat.id)
    tz_offset = tz_info[2] if tz_info and tz_info[2] is not None else {
        'moscow': 3, 'ekb': 5, 'novosib': 7
    }.get(tz_info[0], 3) if tz_info else 3

    _, _, _, text, due_date, *_ = task
    local_due = datetime.fromisoformat(due_date) + timedelta(hours=tz_offset)
    current_date = local_due.strftime('%d.%m.%Y %H:%M')

    await state.update_data({
        'task_id': task_id,
        'current_text': text,
        'current_date': current_date,
        'tz_offset': tz_offset
    })

    await callback.message.delete()
    await send_and_track_message(
        callback.message.chat.id,
        f"🔄 Перенос задачи:\n\n📌 {text}\nТекущая дата: {current_date}\n\n"
        "Введите новую дату в формате ДД.ММ.ГГГГ ЧЧ:ММ\nНапример: 25.07.2025 15:30",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"view_{task_id}")]
        ]),
        task_id=task_id
    )
    await state.set_state(TaskStates.waiting_for_new_date)

@router.message(TaskStates.waiting_for_new_date)
async def process_new_date(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        task_id = data['task_id']
        tz_offset = data['tz_offset']
        await cleanup_user_and_bot_messages(message.chat.id, message.message_id, task_id)
        text = message.text.strip()

        try:
            date_part, time_part = text.split()
            if '.' in date_part:
                parts = date_part.split('.')
                day, month, year = parts if len(parts) == 3 else (parts[0], parts[1][:2], parts[1][2:])
            elif '-' in date_part:
                day, month, year = date_part.split('-')
            else:
                day, month, year = date_part[:2], date_part[2:4], date_part[4:]

            time_part = time_part.replace(':', '').replace('.', '').replace('-', '')
            if len(time_part) == 3:
                time_part = '0' + time_part
            hour, minute = time_part[:2], time_part[2:4]

            if int(hour) > 23 or int(minute) > 59:
                raise ValueError("Некорректное время")

            local_new_date = datetime(int(year), int(month), int(day), int(hour), int(minute))
            utc_new_date = local_new_date - timedelta(hours=tz_offset)
            if utc_new_date < datetime.utcnow():
                raise ValueError("Дата не может быть в прошлом")

            await update_task(task_id, due_date=utc_new_date.isoformat(), notified=0, confirmed=0)

            await send_and_track_message(
                message.chat.id,
                f"✅ Дата задачи успешно изменена на: {text}",
                task_id=task_id,
                delete_after=3
            )

            task = await get_task(task_id)
            if task:
                _, _, _, text, due_date, reminder, *_ = task
                local_due = datetime.fromisoformat(due_date) + timedelta(hours=tz_offset)
                due_date_str = local_due.strftime('%d.%m.%Y %H:%M')
                reminder_text = ""
                if reminder and reminder > 0:
                    h, m = reminder // 60, reminder % 60
                    reminder_text = f"\n⏰ Напоминание: за {h} ч {m} мин" if h else f"\n⏰ Напоминание: за {m} мин"
                await send_and_track_message(
                    message.chat.id,
                    f"📌 Задача #{task_id}\n{text}\n📅 {due_date_str}{reminder_text}",
                    reply_markup=task_actions_menu(task_id),
                    task_id=task_id
                )
            await state.clear()

        except ValueError as e:
            examples = [
                "1. 10.07.2025 13:26",
                "2. 10072025 1326",
                "3. 10.072025 13.26",
                "4. 10-07-2025 13-26"
            ]
            await send_and_track_message(
                message.chat.id,
                f"❌ Ошибка: {str(e)}\n\nПравильные форматы даты:\n" +
                "\n".join(examples) + "\n\nПопробуйте еще раз:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"view_{task_id}")]
                ]),
                task_id=task_id
            )

    except Exception as e:
        await send_and_track_message(
            message.chat.id,
            "❌ Произошла ошибка. Попробуйте еще раз",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"view_{task_id}")]
            ]),
            task_id=task_id,
            delete_after=5
        )

@router.callback_query(F.data.startswith("add_reminder_"))
async def add_reminder_handler(callback: types.CallbackQuery):
    task_id = callback.data.split("_")[2]
    await cleanup_bot_messages(callback.message.chat.id)
    await send_and_track_message(
        callback.message.chat.id,
        "Выберите время напоминания:",
        reply_markup=reminder_menu(task_id),
        task_id=task_id
    )

@router.callback_query(F.data == "delete_all")
async def delete_all_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить ВСЕ задачи?",
        reply_markup=mk.delete_all_confirmation()
    )

@router.callback_query(F.data == "confirm_delete_all")
async def confirm_delete_all_handler(callback: types.CallbackQuery):
    await delete_all_tasks(callback.message.chat.id)
    await callback.message.edit_text(
        "✅ Все задачи удалены",
        reply_markup=mk.group_menu()
    )

@router.callback_query(F.data.startswith("delete_"))
async def delete_task_handler(callback: types.CallbackQuery):
    task_id = callback.data.split("_")[1]
    try:
        pinned_msg_id = await get_pinned_message(callback.message.chat.id, task_id)
        if pinned_msg_id:
            await bot.unpin_chat_message(callback.message.chat.id, pinned_msg_id)
            await delete_pinned_message(callback.message.chat.id, task_id)
    except:
        pass

    await delete_task(task_id)
    tasks = await get_all_tasks(callback.message.chat.id)
    
    if tasks:
        await send_tasks_page(
            chat_id=callback.message.chat.id,
            tasks=tasks,
            edit_message_id=callback.message.message_id
        )
    else:
        await callback.message.edit_text(
            "📭 Нет активных задач",
            reply_markup=mk.group_menu()
        )

@router.callback_query(F.data.startswith("tasks_page_"))
async def tasks_page_handler(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    tasks = await get_all_tasks(callback.message.chat.id)
    await send_tasks_page(
        chat_id=callback.message.chat.id,
        tasks=tasks,
        page=page,
        edit_message_id=callback.message.message_id
    )
    await callback.answer()

@router.callback_query(F.data.startswith("view_"))
async def view_task_handler(callback: types.CallbackQuery):
    task_id = callback.data.split("_")[1]
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return

    tz_info = await get_group_timezone(callback.message.chat.id)
    tz_offset = tz_info[2] if tz_info and tz_info[2] is not None else {
        'moscow': 3, 'ekb': 5, 'novosib': 7
    }.get(tz_info[0], 3) if tz_info else 3

    _, _, _, text, due_date, reminder, *_ = task
    local_due = datetime.fromisoformat(due_date) + timedelta(hours=tz_offset)
    due_date_str = local_due.strftime('%d.%m.%Y %H:%M')

    reminder_text = ""
    if reminder and reminder > 0:
        h, m = reminder // 60, reminder % 60
        reminder_text = f"\n⏰ Напоминание: за {h} ч {m} мин" if h else f"\n⏰ Напоминание: за {m} мин"

    assignees = await get_assignees(task_id)
    assignees_text = ', '.join(a[1:] if a.startswith('@') else a for a in assignees)
    
    await callback.message.delete()
    await send_and_track_message(
        callback.message.chat.id,
        f"<b>📌 Задача #{task_id}</b>\n{escape_html(text)}\n<b>📅 {due_date_str}</b>{reminder_text}\n"
        f"<b>👥 Исполнители:</b> {escape_html(assignees_text)}",
        reply_markup=mk.task_actions_menu(task_id),
        task_id=task_id,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("confirm_"))
async def confirm_task_handler(callback: types.CallbackQuery):
    task_id = callback.data.split('_')[1]

    pinned_msg_id = await get_pinned_message(callback.message.chat.id, task_id)
    if pinned_msg_id:
        chat = await bot.get_chat(callback.message.chat.id)
        if chat.pinned_message and chat.pinned_message.message_id == pinned_msg_id:
            await bot.unpin_chat_message(callback.message.chat.id)
        await bot.delete_message(callback.message.chat.id, pinned_msg_id)
        await delete_pinned_message(callback.message.chat.id, task_id)

    await update_task(task_id, confirmed=1)
    await cleanup_bot_messages(callback.message.chat.id, task_id)
    await callback.answer("✅ Задача подтверждена", show_alert=False)

@router.message(TaskStates.waiting_for_edit_text)
async def process_edit_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['task_id']
    current_text = data['current_text']

    new_text = message.text.strip()

    if not new_text:
        await send_and_track_message(
            message.chat.id,
            "❌ Ошибка: Текст не может быть пустым",
            delete_after=5
        )
        return

    if new_text == current_text:
        await send_and_track_message(
            message.chat.id,
            "❌ Новый текст такой же, как текущий",
            delete_after=3
        )
        return

    await state.update_data({'new_text': new_text})
    await cleanup_user_message(message.chat.id, message.message_id)

    await send_and_track_message(
        message.chat.id,
        f"Вы ввели новый текст:\n{new_text}\n\nПодтвердить изменения?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_text_{task_id}"),
             InlineKeyboardButton(text="❌ Нет", callback_data=f"edit_{task_id}")]
        ]),
        task_id=task_id
    )

@router.callback_query(F.data.startswith("confirm_text_"))
async def confirm_edit_text_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    data = await state.get_data()
    new_text = data['new_text']

    await update_task(task_id, text=new_text)
    await cleanup_bot_messages(callback.message.chat.id, task_id)

    await callback.message.edit_text(
        "✅ Текст задачи успешно изменен!",
        reply_markup=None
    )

    await asyncio.sleep(1.5)
    task = await get_task(task_id)
    if task:
        _, _, _, text, due_date, reminder, *_ = task
        due_date_str = datetime.fromisoformat(due_date).strftime('%d.%m.%Y %H:%M')

        reminder_text = ""
        if reminder and reminder > 0:
            hours = reminder // 60
            mins = reminder % 60
            reminder_text = f"\n⏰ Напоминание: за {hours} ч {mins} мин" if hours else f"\n⏰ Напоминание: за {mins} мин"

        await callback.message.edit_text(
            f"📌 Задача #{task_id}\n{text}\n📅 {due_date_str}{reminder_text}",
            reply_markup=task_actions_menu(task_id)
        )

    await state.clear()
@router.message(TaskStates.waiting_for_edit_date)
async def process_edit_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['task_id']
    tz_offset = data['tz_offset']

    new_date_str = message.text.strip()
    local_new_date = datetime.strptime(new_date_str, '%d.%m.%Y %H:%M')
    utc_new_date = local_new_date - timedelta(hours=tz_offset)

    if utc_new_date < datetime.utcnow():
        await send_and_track_message(
            message.chat.id,
            "❌ Ошибка: Дата не может быть в прошлом\n\nВведите дату в формате ДД.ММ.ГГГГ ЧЧ:ММ",
            delete_after=5
        )
        return

    await state.update_data({'new_date': utc_new_date.isoformat()})
    await cleanup_user_message(message.chat.id, message.message_id)

    await send_and_track_message(
        message.chat.id,
        f"Вы ввели новую дату:\n{new_date_str}\n\nПодтвердить изменения?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_date_{task_id}"),
             InlineKeyboardButton(text="❌ Нет", callback_data=f"edit_{task_id}")]
        ]),
        task_id=task_id
    )

@router.callback_query(F.data.startswith("confirm_date_"))
async def confirm_edit_date_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[2]
    data = await state.get_data()
    new_date = data['new_date']

    await update_task(
        task_id,
        due_date=new_date,
        notified=0,
        confirmed=0
    )
    await cleanup_bot_messages(callback.message.chat.id, task_id)

    await callback.message.edit_text(
        "✅ Дата задачи успешно изменена!",
        reply_markup=None
    )

    await asyncio.sleep(1.5)
    task = await get_task(task_id)
    if task:
        _, _, _, text, due_date, reminder, *_ = task
        due_date_str = datetime.fromisoformat(due_date).strftime('%d.%m.%Y %H:%M')

        reminder_text = ""
        if reminder and reminder > 0:
            hours = reminder // 60
            mins = reminder % 60
            reminder_text = f"\n⏰ Напоминание: за {hours} ч {mins} мин" if hours else f"\n⏰ Напоминание: за {mins} мин"

        await callback.message.edit_text(
            f"📌 Задача #{task_id}\n{text}\n📅 {due_date_str}{reminder_text}",
            reply_markup=task_actions_menu(task_id)
        )

    await state.clear()

async def check_reminders():
    while True:
        now_utc = datetime.utcnow()

        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("""
                DELETE FROM tasks 
                WHERE confirmed=1 AND datetime(due_date) < datetime('now', '-1 day')
            """)
            await conn.commit()

            cursor = await conn.execute("""
                SELECT t.id, t.chat_id, t.text, t.due_date, t.reminder_minutes, 
                       t.notified, t.confirmed, t.main_notified, t.active,
                       g.timezone, g.custom_offset
                FROM tasks t
                LEFT JOIN group_timezones g ON t.chat_id = g.chat_id
                WHERE t.active=1
            """)
            tasks = await cursor.fetchall()

        for task in tasks:
            task_id = task[0]
            chat_id = task[1]
            text = task[2]
            due_date = task[3]
            reminder_minutes = task[4]
            notified = task[5]
            confirmed = task[6]
            main_notified = task[7]
            active = task[8]
            timezone = task[9] if task[9] else 'moscow'
            custom_offset = task[10] if task[10] is not None else None

            try:
                due_datetime = datetime.fromisoformat(due_date.replace(' ', 'T', 1))
            except ValueError:
                continue

            offset = custom_offset if custom_offset is not None else {
                'moscow': 3,
                'ekb': 5,
                'novosib': 7
            }.get(timezone, 3)

            local_due_datetime = due_datetime + timedelta(hours=offset)
            assignees = await get_assignees(task_id)

            assignees_text = ' '.join(escape_html(a) for a in assignees) if assignees else "Нет"
            safe_text = escape_html(text)
            formatted_date = escape_html(local_due_datetime.strftime('%d.%m.%Y %H:%M'))

            if reminder_minutes and reminder_minutes > 0:
                reminder_time = due_datetime - timedelta(minutes=reminder_minutes)
                if now_utc >= reminder_time and not notified:
                    reminder_text = (
                        f"⏰ <b>Напоминание за {reminder_minutes} мин</b>\n"
                        f"📌 <b>Задача:</b> {safe_text}\n"
                        f"🕒 <b>Время:</b> {formatted_date}\n"
                        f"👥 <b>Исполнители:</b> {assignees_text}"
                    )
                    await send_and_track_message(
                        chat_id,
                        reminder_text,
                        reply_markup=mk.confirmation_menu(task_id, reminder=True),
                        task_id=task_id,
                        parse_mode="HTML"
                    )
                    await update_task(task_id, notified=1)
                    await asyncio.sleep(0.5)

            if now_utc >= due_datetime and not main_notified:
                main_text = (
                    f"🔔 <b>Время выполнять!</b>\n"
                    f"📌 <b>Задача:</b> {safe_text}\n"
                    f"🕒 <b>Назначенное время:</b> {formatted_date}\n"
                    f"👥 <b>Исполнители:</b> {assignees_text}"
                )
                msg = await bot.send_message(
                    chat_id,
                    main_text,
                    reply_markup=mk.confirmation_menu(task_id, due=True),
                    parse_mode="HTML"
                )
                try:
                    await bot.pin_chat_message(chat_id, msg.message_id)
                except Exception:
                    pass
                await add_bot_message(chat_id, msg.message_id, task_id)
                await add_pinned_message(chat_id, msg.message_id, task_id)
                await update_task(task_id, main_notified=1)
                await asyncio.sleep(0.5)

        await asyncio.sleep(10)

dp.include_router(router)

async def main():
    await init_db()
    reminders_task = None
    try:
        reminders_task = asyncio.create_task(check_reminders())
        print("Бот запущен")
        await dp.start_polling(bot)
    finally:
        if reminders_task:
            reminders_task.cancel()
            try:
                await reminders_task
            except asyncio.CancelledError:
                pass
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
