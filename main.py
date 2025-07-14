import telebot
from telebot import types
import sqlite3
import g4f
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

bot = telebot.TeleBot('7265663636:AAFwY5EF08zyVbPKzpTZ0CPBxhs4OiGruj8')

scheduler = BackgroundScheduler()
scheduler.start()
back_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
back_kb.add(types.KeyboardButton("Назад"))
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    xp         INTEGER NOT NULL DEFAULT 0,
    streak     INTEGER NOT NULL DEFAULT 0,
    last_active DATE
)
''')
conn.commit()
cursor.execute('''
CREATE TABLE IF NOT EXISTS psychologist_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id     INTEGER NOT NULL,
    question  TEXT    NOT NULL,
    answer    TEXT    NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()
cursor.execute('''
CREATE TABLE IF NOT EXISTS homework_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id     INTEGER NOT NULL,
    question  TEXT    NOT NULL,
    answer    TEXT    NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()
cursor.execute('''
CREATE TABLE IF NOT EXISTS health_checks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id         INTEGER NOT NULL,
    sleep_rating  INTEGER,
    fatigue       TEXT,
    mood          TEXT,
    tips          TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()
cursor.execute('''
CREATE TABLE IF NOT EXISTS sleep_prefs (
    tg_id       INTEGER PRIMARY KEY,
    bedtime     TEXT
)
''')
conn.commit()


@bot.message_handler(commands=['start'])
def start(message):
    ensure_user_exists(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    scheduling_btn = types.InlineKeyboardButton('Составить план', callback_data='scheduling')
    health_btn = types.InlineKeyboardButton('Здоровье', callback_data='health')
    lessons_btn = types.InlineKeyboardButton('Помощь с ДЗ', callback_data='lessons')
    help_btn = types.InlineKeyboardButton('ИИ-Психолог', callback_data='psychologist')
    level_btn = types.InlineKeyboardButton('XP Game', callback_data='xp_game')
    leaderboard_btn = types.InlineKeyboardButton('Лидеры', callback_data='leaderboard')
    markup.row(level_btn)
    markup.row(leaderboard_btn)
    markup.row(scheduling_btn)
    markup.row(lessons_btn)
    markup.row(health_btn, help_btn)
    with open('start_photo.jpg', 'rb') as photo:
        bot.send_photo(
            chat_id=message.chat.id,
            photo=photo,
            caption="Привет! Я — твой многофункциональный бот-помощник 🤖\n\n"
                    "🗓️ «Составить план» — планируй день с помощью ИИ\n📚 «Помощь с ДЗ» — решаем задачи\n"
                    "❤️ «Здоровье» — советы по самочувствию\n🧠 «ИИ‑психолог» — поддержка и советы\n"
                    "🎮 «XP Game» — прокачивай себя и получай XP\n\nВыбери кнопку и вперед! 🚀",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if call.data == 'scheduling':
        go_scheduling(call)
    elif call.data == 'health':
        go_health(call)
    elif call.data == 'lessons':
        go_lessons(call)
    elif call.data == 'psychologist':
        go_psychologist(call)
    elif call.data == 'xp_game':
        go_xp_game(call)
    elif call.data == 'leaderboard':
        go_leaderboard(call)
    elif call.data == 'sleep_prefs':
        go_sleep_prefs(call)
    elif call.data == 'back':
        start(call.message)


def ensure_user_exists(tg_id):
    cursor.execute('SELECT 1 FROM users WHERE tg_id = ?', (tg_id,))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (tg_id, streak, last_active) VALUES (?, ?, ?)',
            (tg_id, 1, datetime.today().date())
        )
        conn.commit()


def get_psychologist_reply(question_text):
    system = ("You are an empathetic professional psychologist. "
              "You only talk about personal and emotional issues. "
              "If asked anything else, refuse: “I can’t help with that.”")
    msgs = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': question_text}
    ]
    return g4f.ChatCompletion.create(
        model="gpt-4",
        messages=msgs
    )


def get_homework_solution(prompt_text):
    system = (
        "You are a helpful AI tutor. "
        "When given a homework question, provide a clear, step‑by‑step solution. "
        "Do not offer unrelated advice."
    )
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': prompt_text}
    ]
    return g4f.ChatCompletion.create(
        model="gpt-4",
        messages=messages
    )


def get_health_tips(sleep, fatigue, mood):
    system = (
        "Говори ТОЛЬКО на русском языке. "
        "You are a friendly health coach. "
        "Based on the user's sleep (1–5), fatigue (yes/no) and mood (emoji), "
        "provide 3 simple personalized tips to improve well‑being today."
    )
    user_msg = f"Sleep: {sleep}/5; Fatigue: {fatigue}; Mood: {mood}"
    msgs = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user_msg}
    ]
    return g4f.ChatCompletion.create(model="gpt-4", messages=msgs)


def schedule_user_sleep_reminder(tg_id: int, bedtime: str):
    h, m = map(int, bedtime.split(':'))
    rem_min = m - 15
    rem_hour = h
    if rem_min < 0:
        rem_min += 60
        rem_hour = (h - 1) % 24
    job_id = f"sleep_{tg_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    scheduler.add_job(
        send_sleep_reminder,
        trigger='cron',
        hour=rem_hour,
        minute=rem_min,
        args=[tg_id],
        id=job_id,
        replace_existing=True
    )


def go_scheduling(call):
    markup = types.InlineKeyboardMarkup()
    back = types.InlineKeyboardButton('Назад', callback_data='back')
    markup.row(back)
    with open('start_photo.jpg', 'rb') as photo:
        bot.send_photo(
            chat_id=call.message.chat.id,
            photo=photo,
            caption="Планирование",
            reply_markup=markup
        )


def go_health(call):
    cursor.execute(
        """
        SELECT sleep_rating, fatigue, mood, tips
        FROM health_checks
        WHERE tg_id = ?
          AND date(created_at) = date('now')
        """,
        (call.message.chat.id,)
    )
    row = cursor.fetchone()
    if row:
        sleep_rating, fatigue, mood, tips = row
        text = (
            f"📊 Твой чек‑ап за сегодня:\n"
            f"• Сон: {sleep_rating}/5\n"
            f"• Усталость: {fatigue}/5\n"
            f"• Настроение: {mood}/5\n\n"
            f"🩺 Советы:\n{tips}"
        )
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton('Назад', callback_data='back'),
            types.InlineKeyboardButton('Настройка сна 🌙', callback_data='sleep_prefs')
        )
        bot.send_message(call.message.chat.id, text, reply_markup=kb)
    else:
        msg = bot.send_message(
            call.message.chat.id,
            "🌙 Оцени, как ты спал сегодня (1 — ужасно, 5 — отлично):",
            reply_markup=back_kb
        )
        bot.register_next_step_handler(msg, health_step_two)


def health_step_two(message):
    if message.text.strip() == "Назад":
        bot.send_message(message.chat.id, "Возвращаю в главное меню…", reply_markup=types.ReplyKeyboardRemove())
        return start(message)
    try:
        sleep = int(message.text.strip())
        if not 1 <= sleep <= 5:
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id,
                               "Неверно. Введи число 1–5 за свой сон:",
                               reply_markup=back_kb
                               )
        return bot.register_next_step_handler(msg, health_step_two)
    msg = bot.send_message(
        message.chat.id,
        "😓 Оцени уровень усталости (1 — не устану, 5 — очень устаю):",
        reply_markup=back_kb
    )
    bot.register_next_step_handler(msg, lambda m: health_step_three(m, sleep))


def health_step_three(message, sleep):
    if message.text.strip() == "Назад":
        bot.send_message(message.chat.id, "Возвращаю в главное меню…", reply_markup=types.ReplyKeyboardRemove())
        return start(message)
    try:
        fatigue = int(message.text.strip())
        if not 1 <= fatigue <= 5:
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id,
                               "Неверно. Введи число 1–5 за усталость:",
                               reply_markup=back_kb
                               )
        return bot.register_next_step_handler(msg, lambda m: health_step_three(m, sleep))
    msg = bot.send_message(
        message.chat.id,
        "🙂 Оцени своё настроение (1 — очень плохо, 5 — супер):",
        reply_markup=back_kb
    )
    bot.register_next_step_handler(msg, lambda m: handle_health_result(m, sleep, fatigue))


def handle_health_result(message, sleep, fatigue):
    try:
        mood = int(message.text.strip())
        if not 1 <= mood <= 5:
            raise ValueError
    except:
        return bot.send_message(message.chat.id, "❗️ Пожалуйста, введи число от 1 до 5 за своё настроение:",
                                reply_markup=back_kb)
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        tips = get_health_tips(sleep, fatigue, mood)
    except Exception as e:
        return bot.send_message(message.chat.id, f"⚠️ Ошибка при получении советов: {e}")
    cursor.execute(
        'INSERT INTO health_checks (tg_id, sleep_rating, fatigue, mood, tips) VALUES (?, ?, ?, ?, ?)',
        (message.chat.id, sleep, fatigue, mood, tips)
    )
    cursor.execute('UPDATE users SET xp = xp + 15 WHERE tg_id = ?', (message.chat.id,))
    conn.commit()
    bot.send_message(message.chat.id, "🎉 Отлично, ты заработал 15 XP!")
    bot.send_message(message.chat.id, tips, reply_markup=types.ReplyKeyboardRemove())
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton('Назад', callback_data='back'),
        types.InlineKeyboardButton('Настройка сна 🌙', callback_data='sleep_prefs')
    )
    bot.send_message(message.chat.id, "Что дальше?", reply_markup=kb)


def go_lessons(call):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton('Закончить'))
    with open('photo_homework.jpg', 'rb') as photo:
        msg = bot.send_photo(
            chat_id=call.message.chat.id,
            photo=photo,
            caption="📝 Введи свой вопрос по домашнему заданию, и я постараюсь помочь.",
            reply_markup=kb
        )
    bot.register_next_step_handler(msg, handle_homework_chat)


def handle_homework_chat(message):
    if message.text == 'Закончить':
        bot.clear_step_handler_by_chat_id(message.chat.id)
        bot.send_message(message.chat.id, "Сессия «Помощь с ДЗ» завершена.", reply_markup=types.ReplyKeyboardRemove())
        return start(message)
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        answer = get_homework_solution(message.text)
    except Exception as e:
        return bot.send_message(message.chat.id, f"⚠️ Ошибка при решении: {e}")
    cursor.execute(
        'INSERT INTO homework_history (tg_id, question, answer) VALUES (?, ?, ?)',
        (message.chat.id, message.text, answer)
    )
    conn.commit()
    bot.send_message(message.chat.id, answer, reply_markup=types.ReplyKeyboardRemove())
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton('Закончить'))
    msg = bot.send_message(message.chat.id, "Задавай новый вопрос или нажми «Закончить»", reply_markup=kb)
    bot.register_next_step_handler(msg, handle_homework_chat)


def go_psychologist(call):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton('Закончить'))
    with open('photo_psychologist.jpg', 'rb') as photo:
        msg = bot.send_photo(
            chat_id=call.message.chat.id,
            photo=photo,
            caption="🧠 Расскажи о своей личной проблеме. Я помогу советом.",
            reply_markup=kb
        )
    bot.register_next_step_handler(msg, handle_psychologist_chat)


def handle_psychologist_chat(message):
    if message.text == 'Закончить':
        bot.clear_step_handler_by_chat_id(message.chat.id)
        bot.send_message(message.chat.id, "Сессия ИИ‑психолога завершена.", reply_markup=types.ReplyKeyboardRemove())
        return start(message)
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        answer = get_psychologist_reply(message.text)
    except Exception as e:
        return bot.send_message(message.chat.id, f"⚠️ Ошибка ИИ: {e}")
    cursor.execute(
        'INSERT INTO psychologist_history (tg_id, question, answer) VALUES (?, ?, ?)',
        (message.chat.id, message.text, answer)
    )
    conn.commit()
    bot.send_message(message.chat.id, answer, reply_markup=types.ReplyKeyboardRemove())
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton('Закончить'))
    msg = bot.send_message(message.chat.id, "Задавай следующий вопрос или нажми «Закончить»", reply_markup=kb)
    bot.register_next_step_handler(msg, handle_psychologist_chat)


def go_leaderboard(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    cursor.execute('''
        SELECT tg_id, xp
        FROM users
        ORDER BY xp DESC
        LIMIT 5
    ''')
    top5 = cursor.fetchall()
    if top5:
        text = "🏆 Топ‑5 по XP:\n\n"
        for i, (tg, xp) in enumerate(top5, start=1):
            try:
                user = bot.get_chat(tg)
                name = f"@{user.username}" if user.username else user.first_name
            except:
                name = str(tg)
            text += f"{i}. {name} — {xp} XP\n"
    else:
        text = "Никто пока не набрал XP"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton('Назад', callback_data='back'))
    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=kb
    )


def go_xp_game(call):
    ensure_user_exists(call.message.chat.id)
    cursor.execute(
        'SELECT xp, streak, last_active FROM users WHERE tg_id = ?',
        (call.message.chat.id,)
    )
    xp, streak, last_active = cursor.fetchone()
    today = datetime.today().date()
    yesterday = today - timedelta(days=1)
    if last_active == today:
        pass
    elif last_active == yesterday:
        streak += 1
        cursor.execute(
            'UPDATE users SET streak = ?, last_active = ? WHERE tg_id = ?',
            (streak, today, call.message.chat.id)
        )
        conn.commit()
    else:
        streak = 1
        cursor.execute(
            'UPDATE users SET streak = ?, last_active = ? WHERE tg_id = ?',
            (streak, today, call.message.chat.id)
        )
        conn.commit()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Назад', callback_data='back'))
    bot.send_message(
        chat_id=call.message.chat.id,
        text=f"🎮 *XP Game*\n\n"
             f"⭐ Опыт (XP): *{xp}*\n"
             f"🔥 Текущий стрик: *{streak}* дней\n",
        parse_mode='Markdown',
        reply_markup=markup
    )


def go_sleep_prefs(call):
    msg = bot.send_message(
        call.message.chat.id,
        "⏰ Во сколько ты обычно ложишься спать? Формат HH:MM (24‑ч):"
    )
    bot.register_next_step_handler(msg, handle_sleep_prefs)


def handle_sleep_prefs(message):
    try:
        h, m = map(int, message.text.strip().split(':'))
        assert 0 <= h < 24 and 0 <= m < 60
    except:
        return bot.send_message(message.chat.id, "Неверный формат, используй HH:MM. Попробуй ещё раз.")
    cursor.execute(
        '''INSERT INTO sleep_prefs (tg_id, bedtime) VALUES (?, ?)
           ON CONFLICT(tg_id) DO UPDATE SET bedtime=excluded.bedtime''',
        (message.chat.id, message.text.strip())
    )
    conn.commit()
    now = datetime.now()
    bedtime_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if bedtime_dt <= now:
        bot.send_message(message.chat.id, "😴 Уже давно пора спать!")
    else:
        delta = bedtime_dt - now
        if delta <= timedelta(minutes=15):
            bot.send_message(message.chat.id, "⌛️ Уже пора готовиться ко сну!")
        else:
            schedule_user_sleep_reminder(message.chat.id, message.text.strip())
            bot.send_message(message.chat.id, f"Отлично! Я напомню за 15 мин до {message.text.strip()}.")
    bot.send_message(message.chat.id, "Возвращаю тебя в главное меню…")
    start(message)


def send_sleep_reminder(tg_id):
    bot.send_message(tg_id, "⌛️ Через 15 минут пора готовиться ко сну!")


def schedule_all_sleep_reminders():
    cursor.execute('SELECT tg_id, bedtime FROM sleep_prefs')
    for tg_id, bedtime in cursor.fetchall():
        schedule_user_sleep_reminder(tg_id, bedtime)


schedule_all_sleep_reminders()
bot.polling(none_stop=True)
