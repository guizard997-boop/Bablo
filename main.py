# -*- coding: utf-8 -*-
"""
Бот канцтоваров — меню снизу (ReplyKeyboard), не в ленте чата.
Токен оплаты: 8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY
Admin: 8569472160
Оплата: Абдумалик К. · +996 220 979 346
"""

import os
import sys
import io
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

try:
    import qrcode
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]>=7.4", "-q"])
    import qrcode

BOT_TOKEN = "8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY"
ADMIN_IDS = [8569472160]
PAYEE_NAME = "Абдумалик К."
PAYEE_PHONE = "+996 220 979 346"
CURRENCY = "KGS"
DATA_FILE = "shop_data.json"

DEFAULT_PRODUCTS = [
    {"id": "p1", "name": "Ручка шариковая синяя", "price": 25, "cat": "Ручки", "stock": 100, "desc": "Шариковая ручка"},
    {"id": "p2", "name": "Ручка гелевая чёрная", "price": 40, "cat": "Ручки", "stock": 80, "desc": "Гелевая ручка"},
    {"id": "p3", "name": "Карандаш HB", "price": 15, "cat": "Карандаши", "stock": 150, "desc": "Простой HB"},
    {"id": "p4", "name": "Набор карандашей 12 шт", "price": 120, "cat": "Карандаши", "stock": 40, "desc": "12 цветов"},
    {"id": "p5", "name": "Тетрадь 12 л. клетка", "price": 30, "cat": "Тетради", "stock": 200, "desc": "12 листов"},
    {"id": "p6", "name": "Тетрадь 48 л. клетка", "price": 55, "cat": "Тетради", "stock": 120, "desc": "48 листов"},
    {"id": "p7", "name": "Блокнот А5", "price": 150, "cat": "Тетради", "stock": 50, "desc": "На пружине"},
    {"id": "p8", "name": "Ластик", "price": 20, "cat": "Мелочи", "stock": 100, "desc": "Мягкий ластик"},
    {"id": "p9", "name": "Линейка 20 см", "price": 25, "cat": "Мелочи", "stock": 90, "desc": "Пластик"},
    {"id": "p10", "name": "Степлер + скобы", "price": 180, "cat": "Офис", "stock": 30, "desc": "Мини-степлер"},
    {"id": "p11", "name": "Папка-скоросшиватель", "price": 45, "cat": "Офис", "stock": 60, "desc": "Для документов"},
    {"id": "p12", "name": "Клей-карандаш", "price": 50, "cat": "Мелочи", "stock": 70, "desc": "15 г"},
]

# user_id -> состояние навигации
# {"screen": "home"|"cats"|"prods"|"item"|"pay", "cat": str, "pid": str, "order_id": str}
STATE = {}

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def load_data():
    empty = {
        "products": {p["id"]: p for p in DEFAULT_PRODUCTS},
        "users": {},
        "orders": {},
    }
    if not os.path.exists(DATA_FILE):
        save_data(empty)
        return empty
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("products", {})
        data.setdefault("users", {})
        data.setdefault("orders", {})
        if not data["products"]:
            data["products"] = {p["id"]: p for p in DEFAULT_PRODUCTS}
            save_data(data)
        return data
    except Exception:
        return empty


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(uid):
    try:
        return int(uid) in ADMIN_IDS
    except Exception:
        return False


def register(user):
    if not user:
        return
    data = load_data()
    uid = str(user.id)
    prev = data["users"].get(uid, {})
    data["users"][uid] = {
        "id": user.id,
        "name": f"{user.first_name or ''} {getattr(user, 'last_name', '') or ''}".strip(),
        "username": user.username or "",
        "registered_at": prev.get("registered_at") or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    save_data(data)


def money(n):
    try:
        n = float(n)
    except Exception:
        return str(n)
    return f"{int(n) if n == int(n) else n} {CURRENCY}"


def get_state(uid):
    return STATE.setdefault(uid, {"screen": "home"})


def set_state(uid, **kwargs):
    st = get_state(uid)
    st.update(kwargs)
    STATE[uid] = st
    return st


def categories():
    data = load_data()
    cats = {}
    for p in data["products"].values():
        if int(p.get("stock") or 0) <= 0:
            continue
        c = p.get("cat") or "Другое"
        cats.setdefault(c, []).append(p)
    return cats


def kb_rows(buttons, row_size=2, extra_rows=None):
    """Собирает ReplyKeyboard из списка строк-кнопок."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=row_size)
    row = []
    for b in buttons:
        row.append(types.KeyboardButton(b))
        if len(row) >= row_size:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    if extra_rows:
        for er in extra_rows:
            kb.row(*[types.KeyboardButton(x) for x in er])
    return kb


def kb_home(admin=False):
    buttons = ["🛍 Каталог", "📦 Мои заказы", "💳 Реквизиты", "ℹ️ Помощь"]
    if admin:
        buttons.append("⚙️ Админ")
    return kb_rows(buttons, row_size=2)


def kb_cats():
    cats = sorted(categories().keys())
    labels = [f"📁 {c}" for c in cats]
    return kb_rows(labels, row_size=2, extra_rows=[["◀️ Назад"]])


def kb_products(cat):
    items = categories().get(cat, [])
    items = sorted(items, key=lambda x: x.get("name") or "")
    labels = [f"{p['name']} — {money(p['price'])}" for p in items]
    return kb_rows(labels, row_size=1, extra_rows=[["◀️ К категориям", "🏠 Меню"]])


def kb_product_actions():
    return kb_rows(["✅ Купить / QR", "◀️ К товарам", "🏠 Меню"], row_size=1)


def kb_after_qr():
    return kb_rows(["✅ Я оплатил", "🛍 В каталог", "🏠 Меню"], row_size=1)


def make_qr(text):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "pay_qr.png"
    return buf


def notify_admins(text):
    for a in ADMIN_IDS:
        try:
            bot.send_message(a, text)
        except Exception as e:
            print("admin", e)


def find_product_by_button(text):
    """Текст кнопки вида 'Название — 25 KGS'."""
    data = load_data()
    t = (text or "").strip()
    for p in data["products"].values():
        label = f"{p['name']} — {money(p['price'])}"
        if t == label or t == p["name"]:
            return p
    # частичное
    for p in data["products"].values():
        if p["name"] in t and str(int(float(p["price"]))) in t.replace(" ", ""):
            return p
    return None


# ---------- start ----------
@bot.message_handler(commands=["start", "menu", "help"])
def cmd_start(message):
    register(message.from_user)
    set_state(message.from_user.id, screen="home", cat=None, pid=None, order_id=None)
    admin = is_admin(message.from_user.id)
    text = (
        "✏️ <b>Канцтовары</b>\n\n"
        "Меню внизу экрана 👇\n"
        "Каталог → категория → товар → QR для оплаты.\n\n"
        f"Оплата: <b>{PAYEE_NAME}</b>\n"
        f"<code>{PAYEE_PHONE}</code>"
    )
    if admin:
        text += (
            "\n\n<b>Админ-команды:</b>\n"
            "<code>/add Название | цена | категория | описание</code>\n"
            "/list · /del ID · /setprice ID цена · /stock ID N · /orders"
        )
    bot.send_message(message.chat.id, text, reply_markup=kb_home(admin))


# ---------- admin cmds ----------
@bot.message_handler(commands=["list"])
def cmd_list(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    lines = ["📦 <b>Товары</b>"]
    for p in sorted(data["products"].values(), key=lambda x: (x.get("cat") or "", x.get("name") or "")):
        lines.append(
            f"<code>{p['id']}</code> · {p.get('cat')} · {p['name']} — {money(p['price'])} · ост. {p.get('stock', 0)}"
        )
    bot.reply_to(message, "\n".join(lines) if len(lines) > 1 else "Пусто")


@bot.message_handler(commands=["add"])
def cmd_add(message):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").replace("/add", "", 1).strip()
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 2:
        bot.reply_to(message, "Формат:\n<code>/add Ручка | 25 | Ручки | описание</code>")
        return
    name = parts[0]
    try:
        price = float(parts[1].replace(",", ".").replace(" ", ""))
    except ValueError:
        bot.reply_to(message, "Цена — число")
        return
    cat = parts[2] if len(parts) > 2 and parts[2] else "Другое"
    desc = parts[3] if len(parts) > 3 else ""
    pid = "p" + uuid.uuid4().hex[:6]
    data = load_data()
    data["products"][pid] = {"id": pid, "name": name, "price": price, "cat": cat, "stock": 50, "desc": desc}
    save_data(data)
    bot.reply_to(message, f"✅ <code>{pid}</code> {name} — {money(price)} · {cat}")


@bot.message_handler(commands=["del"])
def cmd_del(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "/del ID")
        return
    pid = parts[1].strip()
    data = load_data()
    if pid not in data["products"]:
        bot.reply_to(message, "Нет ID")
        return
    name = data["products"][pid]["name"]
    del data["products"][pid]
    save_data(data)
    bot.reply_to(message, f"🗑 {name}")


@bot.message_handler(commands=["setprice"])
def cmd_setprice(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "/setprice ID 99")
        return
    data = load_data()
    pid = parts[1].strip()
    if pid not in data["products"]:
        bot.reply_to(message, "Нет ID")
        return
    data["products"][pid]["price"] = float(parts[2].replace(",", "."))
    save_data(data)
    bot.reply_to(message, f"Цена обновлена: {money(data['products'][pid]['price'])}")


@bot.message_handler(commands=["stock"])
def cmd_stock(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "/stock ID 100")
        return
    data = load_data()
    pid = parts[1].strip()
    if pid not in data["products"]:
        bot.reply_to(message, "Нет ID")
        return
    data["products"][pid]["stock"] = int(parts[2])
    save_data(data)
    bot.reply_to(message, f"Остаток: {data['products'][pid]['stock']}")


@bot.message_handler(commands=["orders"])
def cmd_orders_admin(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    orders = sorted(data["orders"].values(), key=lambda x: x.get("created_at") or "", reverse=True)
    if not orders:
        bot.reply_to(message, "Заказов нет")
        return
    for o in orders[:15]:
        bot.send_message(
            message.chat.id,
            f"#{o['id']} · <b>{o.get('status')}</b>\n"
            f"{o.get('product_name')} — {money(o.get('price'))}\n"
            f"{o.get('user_name')} · {o.get('created_at')}\n"
            f"Подтвердить: <code>/payok {o['id']}</code> · отклонить: <code>/payno {o['id']}</code>",
        )


@bot.message_handler(commands=["payok", "payno"])
def cmd_pay_admin(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "/payok ID или /payno ID")
        return
    oid = parts[1].strip().upper()
    data = load_data()
    o = data["orders"].get(oid)
    if not o:
        bot.reply_to(message, "Нет заказа")
        return
    cmd = parts[0].replace("/", "").split("@")[0]
    if cmd == "payok":
        o["status"] = "paid"
        o["paid_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_data(data)
        bot.reply_to(message, f"✅ #{oid} оплачен")
        try:
            bot.send_message(
                int(o["user_id"]),
                f"✅ Оплата по заказу <b>#{oid}</b> подтверждена!\n{o.get('product_name')} — {money(o.get('price'))}",
                reply_markup=kb_home(False),
            )
        except Exception:
            pass
    else:
        o["status"] = "waiting"
        save_data(data)
        bot.reply_to(message, f"❌ #{oid} не подтверждён")
        try:
            bot.send_message(
                int(o["user_id"]),
                f"❌ По заказу <b>#{oid}</b> оплата не найдена. Проверьте перевод и нажмите «Я оплатил».",
                reply_markup=kb_after_qr(),
            )
        except Exception:
            pass


# ---------- нижнее меню (текст кнопок) ----------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    register(message.from_user)
    uid = message.from_user.id
    text = (message.text or "").strip()
    st = get_state(uid)
    admin = is_admin(uid)
    data = load_data()

    # --- главные кнопки ---
    if text in ("🛍 Каталог", "Каталог"):
        set_state(uid, screen="cats", cat=None, pid=None)
        bot.send_message(message.chat.id, "Выберите категорию 👇", reply_markup=kb_cats())
        return

    if text in ("📦 Мои заказы", "Мои заказы"):
        mine = [o for o in data["orders"].values() if o.get("user_id") == uid]
        mine.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        set_state(uid, screen="home")
        if not mine:
            bot.send_message(message.chat.id, "Заказов пока нет.", reply_markup=kb_home(admin))
            return
        lines = []
        for o in mine[:10]:
            lines.append(
                f"#{o['id']} · {o.get('status')} · {o.get('product_name')} — {money(o.get('price'))}"
            )
        bot.send_message(message.chat.id, "<b>Ваши заказы</b>\n" + "\n".join(lines), reply_markup=kb_home(admin))
        return

    if text in ("💳 Реквизиты", "Реквизиты"):
        set_state(uid, screen="home")
        bot.send_message(
            message.chat.id,
            f"💳 <b>Реквизиты</b>\n\n"
            f"Получатель: <b>{PAYEE_NAME}</b>\n"
            f"Телефон: <code>{PAYEE_PHONE}</code>\n\n"
            f"В комментарии к переводу укажите номер заказа.",
            reply_markup=kb_home(admin),
        )
        return

    if text in ("ℹ️ Помощь", "Помощь"):
        set_state(uid, screen="home")
        bot.send_message(
            message.chat.id,
            "1) Каталог → категория → товар\n"
            "2) «Купить / QR» — придёт QR и цена\n"
            "3) Перевод на номер, в комментарии #заказ\n"
            "4) «Я оплатил» — ждёте подтверждения",
            reply_markup=kb_home(admin),
        )
        return

    if text in ("🏠 Меню", "Меню", "◀️ Назад") and st.get("screen") in ("home", "pay", None):
        set_state(uid, screen="home", cat=None, pid=None)
        bot.send_message(message.chat.id, "Меню 👇", reply_markup=kb_home(admin))
        return

    if text == "⚙️ Админ" and admin:
        bot.send_message(
            message.chat.id,
            "⚙️ /list /add /del /setprice /stock /orders /payok /payno",
            reply_markup=kb_home(True),
        )
        return

    # --- назад к категориям ---
    if text in ("◀️ Назад", "◀️ К категориям"):
        set_state(uid, screen="cats", cat=None, pid=None)
        bot.send_message(message.chat.id, "Категории 👇", reply_markup=kb_cats())
        return

    if text == "🏠 Меню":
        set_state(uid, screen="home", cat=None, pid=None)
        bot.send_message(message.chat.id, "Меню 👇", reply_markup=kb_home(admin))
        return

    if text == "◀️ К товарам":
        cat = st.get("cat")
        if not cat:
            set_state(uid, screen="cats")
            bot.send_message(message.chat.id, "Категории 👇", reply_markup=kb_cats())
            return
        set_state(uid, screen="prods", pid=None)
        bot.send_message(message.chat.id, f"{cat} 👇", reply_markup=kb_products(cat))
        return

    # --- выбор категории ---
    if text.startswith("📁 "):
        cat = text[2:].strip()
        if cat not in categories():
            bot.send_message(message.chat.id, "Нет такой категории", reply_markup=kb_cats())
            return
        set_state(uid, screen="prods", cat=cat, pid=None)
        bot.send_message(message.chat.id, f"<b>{cat}</b> — выберите товар 👇", reply_markup=kb_products(cat))
        return

    # --- выбор товара по кнопке ---
    prod = find_product_by_button(text)
    if prod and st.get("screen") in ("prods", "item", "cats", "home"):
        set_state(uid, screen="item", pid=prod["id"], cat=prod.get("cat") or st.get("cat"))
        bot.send_message(
            message.chat.id,
            f"<b>{prod['name']}</b>\n"
            f"Категория: {prod.get('cat')}\n"
            f"Цена: <b>{money(prod['price'])}</b>\n"
            f"Остаток: {prod.get('stock', 0)}\n"
            f"{prod.get('desc') or ''}\n\n"
            f"Дальше 👇",
            reply_markup=kb_product_actions(),
        )
        return

    # --- купить ---
    if text == "✅ Купить / QR":
        pid = st.get("pid")
        p = data["products"].get(pid) if pid else None
        if not p:
            bot.send_message(message.chat.id, "Сначала выберите товар в каталоге.", reply_markup=kb_home(admin))
            return
        if int(p.get("stock") or 0) <= 0:
            bot.send_message(message.chat.id, "Нет в наличии.", reply_markup=kb_home(admin))
            return

        order_id = uuid.uuid4().hex[:8].upper()
        order = {
            "id": order_id,
            "product_id": pid,
            "product_name": p["name"],
            "price": p["price"],
            "user_id": uid,
            "user_name": f"{message.from_user.first_name or ''} @{message.from_user.username or ''}".strip(),
            "status": "waiting",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        data["orders"][order_id] = order
        data["products"][pid]["stock"] = int(p.get("stock") or 0) - 1
        save_data(data)
        set_state(uid, screen="pay", order_id=order_id)

        payload = (
            f"Оплата канцтовары\n"
            f"Получатель: {PAYEE_NAME}\n"
            f"Телефон: {PAYEE_PHONE}\n"
            f"Сумма: {p['price']} {CURRENCY}\n"
            f"Товар: {p['name']}\n"
            f"Заказ: #{order_id}\n"
            f"Комментарий: #{order_id}"
        )
        qr_buf = make_qr(payload)
        caption = (
            f"🧾 <b>Заказ #{order_id}</b>\n"
            f"Товар: <b>{p['name']}</b>\n"
            f"Цена: <b>{money(p['price'])}</b>\n\n"
            f"👤 {PAYEE_NAME}\n"
            f"📱 <code>{PAYEE_PHONE}</code>\n\n"
            f"Переведите и в комментарии укажите <b>#{order_id}</b>\n"
            f"Потом нажмите «Я оплатил» 👇"
        )
        bot.send_photo(message.chat.id, qr_buf, caption=caption, reply_markup=kb_after_qr())
        notify_admins(
            f"🛒 Заказ #{order_id}\n{p['name']} — {money(p['price'])}\n"
            f"{order['user_name']} (<code>{uid}</code>)\n"
            f"/payok {order_id} или /payno {order_id}"
        )
        return

    # --- я оплатил ---
    if text == "✅ Я оплатил":
        oid = st.get("order_id")
        data = load_data()
        o = data["orders"].get(oid) if oid else None
        if not o:
            # последний waiting заказ пользователя
            mine = [
                x for x in data["orders"].values()
                if x.get("user_id") == uid and x.get("status") in ("waiting", "checking")
            ]
            mine.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            o = mine[0] if mine else None
            oid = o["id"] if o else None
        if not o:
            bot.send_message(message.chat.id, "Нет активного заказа. Сделайте покупку из каталога.", reply_markup=kb_home(admin))
            return
        o["status"] = "checking"
        o["claimed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_data(data)
        bot.send_message(
            message.chat.id,
            f"🔎 Заказ <b>#{oid}</b> на проверке. Ожидайте подтверждения.",
            reply_markup=kb_home(admin),
        )
        notify_admins(
            f"🔎 Оплата по #{oid}?\n{o.get('product_name')} — {money(o.get('price'))}\n"
            f"{o.get('user_name')}\n/payok {oid} · /payno {oid}"
        )
        set_state(uid, screen="home")
        return

    if text == "🛍 В каталог":
        set_state(uid, screen="cats", cat=None, pid=None)
        bot.send_message(message.chat.id, "Категории 👇", reply_markup=kb_cats())
        return

    # fallback
    bot.send_message(
        message.chat.id,
        "Выберите пункт в меню внизу 👇",
        reply_markup=kb_home(admin),
    )


def main():
    print("Shop bot (bottom keyboard) starting...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    for a in ADMIN_IDS:
        try:
            bot.send_message(
                a,
                "✏️ Бот канцтоваров перезапущен.\nМеню снизу экрана.\n/start",
                reply_markup=kb_home(True),
            )
        except Exception as e:
            print(e)
    bot.infinity_polling(timeout=60, long_polling_timeout=40, skip_pending=True)


if __name__ == "__main__":
    main()
