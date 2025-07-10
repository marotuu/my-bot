from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def private_menu():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="➕ Добавить в группу",
            url="https://t.me/TaskSnap_bot?startgroup=true"
        )
    )
    builder.adjust(1)
    return builder.as_markup()


def group_menu():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="➕ Создать задачу", callback_data="create_task"),
        InlineKeyboardButton(text="📋 Все задачи", callback_data="list_tasks"),
        InlineKeyboardButton(text="🗑 Удалить всё", callback_data="delete_all")
    )
    builder.adjust(3, 1)
    return builder.as_markup()


def timezone_menu(current_time_str):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Екатеринбург (UTC+5)", callback_data="tz_ekb"),
        InlineKeyboardButton(text="Москва (UTC+3)", callback_data="tz_moscow"),
        InlineKeyboardButton(text="Новосибирск (UTC+7)", callback_data="tz_novosib"),
        InlineKeyboardButton(text="⏳ Указать вручную", callback_data="tz_custom"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )
    builder.adjust(1)
    return builder.as_markup()


def timezone_confirmation_menu(timezone_name, time_str):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text=f"✅ Да, установить {timezone_name} ({time_str})",
            callback_data="tz_confirm"
        ),
        InlineKeyboardButton(
            text="❌ Нет, выбрать другой",
            callback_data="tz_change"
        )
    )
    builder.adjust(1)
    return builder.as_markup()


def cancel_timezone_menu():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="❌ Отменить", callback_data="tz_change")
    )
    return builder.as_markup()


def reminder_menu(task_id):
    periods = [
        (1440, "За сутки"),
        (360, "За 6 часов"),
        (180, "За 3 часа"),
        (120, "За 2 часа"),
        (60, "За 1 час"),
        (30, "За 30 мин"),
        (10, "За 10 мин"),
        (5, "За 5 мин")
    ]
    builder = InlineKeyboardBuilder()
    for minutes, text in periods:
        builder.add(InlineKeyboardButton(text=text, callback_data=f"remind_{minutes}_{task_id}"))
    builder.add(InlineKeyboardButton(text="❌ Без напоминания", callback_data=f"remind_0_{task_id}"))
    builder.adjust(2)
    return builder.as_markup()


def tasks_pagination_menu(tasks, page=0, tasks_per_page=2):
    builder = InlineKeyboardBuilder()
    for task in tasks[page * tasks_per_page : (page + 1) * tasks_per_page]:
        task_id = task[0]
        builder.add(InlineKeyboardButton(text=f"#{task_id}", callback_data=f"view_{task_id}"))
    
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"tasks_page_{page - 1}"))
    
    pagination_buttons.append(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    
    if (page + 1) * tasks_per_page < len(tasks):
        pagination_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"tasks_page_{page + 1}"))
    
    builder.row(*pagination_buttons)
    return builder.as_markup()


def task_actions_menu(task_id, show_back=True):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="⌛️ Перенести дату", callback_data=f"reschedule_{task_id}"),
        InlineKeyboardButton(text="➕ Изменить напоминание", callback_data=f"add_reminder_{task_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{task_id}")
    )
    if show_back:
        builder.add(InlineKeyboardButton(text="🔙 Назад к списку", callback_data="list_tasks"))
    builder.adjust(1)
    return builder.as_markup()


def delete_all_confirmation():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Да, удалить все", callback_data="confirm_delete_all"),
        InlineKeyboardButton(text="❌ Нет, отменить", callback_data="list_tasks")
    )
    return builder.as_markup()


def assignee_menu(task_id):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Продолжить", callback_data=f"continue_{task_id}"),
        InlineKeyboardButton(text="➕ Добавить еще", callback_data=f"add_more_1_{task_id}")
    )
    return builder.as_markup()


def assignee_choice_menu(task_id):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Да", callback_data=f"with_assignee_{task_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"without_assignee_{task_id}")
    )
    return builder.as_markup()


def confirmation_menu(task_id, reminder=False, due=False):
    builder = InlineKeyboardBuilder()
    if reminder or due:
        builder.add(
            InlineKeyboardButton(text="✅ Я помню", callback_data=f"confirm_{task_id}")
        )
    builder.adjust(1)
    return builder.as_markup()
