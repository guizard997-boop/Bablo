# -*- coding: utf-8 -*-
"""
================================================================================
  БОТ ОПЛАТЫ — база пользователей + счета (квитанции)
================================================================================
Токен:      8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY
Admin ID:   8569472160
Реквизиты:  Абдумалик К. · +996 220 979 346

/start у клиента → он в базе
/users → список зарегистрированных
/new → создать счёт, потом выбрать кому отправить
/sendto USER_ID INV_ID → кинуть квитанцию из базы
================================================================================
"""

import os
import sys
import json
import uuid
import subprocess
from datetime import datetime

try:
    import telebot
    from telebot import types
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyTelegramBotAPI>=4.14.0", "-q"])
    import telebot
    from telebot import types

BOT_TOKEN = "8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY"
ADMIN_IDS = [8569472160]

PAYMENT_DETAILS = """
💳 <b>Реквизиты для оплаты</b>

👤 <b>Получатель:</b> Абдумалик К.
📱 <b>МБанк / Elsom / O! / перевод:</b> <code>+996 220 979 346</code>

💬 В комментарии к платежу укажи: <b>номер счёта</b> из бота
"""

CURRENCY = "USD"
DATA_FILE = "payments.json"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# ---------- storage ----------
def load_data():
    empty = {
        "users": {},
        "invoices": {},
        "meta": {"created": datetime.now().isoformat()},
    }
    if not os.path.exists(DATA_FILE):
        return empty
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "invoices" not in data:
            data["invoices"] = {}
        if "users" not in data:
            data["users"] = {}
        if "meta" not in data:
            data["meta"] = {}
        return data
    except Exception:
        return empty


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(user_id):
    try:
        return int(user_id) in ADMIN_IDS
    except Exception:
        return False


def register_user(user):
    """Сохраняет/обновляет пользователя в базе при любом контакте."""
    if not user:
        return
    data = load_data()
    uid = str(user.id)
    prev = data["users"].get(uid, {})
    data["users"][uid] = {
        "id": user.id,
        "first_name": user.first_name or "",
        "last_name": getattr(user, "last_name", None) or "",
        "username": user.username or "",
        "full_name": f"{user.first_name or ''} {getattr(user, 'last_name', None) or ''}".strip(),
        "registered_at": prev.get("registered_at") or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "is_admin": is_admin(user.id),
    }
    save_data(data)


def new_invoice_id():
    return uuid.uuid4().hex[:8].upper()


def status_label(status):
    return {
        "pending": "⏳ Ожидает оплаты",
        "waiting_confirm": "🔎 На проверке",
        "paid": "✅ Оплачен",
        "rejected": "❌ Отклонён",
        "cancelled": "🚫 Отменён",
    }.get(status, status or "?")


def format_invoice(inv, short=False):
    lines = [
        f"🧾 <b>Счёт #{inv['id']}</b>",
        f"Статус: {status_label(inv.get('status'))}",
        f"Сумма: <b>{inv['amount']} {inv.get('currency', CURRENCY)}</b>",
        f"За что: {inv.get('description') or '—'}",
    ]
    if not short:
        lines += [
            f"Клиент: {inv.get('client_name') or '—'} (id {inv.get('client_id') or '—'})",
            f"Создан: {inv.get('created_at') or '—'}",
        ]
        if inv.get("claimed_at"):
            lines.append(f"Заявка на оплату: {inv['claimed_at']}")
        if inv.get("paid_at"):
            lines.append(f"Подтверждён: {inv['paid_at']}")
    return "\n".join(lines)


def format_user(u):
    uname = f"@{u['username']}" if u.get("username") else "—"
    return (
        f"👤 <b>{u.get('full_name') or 'Без имени'}</b>\n"
        f"id: <code>{u.get('id')}</code>\n"
        f"username: {uname}\n"
        f"в базе с: {u.get('registered_at') or '—'}\n"
        f"был: {u.get('last_seen') or '—'}"
    )


def client_keyboard(inv):
    kb = types.InlineKeyboardMarkup()
    st = inv.get("status")
    if st in ("pending", "waiting_confirm", "rejected"):
        kb.row(
            types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid:{inv['id']}"),
            types.InlineKeyboardButton("💳 Реквизиты", callback_data=f"req:{inv['id']}"),
        )
        if st == "pending":
            kb.row(
                types.InlineKeyboardButton(
                    "🚫 Отменить", callback_data=f"client_cancel:{inv['id']}"
                )
            )
    return kb


def admin_confirm_keyboard(inv_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{inv_id}"),
        types.InlineKeyboardButton("❌ Не пришло", callback_data=f"reject:{inv_id}"),
    )
    return kb


def users_pick_keyboard(inv_id, page=0, per_page=8):
    """Кнопки выбора пользователя из базы для отправки счёта."""
    data = load_data()
    users = [
        u for u in data["users"].values()
        if not u.get("is_admin")
    ]
    users.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    kb = types.InlineKeyboardMarkup()
    start = page * per_page
    chunk = users[start : start + per_page]
    for u in chunk:
        label = u.get("full_name") or "Без имени"
        if u.get("username"):
            label += f" @{u['username']}"
        label = label[:40]
        kb.add(
            types.InlineKeyboardButton(
                f"📤 {label}",
                callback_data=f"senduser:{inv_id}:{u['id']}",
            )
        )
    nav = []
    if page > 0:
        nav.append(
            types.InlineKeyboardButton("⬅️", callback_data=f"userpage:{inv_id}:{page-1}")
        )
    if start + per_page < len(users):
        nav.append(
            types.InlineKeyboardButton("➡️", callback_data=f"userpage:{inv_id}:{page+1}")
        )
    if nav:
        kb.row(*nav)
    kb.add(types.InlineKeyboardButton("❌ Закрыть", callback_data="close"))
    return kb, len(users)


def notify_admins(text, reply_markup=None):
    for admin in ADMIN_IDS:
        try:
            bot.send_message(admin, text, reply_markup=reply_markup)
        except Exception as e:
            print(f"notify admin {admin}: {e}")


def send_invoice_to_client(inv):
    cid = inv.get("client_id")
    if not cid:
        return False
    text = (
        f"🧾 <b>Квитанция / счёт #{inv['id']}</b>\n\n"
        f"Сумма: <b>{inv['amount']} {inv.get('currency', CURRENCY)}</b>\n"
        f"За что: {inv.get('description') or '—'}\n\n"
        f"1) Переведите по реквизитам\n"
        f"2) В комментарии: <b>#{inv['id']}</b>\n"
        f"3) Нажмите «Я оплатил»"
    )
    try:
        bot.send_message(cid, text, reply_markup=client_keyboard(inv))
        bot.send_message(cid, PAYMENT_DETAILS)
        return True
    except Exception as e:
        notify_admins(f"⚠️ Не отправить счёт #{inv['id']}: {e}")
        return False


# ---------- start / register ----------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    register_user(message.from_user)
    if is_admin(message.from_user.id):
        bot.reply_to(
            message,
            "🎩 <b>Бот оплаты — админ</b>\n\n"
            "<b>База клиентов</b>\n"
            "/users — кто зарегистрирован\n"
            "/user ID — карточка пользователя\n\n"
            "<b>Счета / квитанции</b>\n"
            "<code>/new 8500 | Camry 2019</code>\n"
            "→ бот покажет список пользователей для отправки\n"
            "<code>/sendto USER_ID INV_ID</code> — кинуть квитанцию\n"
            "или reply клиенту: <code>/send INV_ID</code>\n\n"
            "/list /pending /paid /stats /find ID\n"
            "/cancel ID · /setamount · /setdesc\n"
            "/requisites · /broadcast текст",
        )
    else:
        bot.reply_to(
            message,
            "👋 Вы зарегистрированы в боте оплаты.\n\n"
            "Когда вам выставят счёт — придёт квитанция.\n"
            "После перевода нажмите <b>«Я оплатил»</b>.\n\n"
            "/my — мои счета\n"
            "/requisites — реквизиты",
        )


@bot.message_handler(commands=["users"])
def cmd_users(message):
    if not is_admin(message.from_user.id):
        return
    register_user(message.from_user)
    data = load_data()
    users = list(data["users"].values())
    users.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    if not users:
        bot.reply_to(message, "База пуста. Клиенты появятся после /start.")
        return

    bot.reply_to(message, f"👥 В базе: <b>{len(users)}</b> чел.")
    buf = ""
    for i, u in enumerate(users, 1):
        uname = f"@{u['username']}" if u.get("username") else "—"
        mark = " 👑" if u.get("is_admin") else ""
        line = (
            f"{i}. <b>{u.get('full_name') or '—'}</b>{mark}\n"
            f"   id: <code>{u.get('id')}</code> · {uname}\n"
            f"   был: {u.get('last_seen') or '—'}\n\n"
        )
        if len(buf) + len(line) > 3500:
            bot.send_message(message.chat.id, buf)
            buf = line
        else:
            buf += line
    if buf:
        bot.send_message(message.chat.id, buf)
    bot.send_message(
        message.chat.id,
        "Чтобы кинуть квитанцию:\n"
        "1) <code>/new 8500 | описание</code>\n"
        "2) выбрать человека кнопкой\n"
        "или <code>/sendto USER_ID INV_ID</code>",
    )


@bot.message_handler(commands=["user"])
def cmd_user(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "<code>/user TELEGRAM_ID</code>")
        return
    uid = parts[1].strip()
    data = load_data()
    u = data["users"].get(uid)
    if not u:
        bot.reply_to(message, "Нет в базе. Пусть напишет боту /start.")
        return
    invs = [
        i for i in data["invoices"].values()
        if str(i.get("client_id")) == str(uid)
    ]
    text = format_user(u) + f"\n\nСчетов: {len(invs)}"
    for inv in invs[-5:]:
        text += "\n• " + format_invoice(inv, short=True).replace("\n", " | ")
    bot.reply_to(message, text)


# ---------- invoices ----------
@bot.message_handler(commands=["requisites"])
def cmd_requisites(message):
    register_user(message.from_user)
    bot.reply_to(message, PAYMENT_DETAILS)


@bot.message_handler(commands=["new"])
def cmd_new(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "Только администратор.")
        return
    register_user(message.from_user)
    raw = (message.text or "").replace("/new", "", 1).strip()
    if "|" not in raw:
        bot.reply_to(message, "Формат:\n<code>/new 8500 | Toyota Camry 2019</code>")
        return
    amount_s, desc = [x.strip() for x in raw.split("|", 1)]
    try:
        amount = float(amount_s.replace(",", ".").replace(" ", "").replace("$", ""))
    except ValueError:
        bot.reply_to(message, "Сумма — число.")
        return
    if amount <= 0:
        bot.reply_to(message, "Сумма > 0.")
        return

    inv_id = new_invoice_id()
    data = load_data()
    inv = {
        "id": inv_id,
        "amount": amount,
        "currency": CURRENCY,
        "description": desc,
        "status": "pending",
        "client_id": None,
        "client_name": None,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "created_by": message.from_user.id,
        "claimed_at": None,
        "paid_at": None,
    }
    data["invoices"][inv_id] = inv
    save_data(data)

    kb, n_users = users_pick_keyboard(inv_id, page=0)
    bot.reply_to(
        message,
        format_invoice(inv)
        + f"\n\n👥 Выбери, кому кинуть квитанцию (в базе {n_users}):"
        + "\nили <code>/sendto USER_ID "
        + inv_id
        + "</code>"
        + "\nили reply клиенту: <code>/send "
        + inv_id
        + "</code>",
        reply_markup=kb if n_users else None,
    )


@bot.message_handler(commands=["sendto"])
def cmd_sendto(message):
    """ /sendto USER_ID INV_ID """
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "Формат:\n<code>/sendto USER_ID INV_ID</code>\nСмотри /users")
        return
    user_id = parts[1].strip()
    inv_id = parts[2].strip().upper()
    data = load_data()
    inv = data["invoices"].get(inv_id)
    if not inv:
        bot.reply_to(message, "Счёт не найден. Сначала /new")
        return
    u = data["users"].get(str(user_id))
    if not u:
        bot.reply_to(message, "Пользователь не в базе. Пусть напишет /start.")
        return

    inv["client_id"] = int(user_id)
    inv["client_name"] = (
        f"{u.get('full_name') or ''} @{u.get('username') or ''}".strip()
    )
    if inv.get("status") != "paid":
        inv["status"] = "pending"
    save_data(data)
    ok = send_invoice_to_client(inv)
    bot.reply_to(
        message,
        f"✅ Квитанция #{inv_id} → {inv['client_name']}"
        if ok
        else "⚠️ Не доставлено. Пользователь заблокировал бота?",
    )


@bot.message_handler(commands=["send"])
def cmd_send(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "Reply клиенту + <code>/send ID</code>")
        return
    inv_id = parts[1].strip().upper()
    data = load_data()
    inv = data["invoices"].get(inv_id)
    if not inv:
        bot.reply_to(message, "Счёт не найден.")
        return
    if inv.get("status") == "cancelled":
        bot.reply_to(message, "Счёт отменён.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Сделай reply на сообщение клиента или используй /sendto / /users")
        return

    client = message.reply_to_message.from_user
    register_user(client)
    inv["client_id"] = client.id
    inv["client_name"] = f"{client.first_name or ''} @{client.username or ''}".strip()
    if inv.get("status") != "paid":
        inv["status"] = "pending"
    save_data(data)
    ok = send_invoice_to_client(inv)
    bot.reply_to(
        message,
        f"✅ Отправлено: {inv['client_name']}" if ok else "⚠️ Клиент должен написать /start",
    )


@bot.message_handler(commands=["list", "pending", "paid"])
def cmd_list(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    invs = list(data["invoices"].values())
    cmd = (message.text or "").split()[0].replace("/", "").split("@")[0]
    if cmd == "pending":
        invs = [i for i in invs if i.get("status") in ("pending", "waiting_confirm")]
    elif cmd == "paid":
        invs = [i for i in invs if i.get("status") == "paid"]
    invs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    if not invs:
        bot.reply_to(message, "Пусто.")
        return
    buf = ""
    for inv in invs[:50]:
        line = format_invoice(inv, short=True) + "\n\n"
        if len(buf) + len(line) > 3500:
            bot.send_message(message.chat.id, buf)
            buf = line
        else:
            buf += line
    if buf:
        bot.send_message(message.chat.id, buf)


@bot.message_handler(commands=["find"])
def cmd_find(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "<code>/find ID</code>")
        return
    inv_id = parts[1].strip().upper()
    inv = load_data()["invoices"].get(inv_id)
    if not inv:
        bot.reply_to(message, "Не найден.")
        return
    kb = admin_confirm_keyboard(inv_id) if inv.get("status") == "waiting_confirm" else None
    bot.reply_to(message, format_invoice(inv), reply_markup=kb)


@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    invs = list(data["invoices"].values())
    users = data.get("users") or {}
    by, paid_sum, pending_sum = {}, 0.0, 0.0
    for inv in invs:
        st = inv.get("status") or "?"
        by[st] = by.get(st, 0) + 1
        try:
            amt = float(inv.get("amount") or 0)
        except Exception:
            amt = 0
        if st == "paid":
            paid_sum += amt
        if st in ("pending", "waiting_confirm"):
            pending_sum += amt
    lines = [
        f"📊 <b>Статистика</b>",
        f"👥 В базе: {len(users)}",
        f"🧾 Счетов: {len(invs)}",
    ]
    for k, v in sorted(by.items()):
        lines.append(f"{status_label(k)}: {v}")
    lines.append(f"\n💰 Оплачено: <b>{paid_sum:.0f} {CURRENCY}</b>")
    lines.append(f"⏳ Ожидание: <b>{pending_sum:.0f} {CURRENCY}</b>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["my"])
def cmd_my(message):
    register_user(message.from_user)
    uid = message.from_user.id
    invs = [i for i in load_data()["invoices"].values() if i.get("client_id") == uid]
    invs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    if not invs:
        bot.reply_to(message, "Нет счетов.")
        return
    for inv in invs[:15]:
        kb = (
            client_keyboard(inv)
            if inv.get("status") in ("pending", "waiting_confirm", "rejected")
            else None
        )
        bot.send_message(message.chat.id, format_invoice(inv), reply_markup=kb)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "<code>/cancel ID</code>")
        return
    inv_id = parts[1].strip().upper()
    data = load_data()
    inv = data["invoices"].get(inv_id)
    if not inv:
        bot.reply_to(message, "Не найден.")
        return
    inv["status"] = "cancelled"
    save_data(data)
    bot.reply_to(message, f"#{inv_id} отменён.")
    if inv.get("client_id"):
        try:
            bot.send_message(inv["client_id"], f"🚫 Счёт #{inv_id} отменён.")
        except Exception:
            pass


@bot.message_handler(commands=["setamount"])
def cmd_setamount(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "<code>/setamount ID 9000</code>")
        return
    inv_id = parts[1].strip().upper()
    try:
        amount = float(parts[2].replace(",", ".").replace("$", ""))
    except ValueError:
        bot.reply_to(message, "Сумма — число.")
        return
    data = load_data()
    inv = data["invoices"].get(inv_id)
    if not inv:
        bot.reply_to(message, "Не найден.")
        return
    inv["amount"] = amount
    save_data(data)
    bot.reply_to(message, f"#{inv_id} = <b>{amount} {CURRENCY}</b>")
    if inv.get("client_id") and inv.get("status") != "paid":
        try:
            bot.send_message(
                inv["client_id"],
                f"✏️ Счёт #{inv_id}: сумма <b>{amount} {CURRENCY}</b>",
                reply_markup=client_keyboard(inv),
            )
        except Exception:
            pass


@bot.message_handler(commands=["setdesc"])
def cmd_setdesc(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "<code>/setdesc ID текст</code>")
        return
    inv_id = parts[1].strip().upper()
    data = load_data()
    inv = data["invoices"].get(inv_id)
    if not inv:
        bot.reply_to(message, "Не найден.")
        return
    inv["description"] = parts[2].strip()
    save_data(data)
    bot.reply_to(message, f"#{inv_id}: описание обновлено.")


@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").replace("/broadcast", "", 1).strip()
    if not text:
        bot.reply_to(message, "<code>/broadcast текст</code>")
        return
    data = load_data()
    # всем из базы, кроме админов
    clients = [
        int(u["id"]) for u in data["users"].values() if not u.get("is_admin")
    ]
    ok = fail = 0
    for cid in clients:
        try:
            bot.send_message(cid, f"📢 {text}")
            ok += 1
        except Exception:
            fail += 1
    bot.reply_to(message, f"Рассылка по базе: OK {ok}, ошибок {fail}")


# ---------- callbacks ----------
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    data = load_data()
    raw = call.data or ""

    if raw == "close":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return

    if raw.startswith("userpage:"):
        # userpage:INV:page
        _, inv_id, page_s = raw.split(":", 2)
        inv_id = inv_id.upper()
        page = int(page_s)
        kb, n_users = users_pick_keyboard(inv_id, page=page)
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=kb
            )
        except Exception:
            pass
        return

    if raw.startswith("senduser:"):
        # senduser:INV:USER_ID
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Только админ", show_alert=True)
            return
        _, inv_id, user_id = raw.split(":", 2)
        inv_id = inv_id.upper()
        inv = data["invoices"].get(inv_id)
        u = data["users"].get(str(user_id))
        if not inv or not u:
            bot.answer_callback_query(call.id, "Не найдено", show_alert=True)
            return
        inv["client_id"] = int(user_id)
        inv["client_name"] = f"{u.get('full_name') or ''} @{u.get('username') or ''}".strip()
        if inv.get("status") != "paid":
            inv["status"] = "pending"
        save_data(data)
        ok = send_invoice_to_client(inv)
        bot.answer_callback_query(call.id, "Отправлено" if ok else "Ошибка")
        try:
            bot.edit_message_text(
                format_invoice(inv)
                + ("\n\n✅ Квитанция отправлена клиенту." if ok else "\n\n⚠️ Не доставлено."),
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                f"{'✅' if ok else '⚠️'} #{inv_id} → {inv['client_name']}",
            )
        return

    parts = raw.split(":", 1)
    if len(parts) != 2:
        bot.answer_callback_query(call.id)
        return
    action, inv_id = parts[0], parts[1].upper()
    inv = data["invoices"].get(inv_id)

    if action == "req":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, PAYMENT_DETAILS)
        return

    if not inv:
        bot.answer_callback_query(call.id, "Счёт не найден", show_alert=True)
        return

    if action == "client_cancel":
        if call.from_user.id != inv.get("client_id") and not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Недоступно", show_alert=True)
            return
        if inv.get("status") == "paid":
            bot.answer_callback_query(call.id, "Уже оплачен", show_alert=True)
            return
        inv["status"] = "cancelled"
        save_data(data)
        bot.answer_callback_query(call.id, "Отменено")
        try:
            bot.edit_message_text(format_invoice(inv), call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        notify_admins(f"Клиент отменил #{inv_id}")
        return

    if action == "paid":
        register_user(call.from_user)
        if inv.get("status") == "paid":
            bot.answer_callback_query(call.id, "Уже подтверждён", show_alert=True)
            return
        if inv.get("status") == "cancelled":
            bot.answer_callback_query(call.id, "Отменён", show_alert=True)
            return
        inv["status"] = "waiting_confirm"
        inv["client_id"] = inv.get("client_id") or call.from_user.id
        inv["client_name"] = inv.get("client_name") or (
            f"{call.from_user.first_name or ''} @{call.from_user.username or ''}".strip()
        )
        inv["claimed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_data(data)
        bot.answer_callback_query(call.id, "На проверке")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.send_message(call.message.chat.id, f"🔎 Счёт #{inv_id} на проверке.")
        notify_admins(
            f"🔎 Клиент оплатил?\n{format_invoice(inv)}",
            reply_markup=admin_confirm_keyboard(inv_id),
        )
        return

    if action in ("confirm", "reject"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Только админ", show_alert=True)
            return
        if action == "confirm":
            inv["status"] = "paid"
            inv["paid_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_data(data)
            bot.answer_callback_query(call.id, "OK")
            try:
                bot.edit_message_text(
                    f"✅ ПОДТВЕРЖДЕНО\n{format_invoice(inv)}",
                    call.message.chat.id,
                    call.message.message_id,
                )
            except Exception:
                bot.send_message(call.message.chat.id, f"✅ #{inv_id} оплачен")
            if inv.get("client_id"):
                try:
                    bot.send_message(
                        inv["client_id"],
                        f"✅ Оплата по счёту <b>#{inv_id}</b> подтверждена.\nСпасибо!",
                    )
                except Exception:
                    pass
        else:
            inv["status"] = "pending"
            save_data(data)
            bot.answer_callback_query(call.id, "Отклонено")
            try:
                bot.edit_message_text(
                    f"❌ НЕ НАЙДЕНО\n{format_invoice(inv)}",
                    call.message.chat.id,
                    call.message.message_id,
                )
            except Exception:
                pass
            if inv.get("client_id"):
                try:
                    bot.send_message(
                        inv["client_id"],
                        f"❌ По счёту <b>#{inv_id}</b> оплата не найдена.\n"
                        f"Проверьте перевод и нажмите «Я оплатил» снова.",
                        reply_markup=client_keyboard(inv),
                    )
                except Exception:
                    pass
        return

    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    register_user(message.from_user)
    if is_admin(message.from_user.id):
        bot.reply_to(message, "/users /new /sendto /list /pending /paid /stats /help")
    else:
        bot.reply_to(message, "/my — счета · /requisites — реквизиты")


def main():
    print("Payment bot + user DB starting...")
    print(f"Admin: {ADMIN_IDS}")
    notify_admins(
        "💳 <b>Бот оплаты запущен</b>\n"
        "База пользователей активна.\n"
        "/users — кто в базе\n"
        "/new — счёт + выбор кому кинуть квитанцию"
    )
    bot.infinity_polling(timeout=60, long_polling_timeout=40, skip_pending=True)


if __name__ == "__main__":
    main()
