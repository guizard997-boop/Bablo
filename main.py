
# -*- coding: utf-8 -*-
"""
Бот-магазин канцтоваров + оплата QR
Токен: 8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY
Admin: 8569472160
Реквизиты: Абдумалик К. · +996 220 979 346

Клиент: каталог → товар → QR + цена
Админ: /add /del /list /setprice /stock
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
CURRENCY = "KGS"  # канцтовары обычно в сомах; можно USD

DATA_FILE = "shop_data.json"

# Стартовый каталог канцтоваров (админ может менять)
DEFAULT_PRODUCTS = [
    {"id": "p1", "name": "Ручка шариковая синяя", "price": 25, "cat": "Ручки", "stock": 100, "desc": "Классическая шариковая ручка"},
    {"id": "p2", "name": "Ручка гелевая чёрная", "price": 40, "cat": "Ручки", "stock": 80, "desc": "Гелевая, мягкое письмо"},
    {"id": "p3", "name": "Карандаш HB", "price": 15, "cat": "Карандаши", "stock": 150, "desc": "Простой карандаш HB"},
    {"id": "p4", "name": "Набор карандашей 12 шт", "price": 120, "cat": "Карандаши", "stock": 40, "desc": "Цветные карандаши 12 цветов"},
    {"id": "p5", "name": "Тетрадь 12 л. клетка", "price": 30, "cat": "Тетради", "stock": 200, "desc": "Школьная тетрадь"},
    {"id": "p6", "name": "Тетрадь 48 л. клетка", "price": 55, "cat": "Тетради", "stock": 120, "desc": "Тетрадь 48 листов"},
    {"id": "p7", "name": "Блокнот А5", "price": 150, "cat": "Тетради", "stock": 50, "desc": "Блокнот на пружине А5"},
    {"id": "p8", "name": "Ластик", "price": 20, "cat": "Мелочи", "stock": 100, "desc": "Мягкий ластик"},
    {"id": "p9", "name": "Линейка 20 см", "price": 25, "cat": "Мелочи", "stock": 90, "desc": "Пластиковая линейка"},
    {"id": "p10", "name": "Степлер + скобы", "price": 180, "cat": "Офис", "stock": 30, "desc": "Степлер мини + скобы"},
    {"id": "p11", "name": "Папка-скоросшиватель", "price": 45, "cat": "Офис", "stock": 60, "desc": "Папка для документов"},
    {"id": "p12", "name": "Клей-карандаш", "price": 50, "cat": "Мелочи", "stock": 70, "desc": "Клей-карандаш 15 г"},
]

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def load_data():
    empty = {
        "products": {p["id"]: p for p in DEFAULT_PRODUCTS},
        "users": {},
        "orders": {},
        "meta": {},
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
    if n == int(n):
        return f"{int(n)} {CURRENCY}"
    return f"{n:.2f} {CURRENCY}"


def categories(products):
    cats = {}
    for p in products.values():
        if int(p.get("stock") or 0) <= 0:
            continue
        c = p.get("cat") or "Другое"
        cats.setdefault(c, []).append(p)
    return cats


def main_menu_kb(admin=False):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("🛍 Каталог", callback_data="menu:catalog"))
    kb.row(types.InlineKeyboardButton("📦 Мои заказы", callback_data="menu:orders"))
    kb.row(types.InlineKeyboardButton("💳 Реквизиты", callback_data="menu:payinfo"))
    if admin:
        kb.row(types.InlineKeyboardButton("⚙️ Админ", callback_data="menu:admin"))
    return kb


def catalog_kb():
    data = load_data()
    cats = categories(data["products"])
    kb = types.InlineKeyboardMarkup()
    for cat in sorted(cats.keys()):
        kb.add(types.InlineKeyboardButton(f"📁 {cat} ({len(cats[cat])})", callback_data=f"cat:{cat}"))
    kb.row(types.InlineKeyboardButton("◀️ Меню", callback_data="menu:home"))
    return kb


def products_kb(cat):
    data = load_data()
    items = [
        p for p in data["products"].values()
        if (p.get("cat") or "Другое") == cat and int(p.get("stock") or 0) > 0
    ]
    items.sort(key=lambda x: x.get("name") or "")
    kb = types.InlineKeyboardMarkup()
    for p in items:
        kb.add(
            types.InlineKeyboardButton(
                f"{p['name']} — {money(p['price'])}",
                callback_data=f"prod:{p['id']}",
            )
        )
    kb.row(types.InlineKeyboardButton("◀️ Каталог", callback_data="menu:catalog"))
    return kb


def product_kb(pid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Купить / QR", callback_data=f"buy:{pid}"),
    )
    kb.row(types.InlineKeyboardButton("◀️ Назад", callback_data="menu:catalog"))
    return kb


def make_qr_png_bytes(text):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "pay_qr.png"
    return buf


def payment_qr_payload(order_id, product_name, price):
    """Текст внутри QR — реквизиты + заказ (для сканера/ручного перевода)."""
    return (
        f"Оплата канцтовары\n"
        f"Получатель: {PAYEE_NAME}\n"
        f"Телефон: {PAYEE_PHONE}\n"
        f"Сумма: {price} {CURRENCY}\n"
        f"Товар: {product_name}\n"
        f"Заказ: #{order_id}\n"
        f"Комментарий к переводу: #{order_id}"
    )


def notify_admins(text, reply_markup=None):
    for a in ADMIN_IDS:
        try:
            bot.send_message(a, text, reply_markup=reply_markup)
        except Exception as e:
            print("admin notify", e)


# ---------- commands ----------
@bot.message_handler(commands=["start", "help", "menu"])
def cmd_start(message):
    register(message.from_user)
    admin = is_admin(message.from_user.id)
    text = (
        "✏️ <b>Канцтовары — магазин</b>\n\n"
        "Выберите товар в каталоге → получите <b>цену и QR</b> для оплаты.\n"
        f"Оплата: {PAYEE_NAME}, <code>{PAYEE_PHONE}</code>\n"
    )
    if admin:
        text += (
            "\n<b>Админ:</b>\n"
            "<code>/add Название | цена | категория | описание</code>\n"
            "<code>/del ID</code> · <code>/list</code> · <code>/orders</code>\n"
            "<code>/setprice ID цена</code> · <code>/stock ID кол-во</code>\n"
        )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb(admin))


@bot.message_handler(commands=["list"])
def cmd_list(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    lines = ["📦 <b>Товары</b>\n"]
    for p in sorted(data["products"].values(), key=lambda x: (x.get("cat") or "", x.get("name") or "")):
        lines.append(
            f"<code>{p['id']}</code> · {p.get('cat')} · <b>{p['name']}</b> — "
            f"{money(p['price'])} · остаток {p.get('stock', 0)}"
        )
    text = "\n".join(lines) if len(lines) > 1 else "Пусто. /add ..."
    # chunk
    buf = ""
    for line in lines:
        if len(buf) + len(line) > 3500:
            bot.send_message(message.chat.id, buf)
            buf = line + "\n"
        else:
            buf += line + "\n"
    if buf:
        bot.send_message(message.chat.id, buf)


@bot.message_handler(commands=["add"])
def cmd_add(message):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").replace("/add", "", 1).strip()
    # name | price | cat | desc
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Формат:\n<code>/add Ручка синяя | 25 | Ручки | Шариковая</code>\n"
            "Минимум: название | цена",
        )
        return
    name = parts[0]
    try:
        price = float(parts[1].replace(",", ".").replace(" ", ""))
    except ValueError:
        bot.reply_to(message, "Цена — число.")
        return
    cat = parts[2] if len(parts) > 2 and parts[2] else "Другое"
    desc = parts[3] if len(parts) > 3 else ""
    pid = "p" + uuid.uuid4().hex[:6]
    data = load_data()
    data["products"][pid] = {
        "id": pid,
        "name": name,
        "price": price,
        "cat": cat,
        "stock": 50,
        "desc": desc,
    }
    save_data(data)
    bot.reply_to(message, f"✅ Добавлено <code>{pid}</code>\n{name} — {money(price)} · {cat}")


@bot.message_handler(commands=["del"])
def cmd_del(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "<code>/del ID</code>")
        return
    pid = parts[1].strip()
    data = load_data()
    if pid not in data["products"]:
        bot.reply_to(message, "Нет такого ID. /list")
        return
    name = data["products"][pid].get("name")
    del data["products"][pid]
    save_data(data)
    bot.reply_to(message, f"🗑 Удалён {name} (<code>{pid}</code>)")


@bot.message_handler(commands=["setprice"])
def cmd_setprice(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "<code>/setprice ID 99</code>")
        return
    pid = parts[1].strip()
    try:
        price = float(parts[2].replace(",", "."))
    except ValueError:
        bot.reply_to(message, "Цена — число.")
        return
    data = load_data()
    if pid not in data["products"]:
        bot.reply_to(message, "Нет ID")
        return
    data["products"][pid]["price"] = price
    save_data(data)
    bot.reply_to(message, f"Цена {data['products'][pid]['name']}: <b>{money(price)}</b>")


@bot.message_handler(commands=["stock"])
def cmd_stock(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "<code>/stock ID 100</code>")
        return
    pid = parts[1].strip()
    try:
        stock = int(parts[2])
    except ValueError:
        bot.reply_to(message, "Число.")
        return
    data = load_data()
    if pid not in data["products"]:
        bot.reply_to(message, "Нет ID")
        return
    data["products"][pid]["stock"] = stock
    save_data(data)
    bot.reply_to(message, f"Остаток {data['products'][pid]['name']}: <b>{stock}</b>")


@bot.message_handler(commands=["orders"])
def cmd_orders(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    orders = list(data["orders"].values())
    orders.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    if not orders:
        bot.reply_to(message, "Заказов нет.")
        return
    for o in orders[:20]:
        kb = None
        if o.get("status") == "waiting":
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("✅ Оплачен", callback_data=f"payok:{o['id']}"),
                types.InlineKeyboardButton("❌ Нет", callback_data=f"payno:{o['id']}"),
            )
        bot.send_message(
            message.chat.id,
            f"🧾 <b>#{o['id']}</b> · {o.get('status')}\n"
            f"{o.get('product_name')} — {money(o.get('price'))}\n"
            f"Клиент: {o.get('user_name')} (<code>{o.get('user_id')}</code>)\n"
            f"{o.get('created_at')}",
            reply_markup=kb,
        )


# ---------- callbacks ----------
@bot.callback_query_handler(func=lambda c: True)
def on_cb(call):
    try:
        raw = (call.data or "").strip()
        uid = call.from_user.id
        register(call.from_user)
        data = load_data()

        def ans(text=None, alert=False):
            try:
                bot.answer_callback_query(call.id, text=text, show_alert=alert)
            except Exception:
                pass

        if raw == "menu:home":
            ans()
            bot.send_message(
                call.message.chat.id,
                "Главное меню:",
                reply_markup=main_menu_kb(is_admin(uid)),
            )
            return

        if raw == "menu:catalog":
            ans()
            bot.send_message(call.message.chat.id, "🛍 <b>Каталог</b> — выберите категорию:", reply_markup=catalog_kb())
            return

        if raw == "menu:payinfo":
            ans()
            bot.send_message(
                call.message.chat.id,
                f"💳 <b>Реквизиты</b>\n\n"
                f"Получатель: <b>{PAYEE_NAME}</b>\n"
                f"Телефон: <code>{PAYEE_PHONE}</code>\n"
                f"В комментарии к переводу укажите <b>номер заказа</b>.",
            )
            return

        if raw == "menu:orders":
            ans()
            mine = [o for o in data["orders"].values() if o.get("user_id") == uid]
            mine.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            if not mine:
                bot.send_message(call.message.chat.id, "У вас пока нет заказов.", reply_markup=main_menu_kb(is_admin(uid)))
                return
            for o in mine[:10]:
                bot.send_message(
                    call.message.chat.id,
                    f"🧾 <b>#{o['id']}</b>\n"
                    f"{o.get('product_name')} — {money(o.get('price'))}\n"
                    f"Статус: <b>{o.get('status')}</b>\n"
                    f"{o.get('created_at')}",
                )
            return

        if raw == "menu:admin":
            if not is_admin(uid):
                ans("Только админ", True)
                return
            ans()
            bot.send_message(
                call.message.chat.id,
                "⚙️ <b>Админ</b>\n"
                "/list — товары\n"
                "/add Название | цена | категория | описание\n"
                "/del ID\n"
                "/setprice ID цена\n"
                "/stock ID число\n"
                "/orders — заказы",
            )
            return

        if raw.startswith("cat:"):
            cat = raw[4:]
            ans()
            bot.send_message(
                call.message.chat.id,
                f"📁 <b>{cat}</b>",
                reply_markup=products_kb(cat),
            )
            return

        if raw.startswith("prod:"):
            pid = raw[5:]
            p = data["products"].get(pid)
            if not p:
                ans("Нет товара", True)
                return
            ans()
            bot.send_message(
                call.message.chat.id,
                f"<b>{p['name']}</b>\n"
                f"Категория: {p.get('cat')}\n"
                f"Цена: <b>{money(p['price'])}</b>\n"
                f"Остаток: {p.get('stock', 0)}\n"
                f"{p.get('desc') or ''}",
                reply_markup=product_kb(pid),
            )
            return

        if raw.startswith("buy:"):
            pid = raw[4:]
            p = data["products"].get(pid)
            if not p:
                ans("Нет товара", True)
                return
            if int(p.get("stock") or 0) <= 0:
                ans("Нет в наличии", True)
                return

            order_id = uuid.uuid4().hex[:8].upper()
            order = {
                "id": order_id,
                "product_id": pid,
                "product_name": p["name"],
                "price": p["price"],
                "user_id": uid,
                "user_name": f"{call.from_user.first_name or ''} @{call.from_user.username or ''}".strip(),
                "status": "waiting",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            data["orders"][order_id] = order
            # stock reserve soft
            data["products"][pid]["stock"] = int(p.get("stock") or 0) - 1
            save_data(data)

            ans("QR отправлен")
            payload = payment_qr_payload(order_id, p["name"], p["price"])
            qr_buf = make_qr_png_bytes(payload)

            caption = (
                f"🧾 <b>Заказ #{order_id}</b>\n\n"
                f"Товар: <b>{p['name']}</b>\n"
                f"Цена: <b>{money(p['price'])}</b>\n\n"
                f"👤 {PAYEE_NAME}\n"
                f"📱 <code>{PAYEE_PHONE}</code>\n\n"
                f"1) Отсканируйте QR или переведите на номер\n"
                f"2) В комментарии: <b>#{order_id}</b>\n"
                f"3) Нажмите «Я оплатил»"
            )
            kb = types.InlineKeyboardMarkup()
            kb.row(types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"i_paid:{order_id}"))
            kb.row(types.InlineKeyboardButton("🛍 В каталог", callback_data="menu:catalog"))

            bot.send_photo(call.message.chat.id, qr_buf, caption=caption, reply_markup=kb)

            notify_admins(
                f"🛒 Новый заказ <b>#{order_id}</b>\n"
                f"{p['name']} — {money(p['price'])}\n"
                f"Клиент: {order['user_name']} (<code>{uid}</code>)"
            )
            return

        if raw.startswith("i_paid:"):
            oid = raw.split(":", 1)[1].upper()
            data = load_data()
            o = data["orders"].get(oid)
            if not o:
                ans("Заказ не найден", True)
                return
            if o.get("status") == "paid":
                ans("Уже подтверждён", True)
                return
            o["status"] = "checking"
            o["claimed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_data(data)
            ans("На проверке")
            bot.send_message(call.message.chat.id, f"🔎 Заказ #{oid} на проверке. Ожидайте подтверждения.")

            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("✅ Оплачен", callback_data=f"payok:{oid}"),
                types.InlineKeyboardButton("❌ Нет", callback_data=f"payno:{oid}"),
            )
            notify_admins(
                f"🔎 Клиент оплатил заказ <b>#{oid}</b>?\n"
                f"{o.get('product_name')} — {money(o.get('price'))}\n"
                f"{o.get('user_name')}",
                reply_markup=kb,
            )
            return

        if raw.startswith("payok:") or raw.startswith("payno:"):
            if not is_admin(uid):
                ans("Только админ", True)
                return
            oid = raw.split(":", 1)[1].upper()
            data = load_data()
            o = data["orders"].get(oid)
            if not o:
                ans("Нет заказа", True)
                return
            if raw.startswith("payok:"):
                o["status"] = "paid"
                o["paid_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_data(data)
                ans("Подтверждено")
                bot.send_message(call.message.chat.id, f"✅ Заказ #{oid} оплачен.")
                try:
                    bot.send_message(
                        int(o["user_id"]),
                        f"✅ Оплата по заказу <b>#{oid}</b> подтверждена!\n"
                        f"{o.get('product_name')} — {money(o.get('price'))}\n"
                        f"Спасибо за покупку.",
                    )
                except Exception:
                    pass
            else:
                o["status"] = "waiting"
                save_data(data)
                # вернуть stock если нужно — уже списали при buy; не возвращаем при reject
                ans("Отклонено")
                bot.send_message(call.message.chat.id, f"❌ Заказ #{oid}: оплата не найдена.")
                try:
                    bot.send_message(
                        int(o["user_id"]),
                        f"❌ По заказу <b>#{oid}</b> оплата не найдена.\n"
                        f"Проверьте перевод (сумма и комментарий #{oid}) и нажмите «Я оплатил» снова.",
                    )
                except Exception:
                    pass
            return

        ans()
    except Exception as e:
        print("callback error", e)
        try:
            bot.answer_callback_query(call.id, "Ошибка", show_alert=True)
        except Exception:
            pass


@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    register(message.from_user)
    if is_admin(message.from_user.id):
        bot.reply_to(message, "Меню: /start · товары: /list · добавить: /add")
    else:
        bot.reply_to(message, "Откройте /start → Каталог")


def main():
    print("Shop bot starting...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    notify_admins(
        "✏️ <b>Бот канцтоваров запущен</b>\n"
        f"Оплата: {PAYEE_NAME} · {PAYEE_PHONE}\n"
        "/start — меню · /list — товары · /add — добавить"
    )
    bot.infinity_polling(timeout=60, long_polling_timeout=40, skip_pending=True)


if __name__ == "__main__":
    main()
