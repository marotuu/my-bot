from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN, DB_NAME
import aiosqlite
import asyncio

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

db_connection = None

async def init_db():
    global db_connection
    db_connection = await aiosqlite.connect(DB_NAME)
    await db_connection.execute("PRAGMA journal_mode=WAL")
    await db_connection.execute("PRAGMA busy_timeout = 30000")

    await db_connection.execute("""
        CREATE TABLE IF NOT EXISTS group_timezones(
            chat_id INTEGER PRIMARY KEY,
            timezone TEXT,
            custom_name TEXT,
            custom_offset INTEGER
        )
    """)

    await db_connection.execute("""
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            text TEXT,
            due_date TEXT,
            reminder_minutes INTEGER,
            notified BOOLEAN DEFAULT 0,
            confirmed BOOLEAN DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            main_notified BOOLEAN DEFAULT 0
        )
    """)

    await db_connection.execute("""
        CREATE TABLE IF NOT EXISTS bot_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            task_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db_connection.execute("""
        CREATE TABLE IF NOT EXISTS pinned_messages(
            chat_id INTEGER,
            message_id INTEGER,
            task_id INTEGER,
            PRIMARY KEY (chat_id, task_id)
        )
    """)

    await db_connection.execute("""
        CREATE TABLE IF NOT EXISTS task_assignees(
            task_id INTEGER,
            assignee TEXT,
            PRIMARY KEY (task_id, assignee),
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)

    await db_connection.commit()

async def close_db():
    global db_connection
    if db_connection:
        await db_connection.close()

async def set_group_timezone(chat_id, timezone, custom_name=None, custom_offset=None):
    await execute_query(
        "INSERT OR REPLACE INTO group_timezones (chat_id, timezone, custom_name, custom_offset) VALUES (?, ?, ?, ?)",
        (chat_id, timezone, custom_name, custom_offset)
    )

async def get_group_timezone(chat_id):
    return await execute_fetchone(
        "SELECT timezone, custom_name, custom_offset FROM group_timezones WHERE chat_id=?",
        (chat_id,)
    )

async def execute_query(query, params=()):
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(query, params)
        await conn.commit()
        return cursor

async def execute_fetchone(query, params=()):
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(query, params)
        return await cursor.fetchone()

async def execute_fetchall(query, params=()):
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(query, params)
        return await cursor.fetchall()

async def add_assignee(task_id, assignee):
    await execute_query(
        "INSERT OR IGNORE INTO task_assignees (task_id, assignee) VALUES (?, ?)",
        (task_id, assignee)
    )

async def get_assignees(task_id):
    rows = await execute_fetchall(
        "SELECT assignee FROM task_assignees WHERE task_id=?",
        (task_id,)
    )
    return [row[0] for row in rows]

async def delete_assignees(task_id):
    await execute_query(
        "DELETE FROM task_assignees WHERE task_id=?",
        (task_id,)
    )

async def add_pinned_message(chat_id, message_id, task_id):
    await execute_query(
        "INSERT OR REPLACE INTO pinned_messages (chat_id, message_id, task_id) VALUES (?, ?, ?)",
        (chat_id, message_id, task_id)
    )

async def get_pinned_message(chat_id, task_id):
    result = await execute_fetchone(
        "SELECT message_id FROM pinned_messages WHERE chat_id=? AND task_id=?",
        (chat_id, task_id)
    )
    return result[0] if result else None

async def delete_pinned_message(chat_id, task_id):
    await execute_query(
        "DELETE FROM pinned_messages WHERE chat_id=? AND task_id=?",
        (chat_id, task_id)
    )

async def add_task(chat_id, user_id, text, due_date, reminder_minutes=None):
    cursor = await execute_query(
        "INSERT INTO tasks (chat_id, user_id, text, due_date, reminder_minutes) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, text, due_date, reminder_minutes)
    )
    return cursor.lastrowid

async def get_task(task_id):
    return await execute_fetchone(
        "SELECT * FROM tasks WHERE id=?",
        (task_id,)
    )

async def is_message_pinned(chat_id, message_id):
    try:
        chat = await bot.get_chat(chat_id)
        if chat.pinned_message and chat.pinned_message.message_id == message_id:
            return True
        return False
    except Exception as e:
        print(f"Error checking pinned message: {e}")
        return False

async def get_all_tasks(chat_id):
    return await execute_fetchall("""
        SELECT id, text, due_date, reminder_minutes
        FROM tasks
        WHERE chat_id=? AND active=1 AND datetime(due_date) > datetime('now', '-1 day')
        ORDER BY datetime(due_date) ASC
    """, (chat_id,))

async def update_task(task_id, text=None, due_date=None, reminder_minutes=None,
                      notified=None, confirmed=None, active=None, main_notified=None):
    updates = []
    params = []

    if text is not None:
        updates.append("text=?")
        params.append(text)
    if due_date is not None:
        updates.append("due_date=?")
        params.append(due_date)
    if reminder_minutes is not None:
        updates.append("reminder_minutes=?")
        params.append(reminder_minutes)
    if notified is not None:
        updates.append("notified=?")
        params.append(int(notified))
    if confirmed is not None:
        updates.append("confirmed=?")
        params.append(int(confirmed))
    if active is not None:
        updates.append("active=?")
        params.append(int(active))
    if main_notified is not None:
        updates.append("main_notified=?")
        params.append(int(main_notified))

    params.append(task_id)
    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id=?"
    await execute_query(query, params)

async def delete_task(task_id):
    await execute_query(
        "DELETE FROM tasks WHERE id=?",
        (task_id,)
    )

async def delete_all_tasks(chat_id):
    await execute_query(
        "DELETE FROM tasks WHERE chat_id=?",
        (chat_id,)
    )

async def add_bot_message(chat_id, message_id, task_id=None):
    await execute_query(
        "INSERT INTO bot_messages (chat_id, message_id, task_id) VALUES (?, ?, ?)",
        (chat_id, message_id, task_id)
    )

async def get_bot_messages(chat_id, task_id=None):
    if task_id:
        rows = await execute_fetchall(
            "SELECT message_id FROM bot_messages WHERE chat_id=? AND task_id=?",
            (chat_id, task_id)
        )
    else:
        rows = await execute_fetchall(
            "SELECT message_id FROM bot_messages WHERE chat_id=?",
            (chat_id,)
        )
    return [row[0] for row in rows]

async def delete_bot_message(chat_id, message_id):
    await execute_query(
        "DELETE FROM bot_messages WHERE chat_id=? AND message_id=?",
        (chat_id, message_id)
    )
