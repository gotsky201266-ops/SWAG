
import re
import time
import urllib.request
from pathlib import Path
import os
import shutil
from datetime import datetime, timedelta

from vkbottle.bot import Bot, Message, rules
from vkbottle import Keyboard, Callback, KeyboardButtonColor, Text, GroupEventType, GroupTypes, User
import json
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

try:
    with CONFIG_PATH.open("r", encoding="utf-8") as js:
        open_file = json.load(js)
except (OSError, json.JSONDecodeError) as exc:
    raise RuntimeError(f"Не удалось прочитать конфигурацию {CONFIG_PATH}: {exc}") from exc

# Railway: задайте VK_TOKEN в Variables. Для локального запуска можно указать
# токен сообщества в поле bot-token файла config.json.
BOT_TOKEN = os.getenv("VK_TOKEN") or open_file.get("bot-token", "")
if not BOT_TOKEN or BOT_TOKEN.strip().lower() in {"token", "your_token", "вставьте_токен"}:
    raise RuntimeError("Не задан токен сообщества VK. Укажите VK_TOKEN в Railway Variables или bot-token в config.json.")

bot = Bot(token=BOT_TOKEN)

async def get_logic(number = int):
    if number < 1: return False
    else: return True

async def getID(arg=str):
    arg_split = arg.split("|")
    if arg_split[0] == arg:
        try:
            cc_split = arg.split("k.com/")
            scr_split = await bot.api.utils.resolve_screen_name(cc_split[1])
            x = json.loads(scr_split.json())
            return int(x['object_id'])
        except: pass
        com_split = arg.split('vk.com/id')
        try:
            com_split[1]
            if com_split[1].isnumeric():
                return com_split[1]
            else:
                return False
        except:
            screen_split = arg.split('vk.com/')
            try:
                screen_split[1]
                scr_split = await bot.api.utils.resolve_screen_name(screen_split[1])
                ut_split = str(scr_split).split(' ')
                obj_split = ut_split[1].split("_id=")
                if not obj_split[1].isnumeric():
                    return False
                return obj_split[1]
            except:
                return False
    try:
        id_split = arg_split[0].split('id')
        return int(id_split[1])
    except:
        return False

async def get_registration_date(user_id=int):
    """Получить дату регистрации VK; при недоступности FOAF вернуть понятный статус."""
    try:
        vk_link = f"https://vk.com/foaf.php?id={int(user_id)}"
        request = urllib.request.Request(vk_link, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=7) as response:
            vk_xml = response.read().decode("windows-1251", errors="replace")

        match = re.search(r'created\s+dc:date="([^"]+)"', vk_xml)
        if not match:
            return "Не удалось определить"

        raw_date = match.group(1).split("+")[0].split("Z")[0]
        registered = datetime.fromisoformat(raw_date)
        months = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }
        return f"{registered.day}-ого {months[registered.month]} {registered.year}г"
    except Exception:
        return "Недоступна (ошибка запроса VK)"

async def get_string(text=[], arg=int):
    data_string = []
    for i in range(len(text)):
        if i < arg: pass
        else: data_string.append(text[i])
    return_string = " ".join(data_string)
    if return_string == "": return False
    else: return return_string

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "database.db"))).expanduser()
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
# При первом подключении Railway Volume переносим в него исходную базу проекта,
# чтобы не создать пустую БД вместо существующих данных.
DEFAULT_DATABASE_PATH = BASE_DIR / "database.db"
if not DATABASE_PATH.exists() and DATABASE_PATH.resolve() != DEFAULT_DATABASE_PATH.resolve() and DEFAULT_DATABASE_PATH.exists():
    shutil.copy2(DEFAULT_DATABASE_PATH, DATABASE_PATH)
database = sqlite3.connect(str(DATABASE_PATH), timeout=30, check_same_thread=False)
sql = database.cursor()
async def check_chat(chat_id=int):
    sql.execute(f"SELECT * FROM chats WHERE chat_id = {chat_id}")
    if sql.fetchone() == None: return False
    else: return True

async def new_chat(chat_id=int, peer_id=int, owner_id=int):
    sql.execute(f"INSERT INTO chats VALUES (?, ?, ?, 'Добро пожаловать, уважаемый %i пользователь!', 0, 0, 0, 0, 0, 0);", (chat_id, peer_id, owner_id))
    sql.execute(f"CREATE TABLE IF NOT EXISTS permissions_{chat_id} (user_id BIGINT, level BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS nicks_{chat_id} (user_id BIGINT, nick TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS banwords_{chat_id} (banword TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS warns_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS mutes_{chat_id} (user_id BIGINT, moder TEXT, reason TEXT, date BIGINT, date_string TEXT, time BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS bans_{chat_id} (user_id BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS messages_{chat_id} (user_id BIGINT, date BIGINT, date_string TEXT, message_id BIGINT, cmid BIGINT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS warnhistory_{chat_id} (user_id BIGINT, count BIGINT, moder BIGINT, reason TEXT, date BIGINT, date_string TEXT);")
    sql.execute(f"CREATE TABLE IF NOT EXISTS punishments_{chat_id} (user_id BIGINT, date TEXT);")
    database.commit()

# Глобальные роли отделены от старых ролей внутри бесед.
# 9 — Основатель, 8 — Заместитель, 7 — Куратор, 6 — Менеджер.
GLOBAL_ROLE_NAMES = {
    9: "👑 Основатель",
    8: "⭐ Заместитель",
    7: "🛡 Куратор",
    6: "🔧 Менеджер",
}

FOUNDER_VK_ID = int(os.getenv("FOUNDER_VK_ID", "0") or 0)


def init_global_roles():
    sql.execute("CREATE TABLE IF NOT EXISTS global_managers (user_id INTEGER PRIMARY KEY, level INTEGER NOT NULL CHECK(level BETWEEN 6 AND 9))")
    sql.execute("CREATE TABLE IF NOT EXISTS global_role_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL, target_id INTEGER NOT NULL, old_level INTEGER, new_level INTEGER, action TEXT NOT NULL, created_at TEXT NOT NULL)")

    # Однократная совместимость со старой схемой: 2/1/0 = основатель/заместитель/куратор.
    columns = [row[1] for row in sql.execute("PRAGMA table_info(global_managers)").fetchall()]
    if "user_id" in columns and "level" in columns:
        sql.execute("UPDATE global_managers SET level = CASE level WHEN 2 THEN 9 WHEN 1 THEN 8 WHEN 0 THEN 7 ELSE level END WHERE level IN (0, 1, 2)")
        # Удаляем некорректные старые уровни и дубликаты перед созданием уникального индекса.
        sql.execute("DELETE FROM global_managers WHERE level NOT BETWEEN 6 AND 9")
        sql.execute("DELETE FROM global_managers WHERE rowid NOT IN (SELECT MIN(rowid) FROM global_managers GROUP BY user_id)")
        sql.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_global_managers_user_id ON global_managers(user_id)")
    if FOUNDER_VK_ID > 0:
        sql.execute("INSERT INTO global_managers(user_id, level) VALUES (?, 9) ON CONFLICT(user_id) DO UPDATE SET level = 9", (FOUNDER_VK_ID,))

    # Дополнительные инструменты глобального персонала.
    sql.execute("""CREATE TABLE IF NOT EXISTS global_bans (
        user_id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL,
        reason TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    sql.execute("""CREATE TABLE IF NOT EXISTS global_complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT, author_id INTEGER NOT NULL,
        text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
        assigned_to INTEGER, resolution TEXT, created_at TEXT NOT NULL,
        closed_at TEXT
    )""")
    sql.execute("""CREATE TABLE IF NOT EXISTS global_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, target_id INTEGER NOT NULL,
        actor_id INTEGER NOT NULL, note TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
        closed_at TEXT
    )""")
    sql.execute("""CREATE TABLE IF NOT EXISTS global_settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )""")
    sql.execute("""CREATE TABLE IF NOT EXISTS global_action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL,
        action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    database.commit()


init_global_roles()

async def get_global_role(user_id: int) -> int:
    sql.execute("SELECT level FROM global_managers WHERE user_id = ?", (int(user_id),))
    row = sql.fetchone()
    return int(row[0]) if row else 0


async def set_global_role(actor_id: int, target_id: int, level: int):
    old_level = await get_global_role(target_id)
    if target_id == FOUNDER_VK_ID and level != 9:
        return False, "Нельзя изменить роль Основателя."
    if old_level == 9 and level != 9:
        return False, "Нельзя снять или заменить Основателя."
    if level == 9 and target_id != FOUNDER_VK_ID:
        return False, "Назначить Основателя можно только через FOUNDER_VK_ID в настройках окружения."
    if level == 0:
        sql.execute("DELETE FROM global_managers WHERE user_id = ?", (target_id,))
        new_level = 0
        action = "remove"
    else:
        sql.execute("INSERT INTO global_managers(user_id, level) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET level = excluded.level", (target_id, level))
        new_level = level
        action = "set"
    sql.execute("INSERT INTO global_role_logs(actor_id, target_id, old_level, new_level, action, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (actor_id, target_id, old_level or None, new_level or None, action, datetime.now().isoformat(timespec="seconds")))
    database.commit()
    return True, "OK"


async def global_log(actor_id: int, action: str, details: str):
    sql.execute(
        "INSERT INTO global_action_logs(actor_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (int(actor_id), action[:80], details[:1000], datetime.now().isoformat(timespec="seconds"))
    )
    database.commit()


async def is_global_banned(user_id: int) -> bool:
    sql.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (int(user_id),))
    return sql.fetchone() is not None


async def is_technical_mode() -> bool:
    sql.execute("SELECT value FROM global_settings WHERE key = 'technical_mode'")
    row = sql.fetchone()
    return bool(row and row[0] == "1")


async def get_role(user_id = int, chat_id = int):
    # Старые уровни 0–6 в беседах не меняются и не зависят от глобальной роли.
    sql.execute("SELECT owner_id FROM chats WHERE chat_id = ?", (chat_id,))
    owner = sql.fetchone()
    if owner and owner[0] == user_id:
        return 5
    sql.execute(f"SELECT level FROM permissions_{int(chat_id)} WHERE user_id = ?", (user_id,))
    fetch = sql.fetchone()
    return 0 if fetch is None else fetch[0]

async def get_warns(user_id=int, chat_id=int):
    sql.execute(f"SELECT count FROM warns_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None: return 0
    else: return fetch[0]

async def get_user_name(user_id=int, chat_id=int):
    sql.execute(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if not fetch == None:
        return fetch[0]
    else:
        try:
            info = await bot.api.users.get(user_id)
            return f"{info[0].first_name} {info[0].last_name}"
        except: return 'Пользователь'

async def is_nick(user_id=int, chat_id=int):
    sql.execute(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")
    if sql.fetchone() == None: return False
    else: return True

async def setnick(user_id=int, chat_id=int, nick=str):
    sql.execute(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")
    if sql.fetchone() == None:
        sql.execute(f"INSERT INTO nicks_{chat_id} VALUES (?, ?)", (user_id, nick))
        database.commit()
    else:
        sql.execute(f"UPDATE nicks_{chat_id} SET nick = ? WHERE user_id = ?", (nick, user_id))
        database.commit()

async def rnick(user_id=int, chat_id=int):
    sql.execute(f"DELETE FROM nicks_{chat_id} WHERE user_id = {user_id}")
    database.commit()

async def equals_roles(user_id_sender=int, user_id_two=int, chat_id=int):
    if await get_role(user_id_sender, chat_id) > await get_role(user_id_two, chat_id):
        return 2
    elif await get_role(user_id_sender, chat_id) == await get_role(user_id_two, chat_id):
        return 1
    else: return 0

async def get_acc(chat_id=int, nick=str):
    sql.execute(f"SELECT user_id FROM nicks_{chat_id} WHERE nick = '{nick}'")
    fetch = sql.fetchone()
    if fetch == None: return False
    else: return fetch[0]

async def get_nick(user_id=int, chat_id=int):
    sql.execute(f"SELECT nick FROM nicks_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None: return False
    else: return fetch[0]

async def nlist(chat_id=int, page=int):
    sql.execute(f"SELECT * FROM nicks_{chat_id}")
    fetch = sql.fetchall()
    nicks = []
    gi = 0
    with CONFIG_PATH.open("r", encoding="utf-8") as json_file:
        open_file = json.load(json_file)
    max_nicks = open_file['nicks_max']
    for i in fetch:
        gi = gi + 1
        if page*max_nicks >= gi and page*max_nicks-max_nicks < gi:
            info = await bot.api.users.get(i[0])
            nicks.append(f'{gi}) @id{i[0]} ({info[0].first_name} {info[0].last_name}) - {i[1]}')
    return nicks

async def nonick(chat_id=int, page=int):
    sql.execute(f"SELECT * FROM nicks_{chat_id}")
    fetch = sql.fetchall()
    nicks = []
    for i in fetch:
        nicks.append(i[0])

    gi = 0
    nonick = []
    with CONFIG_PATH.open("r", encoding="utf-8") as json_file:
        open_file = json.load(json_file)
    max_nonick = open_file['nonick_max']
    users = await bot.api.messages.get_conversation_members(peer_id=2000000000+chat_id)
    users = json.loads(users.json())
    for i in users["profiles"]:
        if not i['id'] in nicks:
            gi = gi + 1
            if page*max_nonick >= gi and page*max_nonick-max_nonick < gi:
                nonick.append(f"{gi}) @id{i['id']} ({i['first_name']} {i['last_name']})")

    return nonick

async def warn(chat_id=int, user_id=int, moder=int, reason=str):
    actualy_warns = await get_warns(user_id, chat_id)
    date = time.time()
    cd = str(datetime.now()).split('.')
    date_string = cd[0]
    sql.execute(f"INSERT INTO warnhistory_{chat_id} VALUES (?, {actualy_warns+1}, ?, ?, {date}, '{date_string}')",(user_id, moder, reason))
    database.commit()
    if actualy_warns < 1:
        sql.execute(f"INSERT INTO warns_{chat_id} VALUES (?, 1, ?, ?, {date}, '{date_string}')", (user_id, moder, reason))
        database.commit()
        return 1
    else:
        sql.execute(f"UPDATE warns_{chat_id} SET user_id = ?, count = ?, moder = ?, reason = ?, date = {date}, date_string = '{date_string}' WHERE user_id = {user_id}", (user_id, actualy_warns+1, moder, reason))
        database.commit()
        return actualy_warns+1

async def clear_warns(chat_id=int, user_id=int):
    sql.execute(f"DELETE FROM warns_{chat_id} WHERE user_id = {user_id}")
    database.commit()

async def unwarn(chat_id=int, user_id=int):
    warns = await get_warns(user_id, chat_id)
    if warns < 2: await clear_warns(chat_id, user_id)
    else:
        sql.execute(f"UPDATE warns_{chat_id} SET count = {warns-1} WHERE user_id = {user_id}")
        database.commit()

    return warns-1

async def gwarn(user_id=int, chat_id=int):
    sql.execute(f"SELECT * FROM warns_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None: return False
    else:
        return {
            'count': fetch[1],
            'moder': fetch[2],
            'reason': fetch[3],
            'time': fetch[5]
        }

async def warnhistory(user_id=int, chat_id=int):
    sql.execute(f"SELECT * FROM warnhistory_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchall()
    warnhistory_mass = []
    gi = 0
    if fetch == None: return False
    else:
        for i in fetch:
            gi = gi + 1
            warnhistory_mass.append(f"{gi}) @id{i[2]} (Модератор) | {i[3]} | {i[5]}")

    return warnhistory_mass

async def warnlist(chat_id=int):
    sql.execute(f"SELECT * FROM warns_{chat_id}")
    fetch = sql.fetchall()
    warns = []
    gi = 0
    for i in fetch:
        gi = gi + 1
        warns.append(f"{gi}) @id{i[0]} (Пользователь) | {i[3]} | @id{i[2]} (Модератор) | {i[1]}/3 | {i[5]}")

    if fetch == None: return False
    return warns

async def staff(chat_id=int):
    sql.execute(f"SELECT * FROM permissions_{chat_id}")
    fetch = sql.fetchall()
    moders = []
    stmoders = []
    admins = []
    stadmins = []
    if fetch == None: return False
    for i in fetch:
        level = i[1]
        if level == 1: moders.append(f'@id{i[0]} ({await get_user_name(i[0], chat_id)})')
        elif level == 2: stmoders.append(f'@id{i[0]} ({await get_user_name(i[0], chat_id)})')
        elif level == 3: admins.append(f'@id{i[0]} ({await get_user_name(i[0], chat_id)})')
        elif level == 4: stadmins.append(f'@id{i[0]} ({await get_user_name(i[0], chat_id)})')

    return {
        'moders': moders,
        'stmoders': stmoders,
        'admins': admins,
        'stadmins': stadmins
    }

async def mute(user_id=int, chat_id=int, moder=int, reason=str, mute_time=int):
    cd = str(datetime.now()).split('.')
    date_string = cd[0]
    sql.execute(f"INSERT INTO mutes_{chat_id} VALUES (?, ?, ?, ?, ?, ?)", (user_id, moder, reason, time.time(), date_string, mute_time))
    database.commit()

async def get_mute(user_id=int, chat_id=int):
    await checkMute(chat_id, user_id)

    sql.execute(f"SELECT * FROM mutes_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()

    if fetch == None: return False
    else:
        return {
            'moder': fetch[1],
            'reason': fetch[2],
            'date': fetch[4],
            'time': fetch[5]
        }

async def unmute(user_id=int, chat_id=int):
    sql.execute(f"DELETE FROM mutes_{chat_id} WHERE user_id = {user_id}")
    database.commit()

async def mutelist(chat_id=int):
    sql.execute(f"SELECT * FROM mutes_{chat_id}")
    fetch = sql.fetchall()
    mutes = []
    if fetch==None: return False
    else:
        for i in fetch:
            if not await checkMute(chat_id, i[0]):
                do_time = datetime.fromisoformat(i[4]) + timedelta(minutes=i[5])
                mute_time = str(do_time).split('.')[0]
                try:
                    int(i[1])
                    mutes.append(f"@id{i[0]} (Пользователь) | {i[2]} | @id{i[1]} (модератор) | До: {mute_time}")
                except: mutes.append(f"@id{i[0]} (Пользователь) | {i[2]} | Бот | До: {mute_time}")

    return mutes

async def checkMute(chat_id=int, user_id=int):
    sql.execute(f"SELECT * FROM mutes_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if not fetch == None:
        do_time = datetime.fromisoformat(fetch[4]) + timedelta(minutes=fetch[5])
        if datetime.now() > do_time:
            sql.execute(f"DELETE FROM mutes_{chat_id} WHERE user_id = {user_id}")
            database.commit()
            return True
        else: return False
    return False

async def check_quit(chat_id=int):
    sql.execute(f"SELECT silence FROM chats WHERE chat_id = {chat_id}")
    fetch = sql.fetchone()
    if fetch == None: return False
    else:
        return await get_logic(fetch[0])

async def get_banwords(chat_id=int):
    sql.execute(f"SELECT * FROM banwords_{chat_id}")
    banwords = []
    fetch = sql.fetchall()
    for i in fetch:
        banwords.append(i[0])

    return banwords

async def clear(user_id=int, chat_id=int, group_id=int, peer_id=int):
    sql.execute(f"SELECT cmid FROM messages_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchall()
    cmids = []
    gi = 0
    for i in fetch:
        gi = gi + 1
        if gi <= 199:
            cmids.append(i[0])
    try: await bot.api.messages.delete(group_id=group_id, peer_id=peer_id, delete_for_all=True, cmids=cmids)
    except: pass

    sql.execute(f"DELETE FROM messages_{chat_id} WHERE user_id = {user_id}")
    database.commit()

async def new_message(user_id=int, message_id=int, cmid=int, chat_id=int):
    cd = str(datetime.now()).split('.')
    date_string = cd[0]
    sql.execute(f"INSERT INTO messages_{chat_id} VALUES (?, ?, ?, ?, ?)", (user_id, time.time(), date_string, message_id, cmid))
    database.commit()

async def checkban(user_id=int, chat_id=int):
    sql.execute(f"SELECT * FROM bans_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None: return False
    else:
        return {
            'moder': fetch[1],
            'reason': fetch[2],
            'date': fetch[4]
        }

async def ban(user_id=int, moder=int, chat_id=int, reason=str):
    sql.execute(f"SELECT user_id FROM bans_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    cd = str(datetime.now()).split('.')
    date_string = cd[0]
    if fetch == None:
        sql.execute(f"INSERT INTO bans_{chat_id} VALUES (?, ?, ?, ?, ?)", (user_id, moder, reason, time.time(), date_string))
        database.commit()
    else:
        sql.execute(f"DELETE FROM bans_{chat_id} WHERE user_id = {user_id}")
        sql.execute(f"INSERT INTO bans_{chat_id} VALUES (?, ?, ?, ?, ?)",(user_id, moder, reason, time.time(), date_string))
        database.commit()

async def unban(user_id=int, chat_id=int):
    sql.execute(f"DELETE FROM bans_{chat_id} WHERE user_id = {user_id}")
    database.commit()

async def roleG(user_id=int, chat_id=int, role=int):
    sql.execute(f"SElECT user_id FROM permissions_{chat_id} WHERE user_id = {user_id}")
    fetch = sql.fetchone()
    if fetch == None:
        if role == 0: sql.execute(f"DELETE FROM permissions_{chat_id} WHERE user_id = {user_id}")
        else: sql.execute(f"INSERT INTO permissions_{chat_id} VALUES (?, ?)", (user_id, role))
    else:
        if role == 0: sql.execute(f"DELETE FROM permissions_{chat_id} WHERE user_id = {user_id}")
        else: sql.execute(f"UPDATE permissions_{chat_id} SET level = ? WHERE user_id = ?", (role, user_id))

    database.commit()

async def banlist(chat_id=int):
    sql.execute(f"SELECT * FROM bans_{chat_id}")
    fetch = sql.fetchall()
    banlist = []
    for i in fetch:
        banlist.append(f"@id{i[0]} (Пользователь) | {i[2]} | @id{i[1]} (Модератор) | {i[4]}")

    return banlist

async def quiet(chat_id=int):
    sql.execute(f"SELECT silence FROM chats WHERE chat_id = {chat_id}")
    result = sql.fetchone()[0]
    if not await get_logic(result):
        sql.execute(f"UPDATE chats SET silence = 1 WHERE chat_id = {chat_id}")
        database.commit()
        return True
    else:
        sql.execute(f"UPDATE chats SET silence = 0 WHERE chat_id = {chat_id}")
        database.commit()
        return False

async def get_pull_chats(chat_id=int):
    sql.execute(f"SELECT owner_id, in_pull FROM chats WHERE chat_id = {chat_id}")
    fetch = sql.fetchone()
    if fetch == None: return False
    if not await get_logic(fetch[1]): return False
    sql.execute(f"SELECT chat_id FROM chats WHERE owner_id = ? AND in_pull = ?", (fetch[0], fetch[1]))
    result = []
    fetch2 = sql.fetchall()
    for i in fetch2:
        result.append(i[0])

    return result

async def get_pull_id(chat_id=int):
    sql.execute(f"SELECT in_pull FROM chats WHERE chat_id = {chat_id}")
    fetch = sql.fetchone()
    return fetch[0]

async def rnickall(chat_id=int):
    sql.execute(f"DELETE FROM nicks_{chat_id}")
    database.commit()

async def banwords(slovo=str, delete=bool, chat_id=int):
    if delete:
        sql.execute(f"DELETE FROM banwords_{chat_id} WHERE banword = ?", (slovo, ))
        database.commit()
    else:
        sql.execute(f"SELECT * FROM banwords_{chat_id} WHERE banword = ?", (slovo, ))
        fetch = sql.fetchone()
        if fetch == None:
            sql.execute(f"INSERT INTO banwords_{chat_id} VALUES (?)", (slovo,))
            database.commit()

async def get_filter(chat_id=int):
    sql.execute(f"SELECT filter FROM chats WHERE chat_id = {chat_id}")
    fetch = sql.fetchone()
    return await get_logic(fetch[0])

async def set_filter(chat_id=int, value=int):
    sql.execute("UPDATE chats SET filter = ? WHERE chat_id = ?", (value, chat_id))
    database.commit()

async def get_antiflood(chat_id=int):
    sql.execute(f"SELECT antiflood FROM chats WHERE chat_id = {chat_id}")
    fetch = sql.fetchone()
    return await get_logic(fetch[0])

async def set_antiflood(chat_id=int, value=int):
    sql.execute("UPDATE chats SET antiflood = ? WHERE chat_id = ?", (value, chat_id))
    database.commit()

async def get_spam(user_id=int, chat_id=int):
    sql.execute(f"SELECT date_string FROM messages_{chat_id}  WHERE user_id = {user_id} ORDER BY date_string DESC LIMIT 3")
    fetch = sql.fetchall()
    list_messages = []
    for i in fetch:
        list_messages.append(datetime.fromisoformat(i[0]))
    try: list_messages = list_messages[:3]
    except: return False

    if list_messages[0] - list_messages[2] < timedelta(seconds=2): return True
    else: return False

async def set_welcome(chat_id=int, text=int):
    sql.execute(f"UPDATE chats SET welcome_text = ? WHERE chat_id = ?", (text, chat_id))
    database.commit()

async def get_welcome(chat_id=int):
    sql.execute("SELECT welcome_text FROM chats WHERE chat_id = ?", (chat_id, ))
    fetch = sql.fetchone()
    if str(fetch[0]).lower().strip() == "off": return False
    else: return str(fetch[0])

async def invite_kick(chat_id=int, change=None):
    sql.execute("SELECT invite_kick FROM chats WHERE chat_id = ?", (chat_id, ))
    fetch = sql.fetchone()
    if not change == None:
        if await get_logic(fetch[0]):
            sql.execute("UPDATE chats SET invite_kick = 0 WHERE chat_id = ?", (chat_id, ))
            database.commit()
            return False
        else:
            sql.execute("UPDATE chats SET invite_kick = 1 WHERE chat_id = ?", (chat_id,))
            database.commit()
            return True
    else:
        return await get_logic(fetch[0])

async def leave_kick(chat_id=int, change=None):
    sql.execute("SELECT leave_kick FROM chats WHERE chat_id = ?", (chat_id,))
    fetch = sql.fetchone()
    if fetch == None: return False
    if change == None: return await get_logic(fetch[0])
    if await get_logic(fetch[0]):
        sql.execute("UPDATE chats SET leave_kick = 0 WHERE chat_id = ?", (chat_id,))
        database.commit()
        return False
    else:
        sql.execute("UPDATE chats SET leave_kick = 1 WHERE chat_id = ?", (chat_id,))
        database.commit()
        return True

async def message_stats(user_id=int, chat_id=int):
    try:
        sql.execute(f"SELECT date_string FROM messages_{chat_id} WHERE user_id = ?", (user_id, ))
        fetch_all = sql.fetchall()
        sql.execute(f"SELECT date_string FROM messages_{chat_id} WHERE user_id = ? ORDER BY date_string DESC LIMIT 1", (user_id,))
        fetch_last = sql.fetchone()
        last = fetch_last[0]
        return {
            'count': len(fetch_all),
            'last': last
        }
    except: return {
        'count': 0,
        'last': 0
    }

async def set_pull(chat_id=int, value=int):
    sql.execute(f"UPDATE chats SET in_pull = ? WHERE chat_id = ?", (value, chat_id))
    database.commit()

async def get_all_peerids():
    sql.execute("SELECT peer_id FROM chats")
    fetch = sql.fetchall()
    peer_ids = []
    for i in fetch:
        peer_ids.append(i[0])

    return peer_ids

async def add_punishment(chat_id=int, user_id=int):
    cd = str(datetime.now()).split('.')
    date_string = cd[0]
    sql.execute(f"INSERT INTO punishments_{chat_id} VALUES (?, ?)", (user_id, date_string))
    database.commit()

async def get_sliv(user_id=int, chat_id=int):
    sql.execute(f"SELECT date FROM punishments_{chat_id}  WHERE user_id = {user_id} ORDER BY date DESC LIMIT 3")
    fetch = sql.fetchall()
    list_messages = []
    for i in fetch:
        list_messages.append(datetime.fromisoformat(i[0]))
    try: list_messages = list_messages[:3]
    except: return False

    if list_messages[0] - list_messages[2] < timedelta(seconds=6): return True
    else: return False

async def staff_zov(chat_id=int):
    sql.execute(f"SElECT user_id FROM permissions_{chat_id}")
    fetch = sql.fetchall()
    staff_zov_str = []
    for i in fetch:
        staff_zov_str.append(f"@id{i[0]} (⚜️)")

    return ''.join(staff_zov_str)

async def delete_message(group_id=int, peer_id=int, cmid=int):
    try: await bot.api.messages.delete(group_id=group_id, peer_id=peer_id, delete_for_all=True, cmids=cmid)
    except: pass

async def set_onwer(user=int, chat=int):
    sql.execute("UPDATE chats SET owner_id = ? WHERE chat_id = ?", (user, chat))
    database.commit()

@bot.on.chat_message(rules.ChatActionRule("chat_kick_user"))
async def user_leave(message: Message) -> None:
    user_id = message.from_id
    chat_id = message.chat_id
    if not await check_chat(chat_id): return True
    if not message.action.member_id == message.from_id: return True
    if await leave_kick(chat_id):
        try: await bot.api.messages.remove_chat_user(chat_id, user_id)
        except: pass
        await message.answer(f"@id{user_id} (Пользователь) вышел(-а) из беседы", disable_mentions=1)
    else:
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("Исключить", {"command": "kick", "user": user_id, "chatId": chat_id}), color=KeyboardButtonColor.NEGATIVE)
        )
        await message.answer(f"@id{user_id} (Пользователь) вышел(-а) из беседы", disable_mentions=1, keyboard=keyboard)

@bot.on.chat_message(rules.ChatActionRule("chat_invite_user_by_link"))
async def user_joined_link(message: Message) -> None:
    user_id = message.from_id
    chat_id = message.chat_id
    if not await check_chat(chat_id): return True
    checkban_str = await checkban(user_id, chat_id)
    if checkban_str:
        try: await bot.api.messages.remove_chat_user(chat_id, user_id)
        except: pass
        info = await bot.api.users.get(user_id)
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("Снять бан", {"command": "unban", "user": user_id, "chatId": chat_id}),color=KeyboardButtonColor.POSITIVE)
        )
        await message.answer(f"@id{user_id} ({info[0].first_name}) заблокирован(-а) в этой беседе!\n\nИнформация о блокировке:\n@id{checkban_str['moder']} (Модератор) | {checkban_str['reason']} | {checkban_str['date']}",disable_mentions=1, keyboard=keyboard)
        return True

    welcome = await get_welcome(chat_id)
    if welcome:
        info = await bot.api.users.get(user_id)
        welcome = welcome.replace('%u', f'@id{user_id}')
        welcome = welcome.replace('%n', f'@id{user_id} ({info[0].first_name})')
        welcome = welcome.replace('%i', f'@id{user_id}')
        uinfo = await bot.api.users.get(user_id)
        welcome = welcome.replace('%p', f'@id{user_id} ({uinfo[0].first_name})')
        await message.answer(welcome)

@bot.on.chat_message(rules.ChatActionRule("chat_invite_user"))
async def user_joined(message: Message) -> None:
    invited_user = message.action.member_id
    user_id = message.from_id
    chat_id = message.chat_id
    if not await check_chat(chat_id): return True
    if invited_user == -224437676:
        await message.answer("Бот успешно добавлен в беседу!\nДля его активации, выдайте боту звезду в беседе и напишите /start!")
    elif user_id == invited_user:
        checkban_str = await checkban(invited_user, chat_id)
        if checkban_str:
            try:await bot.api.messages.remove_chat_user(chat_id, invited_user)
            except:pass
            info = await bot.api.users.get(invited_user)
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": invited_user, "chatId": chat_id}),color=KeyboardButtonColor.POSITIVE)
            )
            await message.answer(f"@id{invited_user} ({info[0].first_name}) заблокирован(-а) в этой беседе!\n\nИнформация о блокировке:\n@id{checkban_str['moder']} (Модератор) | {checkban_str['reason']} | {checkban_str['date']}",disable_mentions=1, keyboard=keyboard)
            return True

        welcome = await get_welcome(chat_id)
        if welcome:
            info = await bot.api.users.get(invited_user)
            welcome = welcome.replace('%u', f'@id{invited_user}')
            welcome = welcome.replace('%n', f'@id{invited_user} ({info[0].first_name})')
            welcome = welcome.replace('%i', f'@id{user_id}')
            uinfo = await bot.api.users.get(user_id)
            welcome = welcome.replace('%p', f'@id{user_id} ({uinfo[0].first_name})')
            await message.answer(welcome)
    else:
        if await get_role(user_id, chat_id) < 1 and await invite_kick(chat_id):
            try: await bot.api.messages.remove_chat_user(chat_id, invited_user)
            except: pass
            return True

        checkban_str = await checkban(invited_user, chat_id)
        if checkban_str:
            try: await bot.api.messages.remove_chat_user(chat_id, invited_user)
            except: pass
            info = await bot.api.users.get(invited_user)
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": invited_user, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )
            await message.answer(f"@id{invited_user} ({info[0].first_name}) заблокирован(-а) в этой беседе!\n\nИнформация о блокировке:\n@id{checkban_str['moder']} (Модератор) | {checkban_str['reason']} | {checkban_str['date']}", disable_mentions=1, keyboard=keyboard)
            return True

        welcome = await get_welcome(chat_id)
        if welcome:
            info = await bot.api.users.get(invited_user)
            welcome = welcome.replace('%u', f'@id{invited_user}')
            welcome = welcome.replace('%n', f'@id{invited_user} ({info[0].first_name})')
            welcome = welcome.replace('%i', f'@id{user_id}')
            uinfo = await bot.api.users.get(user_id)
            welcome = welcome.replace('%p', f'@id{user_id} ({uinfo[0].first_name})')
            await message.answer(welcome)

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=GroupTypes.MessageEvent)
async def handlers(message: GroupTypes.MessageEvent):
    payload = message.object.payload
    command = str(payload.get("command")).lower()
    user_id = message.object.user_id
    chat_id = payload.get("chatId")
    if command == "nicksminus":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True
        page = payload.get("page")
        if page < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это первая страница!"})
            )
            return True

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nicksMinus", "page": page - 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nicksPlus", "page": page - 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        nicks_str = '\n'.join(await nlist(chat_id, page-1))
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"Пользователи с ником [{page-1} страница]:\n{nicks_str}\n\nПользователи без ников: «/nonick»", disable_mentions=1, random_id=0, keyboard=keyboard)

    if command == "nicksplus":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        page = payload.get("page")

        nicks = await nlist(chat_id, page + 1)
        if len(nicks) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return True

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nicksMinus", "page": page+1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nicksPlus", "page": page+1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        nicks_str = '\n'.join(nicks)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,message=f"Пользователи с ником [{page + 1} страница]:\n{nicks_str}\n\nПользователи без ников: «/nonick»",disable_mentions=1, random_id=0, keyboard=keyboard)

    if command == "nonicks":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        nonicks = await nonick(chat_id, 1)
        nonick_list = '\n'.join(nonicks)
        if nonick_list == "": nonick_list = "Пользователи без ников отсутствуют!"

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nonickMinus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("С никами", {"command": "nicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nonickPlus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000+chat_id, message=f"Пользователи без ников [1]:\n{nonick_list}\n\nПользователи с никами: «/nlist»", disable_mentions=1, random_id=0 ,keyboard=keyboard)

    if command == "nicks":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        nicks = await nlist(chat_id, 1)
        nick_list = '\n'.join(nicks)
        if nick_list == "": nick_list = "Ники отсутствуют!"

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nicksMinus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nicksPlus", "page": 1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000+chat_id, message=f"Пользователи с ником [1 страница]:\n{nick_list}\n\nПользователи без ников: «/nonick»",
                            disable_mentions=1, keyboard=keyboard, random_id=0)

    if command == "nonickminus":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        page = payload.get("page")
        if page < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это первая страница!"})
            )
            return True

        nonicks = await nonick(chat_id, 1)
        nonick_list = '\n'.join(nonicks)
        if nonick_list == "": nonick_list = "Пользователи без ников отсутствуют!"

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("⏪", {"command": "nonickMinus", "page": page+1, "chatId": chat_id}),
                 color=KeyboardButtonColor.NEGATIVE)
            .add(Callback("С никами", {"command": "nicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("⏩", {"command": "nonickPlus", "page": page+1, "chatId": chat_id}),
                 color=KeyboardButtonColor.POSITIVE)
        )

        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"Пользователи без ников [{page-1}]:\n{nonick_list}\n\nПользователи с никами: «/nlist»", disable_mentions=1, random_id=0, keyboard=keyboard)

    if command == "nonickplus":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True
        page = payload.get("page")
        nonicks = await nonick(chat_id, page+1)
        if len(nonicks) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Это последняя страница!"})
            )
            return True

        nonicks_str = '\n'.join(nonicks)
        await delete_message(message.group_id, message.object.peer_id, message.object.conversation_message_id)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"Пользователи без ников [{page + 1}]:\n{nonicks_str}\n\nПользователи с никами: «/nlist»",
                                    disable_mentions=1, random_id=0, keyboard=keyboard)

    if command == "clear":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")
        await clear(user, chat_id, message.group_id, 2000000000+chat_id)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000+chat_id, conversation_message_ids=message.object.conversation_message_id, group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x, conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) очистил(-а) сообщения", disable_mentions=1, random_id=0)

    if command == "unwarn":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")
        if await equals_roles(user_id, user, chat_id) < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Вы не можете снять пред данному пользователю!"})
            )
            return True

        await unwarn(chat_id, user)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,conversation_message_ids=message.object.conversation_message_id,group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x, conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) снял(-а) предупреждение @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1, random_id=0)

    if command == 'stats':
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")
        reg_data = await get_registration_date(user)
        info = await bot.api.users.get(user)
        role = await get_role(user, chat_id)
        warns = await get_warns(user, chat_id)
        if await is_nick(user, chat_id):
            nick = await get_nick(user, chat_id) or "Нет"
        else:
            nick = "Нет"
        messages = await message_stats(user, chat_id)

        roles = {0: "Пользователь", 1: "Модератор", 2: "Старший Модератор", 3: "Администратор",
                 4: "Старший Администратор", 5: "Владелец беседы", 6: "Менеджер бота"}

        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}), статистика @id{user} (пользователя):\nИмя и фамилия: {info[0].first_name} {info[0].last_name}\nДата регистрации: {reg_data}\nНик: {nick}\nРоль: {roles.get(role)}\nВсего предупреждений: {warns}/3\nВсего сообщений: {messages['count']}\nПоследнее сообщение: {messages['last']}", disable_mentions=1, random_id=0)

    if command == "activewarns":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")
        warns = await gwarn(user, chat_id)
        string_info = str
        if not warns: string_info = "Активных предупреждений нет!"
        else: string_info = f"@id{warns['moder']} (Модератор) | {warns['reason']} | {warns['count']}/3 | {warns['time']}"

        keyboard = (
            Keyboard(inline=True)
            .add(Callback("История предупреждений", {"command": "warnhistory", "user": user, "chatId": chat_id}),
                 color=KeyboardButtonColor.PRIMARY)
        )

        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}), информация о активных предупреждениях @id{user} (пользователя):\n{string_info}", disable_mentions=1, keyboard=keyboard, random_id=0)

    if command == "warnhistory":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")

        warnhistory_mass = await warnhistory(user, chat_id)
        if not warnhistory_mass:wh_string = "Предупреждений не было!"
        else:wh_string = '\n'.join(warnhistory_mass)

        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id, message=f"Информация о всех предупреждениях @id{user} ({await get_user_name(user, chat_id)})\nКоличество предупреждений пользователя: {await get_warns(user, chat_id)}\n\nИнформация о последних 10 предупреждений пользователя:\n{wh_string}",disable_mentions=1, random_id=0)

    if command == "unmute":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")

        if await get_role(user_id, chat_id) <= await get_role(user, chat_id):
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        await unmute(user, chat_id)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) размутил(-а) @id{user} ({await get_user_name(user, chat_id)})",
                                    disable_mentions=1, random_id=0)

    if command == "unban":
        if await get_role(user_id, chat_id) < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")
        if await equals_roles(user_id, user, chat_id) < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps(
                    {"type": "show_snackbar", "text": "Вы не можете снять бан данному пользователю!"})
            )
            return True

        await unban(user, chat_id)
        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) разблокировал(-а) @id{user} ({await get_user_name(user, chat_id)})",
                                    disable_mentions=1, random_id=0)

    if command == "kick":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        user = payload.get("user")
        if await equals_roles(user_id, user, chat_id) < 2:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps(
                    {"type": "show_snackbar", "text": "Вы не можете кикнуть данного пользователя!"})
            )
            return True

        try: await bot.api.messages.remove_chat_user(chat_id, user)
        except: pass

        x = await bot.api.messages.get_by_conversation_message_id(peer_id=2000000000 + chat_id,
                                                                  conversation_message_ids=message.object.conversation_message_id,
                                                                  group_id=message.group_id)
        x = json.loads(x.json())['items'][0]['text']
        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=x,
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)
        await bot.api.messages.send(peer_id=2000000000 + chat_id,
                                    message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) кикнул(-а) @id{user} ({await get_user_name(user, chat_id)})",
                                    disable_mentions=1, random_id=0)

    if command == "alt":
        if await get_role(user_id, chat_id) < 1:
            await bot.api.messages.send_message_event_answer(
                event_id=message.object.event_id,
                peer_id=message.object.peer_id,
                user_id=message.object.user_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Недостаточно прав!"})
            )
            return True

        commands_levels = {
            1: [
                '\nКоманды модераторов:',
                '/setnick — snick, nick, addnick, ник, сетник, аддник',
                '/removenick —  removenick, clearnick, cnick, рник, удалитьник, снятьник',
                '/getnick — gnick, гник, гетник',
                '/getacc — acc, гетакк, аккаунт, account',
                '/nlist — ники, всеники, nlist, nickslist, nicklist, nicks',
                '/nonick — nonicks, nonicklist, nolist, nnlist, безников, ноникс',
                '/kick — кик, исключить',
                '/warn — пред, варн, pred, предупреждение',
                '/unwarn — унварн, анварн, снятьпред, минуспред',
                '/getwarn — gwarn, getwarns, гетварн, гварн',
                '/warnhistory — historywarns, whistory, историяварнов, историяпредов',
                '/warnlist — warns, wlist, варны, варнлист',
                '/staff — стафф',
                '/reg — registration, regdate, рег, регистрация, датарегистрации',
                '/mute — мут, мьют, муте, addmute',
                '/unmute — снятьмут, анмут, унмут, снятьмут',
                '/alt — альт, альтернативные',
                '/getmute -- gmute, гмут, гетмут, чекмут',
                '/mutelist -- mutes, муты, мутлист',
                '/clear -- чистка, очистить, очистка',
                '/getban -- чекбан, гетбан, checkban',
                '/delete -- удалить'
            ],
            2: [
                '\nКоманды старших модераторов:',
                '/ban — бан, блокировка',
                '/unban -- унбан, снятьбан',
                '/addmoder -- moder',
                '/removerole -- rrole, снятьроль',
                '/zov - зов, вызов',
                '/online - ozov, озов',
                '/onlinelist - olist, олист',
                '/banlist - bans, банлист, баны',
                '/inactive - ilist, inactive',
                '/masskick - mkick'
            ],
            3: [
                '\nКоманды администраторов:',
                '/quiet -- silence, тишина',
                '/skick -- скик, снят',
                '/sban -- сбан',
                '/sunban — сунбан, санбан',
                '/addsenmoder — senmoder',
                '/rnickall -- allrnick, arnick, mrnick',
                '/sremovenick -- srnick',
                '/szov -- serverzov, сзов',
                '/srole -- prole, pullrole'
            ],
            4: [
                '\nКоманды старших администраторов:',
                '/addadmin -- admin',
                '/pullinfo -- pulli',
                '/banwords -- bws',
                '/filter -- none',
                '/sremoverole -- srrole'
            ],
            5: [
                '\nСписок команд владельца беседы',
                '/antiflood -- af',
                '/welcometext -- welcome, wtext',
                '/invite -- none',
                '/leave -- none',
                '/addsenadmin -- senadm, addsenadm, senadmin',
                '/setpull -- pull',
                '/setowner -- owner'
            ]
        }

        user_role = await get_role(user_id, chat_id)

        commands = []
        for i in commands_levels.keys():
            if i <= user_role:
                for b in commands_levels[i]:
                    commands.append(b)

        level_commands = '\n'.join(commands)

        await bot.api.messages.edit(peer_id=2000000000 + chat_id, message=f"Альтернативные команды\n\n{level_commands}",
                                    conversation_message_id=message.object.conversation_message_id, keyboard=None)


@bot.on.chat_message()
async def on_chat_message(message: Message):
    bot_identifiers = ['!', '+', '/']

    user_id = message.from_id
    chat_id = message.chat_id
    peer_id = message.peer_id
    # В VK могут приходить сообщения без текстового содержимого (вложения/события).
    if not message.text:
        return True

    arguments = message.text.split(' ')
    arguments_lower = message.text.lower().split(' ')

    try:
        command_identifier = arguments[0].strip()[0]
        command = arguments_lower[0][1:]
    except:
        command_identifier = " "
        command = " "

    if command_identifier in bot_identifiers:
        
        if command in ['gstaff', 'гстафф']:
            if await get_global_role(user_id) < 6:
                await message.reply("Недостаточно прав! Эта команда доступна глобальному персоналу.")
                return True
            sql.execute("SELECT user_id, level FROM global_managers ORDER BY level DESC, user_id ASC")
            global_staff = sql.fetchall()
            if not global_staff:
                await message.reply("🌐 Глобальный персонал пока отсутствует.")
                return True
            lines = ["🌐 ГЛОБАЛЬНЫЙ ПЕРСОНАЛ\n"]
            for staff_id, level in global_staff:
                try:
                    info = await bot.api.users.get(int(staff_id))
                    name = f"{info[0].first_name} {info[0].last_name}"
                except Exception:
                    name = "Пользователь"
                lines.append(f"{GLOBAL_ROLE_NAMES.get(level, 'Неизвестная роль')}\n👤 {name}\n🆔 ID: {staff_id}\n")
            await message.reply("\n".join(lines), disable_mentions=1)
            return True

        if command in ['grole', 'гроль']:
            actor_level = await get_global_role(user_id)
            if actor_level < 8:
                await message.reply("Недостаточно прав! Управлять глобальными ролями может Основатель или Заместитель.")
                return True
            target_id = None
            level_arg_index = 2
            if message.reply_message:
                target_id = int(message.reply_message.from_id)
                level_arg_index = 1
            elif len(arguments) > 1:
                resolved = await getID(arguments[1])
                if resolved:
                    target_id = int(resolved)
            if not target_id:
                await message.reply("Укажите пользователя: /grole @id123 7 (или ответьте на его сообщение).")
                return True
            if len(arguments) <= level_arg_index:
                await message.reply("Укажите уровень: 8 — Заместитель, 7 — Куратор, 6 — Менеджер, 0 — снять роль.")
                return True
            value = arguments[level_arg_index].lower()
            aliases = {"заместитель": 8, "куратор": 7, "менеджер": 6, "снять": 0, "удалить": 0}
            if value in aliases:
                new_level = aliases[value]
            elif value.isdigit():
                new_level = int(value)
            else:
                await message.reply("Неизвестный уровень. Доступны 8, 7, 6 или 0.")
                return True
            if new_level not in (0, 6, 7, 8):
                await message.reply("Допустимые уровни: 8 — Заместитель, 7 — Куратор, 6 — Менеджер, 0 — снять роль.")
                return True
            # Заместитель может назначать/снимать кураторов и менеджеров,
            # но не может назначать других заместителей или менять Основателя.
            if actor_level == 8 and new_level not in (0, 6, 7):
                await message.reply("Заместитель может назначать только Кураторов и Менеджеров.")
                return True
            target_level = await get_global_role(target_id)
            if actor_level <= target_level and target_id != user_id:
                await message.reply("Нельзя менять роль сотрудника с равным или более высоким уровнем.")
                return True
            if target_id == user_id and new_level == 0:
                await message.reply("Нельзя снять собственную глобальную роль этой командой.")
                return True
            ok, error = await set_global_role(user_id, target_id, new_level)
            if not ok:
                await message.reply(error)
                return True
            role_title = GLOBAL_ROLE_NAMES.get(new_level, "Без глобальной роли")
            await message.reply(f"✅ Глобальная роль пользователя @id{target_id} изменена: {role_title}.", disable_mentions=1)
            return True

        # Глобальные команды доступны независимо от активации бота в беседе.
        global_level = await get_global_role(user_id)
        if await is_global_banned(user_id):
            await message.reply("⛔ Ваш доступ к Black Manager ограничен глобальной блокировкой.")
            return True
        if await is_technical_mode() and global_level < 9 and command not in ("id", "ид"):
            await message.reply("🛠 Бот находится в техническом режиме. Попробуйте позже.")
            return True

        if command in ["gpanel", "ghelp", "гпанель", "гхелп"]:
            if global_level < 8:
                await message.reply("Панель доступна Заместителю и Основателю.")
                return True
            await message.reply(

"👑 Уровень 9 — Основатель
Полный контроль над ботом."

/gpanel — главная панель управления.

/gstaff — список глобальной администрации.

/grole — назначение и снятие глобальных ролей.

/glogs — просмотр журналов действий.

/gstats — глобальная статистика.

/gban — глобальная блокировка.

/gunban — снятие блокировки.

/gbanlist — список заблокированных.

/gbroadcast — глобальная рассылка.

/gbackup — резервная копия.

/gtech on/off — технический режим.

/gcheck, /gchecks, /gcheckdone — проверки.

/complaint, /complaints, /complaintdone — жалобы.

/gchats, /gchat — управление чатами.

/cpanel — панель чата.

🛡 Уровень 8 — Заместитель основателя
/gpanel
/gstaff
/glogs
/gstats
/gban
/gunban
/gbanlist
/gbroadcast
/gcheck
/gchecks
/gcheckdone
/complaints
/complaintdone
/gchats
/gchat
/cpanel

⚜️ Уровень 7 — Куратор
/gpanel
/gstaff
/gstats
/gcheck
/gchecks
/gcheckdone
/complaint
/complaints
/complaintdone
/gchats
/gchat

🔰 Уровень 6 — Менеджер
/gpanel
/gstats
/gcheck
/gchecks
/complaint
/complaints
/gchats
            )
            return True

        if command in ["cpanel", "curatorpanel", "кпанель", "панелькуратора"]:
            if global_level < 7:
                await message.reply("Панель доступна Куратору и старшим глобальным ролям.")
                return True
            await message.reply(
                "🛡 ПАНЕЛЬ КУРАТОРА\\n\\n"
                "/gstaff — персонал проекта\\n"
                
                "/gstats — статистика проекта\\n"
                
                "/gcheck @id заметка — открыть проверку\\n"
                
                "/gchecks — список открытых проверок\\n"
                
                "/gcheckdone ID — закрыть проверку\\n"
                
                "/complaints — обращения пользователей\\n"
                
                "/complaintdone ID ответ — закрыть обращение\\n"
                
                "/complaint текст — отправить обращение"
            )
            return True

        if command in ["gban", "гбан"]:
            if global_level < 8:
                await message.reply("Глобальную блокировку может выдавать Основатель или Заместитель.")
                return True
            target = None
            arg_i = 2 if message.reply_message else 1
            if message.reply_message:
                target = int(message.reply_message.from_id)
            elif len(arguments) > 1:
                target = await getID(arguments[1])
            reason = await get_string(arguments, arg_i)
            if not target or int(target) < 1 or not reason:
                await message.reply("Использование: /gban @id123 причина (или ответом на сообщение).")
                return True
            target = int(target)
            if target == FOUNDER_VK_ID or await get_global_role(target) >= global_level:
                await message.reply("Нельзя заблокировать Основателя или сотрудника с равной/старшей ролью.")
                return True
            sql.execute(
                "INSERT INTO global_bans(user_id, actor_id, reason, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET actor_id=excluded.actor_id, reason=excluded.reason, created_at=excluded.created_at",
                (target, user_id, reason, datetime.now().isoformat(timespec="seconds"))
            )
            database.commit()
            await global_log(user_id, "global_ban", f"user={target}; reason={reason}")
            await message.reply(f"⛔ Пользователь @id{target} глобально заблокирован. Причина: {reason}", disable_mentions=1)
            return True

        if command in ["gunban", "разгбан", "глобан"]:
            if global_level < 8:
                await message.reply("Недостаточно прав.")
                return True
            target = int(message.reply_message.from_id) if message.reply_message else (await getID(arguments[1]) if len(arguments) > 1 else 0)
            if not target:
                await message.reply("Использование: /gunban @id123")
                return True
            sql.execute("DELETE FROM global_bans WHERE user_id = ?", (int(target),))
            changed = sql.rowcount
            database.commit()
            await global_log(user_id, "global_unban", f"user={target}")
            await message.reply("✅ Глобальная блокировка снята." if changed else "У пользователя не было глобальной блокировки.")
            return True

        if command in ["gbanlist", "гбанлист"]:
            if global_level < 7:
                await message.reply("Недостаточно прав.")
                return True
            sql.execute("SELECT user_id, actor_id, reason, created_at FROM global_bans ORDER BY created_at DESC LIMIT 50")
            rows = sql.fetchall()
            if not rows:
                await message.reply("Глобальных блокировок нет.")
            else:
                await message.reply("⛔ ГЛОБАЛЬНЫЕ БЛОКИРОВКИ\\n" + "\\n".join(
                    f"ID {r[0]} • выдал: {r[1]} • {r[2]} • {r[3]}" for r in rows
                ), disable_mentions=1)
            return True

        if command in ["gbroadcast", "грассылка"]:
            if global_level < 8:
                await message.reply("Рассылку может запускать Основатель или Заместитель.")
                return True
            broadcast_text = await get_string(arguments, 1)
            if not broadcast_text:
                await message.reply("Укажите текст: /gbroadcast текст объявления")
                return True
            sql.execute("SELECT DISTINCT peer_id FROM chats")
            peers = [int(row[0]) for row in sql.fetchall() if row[0]]
            sent, failed = 0, 0
            await message.reply(f"Начинаю рассылку по {len(peers)} активным беседам.")
            for target_peer in peers:
                try:
                    await bot.api.messages.send(peer_id=target_peer, message="📢 ОБЪЯВЛЕНИЕ ПРОЕКТА\\n\\n" + broadcast_text, random_id=0)
                    sent += 1
                except Exception:
                    failed += 1
            await global_log(user_id, "broadcast", f"sent={sent}; failed={failed}")
            await message.reply(f"Рассылка завершена. Отправлено: {sent}; ошибок: {failed}.")
            return True

        if command in ["gchats", "гбеседы", "беседы"]:
            if global_level < 7:
                await message.reply("Список бесед доступен Куратору и старшим ролям.")
                return True
            sql.execute("SELECT chat_id, peer_id, owner_id FROM chats ORDER BY chat_id DESC LIMIT 50")
            rows = sql.fetchall()
            if not rows:
                await message.reply("Активированных бесед пока нет.")
            else:
                await message.reply("💬 АКТИВНЫЕ БЕСЕДЫ БОТА\\n" + "\\n".join(
                    f"Чат #{r[0]} • peer_id={r[1]} • владелец ID {r[2]}" for r in rows
                ), disable_mentions=1)
            return True

        if command in ["gchat", "гбеседа"]:
            if global_level < 7:
                await message.reply("Информация о беседах доступна Куратору и старшим ролям.")
                return True
            chat_arg = arguments[1] if len(arguments) > 1 else ""
            chat_num = int(chat_arg) if chat_arg.isdigit() else 0
            if not chat_num:
                await message.reply("Использование: /gchat ID_беседы")
                return True
            sql.execute("SELECT chat_id, peer_id, owner_id FROM chats WHERE chat_id=?", (chat_num,))
            row = sql.fetchone()
            if not row:
                await message.reply("Эта беседа не активирована в боте.")
                return True
            sql.execute(f"SELECT COUNT(*) FROM permissions_{chat_num}")
            moderators = sql.fetchone()[0]
            sql.execute(f"SELECT COUNT(*) FROM bans_{chat_num}")
            local_bans = sql.fetchone()[0]
            await message.reply(
                f"💬 ИНФОРМАЦИЯ О БЕСЕДЕ #{row[0]}\\npeer_id: {row[1]}\\n"
                f"Владелец ID: {row[2]}\\nНазначенных сотрудников: {moderators}\\n"
                f"Локальных банов: {local_bans}"
            )
            return True

        if command in ["gstats", "гстат"]:
            if global_level < 7:
                await message.reply("Недостаточно прав.")
                return True
            sql.execute("SELECT COUNT(*) FROM chats")
            chats_count = sql.fetchone()[0]
            sql.execute("SELECT COUNT(*) FROM global_managers")
            staff_count = sql.fetchone()[0]
            sql.execute("SELECT COUNT(*) FROM global_bans")
            bans_count = sql.fetchone()[0]
            sql.execute("SELECT COUNT(*) FROM global_complaints WHERE status='open'")
            complaints_count = sql.fetchone()[0]
            sql.execute("SELECT COUNT(*) FROM global_checks WHERE status='open'")
            checks_count = sql.fetchone()[0]
            await message.reply(
                "📊 СТАТИСТИКА BLACK MANAGER LITE\\n"
                f"Активированных бесед: {chats_count}\\nГлобальный персонал: {staff_count}\\n"
                f"Глобальные блокировки: {bans_count}\\nОткрытые обращения: {complaints_count}\\n"
                f"Открытые проверки: {checks_count}"
            )
            return True

        if command in ["glogs", "глоги"]:
            if global_level < 8:
                await message.reply("Журнал доступен Основателю и Заместителю.")
                return True
            sql.execute("SELECT actor_id, action, details, created_at FROM global_action_logs ORDER BY id DESC LIMIT 15")
            rows = sql.fetchall()
            sql.execute("SELECT actor_id, target_id, old_level, new_level, action, created_at FROM global_role_logs ORDER BY id DESC LIMIT 15")
            role_rows = sql.fetchall()
            lines = [f"{r[3]} | {r[1]} | ID {r[0]} | {r[2]}" for r in rows]
            lines.extend(
                f"{r[5]} | global_role_{r[4]} | actor={r[0]} target={r[1]} | {r[2]} -> {r[3]}"
                for r in role_rows
            )
            await message.reply("📜 ЖУРНАЛ ДЕЙСТВИЙ\\n" + ("\\n".join(lines[:25]) if lines else "Записей пока нет."), disable_mentions=1)
            return True

        if command in ["gbackup", "гбэкап", "backupglobal"]:
            if global_level < 8:
                await message.reply("Резервную копию может создавать Основатель или Заместитель.")
                return True
            backup_dir = BASE_DIR / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_file = backup_dir / f"database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_db = sqlite3.connect(str(backup_file))
            try:
                database.backup(backup_db)
            finally:
                backup_db.close()
            await global_log(user_id, "backup", str(backup_file.name))
            await message.reply(f"✅ Резервная копия создана: {backup_file.name}")
            return True

        if command in ["gtech", "гтех"]:
            if global_level < 9:
                await message.reply("Технический режим может переключать только Основатель.")
                return True
            mode = arguments[1].lower() if len(arguments) > 1 else ""
            if mode not in ("on", "off", "вкл", "выкл"):
                await message.reply("Использование: /gtech on или /gtech off")
                return True
            enabled = mode in ("on", "вкл")
            sql.execute(
                "INSERT INTO global_settings(key, value) VALUES ('technical_mode', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("1" if enabled else "0",)
            )
            database.commit()
            await global_log(user_id, "technical_mode", "on" if enabled else "off")
            await message.reply("🛠 Технический режим включён." if enabled else "✅ Технический режим выключен.")
            return True

        if command in ["gcheck", "гпроверка"]:
            if global_level < 7:
                await message.reply("Проверки доступны Куратору и старшим ролям.")
                return True
            target = int(message.reply_message.from_id) if message.reply_message else (await getID(arguments[1]) if len(arguments) > 1 else 0)
            note_index = 1 if message.reply_message else 2
            note = await get_string(arguments, note_index)
            if not target or not note:
                await message.reply("Использование: /gcheck @id123 причина или заметка.")
                return True
            sql.execute(
                "INSERT INTO global_checks(target_id, actor_id, note, created_at) VALUES (?, ?, ?, ?)",
                (int(target), user_id, note, datetime.now().isoformat(timespec="seconds"))
            )
            database.commit()
            await global_log(user_id, "check_open", f"target={target}; note={note}")
            await message.reply(f"🛡 Проверка #{sql.lastrowid} открыта для ID {target}.")
            return True

        if command in ["gchecks", "проверки"]:
            if global_level < 7:
                await message.reply("Недостаточно прав.")
                return True
            sql.execute("SELECT id, target_id, actor_id, note, created_at FROM global_checks WHERE status='open' ORDER BY id DESC LIMIT 30")
            rows = sql.fetchall()
            await message.reply("🛡 ОТКРЫТЫЕ ПРОВЕРКИ\\n" + ("\\n".join(
                f"#{r[0]} • пользователь {r[1]} • куратор {r[2]} • {r[3]} • {r[4]}" for r in rows
            ) if rows else "Открытых проверок нет."), disable_mentions=1)
            return True

        if command in ["gcheckdone", "проверказакрыть"]:
            if global_level < 7:
                await message.reply("Недостаточно прав.")
                return True
            check_id = int(arguments[1]) if len(arguments) > 1 and arguments[1].isdigit() else 0
            if not check_id:
                await message.reply("Использование: /gcheckdone ID")
                return True
            sql.execute("UPDATE global_checks SET status='closed', closed_at=? WHERE id=? AND status='open'",
                        (datetime.now().isoformat(timespec="seconds"), check_id))
            database.commit()
            await global_log(user_id, "check_close", f"id={check_id}")
            await message.reply("✅ Проверка закрыта." if sql.rowcount else "Открытая проверка не найдена.")
            return True

        if command in ["complaint", "жалоба"]:
            complaint_text = await get_string(arguments, 1)
            if not complaint_text:
                await message.reply("Опишите обращение: /complaint текст обращения")
                return True
            sql.execute(
                "INSERT INTO global_complaints(author_id, text, created_at) VALUES (?, ?, ?)",
                (user_id, complaint_text, datetime.now().isoformat(timespec="seconds"))
            )
            database.commit()
            complaint_id = sql.lastrowid
            await global_log(user_id, "complaint_created", f"id={complaint_id}")
            await message.reply(f"✅ Обращение #{complaint_id} принято. Персонал проекта рассмотрит его.")
            return True

        if command in ["complaints", "жалобы"]:
            if global_level < 7:
                await message.reply("Список обращений доступен Куратору и старшим ролям.")
                return True
            sql.execute("SELECT id, author_id, text, created_at FROM global_complaints WHERE status='open' ORDER BY id DESC LIMIT 30")
            rows = sql.fetchall()
            await message.reply("📨 ОТКРЫТЫЕ ОБРАЩЕНИЯ\\n" + ("\\n".join(
                f"#{r[0]} • автор {r[1]} • {r[2]} • {r[3]}" for r in rows
            ) if rows else "Открытых обращений нет."), disable_mentions=1)
            return True

        if command in ["complaintdone", "жалобазакрыть"]:
            if global_level < 7:
                await message.reply("Недостаточно прав.")
                return True
            complaint_id = int(arguments[1]) if len(arguments) > 1 and arguments[1].isdigit() else 0
            resolution = await get_string(arguments, 2)
            if not complaint_id or not resolution:
                await message.reply("Использование: /complaintdone ID ответ")
                return True
            sql.execute(
                "UPDATE global_complaints SET status='closed', assigned_to=?, resolution=?, closed_at=? "
                "WHERE id=? AND status='open'",
                (user_id, resolution, datetime.now().isoformat(timespec="seconds"), complaint_id)
            )
            database.commit()
            await global_log(user_id, "complaint_close", f"id={complaint_id}; resolution={resolution}")
            await message.reply("✅ Обращение закрыто." if sql.rowcount else "Открытое обращение не найдено.")
            return True

        # Технический режим и глобальные блокировки проверяются до локальных команд беседы.
        # Ниже продолжается исходная система прав и существующие команды.

        try: test_admin = await bot.api.messages.get_conversation_members(peer_id=message.peer_id)
        except:
            await message.reply("Бот не будет работать без звезды в беседе!", disable_mentions=1)
            return True

        if await check_chat(chat_id):
            if await get_mute(user_id, chat_id) and not await checkMute(chat_id, user_id):
                try: await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id, delete_for_all=True, cmids=message.conversation_message_id)
                except: pass
            elif await check_quit(chat_id) and await get_role(user_id, chat_id) < 1:
                try: await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id, delete_for_all=True, cmids=message.conversation_message_id)
                except: pass
            else:
                for i in await get_banwords(chat_id):
                    if i in message.text.lower() and await get_role(user_id, chat_id) < 1:
                        await mute(user_id, chat_id, 'Бот', 'Написание запрещенных слов', 30)
                        keyboard = (
                            Keyboard(inline=True)
                            .add(Callback("Снять мут", {"command": "unmute", "chatId": chat_id, "user": user_id}), color=KeyboardButtonColor.POSITIVE)
                        )
                        await message.reply(f"@id{user_id} (Пользователь) получил(-а) мут на 30 минут за написание запрещенного слова!")
                        try: await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,delete_for_all=True, cmids=message.conversation_message_id)
                        except: pass
                        return True


        if command in ['start', 'старт', 'активировать']:
            if await check_chat(chat_id):
                await message.reply("Бот уже активирован!", disable_mentions=1)
                return True
            try:
                x = await bot.api.messages.get_conversations_by_id(peer_ids=peer_id, extended=1,fields='chat_settings', group_id=message.group_id)
                x = json.loads(x.json())
                for i in x['items']: owner = int(i["chat_settings"]["owner_id"])
                if not owner == user_id:
                    await message.reply("Включить бота может только создатель беседы!", disable_mentions=1)
                    return True
                await new_chat(chat_id, peer_id, user_id)
                await message.reply("Бот успешно запущен!\nДля того, чтобы начать пользоваться им, напишите /help!", disable_mentions=1)
            except Exception as ex:
                await message.reply(f"Вы не выдали звезду боту!", disable_mentions=1)
                return True

        if not await check_chat(chat_id): return True

        if command in ['id', 'ид', 'getid', 'гетид', 'получитьид', 'giveid']:
            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                user = user_id
            if user < 0:
                await message.reply(f"Оригинальная ссылка [club{abs(user)}|сообщества]:\nhttps://vk.com/club{abs(user)}",disable_mentions=1)
                return True
            await message.reply(f"Оригинальная ссылка @id{user} (пользователя):\nhttps://vk.com/id{user}", disable_mentions=1)

        if message.reply_message and message.reply_message.from_id < 0:
            return True

        if command in ['stats', 'стата', 'статистика', 'stata', 'statistic']:
            user = int

            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0: user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else: user = user_id

            if user < 0:
                await message.reply("Нельзя взаимодействовать с сообществом!")
                return True

            reg_data = await get_registration_date(user)
            info = await bot.api.users.get(user)
            role = await get_role(user, chat_id)
            warns = await get_warns(user, chat_id)
            if await is_nick(user, chat_id): nick = await get_nick(user, chat_id) or "Нет"
            else: nick = "Нет"
            messages = await message_stats(user, chat_id)

            roles = {0: "Пользователь", 1: "Модератор", 2: "Старший Модератор", 3: "Администратор", 4: "Старший Администратор", 5: "Владелец беседы", 6: "Менеджер бота"}

            await message.reply(f"@id{user_id} ({await get_user_name(user_id, chat_id)}), статистика @id{user} (пользователя):\nИмя и фамилия: {info[0].first_name} {info[0].last_name}\nДата регистрации: {reg_data}\nНик: {nick}\nРоль: {roles.get(role)}\nВсего предупреждений: {warns}/3\nВсего сообщений: {messages['count']}\nПоследнее сообщение: {messages['last']}", disable_mentions=1)

        if command in ['help', 'помощь', 'хелп', 'команды', 'commands']:
            commands_levels = {
                0: [
                    'Команды пользователей:',
                    '/help — список доступных вам команд',
                    '/stats — информация о пользователе',
                    '/getid — узнать оригинальный ID пользователя в ВК'
                ],
                1: [
                    '\nКоманды модераторов:',
                    '/setnick — сменить ник у пользователя',
                    '/removenick — очистить ник у пользователя',
                    '/getnick — проверить ник пользователя',
                    '/getacc — узнать пользователя по нику',
                    '/nlist — просмотреть ники пользователей',
                    '/nonick — пользователи без ников',
                    '/kick — исключить пользователя из беседы',
                    '/warn — выдать предупреждение пользователю',
                    '/unwarn — снять предупреждение пользователю',
                    '/getwarn — информация о активных предупреждениях пользователя',
                    '/warnhistory — информация о всех предупреждениях пользователя',
                    '/warnlist — список пользователей с варном',
                    '/staff — пользователи с ролями',
                    '/reg — узнать дату регистрации пользователя',
                    '/mute — замутить пользователя',
                    '/unmute — размутить пользователя',
                    '/alt — узнать альтернативные команды',
                    '/getmute -- информация о муте пользователя',
                    '/mutelist -- список пользователей с мутом',
                    '/clear -- очистить сообщения',
                    '/getban -- информация о банах пользователя',
                    '/delete -- удалить сообщение пользователя'
                ],
                2: [
                    '\nКоманды старших модераторов:',
                    '/ban — заблокировать пользователя в беседе',
                    '/unban -- разблокировать пользователя в беседе',
                    '/addmoder -- выдать пользователю модератора',
                    '/removerole -- забрать роль у пользователя',
                    '/zov -- упомянуть всех пользователей',
                    '/online -- упомянуть пользователей онлайн',
                    '/onlinelist — посмотреть пользователей в онлайн',
                    '/banlist -- посмотреть заблокированных',
                    '/inactivelist -- список неактивных пользователей',
                    '/masskick -- исключить нескольких пользователей'
                ],
                3: [
                    '\nСписок команд администраторов:',
                    '/quiet -- Включить выключить режим тишины',
                    '/skick -- исключить пользователя с бесед сетки',
                    '/sban -- заблокировать пользователя в сетке бесед',
                    '/sunban — разбанить пользователя в сетке бесед',
                    '/addsenmoder — дать пользователю роль старшего модератора',
                    '/rnickall -- очистить все ники в беседе',
                    '/sremovenick -- очистить ник у пользователя в сетке бесед',
                    '/szov -- вызов участников бесед сетки',
                    '/srole -- выдать права в сетке бесед'
                ],
                4: [
                    '\nСписок команд старших администраторов:',
                    '/addadmin -- дать пользователю роль администратора',
                    '/pullinfo -- информация о сетке бесед',
                    '/banwords -- запрещенные в беседе слова',
                    '/filter -- фильтр запрещенных слов',
                    '/sremoverole -- забрать роль у пользователя в сетке бесед'
                ],
                5: [
                    '\nСписок команд владельца беседы:',
                    '/antiflood -- режим защиты от спама',
                    '/welcometext -- текст приветствия',
                    '/invite -- система добавления пользователей только модераторами',
                    '/leave -- система исключения пользователей при выходе',
                    '/addsenadmin -- дать пользователю роль старшего администратора',
                    '/setpull -- изменить сетку бесед',
                    '/editowner -- передать права владельца беседы',
                    '/masskick all/все -- исключить участников без ролей'
                ],
                6: [
                    '\nСписок команд менеджеров бота:',
                    '/news -- сообщение во все беседы'
                ]
            }

            user_role = await get_role(user_id, chat_id)

            if user_role > 1:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Альтернативные команды", {"command": "alt", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
                )
            else:
                keyboard = None

            commands = []
            for i in commands_levels.keys():
                if i <= user_role:
                    for b in commands_levels[i]:
                        commands.append(b)

            level_commands = '\n'.join(commands)

            await message.reply(f"{level_commands}", disable_mentions=1, keyboard=keyboard)

        if command in ['snick', 'setnick', 'nick', 'addnick', 'ник', 'сетник', 'аддник']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!")
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) == 0:
                await message.reply("Вы не можете установить ник данному пользователю!", disable_mentions=1)
                return True

            new_nick = await get_string(arguments, arg)
            if not new_nick:
                await message.reply("Укажите ник пользователя!", disable_mentions=1)
                return True
            else: await setnick(user, chat_id, new_nick)

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) установил новое имя @id{user} (пользователю)!\nНовый ник: {new_nick}", disable_mentions=1)

        if command in ['rnick', 'removenick', 'clearnick', 'cnick', 'рник', 'удалитьник', 'снятьник']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) == 0:
                await message.reply("Вы не можете удалить ник данному пользователю!", disable_mentions=1)
                return True

            await rnick(user, chat_id)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) убрал(-а) ник у @id{user} (пользователя)!", disable_mentions=1)

        if command in ['getacc', 'acc', 'гетакк', 'аккаунт', 'account']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            nick = await get_string(arguments, 1)
            if not nick:
                await message.reply("Укажите ник!", disable_mentions=1)
                return True

            nick_result = await get_acc(chat_id, nick)

            if not nick_result: await message.reply(f"Ник {nick} никому не принадлежит!", disable_mentions=1)
            else:
                info = await bot.api.users.get(nick_result)
                await message.reply(f"Ник {nick} принадлежит @id{nick_result} ({info[0].first_name} {info[0].last_name})", disable_mentions=1)

        if command in ['getnick', 'gnick', 'гник', 'гетник']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = 0
            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            nick = await get_nick(user, chat_id)
            if not nick: await message.reply(f"У данного @id{user} (пользователя) нет ника!", disable_mentions=1)
            else: await message.reply(f"Ник данного @id{user} (пользователя): {nick}", disable_mentions=1)

        if command in ['никлист', 'ники', 'всеники', 'nlist', 'nickslist', 'nicklist', 'nicks']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            nicks = await nlist(chat_id, 1)
            nick_list = '\n'.join(nicks)
            if nick_list == "": nick_list = "Ники отсутствуют!"

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "nicksMinus", "page": 1, "chatId": chat_id}), color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("Без ников", {"command": "nonicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
                .add(Callback("⏩", {"command": "nicksPlus", "page": 1, "chatId": chat_id}), color=KeyboardButtonColor.POSITIVE)
            )

            await message.reply(f"Пользователи с ником [1 страница]:\n{nick_list}\n\nПользователи без ников: «/nonick»", disable_mentions=1, keyboard=keyboard)

        if command in ['nonick', 'nonicks', 'nonicklist', 'nolist', 'nnlist', 'безников', 'ноникс']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            nonicks = await nonick(chat_id, 1)
            nonick_list = '\n'.join(nonicks)
            if nonick_list == "": nonick_list = "Пользователи без ников отсутствуют!"

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("⏪", {"command": "nonickMinus", "page": 1, "chatId": chat_id}), color=KeyboardButtonColor.NEGATIVE)
                .add(Callback("С никами", {"command": "nicks", "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
                .add(Callback("⏩", {"command": "nonickPlus", "page": 1, "chatId": chat_id}),
                     color=KeyboardButtonColor.POSITIVE)
            )

            await message.reply(f"Пользователи без ников [1]:\n{nonick_list}\n\nПользователи с никами: «/nlist»", disable_mentions=1, keyboard=keyboard)

        if command in ['kick', 'кик', 'исключить']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете исключить данного пользователя!", disable_mentions=1)
                return True

            reason = await get_string(arguments, arg)

            try: await bot.api.messages.remove_chat_user(chat_id, user)
            except:
                await message.reply(f"Не удается исключить данного @id{user} (пользователя)! Необходимо забрать у него звезду.", disable_mentions=1)
                return True

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}), color=KeyboardButtonColor.NEGATIVE)
            )

            if not reason: await message.reply(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) кикнул(-а) @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1, keyboard=keyboard)
            else: await message.reply(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) кикнул(-а) @id{user} ({await get_user_name(user, chat_id)})\nПричина: {reason}", disable_mentions=1, keyboard=keyboard)

            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['warn', 'пред', 'варн', 'pred', 'предупреждение']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать пред данному пользователю!", disable_mentions=1)
                return True

            reason = await get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину предупреждения!")
                return True

            warns = await warn(chat_id, user, user_id, reason)
            if warns < 3:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Снять варн", {"command": "unwarn", "user": user, "chatId": chat_id}), color=KeyboardButtonColor.POSITIVE)
                    .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}), color=KeyboardButtonColor.NEGATIVE)
                )
                await message.reply(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) предупреждение @id{user} ({await get_user_name(user, chat_id)})\nПричина: {reason}\nКоличество предупреждений: {warns}", disable_mentions=1, keyboard=keyboard)
            else:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}),color=KeyboardButtonColor.NEGATIVE)
                )
                await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) последнее предупреждение @id{user} ({await get_user_name(user, chat_id)}) (3/3)\nПричина: {reason}\n@id{user} (Пользователь) был исключен за большое количество предупреждений!",disable_mentions=1, keyboard=keyboard)
                try: await bot.api.messages.remove_chat_user(user)
                except: pass
                await clear_warns(chat_id, user)

            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['unwarn', 'унварн', 'анварн', 'снятьпред', 'минуспред']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете снять пред данному пользователю!", disable_mentions=1)
                return True

            if await get_warns(user, chat_id) < 1:
                await message.reply("У пользователя нет предупреждений!")
                return True

            warns = await unwarn(chat_id, user)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) снял(-а) предупреждение @id{user} ({await get_user_name(user, chat_id)})\nКоличество предупреждений: {warns}", disable_mentions=1)

        if command in ['getwarn', 'gwarn', 'getwarns', 'гетварн', 'гварн']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Вы не указали @пользователя!", disable_mentions=1)
                return True

            warns = await gwarn(user, chat_id)
            string_info = str
            if not warns: string_info = "Активных предупреждений нет!"
            else: string_info = f"@id{warns['moder']} (Модератор) | {warns['reason']} | {warns['count']}/3 | {warns['time']}"

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("История предупреждений", {"command": "warnhistory", "user": user, "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            )

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}), информация о активных предупреждениях @id{user} (пользователя):\n{string_info}", disable_mentions=1, keyboard=keyboard)

        if command in ['warnhistory', 'historywarns', 'whistory', 'историяварнов', 'историяпредов']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            warnhistory_mass = await warnhistory(user, chat_id)
            if not warnhistory_mass: wh_string = "Предупреждений не было!"
            else: wh_string = '\n'.join(warnhistory_mass)

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Активные предупреждения", {"command": "activeWarns", "user": user, "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
                .add(Callback("Вся информация", {"command": "stats", "user": user, "chatId": chat_id}),color=KeyboardButtonColor.PRIMARY)
            )

            await message.reply(f"Информация о всех предупреждениях @id{user} ({await get_user_name(user, chat_id)})\nКоличество предупреждений пользователя: {await get_warns(user, chat_id)}\n\nИнформация о последних 10 предупреждений пользователя:\n{wh_string}", disable_mentions=1, keyboard=keyboard)

        if command in ['warnlist', 'warns', 'wlist', 'варны', 'варнлист']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            warns = await warnlist(chat_id)
            if warns == False: warns_string = "Пользователей с предупреждениями нет!"
            else: warns_string = '\n'.join(warns)

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}), список пользователей с варнами:\n{warns_string}", disable_mentions=1)

        if command in ['staff', 'стафф']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            staff_mass = await staff(chat_id)

            if staff_mass == None: staff_str = "В данной беседе нет пользователей с ролями!"
            else:
                moders = '\n'.join(staff_mass['moders'])
                stmoders = '\n'.join(staff_mass['stmoders'])
                admins = '\n'.join(staff_mass['admins'])
                stadmins = '\n'.join(staff_mass['stadmins'])

                x = await bot.api.messages.get_conversations_by_id(peer_ids=peer_id, extended=1, fields='chat_settings',group_id=message.group_id)
                x = json.loads(x.json())
                for i in x['items']: owner = int(i["chat_settings"]["owner_id"])

                if owner < 1: owner = f"[club{abs(owner)}|Сообщество]"
                else: owner = f"@id{owner} ({await get_user_name(owner, chat_id)})"

                await message.reply(f"Владелец беседы:\n{owner} - ⭐️\n\nСтаршие администраторы:\n{stadmins}\n\nАдмнистраторы:\n{admins}\n\nСтаршие модераторы:\n{stmoders}\n\nМодераторы:\n{moders}", disable_mentions=1)

        if command in ['reg', 'registration', 'regdate', 'рег', 'регистрация', 'датарегистрации']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):user = await getID(arguments[1])
            else: user = user_id

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Вся информация", {"command": "stats", "user": user, "chatId": chat_id}), color=KeyboardButtonColor.PRIMARY)
            )
            await message.reply(f"Дата регистрации @id{user} (пользователя): {await get_registration_date(user)}", disable_mentions=1, keyboard=keyboard)

        if command in ['mute', 'мут', 'мьют', 'муте', 'addmute']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 2
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 2
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 3
            else:
                await message.reply("Укажите пользователя!")
                return True

            if len(arguments) < 4 and arg == 3:
                await message.reply("Укажите аргументы команды!")
                return True

            if len(arguments) < 3 and arg == 2:
                await message.reply("Укажите аргументы команды!")
                return True

            await checkMute(chat_id, user)

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать мут данному пользователю!", disable_mentions=1)
                return True

            if await get_mute(user, chat_id):
                await message.reply("Пользователь уже замьючен!")
                return True

            reason = await get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину предупреждения!")
                return True

            if arg == 3: mute_time = arguments[2]
            else: mute_time = arguments[1]
            try: mute_time = int(mute_time)
            except:
                await message.reply("Укажите время в минутах!")
                return True


            if mute_time < 1 or mute_time > 1000:
                await message.reply("Время не должно превышать 1000, и быть не менее 0!")
                return True

            await mute(user, chat_id, user_id, reason, mute_time)

            do_time = datetime.now() + timedelta(minutes=mute_time)
            mute_time = str(do_time).split('.')[0]


            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять мут", {"command": "unmute", "user": user, "chatId": chat_id}), color=KeyboardButtonColor.POSITIVE)
                .add(Callback("Очистить", {"command": "clear", "chatId": chat_id, "user": user}), color=KeyboardButtonColor.NEGATIVE)
            )

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) замутил(-а) @id{user} ({await get_user_name(user, chat_id)})\nПричина: {reason}\nМут выдан до: {mute_time}", disable_mentions=1, keyboard=keyboard)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['unmute', 'снятьмут', 'анмут', 'анмьют', 'унмут']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            await checkMute(chat_id, user)

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете снять мут данному пользователю!", disable_mentions=1)
                return True

            if not await get_mute(user, chat_id):
                await message.reply(f"У @id{user} (пользователя) нет мута!", disable_mentions=1)
                return True

            await unmute(user, chat_id)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) размутил(-а) @id{user} ({await get_user_name(user, chat_id)})")

        if command in ['getmute', 'gmute', 'гмут', 'гетмут', 'чекмут']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            await checkMute(chat_id, user)

            mute_string = str
            gmute = await get_mute(user, chat_id)
            if not gmute: mute_string = "У пользователя нет мута!"
            else:
                do_time = datetime.fromisoformat(gmute['date']) + timedelta(minutes=gmute['time'])
                mute_time = str(do_time).split('.')[0]

                try:
                    int(gmute['moder'])
                    mute_string = f"@id{gmute['moder']} (Модератор) | {gmute['reason']} | {gmute['date']} | До: {mute_time}"
                except: mute_string = f"Бот | {gmute['reason']} | {gmute['date']} | До: {mute_time}"

            await message.reply(f"Информация о муте @id{user} ({await get_user_name(user, chat_id)}):\n\n{mute_string}", disable_mentions=1)

        if command in ['mutelist', 'mutes', 'муты', 'мутлист']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            mutes = await mutelist(chat_id)
            if not mutes: mutes_str = ""
            else:
                mutes_str = '\n'.join(mutes)

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}), список пользователей с мутами:\n{mutes_str}", disable_mentions=1)

        if command in ['clear', 'чистка', 'очистить', 'очистка']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете очистить сообщения данного пользователя!", disable_mentions=1)
                return True

            await clear(user, chat_id, message.group_id, message.peer_id)
            await message.reply(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) очистил(-а) сообщение(-я)!")

        if command in ['alt', 'альт', 'альтернативные']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            commands_levels = {
                1: [
                    '\nКоманды модераторов:',
                    '/setnick — snick, nick, addnick, ник, сетник, аддник',
                    '/removenick —  removenick, clearnick, cnick, рник, удалитьник, снятьник',
                    '/getnick — gnick, гник, гетник',
                    '/getacc — acc, гетакк, аккаунт, account',
                    '/nlist — ники, всеники, nlist, nickslist, nicklist, nicks',
                    '/nonick — nonicks, nonicklist, nolist, nnlist, безников, ноникс',
                    '/kick — кик, исключить',
                    '/warn — пред, варн, pred, предупреждение',
                    '/unwarn — унварн, анварн, снятьпред, минуспред',
                    '/getwarn — gwarn, getwarns, гетварн, гварн',
                    '/warnhistory — historywarns, whistory, историяварнов, историяпредов',
                    '/warnlist — warns, wlist, варны, варнлист',
                    '/staff — стафф',
                    '/reg — registration, regdate, рег, регистрация, датарегистрации',
                    '/mute — мут, мьют, муте, addmute',
                    '/unmute — снятьмут, анмут, унмут, снятьмут',
                    '/alt — альт, альтернативные',
                    '/getmute -- gmute, гмут, гетмут, чекмут',
                    '/mutelist -- mutes, муты, мутлист',
                    '/clear -- чистка, очистить, очистка',
                    '/getban -- чекбан, гетбан, checkban',
                    '/delete -- удалить'
                ],
                2: [
                    '\nКоманды старших модераторов:',
                    '/ban — бан, блокировка',
                    '/unban -- унбан, снятьбан',
                    '/addmoder -- moder',
                    '/removerole -- rrole, снятьроль',
                    '/zov - зов, вызов',
                    '/online - ozov, озов',
                    '/onlinelist - olist, олист',
                    '/banlist - bans, банлист, баны',
                    '/inactive - ilist, inactive',
                    '/masskick - mkick'
                ],
                3: [
                    '\nКоманды администраторов:',
                    '/quiet -- silence, тишина',
                    '/skick -- скик, снят',
                    '/sban -- сбан',
                    '/sunban — сунбан, санбан',
                    '/addsenmoder — senmoder',
                    '/rnickall -- allrnick, arnick, mrnick',
                    '/sremovenick -- srnick',
                    '/szov -- serverzov, сзов',
                    '/srole -- prole, pullrole'
                ],
                4: [
                    '\nКоманды старших администраторов:',
                    '/addadmin -- admin',
                    '/pullinfo -- pulli',
                    '/banwords -- bws',
                    '/filter -- none',
                    '/sremoverole -- srrole'
                ],
                5: [
                    '\nСписок команд владельца беседы',
                    '/antiflood -- af',
                    '/welcometext -- welcome, wtext',
                    '/invite -- none',
                    '/leave -- none',
                    '/addsenadmin -- senadm, addsenadm, senadmin',
                    '/setpull -- pull',
                    '/editowner -- owner, setowner'
                ]
            }

            user_role = await get_role(user_id, chat_id)

            commands = []
            for i in commands_levels.keys():
                if i <= user_role:
                    for b in commands_levels[i]:
                        commands.append(b)

            level_commands = '\n'.join(commands)

            await message.reply(f"Альтернативные команды\n\n{level_commands}", disable_mentions=1)

        if command in ['getban', 'чекбан', 'гетбан', 'checkban']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            getban = await checkban(user, chat_id)
            if not getban: getban_str = "Блокировок нет!"
            else: getban_str = f"@id{getban['moder']} (Модератор) | {getban['reason']} | {getban['date']}"

            await message.reply(f"Информация о блокировках @id{user} ({await get_user_name(user, chat_id)}):\n\n{getban_str}", disable_mentions=1)

        if command in ['ban', 'бан', 'блокировка']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать бан данному пользователю!", disable_mentions=1)
                return True

            reason = await get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину бана!")
                return True

            if await checkban(user, chat_id):
                await message.reply("Пользователь уже заблокирован в этой беседе!")
                return True

            await ban(user, user_id, chat_id, reason)

            try: await bot.api.messages.remove_chat_user(chat_id, user)
            except: pass

            keyboard = (
                Keyboard(inline=True)
                .add(Callback("Снять бан", {"command": "unban", "user": user, "chatId": chat_id}), color=KeyboardButtonColor.POSITIVE)
            )

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) заблокировал(-а) @id{user} ({await get_user_name(user, chat_id)})\nПричина: {reason}", disable_mentions=1, keyboard=keyboard)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['unban', 'унбан', 'снятьбан']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            getban = await checkban(user, chat_id)
            if not getban:
                await message.reply("Пользователь не заблокирован в этой беседе")
                return True

            if await equals_roles(user_id, getban['moder'], chat_id) < 1:
                await message.reply("Вы не можете снять бан данному пользователю, т.к. его заблокировал человек с уровнем прав выше!", disable_mentions=1)
                return True

            await unban(user, chat_id)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) разблокировал(-а) @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1)

        if command in ['addmoder', 'moder']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 1)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) права модератора @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['removerole', 'rrole', 'снятьроль']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 0)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) забрал(-а) роль у @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['zov', 'зов', 'вызов']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = await get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True

            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id, fields=["online_info", "online"])
            users = json.loads(users.json())
            user_f = []
            gi = 0
            for i in users["profiles"]:
                if not i['id'] == user_id:
                    gi = gi + 1
                    if gi <= 100:
                        user_f.append(f"@id{i['id']} (🖤)")
            zov_users = ''.join(user_f)

            await message.answer(f"🔔 Вы были вызваны @id{user_id} (администратором) беседы\n\n{zov_users}\n\n❗ Причина вызова: {reason}")

        if command in ['ozov', 'online', 'озов']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = await get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True

            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id, fields=["online_info", "online"])
            users = json.loads(users.json())
            online_users = []
            gi = 0
            for i in users["profiles"]:
                if i["online"] == 1:
                    if not i['id'] == user_id:
                        gi = gi + 1
                        if gi <= 100:
                            online_users.append(f"@id{i['id']} (♦️)")

            online_zov = "".join(online_users)
            await message.answer(f"🔔 Вы были вызваны @id{user_id} (администратором) беседы\n\n{online_zov}\n\n❗ Причина вызова: {reason}")

        if command in ['onlinelist', 'olist', 'олист']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id, fields=["online", "online_info"])
            users = json.loads(users.json())
            online_users = []
            gi = 0
            for i in users["profiles"]:
                if i["online"] == 1:
                    if not i['id'] == user_id:
                        gi = gi + 1
                        if gi <= 80:
                            if i["online_info"]["is_mobile"] == False:
                                online_users.append(f"@id{i['id']} ({await get_user_name(i['id'], chat_id)}) -- 💻")
                            else:
                                online_users.append(f"@id{i['id']} ({await get_user_name(i['id'], chat_id)}) -- 📱")

            olist_users = "\n".join(online_users)
            await message.reply(f"@id{user_id} ({await get_user_name(user_id, chat_id)}), cписок пользователей онлайн\n\n{olist_users}\n\nВсего в онлайн: {gi}", disable_mentions=1)

        if command in ['banlist', 'bans', 'банлист', 'баны']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            bans = await banlist(chat_id)
            bans_do = []
            gi = 0
            for i in bans:
                gi = gi + 1
                if gi <= 10:
                    bans_do.append(i)
            bans_str = "\n".join(bans_do)

            await message.reply(f"Информация о последних 10 блокировках в беседе:\n\n{bans_str}\n\nВсего блокировок: {gi}", disable_mentions=1)

        if command in ['delete', 'удалить']:
            if await get_role(user_id, chat_id) < 1:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if not message.reply_message:
                await message.reply("Чтобы удалить сообщение, нужно ответить на него!")
                return True

            cmid = message.reply_message.conversation_message_id
            user = message.reply_message.from_id

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете удалить сообщение данного пользователя!", disable_mentions=1)
                return True

            try: await bot.api.messages.delete(group_id=message.group_id, peer_id=peer_id, delete_for_all=True, cmids=cmid)
            except: pass

            try: await bot.api.messages.delete(group_id=message.group_id, peer_id=peer_id, delete_for_all=True, cmids=message.conversation_message_id)
            except: pass

        if command in ['inactivelist', 'inactive', 'ilist']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,fields=["online_info", "online", "last_seen"])
            users = json.loads(users.json())
            unactive_users_day = []
            count_uad = 0
            unactive_users_moon = []
            count_uam = 0
            for i in users["profiles"]:
                try:
                    import time
                    currency_time = time.time()
                    time_seen = i['last_seen']['time']
                    last_seen_device_list = {1: "📱", 2: "📱", 3: "📱", 4: "📱", 5: "📱", 6: "💻", 7: "💻"}
                    last_seen_device = last_seen_device_list.get(i['last_seen']['platform'])
                    if time_seen <= currency_time - 604800:
                        count_uam = count_uam + 1
                        if count_uam <= 30:
                            info = await bot.api.users.get(i['id'])
                            unactive_users_moon.append(
                                f"{count_uam}) @id{i['id']} ({info[0].first_name} {info[0].last_name}) -- {last_seen_device}")
                    elif time_seen <= currency_time - 86400:
                        count_uad = count_uad + 1
                        if count_uad <= 30:
                            info = await bot.api.users.get(i['id'])
                            unactive_users_day.append(
                                f"{count_uad}) @id{i['id']} ({info[0].first_name} {info[0].last_name}) -- {last_seen_device}")
                except:
                    pass
            uad = "\n".join(unactive_users_day)
            uam = "\n".join(unactive_users_moon)
            await message.reply(f"Список неактивных пользователей [Более недели]\n{uam}\n\nБолее дня\b{uad}", disable_mentions=1)

        if command in ['mkick', 'мкик', 'masskick']:
            if await get_role(user_id, chat_id) < 2:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) <= 1:
                await message.reply("Укажите пользователя(-ей)", disable_mentions=1)
                return True
            if len(arguments) >= 30:
                await message.reply("Не более 30 пользователей!", disable_mentions=1)
                return True

            if arguments[1] in ['all', 'все']:
                if await get_role(user_id, chat_id) < 5:
                    await message.reply("Недостаточно прав!", disable_mentions=1)
                    return True

                users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id,
                                                                        fields=["online_info", "online"])
                users = json.loads(users.json())
                user_f = []
                gi = 0
                for i in users["profiles"]:
                    if not i['id'] == user_id and await get_role(i['id'], chat_id) <= 0:
                        await bot.api.messages.remove_chat_user(chat_id, int(i['id']))

                await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) пользователей без ролей", disable_mentions=1)
                return True


            do_users = []
            for i in range(len(arguments)):
                if i <= 0:
                    pass
                else:
                    do_users.append(arguments[i])
            users = []
            for i in do_users:
                idp = await getID(i)
                if idp:
                    users.append(idp)
            kick_users_list = []
            for i in users:
                if await equals_roles(user_id, i, chat_id) < 2:
                    await message.answer(f"У @id{i} уровень прав выше!", disable_mentions=1)
                else:
                    try:
                        await bot.api.messages.remove_chat_user(chat_id, i)
                        info = await bot.api.users.get(int(i))
                        kick_users_list.append(f"@id{i} ({info[0].first_name})")
                    except:
                        pass
            kick_users = ", ".join(kick_users_list)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил пользователей: {kick_users}", disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['quiet', 'silence', 'тишина']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            silence = await quiet(chat_id)
            if silence: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) включил(-а) режим тишины!")
            else: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выключил(-а) режим тишины!")

        if command in ['skick', 'снят', 'скик']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете исключить данного пользователя!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /pull <число>")
                return True

            reason = await get_string(arguments, arg)

            for i in pull:
                try:
                    await bot.api.messages.remove_chat_user(i, user)
                    if reason:
                        await bot.api.messages.send(peer_id=2000000000+i, message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед\nПричина: {reason}", disable_mentions=1, random_id=0)
                    else:
                        await bot.api.messages.send(peer_id=2000000000 + i,message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед",disable_mentions=1, random_id=0)
                except:
                    if i == chat_id:
                        try:
                            if reason: await bot.api.messages.send(peer_id=2000000000 + i,message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед\nПричина: {reason}",disable_mentions=1, random_id=0)
                            else:
                                await bot.api.messages.send(peer_id=2000000000 + i,message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед",disable_mentions=1, random_id=0)
                        except: pass
            if not chat_id in pull: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед",disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['sban', 'сбан']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 0
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif message.fwd_messages and message.fwd_messages[0].from_id > 0:
                user = message.fwd_messages[0].from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
                arg = 2
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете заблокировать данного пользователя!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /pull <число>")
                return True

            reason = await get_string(arguments, arg)
            if not reason:
                await message.reply("Укажите причину блокировки!")
                return True

            for i in pull:
                try:
                    await ban(user, user_id, i, reason)
                    await bot.api.messages.remove_chat_user(i, user)
                    keyboard = (
                        Keyboard(inline=True)
                        .add(Callback("Снять бан", {"command": "unban", "user": user, "chatId": chat_id}),
                             color=KeyboardButtonColor.POSITIVE)
                    )
                    await bot.api.messages.send(peer_id=2000000000+i, message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) заблокировал(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед\nПричина: {reason}", disable_mentions=1, random_id=0, keyboard=keyboard)
                except:
                    if i == chat_id:
                        try:
                            if reason: await bot.api.messages.send(peer_id=2000000000 + i,message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) заблокировал(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед\nПричина: {reason}",disable_mentions=1, random_id=0)
                            else:
                                await bot.api.messages.send(peer_id=2000000000 + i,message=f"@id{user_id} ({await get_user_name(user_id, chat_id)}) заблокировал(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед",disable_mentions=1, random_id=0)
                        except: pass

            if not chat_id in pull: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) заблокировал(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед\nПричина: {reason}", disable_mentions=1)

            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['sunban', 'санбан', 'сунбан']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:
                user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):
                user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /pull <число>")
                return True

            for i in pull:
                try: await unban(user, i)
                except: pass

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) разблокировал(-а) @id{user} ({await get_user_name(user, chat_id)}) в сетке бесед")

        if command in ['addsenmoder', 'senmoder']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 2)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) права старшего модератора @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['rnickall', 'allrnick', 'arnick', 'mrnick']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            await rnickall(chat_id)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) очистил(-а) ники в беседе", disable_mentions=1)

        if command in ['sremovenick', 'srnick']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /pull <число>")
                return True

            for i in pull:
                try: await rnick(user, i)
                except: pass

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) убрал(-а) ник @id{user} (пользователю) в сетке бесед", disable_mentions=1)

        if command in ['addadmin', 'admin']:
            if await get_role(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 3)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) права администратора @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1)
            await add_punishment(chat_id, user_id)
            if await get_sliv(user_id, chat_id) and await get_role(user_id, chat_id) < 5:
                await roleG(user_id, chat_id, 0)
                await message.reply(
                    f"❗️ Уровень прав @id{user_id} (пользователя) был снят из-за подозрений в сливе беседы\n\n{await staff_zov(chat_id)}")

        if command in ['pullinfo', 'pulli']:
            if await get_role(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull: pull_str = "Беседа не находится в связке!"
            else: pull_str = f"ID сетки бесед: {await get_pull_id(chat_id)} | Всего бесед в сетке: {len(pull)}"

            await message.reply(f"Информация о сетке бесед\n{pull_str}")

        if command in ['demote']:
            if await get_role(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            users = await bot.api.messages.get_conversation_members(peer_id=message.peer_id, fields=["online_info", "online"])
            users = json.loads(users.json())
            for i in users["profiles"]:
                if not i['id'] == user_id and await get_role(i['id'], chat_id) < 1:
                    try: await bot.api.messages.remove_chat_user(chat_id, i['id'])
                    except: pass

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) исключил(-а) всех участников без ролей!", disable_mentions=1)

        if command in ['banwords', 'bws', 'банворды']:
            if await get_role(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                bwss = await get_banwords(chat_id)
                bwss_str = ', '.join(bwss)
                await message.reply(f"Список запрещенных слов в беседе\n{bwss_str}\n\nУдалить слово: «/{command} delete <слово>»\nДобавить слово: «/{command} <слово>»")
            else:
                if arguments_lower[1] in ['удалить', 'clear', 'delete'] and len(arguments) > 2:
                    slovo = arguments_lower[2]
                    await banwords(slovo, True, chat_id)
                    await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) удалил(-а) слово из списка запрещенных")
                else:
                    slovo = arguments_lower[1]
                    await banwords(slovo, False, chat_id)
                    await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) добавил(-а) слово в список запрещенных")

        if command in ['filter']:
            if await get_role(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if await get_filter(chat_id):
                await set_filter(chat_id, 0)
                await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выключил(-а) фильтр запрещенных слов", disable_mentions=1)
            else:
                await set_filter(chat_id, 1)
                await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) включил(-а) фильтр запрещенных слов", disable_mentions=1)

        if command in ['sremoverole', 'srrole']:
            if await get_role(user_id, chat_id) < 4:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message:user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]):user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете снять роль данному пользователю!", disable_mentions=1)
                return True

            pull = await get_pull_chats(chat_id)
            if not pull:
                await message.reply("Сначала укажите сетку бесед, используя /pull <число>")
                return True

            for i in pull:
                try: await roleG(user, i, 0)
                except: pass

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) забрал(-а) роль у @id{user} (пользователя) в сетке бесед", disable_mentions=1)

        if command in ['antiflood', 'af']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if await get_antiflood(chat_id):
                await set_antiflood(chat_id, 0)
                await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выключил(-а) режим антифлуда", disable_mentions=1)
            else:
                await set_antiflood(chat_id, 1)
                await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) включил(-а) режим антифлуда", disable_mentions=1)

        if command in ['welcome', 'welcometext', 'wtext']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply(f"Укажите текст приветсвия, либо напишите «off»\n\nАктивный текст: {await get_welcome(chat_id)}\n\n«%u» - заменяется на @id пользователя\n«%n» - заменяется на тег с именем пользователя\n«%i» - заменяется на @id пригласившего\n«%p» - заменяется на тег с именем пригласившего")
                return True

            text = await get_string(arguments, 1)
            await set_welcome(chat_id, text)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) изменил(-а) приветствие в беседе")

        if command in ['invite']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            result = await invite_kick(chat_id, True)
            if result: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) включил(-а) функцию приглашения модераторами")
            else: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выключил(-а) функцию приглашения модераторами")

        if command in ['leave']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            result = await leave_kick(chat_id, True)
            if result: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) включил(-а) функцию исключения при выходе")
            else: await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выключил(-а) функцию исключения при выходе")

        if command in ['addsenadmin', 'addsenadm', 'senadm', 'senadmin']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if message.reply_message: user = message.reply_message.from_id
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await equals_roles(user_id, user, chat_id) < 2:
                await message.reply("Вы не можете выдать роль данному пользователю!", disable_mentions=1)
                return True

            await roleG(user, chat_id, 4)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) права старшего администратора @id{user} ({await get_user_name(user, chat_id)})", disable_mentions=1)

        if command in ['pull', 'setpull']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            if len(arguments) < 2:
                await message.reply("Укажите ID сетки бесед. 0 - удалить привязку")
                return True

            setka = arguments[1]
            try: setka = int(setka)
            except:
                await message.reply("ID сетки должно быть в виде чила")
                return True

            if setka < 0:
                await message.reply("ID сетки не должен быть меньше нуля")
                return True
            if setka > 2000:
                await message.reply("ID сетки не должен быть больше 2000")
                return True

            await set_pull(chat_id, setka)
            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) изменил(-а) сетку беседы на {setka}")

        if command in ['news']:
            if await get_role(user_id, chat_id) < 6:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = await get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите текст!")
                return True

            peer_ids = await get_all_peerids()
            for i in peer_ids:
                try: await bot.api.messages.send(peer_id=i, message=reason, disable_mentions=1, random_id=0)
                except: pass

        if command in ['szov', 'serverzov', 'сзов']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            reason = await get_string(arguments, 1)
            if not reason:
                await message.reply("Укажите причину вызова!")
                return True

            if not await get_pull_chats(chat_id): return await message.reply("Сначала укажите сетку бесед!")

            for i in await get_pull_chats(chat_id):
                users = await bot.api.messages.get_conversation_members(peer_id=2000000000+i, fields=["online_info", "online"])
                users = json.loads(users.json())
                user_f = []
                gi = 0
                for b in users["profiles"]:
                    if not b['id'] == user_id:
                        gi = gi + 1
                        if gi <= 100:
                            user_f.append(f"@id{b['id']} (🖤)")
                zov_users = ''.join(user_f)

                await bot.api.messages.send(peer_id=2000000000+i, message=f"🔔 Вы были вызваны @id{user_id} (администратором) бесед\n\n{zov_users}\n\n❗ Причина вызова: {reason}", random_id=0)

        if command in ['editowner', 'owner', 'setowner']:
            if await get_role(user_id, chat_id) < 5:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            if len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if user == user_id: return await message.reply("Вы не можете передать права самому себе!")

            if len(arguments) <= 2: return await message.reply("После ссылки на пользователя напишите <<confirm>> (Пример: /owner @id1 confirm)")
            if not arguments_lower[2] == "confirm":
                return await message.reply("После ссылки на пользователя напишите <<confirm>> (Пример: /owner @id1 confirm)")

            await set_onwer(user, chat_id)
            await roleG(user_id, chat_id, 4)

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) успешно передал(-a) права владельца беседы пользователю @id{user} ({await get_user_name(user, chat_id)})\n@id{user_id} ({await get_user_name(user_id, chat_id)}) выданы права Старшего Администратора.")

        if command in ['srole', 'prole', 'pullrole']:
            if await get_role(user_id, chat_id) < 3:
                await message.reply("Недостаточно прав!", disable_mentions=1)
                return True

            user = int
            arg = 2
            if message.reply_message:
                user = message.reply_message.from_id
                arg = 1
            elif len(arguments) >= 2 and await getID(arguments[1]): user = await getID(arguments[1])
            else:
                await message.reply("Укажите пользователя!", disable_mentions=1)
                return True

            if await get_role(user_id, chat_id) <= await get_role(user, chat_id): return await message.reply(
                "Вы не можете взаимодействовать с данным пользователем!")

            if len(arguments) < arg+1: return await message.reply("Укажите аргументы!")

            if not arguments[arg].isdigit(): return await message.reply("Укажите число!")

            level = int(arguments[arg])
            if level >= await get_role(user_id, chat_id): return await message.reply("Вы не можете выдать роль, которая выше вашей!")

            if level < 0: return await message.reply("Нельзя выдать такую роль!")

            if await get_pull_id(chat_id) == 0: return await message.reply("Сначала укажите сетку бесед, используя /pull")

            chats = await get_pull_chats(chat_id)

            print(chats)

            for i in chats:
                await roleG(user, i, level)

            await message.answer(f"@id{user_id} ({await get_user_name(user_id, chat_id)}) выдал(-а) уровень прав {level} в сетке бесед пользователю @id{user} ({await get_user_name(user, chat_id)})")




    else:
        if user_id < 1: return True
        if await check_chat(chat_id):
            if await get_mute(user_id, chat_id) and not await checkMute(chat_id, user_id):
                try: await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id, delete_for_all=True, cmids=message.conversation_message_id)
                except: pass
            elif await check_quit(chat_id) and await get_role(user_id, chat_id) < 1:
                try: await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id, delete_for_all=True, cmids=message.conversation_message_id)
                except: pass
                print(await get_role(user_id, chat_id) < 1)
            else:
                if await get_filter(chat_id):
                    bws = await get_banwords(chat_id)
                    for i in bws:
                        if i in message.text.lower() and await get_role(user_id, chat_id) < 1:
                            await mute(user_id, chat_id, 'Бот', 'Написание запрещенных слов', 30)
                            keyboard = (
                                Keyboard(inline=True)
                                .add(Callback("Снять мут", {"command": "unmute", "chatId": chat_id, "user": user_id}), color=KeyboardButtonColor.POSITIVE)
                            )
                            await message.reply(f"@id{user_id} (Пользователь) получил(-а) мут на 30 минут за написание запрещенного слова!", disable_mentions=1, keyboard=keyboard)
                            try: await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,delete_for_all=True, cmids=message.conversation_message_id)
                            except: pass
                            return True

            await new_message(user_id, message.message_id, message.conversation_message_id, chat_id)
            if await get_spam(user_id, chat_id) and await get_role(user_id, chat_id) < 1:
                keyboard = (
                    Keyboard(inline=True)
                    .add(Callback("Снять мут", {"command": "unmute", "chatId": chat_id, "user": user_id}), color=KeyboardButtonColor.POSITIVE)
                )
                await message.reply(f"@id{user_id} (Пользователь) получил(-а) мут на 30 минут за спам!", disable_mentions=1, keyboard=keyboard)
                await mute(user_id, chat_id, 'Bot', 'Спам', 30)
                try:await bot.api.messages.delete(group_id=message.group_id, peer_id=message.peer_id,delete_for_all=True, cmids=message.conversation_message_id)
                except: pass



 #в config.json токен бота


bot.run_forever()
