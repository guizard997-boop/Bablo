from flask import Flask, request, redirect, url_for, flash, session, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
import os, uuid, json, requests, base64

_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mir-kancelyarii-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(_BASE, 'shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
try:
    from sqlalchemy.pool import NullPool
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'poolclass': NullPool}
except Exception:
    pass
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
UPLOAD_FOLDER = os.path.join(_BASE, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
db = SQLAlchemy(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def save_upload(file_storage):
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    name = f'{uuid.uuid4().hex}.{ext}'
    file_storage.save(os.path.join(UPLOAD_FOLDER, name))
    return f'/uploads/{name}'

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Новый')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, default='')

class BotState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    step = db.Column(db.String(50), default='idle')
    draft_name = db.Column(db.String(300), default='')
    draft_image = db.Column(db.String(500), default='')
    draft_price = db.Column(db.Float, default=0)
    draft_category_id = db.Column(db.Integer, nullable=True)

def get_setting(key, default=''):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default

def set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s:
        s.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()

def get_cart():
    return session.get('cart', {})

def cart_count():
    return sum(get_cart().values())

def cart_total():
    t = 0.0
    for pid, qty in get_cart().items():
        p = db.session.get(Product, int(pid))
        if p:
            t += p.price * qty
    return t

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

ADMIN_PASSWORD = 'admin123'
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY')
ADMIN_IDS = [x.strip() for x in os.environ.get('TELEGRAM_ADMIN_IDS', '8569472160').split(',') if x.strip()]
HF_TOKEN = os.environ.get('HF_TOKEN', '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').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
DEFAULT_SITE = os.environ.get('SITE_URL', 'https://mircancelyarii-production.up.railway.app').rstrip('/')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

LAYOUT = '''<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }} — Мир канцелярии</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{brand:'#6C5CE7',accent:'#FF6B35',soft:'#F8F7FF'}}}}</script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
body{font-family:'Nunito',system-ui,sans-serif}.btn-g{background:linear-gradient(135deg,#6C5CE7,#A66CFF)}
.btn-o{background:linear-gradient(135deg,#FF6B35,#FF8F66)}</style>
</head><body class="bg-white min-h-screen flex flex-col">
<header class="sticky top-0 z-50 bg-white border-b shadow-sm">
<div class="max-w-6xl mx-auto px-4 h-14 flex items-center gap-3">
<a href="/" class="font-extrabold text-brand text-lg">МИР КАНЦЕЛЯРИИ</a>
<a href="/catalog" class="text-sm bg-brand text-white px-3 py-1.5 rounded-xl font-semibold">Каталог</a>
<form action="/catalog" method="get" class="flex-1 max-w-md">
<input name="q" value="{{ request.args.get('q','') }}" placeholder="Поиск..." class="w-full border rounded-full px-4 py-2 text-sm">
</form>
<a href="/cart" class="relative p-2"><i class="fas fa-shopping-bag text-xl"></i>
{% if cart_count %}<span class="absolute -top-1 -right-1 bg-accent text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">{{ cart_count }}</span>{% endif %}
</a></div></header>
{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}
<div class="max-w-6xl mx-auto px-4 mt-2">{% for c,m in messages %}<div class="p-2 rounded-xl text-sm {% if c=='success' %}bg-green-50 text-green-700{% else %}bg-red-50 text-red-700{% endif %}">{{ m }}</div>{% endfor %}</div>{% endif %}{% endwith %}
<main class="flex-1">{{ content|safe }}</main>
<footer class="bg-gray-900 text-gray-500 text-center text-xs py-4 mt-10">© 2026 Мир канцелярии</footer>
</body></html>'''

def page(title, content):
    from flask import get_flashed_messages, request as req
    return render_template_string(LAYOUT, title=title, content=content, cart_count=cart_count(),
                                  get_flashed_messages=get_flashed_messages, request=req)

def product_card(p):
    img = p.image_url or 'https://via.placeholder.com/400'
    return f'''<div class="bg-white rounded-2xl border overflow-hidden shadow-sm">
<a href="/product/{p.id}"><img src="{img}" class="w-full aspect-square object-cover bg-gray-50" onerror="this.src='https://via.placeholder.com/400'"></a>
<div class="p-3"><a href="/product/{p.id}" class="font-bold text-sm hover:text-brand">{p.name}</a>
<div class="flex justify-between items-center mt-2">
<span class="font-extrabold text-brand">{p.price:,.0f} сом</span>
<form action="/cart/add/{p.id}" method="post"><button class="w-8 h-8 rounded-xl btn-g text-white text-xs"><i class="fas fa-plus"></i></button></form>
</div></div></div>'''

@app.route('/')
def index():
    products = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    cards = ''.join(product_card(p) for p in products) or '<p class="col-span-full text-center text-gray-400 py-12">Каталог пока пуст</p>'
    content = f'''<div class="max-w-6xl mx-auto px-4 py-10">
<h1 class="text-3xl font-extrabold mb-2">Мир канцелярии</h1>
<p class="text-gray-500 mb-6">Всё для учёбы и творчества. Предзаказ по Кыргызстану.</p>
<a href="/catalog" class="btn-o text-white font-bold px-5 py-2.5 rounded-full inline-block mb-10">В каталог</a>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4">{cards}</div></div>'''
    return page('Главная', content)

@app.route('/catalog')
def catalog():
    q = request.args.get('q', '').strip()
    query = Product.query
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    products = query.order_by(Product.created_at.desc()).all()
    cards = ''.join(product_card(p) for p in products) or '<p class="col-span-full text-center text-gray-400 py-12">Ничего не найдено</p>'
    content = f'''<div class="max-w-6xl mx-auto px-4 py-8">
<form method="get" class="mb-6"><input name="q" value="{q}" placeholder="Поиск..." class="w-full max-w-md border rounded-full px-4 py-2"></form>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4">{cards}</div></div>'''
    return page('Каталог', content)

@app.route('/product/<int:pid>')
def product_detail(pid):
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    img = p.image_url or 'https://via.placeholder.com/600'
    content = f'''<div class="max-w-6xl mx-auto px-4 py-8 grid md:grid-cols-2 gap-8">
<img src="{img}" class="w-full rounded-2xl aspect-square object-cover bg-gray-50">
<div><h1 class="text-2xl font-extrabold mb-2">{p.name}</h1>
<div class="text-2xl font-extrabold text-brand mb-4">{p.price:,.0f} сом</div>
<p class="text-gray-500 mb-6">{p.description or ''}</p>
<form action="/cart/add/{p.id}" method="post" class="flex gap-2">
<input type="number" name="quantity" value="1" min="1" class="w-20 border rounded-xl px-2 py-2 text-center">
<button class="btn-g text-white font-bold px-6 py-2 rounded-xl">В предзаказ</button>
</form></div></div>'''
    return page(p.name, content)


@app.route('/cart')
def cart():
    items_html, total = '', 0.0
    for pid, qty in get_cart().items():
        p = db.session.get(Product, int(pid))
        if not p:
            continue
        sub = p.price * qty
        total += sub
        items_html += f'''<div class="flex gap-3 items-center border-b p-3">
<img src="{p.image_url or ''}" class="w-14 h-14 rounded-lg object-cover bg-gray-50">
<div class="flex-1 font-semibold text-sm">{p.name}</div>
<form action="/cart/update/{p.id}" method="post" class="flex gap-1">
<input type="number" name="quantity" value="{qty}" min="0" class="w-14 border rounded px-1 text-center text-sm">
<button class="text-brand text-xs">OK</button></form>
<span class="font-bold text-sm w-16 text-right">{sub:,.0f}</span>
<a href="/cart/remove/{p.id}" class="text-red-400 text-sm">✕</a></div>'''
    if items_html:
        content = f'''<div class="max-w-xl mx-auto px-4 py-8"><h1 class="text-xl font-extrabold mb-4">Предзаказ</h1>
<div class="border rounded-2xl overflow-hidden">{items_html}
<div class="p-4 flex justify-between items-center bg-soft">
<span class="font-extrabold text-lg">{total:,.0f} сом</span>
<a href="/checkout" class="btn-o text-white font-bold px-4 py-2 rounded-xl">Оформить</a>
</div></div></div>'''
    else:
        content = '<div class="text-center py-16 text-gray-400"><p class="mb-4">Предзаказ пуст</p><a href="/catalog" class="text-brand font-bold">В каталог</a></div>'
    return page('Предзаказ', content)

@app.route('/cart/add/<int:pid>', methods=['POST'])
def add_to_cart(pid):
    p = db.session.get(Product, pid)
    if not p:
        return redirect(url_for('catalog'))
    qty = int(request.form.get('quantity', 1) or 1)
    cart = get_cart()
    cart[str(pid)] = cart.get(str(pid), 0) + qty
    session['cart'] = cart
    flash(f'«{p.name}» добавлен', 'success')
    return redirect(request.referrer or url_for('catalog'))

@app.route('/cart/update/<int:pid>', methods=['POST'])
def update_cart(pid):
    qty = int(request.form.get('quantity', 1) or 0)
    cart = get_cart()
    if qty <= 0:
        cart.pop(str(pid), None)
    else:
        cart[str(pid)] = qty
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:pid>')
def remove_from_cart(pid):
    cart = get_cart()
    cart.pop(str(pid), None)
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not get_cart():
        flash('Предзаказ пуст', 'danger')
        return redirect(url_for('catalog'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        if not name or not phone:
            flash('Укажите имя и телефон', 'danger')
            return redirect(url_for('checkout'))
        order = Order(customer_name=name, customer_phone=phone, total_price=cart_total())
        db.session.add(order)
        db.session.flush()
        for pid, qty in get_cart().items():
            p = db.session.get(Product, int(pid))
            if p:
                db.session.add(OrderItem(order_id=order.id, product_id=p.id, quantity=qty, price=p.price))
        db.session.commit()
        session['cart'] = {}
        flash(f'Предзаказ #{order.id} принят!', 'success')
        return redirect(url_for('index'))
    content = '''<div class="max-w-md mx-auto px-4 py-8"><h1 class="text-xl font-extrabold mb-4">Оставить предзаказ</h1>
<form method="post" class="space-y-3 border rounded-2xl p-5">
<input name="name" required placeholder="Имя" class="w-full border rounded-xl px-4 py-2.5">
<input name="phone" required placeholder="+996 ..." class="w-full border rounded-xl px-4 py-2.5">
<button class="w-full btn-o text-white font-bold py-3 rounded-xl">Отправить</button>
</form></div>'''
    return page('Предзаказ', content)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Неверный пароль', 'danger')
    content = '''<div class="min-h-[50vh] flex items-center justify-center px-4">
<form method="post" class="border rounded-2xl p-6 w-full max-w-xs text-center space-y-3">
<h1 class="font-extrabold text-lg">Админ</h1>
<input type="password" name="password" required class="w-full border rounded-xl px-4 py-2 text-center" placeholder="Пароль">
<button class="w-full btn-g text-white font-bold py-2.5 rounded-xl">Войти</button>
</form></div>'''
    return page('Вход', content)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    pc = Product.query.count()
    oc = Order.query.count()
    content = f'''<div class="max-w-3xl mx-auto px-4 py-8">
<div class="flex gap-3 text-sm mb-6">
<a href="/admin/dashboard" class="font-bold text-brand">Дашборд</a>
<a href="/admin/products" class="text-gray-500">Товары</a>
<a href="/admin/orders" class="text-gray-500">Заявки</a>
<a href="/admin/logout" class="text-red-500 ml-auto">Выйти</a></div>
<h1 class="text-xl font-extrabold mb-4">Дашборд</h1>
<p>Товаров: <b>{pc}</b> · Заявок: <b>{oc}</b></p></div>'''
    return page('Админ', content)

@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    rows = ''.join(
        f'<tr class="border-t"><td class="px-3 py-2 text-sm">{p.name}</td><td class="px-3 py-2">{p.price:,.0f}</td>'
        f'<td class="px-3 py-2"><a href="/admin/products/edit/{p.id}" class="text-brand text-sm">Изм.</a> '
        f'<form action="/admin/products/delete/{p.id}" method="post" class="inline" onsubmit="return confirm(\'Удалить?\')">'
        f'<button class="text-red-400 text-sm">Удал.</button></form></td></tr>'
        for p in products
    )
    content = f'''<div class="max-w-3xl mx-auto px-4 py-8">
<a href="/admin/dashboard" class="text-sm text-brand">← Назад</a>
<div class="flex justify-between my-4"><h1 class="text-xl font-extrabold">Товары</h1>
<a href="/admin/products/add" class="btn-g text-white text-sm font-bold px-3 py-1.5 rounded-xl">+ Добавить</a></div>
<table class="w-full border rounded-xl overflow-hidden text-sm"><tbody>{rows or "<tr><td class='p-6 text-center text-gray-400'>Нет товаров</td></tr>"}</tbody></table></div>'''
    return page('Товары', content)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@app.route('/admin/products/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_product_form(pid=None):
    p = db.session.get(Product, pid) if pid else None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        try:
            price = float(request.form.get('price', 0) or 0)
        except ValueError:
            price = 0
        if not name or price <= 0:
            flash('Название и цена обязательны', 'danger')
            return redirect(request.url)
        uploaded = save_upload(request.files.get('photo'))
        if p:
            p.name = name
            p.description = request.form.get('description', '')
            p.price = price
            if uploaded:
                p.image_url = uploaded
        else:
            db.session.add(Product(name=name, description=request.form.get('description', ''),
                                   price=price, image_url=uploaded or ''))
        db.session.commit()
        flash('Сохранено', 'success')
        return redirect(url_for('admin_products'))
    content = f'''<div class="max-w-md mx-auto px-4 py-8">
<form method="post" enctype="multipart/form-data" class="border rounded-2xl p-5 space-y-3">
<input name="name" required value="{p.name if p else ''}" placeholder="Название" class="w-full border rounded-xl px-4 py-2">
<textarea name="description" rows="2" placeholder="Описание" class="w-full border rounded-xl px-4 py-2">{p.description if p else ''}</textarea>
<input name="price" type="number" step="0.01" required value="{p.price if p else ''}" placeholder="Цена" class="w-full border rounded-xl px-4 py-2">
<input type="file" name="photo" accept="image/*" class="w-full text-sm">
<button class="btn-g text-white font-bold px-5 py-2 rounded-xl">Сохранить</button>
</form></div>'''
    return page('Товар', content)

@app.route('/admin/products/delete/<int:pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    p = db.session.get(Product, pid)
    if p:
        db.session.delete(p)
        db.session.commit()
    flash('Удалено', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    rows = ''.join(
        f'<tr class="border-t text-sm"><td class="px-3 py-2">#{o.id}</td><td class="px-3 py-2">{o.customer_name}</td>'
        f'<td class="px-3 py-2">{o.customer_phone}</td><td class="px-3 py-2">{o.total_price:,.0f}</td>'
        f'<td class="px-3 py-2">{o.status}</td></tr>' for o in orders
    )
    content = f'''<div class="max-w-3xl mx-auto px-4 py-8">
<a href="/admin/dashboard" class="text-sm text-brand">← Назад</a>
<h1 class="text-xl font-extrabold my-4">Заявки</h1>
<table class="w-full border rounded-xl"><tbody>{rows or "<tr><td class='p-6 text-center text-gray-400'>Нет заявок</td></tr>"}</tbody></table></div>'''
    return page('Заявки', content)

# ---------- TELEGRAM ----------
def tg_api(method, data=None):
    if not TELEGRAM_TOKEN:
        return None
    try:
        r = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}', json=data or {}, timeout=30)
        return r.json()
    except Exception as e:
        print('TG error', e)
        return None

def tg_send(chat_id, text):
    return tg_api('sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'})

def get_bot_state(chat_id):
    st = BotState.query.filter_by(chat_id=str(chat_id)).first()
    if not st:
        st = BotState(chat_id=str(chat_id), step='idle')
        db.session.add(st)
        db.session.commit()
    return st

def is_admin(user_id):
    if not ADMIN_IDS:
        return True
    return str(user_id) in ADMIN_IDS

def ai_describe_product(image_path):
    """HF (if token works) -> Gemini -> None"""
    cats = Category.query.order_by(Category.name).all()

    def match_cat(text):
        if not text or not cats:
            return None
        t = text.lower()
        rules = [
            (['карандаш', 'ручка', 'маркер', 'фломастер'], ['письмен']),
            (['тетрад', 'блокнот'], ['тетрад', 'блокнот']),
            (['краск', 'кист', 'рисун', 'творч'], ['творч', 'рисов']),
            (['школ', 'пенал', 'линейк'], ['школ']),
            (['офис', 'степлер'], ['офис']),
            (['подар'], ['подар']),
        ]
        for keys, parts in rules:
            if any(k in t for k in keys):
                for c in cats:
                    if any(p in c.name.lower() for p in parts):
                        return c.id
        return None

    hf = HF_TOKEN or os.environ.get('HUGGINGFACE_TOKEN', '').strip()
    if hf:
        try:
            with open(image_path, 'rb') as f:
                img_bytes = f.read()
            headers = {'Authorization': f'Bearer {hf}'}
            for model in ['Salesforce/blip-image-captioning-base', 'Salesforce/blip-image-captioning-large']:
                r = requests.post(f'https://api-inference.huggingface.co/models/{model}',
                                  headers=headers, data=img_bytes, timeout=60)
                if r.status_code == 503:
                    import time
                    time.sleep(2)
                    r = requests.post(f'https://api-inference.huggingface.co/models/{model}',
                                      headers=headers, data=img_bytes, timeout=90)
                if r.status_code != 200:
                    print('HF', r.status_code, r.text[:150])
                    continue
                data = r.json()
                caption = None
                if isinstance(data, list) and data:
                    caption = data[0].get('generated_text') or data[0].get('caption')
                elif isinstance(data, dict):
                    caption = data.get('generated_text')
                if caption:
                    name = caption.strip()
                    for pref in ['a photo of ', 'a picture of ', 'an image of ']:
                        if name.lower().startswith(pref):
                            name = name[len(pref):]
                    name = name[:200].strip()
                    if name:
                        name = name[0].upper() + name[1:]
                    return name, match_cat(name)
        except Exception as e:
            print('HF error', e)

    if GEMINI_KEY:
        try:
            with open(image_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
            ext = image_path.rsplit('.', 1)[-1].lower()
            mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                    'webp': 'image/webp'}.get(ext, 'image/jpeg')
            cat_list = ', '.join(f'{c.id}:{c.name}' for c in cats) or 'нет'
            prompt = (f'Канцтовары Кыргызстан. Ответь:\nНАЗВАНИЕ: 2-6 слов RU\nКАТЕГОРИЯ: id или 0\nКатегории: {cat_list}')
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}'
            payload = {'contents': [{'parts': [{'text': prompt}, {'inline_data': {'mime_type': mime, 'data': b64}}]}]}
            resp = requests.post(url, json=payload, timeout=45)
            data = resp.json()
            raw = data['candidates'][0]['content']['parts'][0]['text'].strip()
            name, cat_id = None, None
            for line in raw.splitlines():
                line = line.strip()
                if line.upper().startswith('НАЗВАНИЕ:'):
                    name = line.split(':', 1)[1].strip()
                elif line.upper().startswith('КАТЕГОРИЯ:'):
                    try:
                        cat_id = int(line.split(':', 1)[1].strip().split()[0])
                    except Exception:
                        cat_id = None
            if not name:
                name = raw.splitlines()[0][:200]
            if cat_id == 0 or (cat_id and not db.session.get(Category, cat_id)):
                cat_id = None
            if name:
                return name[:200], cat_id
        except Exception as e:
            print('Gemini error', e)
    return None, None

def download_tg_photo(file_id):
    info = tg_api('getFile', {'file_id': file_id})
    if not info or not info.get('ok'):
        return None
    file_path = info['result']['file_path']
    try:
        r = requests.get(f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}', timeout=60)
        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else 'jpg'
        if ext not in ALLOWED_EXT:
            ext = 'jpg'
        name = f'{uuid.uuid4().hex}.{ext}'
        full = os.path.join(UPLOAD_FOLDER, name)
        with open(full, 'wb') as f:
            f.write(r.content)
        return f'/uploads/{name}', full
    except Exception as e:
        print('download error', e)
        return None

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get('message') or update.get('edited_message')
    if not message:
        return 'ok', 200
    chat_id = message['chat']['id']
    user_id = message.get('from', {}).get('id')
    text = (message.get('text') or '').strip()
    if not is_admin(user_id):
        tg_send(chat_id, '⛔ Нет доступа')
        return 'ok', 200
    st = get_bot_state(chat_id)

    if text.startswith('/start'):
        st.step = 'idle'
        st.draft_name = ''
        st.draft_image = ''
        st.draft_price = 0
        st.draft_category_id = None
        db.session.commit()
        tg_send(chat_id, '👋 Бот «Мир канцелярии»\n\nОтправьте <b>фото</b> товара.\nПотом — цену числом.\n\n/cancel — отмена')
        return 'ok', 200

    if text.startswith('/cancel'):
        st.step = 'idle'
        st.draft_name = ''
        st.draft_image = ''
        st.draft_price = 0
        st.draft_category_id = None
        db.session.commit()
        tg_send(chat_id, '❌ Отменено')
        return 'ok', 200

    photos = message.get('photo')
    if photos:
        tg_send(chat_id, '🔍 Смотрю на фото...')
        result = download_tg_photo(photos[-1]['file_id'])
        if not result:
            tg_send(chat_id, 'Не удалось скачать фото')
            return 'ok', 200
        web_path, full_path = result
        name, cat_id = ai_describe_product(full_path)
        st.draft_image = web_path
        st.draft_category_id = cat_id
        if name:
            st.draft_name = name
            st.step = 'wait_price'
            db.session.commit()
            cat_info = ''
            if cat_id:
                c = db.session.get(Category, cat_id)
                if c:
                    cat_info = f'\nКатегория: <b>{c.name}</b>'
            tg_send(chat_id, f'✅ Похоже, это:\n<b>{name}</b>{cat_info}\n\nПришлите <b>цену</b> (число) или другое название.')
        else:
            st.draft_name = ''
            st.step = 'wait_name'
            db.session.commit()
            tg_send(chat_id, '📷 Фото получено.\nAI не распознал (токен HF мог истечь).\n\nНапишите <b>название</b> товара:')
        return 'ok', 200

    if st.step == 'wait_name' and text:
        st.draft_name = text[:200]
        st.step = 'wait_price'
        db.session.commit()
        tg_send(chat_id, f'Название: <b>{st.draft_name}</b>\n\nПришлите <b>цену</b> (число):')
        return 'ok', 200

    if st.step == 'wait_price' and text:
        try:
            price = float(text.replace('сом', '').replace(',', '.').strip())
            if price <= 0:
                raise ValueError()
        except ValueError:
            st.draft_name = text[:200]
            db.session.commit()
            tg_send(chat_id, f'Название: <b>{st.draft_name}</b>\n\nПришлите <b>цену</b> (число):')
            return 'ok', 200
        product = Product(
            name=st.draft_name or 'Товар',
            description='',
            price=price,
            image_url=st.draft_image or '',
            category_id=st.draft_category_id
        )
        db.session.add(product)
        st.step = 'idle'
        st.draft_name = ''
        st.draft_image = ''
        st.draft_price = 0
        st.draft_category_id = None
        db.session.commit()
        cat_name = ''
        if product.category_id:
            c = db.session.get(Category, product.category_id)
            if c:
                cat_name = f'\nКатегория: {c.name}'
        tg_send(chat_id, f'🎉 Добавлено!\n<b>{product.name}</b>\n{product.price:,.0f} сом{cat_name}\n\n{DEFAULT_SITE}/product/{product.id}')
        return 'ok', 200

    if text:
        tg_send(chat_id, 'Пришлите <b>фото</b> или /start')
    return 'ok', 200

@app.route('/setup-webhook')
def setup_webhook():
    site = os.environ.get('SITE_URL', DEFAULT_SITE).rstrip('/')
    webhook_url = f'{site}/telegram-webhook'
    r = tg_api('setWebhook', {'url': webhook_url})
    return f'<pre>Webhook: {webhook_url}\n\n{json.dumps(r, indent=2, ensure_ascii=False)}</pre>'

@app.route('/health')
def health():
    return {'ok': True}

with app.app_context():
    try:
        db.create_all()
        if Category.query.count() == 0:
            for n in ['Письменные принадлежности', 'Тетради и блокноты', 'Творчество и рисование',
                      'Школьные товары', 'Офисные принадлежности', 'Подарки и сувениры']:
                db.session.add(Category(name=n))
            db.session.commit()
    except Exception as e:
        print('DB init:', e)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
