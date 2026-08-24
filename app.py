from flask import Flask, request, redirect, url_for, flash, session, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
import os, uuid, json, requests, base64

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mir-kancelyarii-secret-key-2026-kg')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
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
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), default='https://via.placeholder.com/400x300?text=Product')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
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

def get_setting(key, default=''):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default

def set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s: s.value = value
    else: db.session.add(Setting(key=key, value=value))
    db.session.commit()

def get_cart():
    return session.get('cart', {})

def cart_count():
    return sum(get_cart().values())

def cart_total():
    t = 0
    for pid, qty in get_cart().items():
        p = Product.query.get(int(pid))
        if p: t += p.price * qty
    return t

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

ADMIN_PASSWORD = 'admin123'

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

LAYOUT = '''
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }} — Мир канцелярии</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{brand:'#6C5CE7',brand2:'#A66CFF',accent:'#FF6B35',soft:'#F8F7FF'}}}}</script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
body{font-family:'Nunito',system-ui,sans-serif}
.card{transition:.25s}.card:hover{transform:translateY(-4px);box-shadow:0 12px 28px -8px rgba(108,92,231,.2)}
.btn-grad{background:linear-gradient(135deg,#6C5CE7,#A66CFF)}
.btn-orange{background:linear-gradient(135deg,#FF6B35,#FF8F66)}
.hero-grad{background:linear-gradient(135deg,#f8f7ff 0%,#fff 50%,#fff5f0 100%)}
</style>
</head>
<body class="bg-white min-h-screen flex flex-col">
<header class="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-100 shadow-sm">
<div class="max-w-7xl mx-auto px-4 h-16 flex items-center gap-3">
  <a href="/" class="flex items-center gap-2 flex-shrink-0">
    <div class="w-10 h-10 rounded-xl btn-grad flex items-center justify-center text-white font-extrabold text-lg">М</div>
    <div class="hidden sm:block leading-tight">
      <div class="font-extrabold text-brand text-sm">МИР</div>
      <div class="text-[10px] text-gray-500 -mt-0.5 tracking-wide">КАНЦЕЛЯРИИ</div>
    </div>
  </a>
  <a href="/catalog" class="hidden md:inline-flex items-center gap-1.5 bg-brand text-white text-sm font-semibold px-4 py-2 rounded-xl">Каталог</a>
  <form action="/catalog" method="get" class="flex-1 max-w-xl">
    <div class="relative">
      <input type="text" name="q" value="{{ request.args.get('q','') }}" placeholder="Поиск товаров..."
        class="w-full pl-4 pr-10 py-2.5 bg-gray-50 border border-gray-200 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-brand/40">
      <button type="submit" class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"><i class="fas fa-search"></i></button>
    </div>
  </form>
  <a href="/cart" class="relative p-2 rounded-xl hover:bg-soft transition">
    <i class="fas fa-shopping-bag text-xl text-gray-600"></i>
    {% if cart_count %}<span class="absolute -top-0.5 -right-0.5 bg-accent text-white text-[10px] font-bold rounded-full h-5 w-5 flex items-center justify-center">{{ cart_count }}</span>{% endif %}
  </a>
</div>
</header>
{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}<div class="max-w-7xl mx-auto px-4 mt-3 space-y-1">
{% for cat,msg in messages %}
<div class="px-4 py-2.5 rounded-xl text-sm font-medium {% if cat=='success' %}bg-green-50 text-green-700{% elif cat=='danger' %}bg-red-50 text-red-700{% else %}bg-blue-50 text-blue-700{% endif %}">{{ msg }}</div>
{% endfor %}</div>{% endif %}{% endwith %}
<main class="flex-1">{{ content|safe }}</main>
<footer class="bg-gray-900 text-gray-400 mt-16 text-center text-sm py-6">© 2026 Мир канцелярии · Кыргызстан</footer>
</body></html>
'''

def page(title, content, **ctx):
    from flask import get_flashed_messages, request as req
    ctx.update(title=title, content=content, cart_count=cart_count(),
               categories=Category.query.all(), get_flashed_messages=get_flashed_messages, request=req)
    return render_template_string(LAYOUT, **ctx)

def product_card(p):
    return f'''<div class="card bg-white rounded-2xl overflow-hidden border border-gray-100 shadow-sm">
<a href="/product/{p.id}"><div class="aspect-square bg-gray-50 overflow-hidden">
<img src="{p.image_url}" class="w-full h-full object-cover" onerror="this.src='https://via.placeholder.com/400'"></div></a>
<div class="p-3.5"><a href="/product/{p.id}"><h3 class="font-bold text-sm line-clamp-2 hover:text-brand">{p.name}</h3></a>
<div class="flex justify-between items-center mt-2.5">
<span class="font-extrabold text-brand">{p.price:,.0f} сом</span>
<form action="/cart/add/{p.id}" method="post"><button class="w-9 h-9 rounded-xl btn-grad text-white"><i class="fas fa-plus text-xs"></i></button></form>
</div></div></div>'''

@app.route('/')
def index():
    products = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    cards = ''.join(product_card(p) for p in products) or '<div class="col-span-full text-center py-16 text-gray-400">Каталог пока пуст</div>'
    content = f'''
<section class="hero-grad py-16 px-4">
<div class="max-w-7xl mx-auto">
<h1 class="text-4xl font-extrabold mb-4">Мир канцелярии —<br><span class="text-brand">всё для учёбы</span> и <span class="text-accent">творчества</span></h1>
<p class="text-gray-500 mb-6">Оформите предзаказ — мы свяжемся с вами</p>
<a href="/catalog" class="btn-orange text-white font-bold px-6 py-3 rounded-full inline-block">В каталог</a>
</div></section>
<section class="max-w-7xl mx-auto px-4 py-12">
<h2 class="text-2xl font-extrabold mb-6">Товары</h2>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4">{cards}</div>
</section>'''
    return page('Главная', content)

@app.route('/catalog')
def catalog():
    q = request.args.get('q', '').strip()
    cat_id = request.args.get('category', type=int)
    query = Product.query
    if q: query = query.filter(Product.name.ilike(f'%{q}%'))
    if cat_id: query = query.filter(Product.category_id == cat_id)
    products = query.order_by(Product.created_at.desc()).all()
    cards = ''.join(product_card(p) for p in products) or '<div class="col-span-full text-center py-16 text-gray-400">Ничего не найдено</div>'
    content = f'''<div class="max-w-7xl mx-auto px-4 py-8">
<form method="get" class="mb-6 flex gap-2"><input name="q" value="{q}" placeholder="Поиск..." class="flex-1 border rounded-full px-4 py-2">
<button class="btn-grad text-white px-5 py-2 rounded-full font-bold">Найти</button></form>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4">{cards}</div></div>'''
    return page('Каталог', content)

@app.route('/product/<int:pid>')
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    content = f'''<div class="max-w-7xl mx-auto px-4 py-8 grid md:grid-cols-2 gap-8">
<img src="{p.image_url}" class="w-full rounded-3xl aspect-square object-cover bg-gray-50">
<div><h1 class="text-3xl font-extrabold mb-3">{p.name}</h1>
<div class="text-3xl font-extrabold text-brand mb-4">{p.price:,.0f} сом</div>
<p class="text-gray-500 mb-6">{p.description or ""}</p>
<form action="/cart/add/{p.id}" method="post" class="flex gap-3">
<input type="number" name="quantity" value="1" min="1" class="w-20 border rounded-xl px-3 py-3 text-center">
<button class="btn-grad text-white font-bold px-8 py-3 rounded-xl">В предзаказ</button>
</form></div></div>'''
    return page(p.name, content)

@app.route('/cart')
def cart():
    items_html, total = '', 0
    for pid, qty in get_cart().items():
        p = Product.query.get(int(pid))
        if not p: continue
        sub = p.price * qty; total += sub
        items_html += f'''<div class="p-4 flex gap-4 items-center border-b">
<img src="{p.image_url}" class="w-16 h-16 rounded-xl object-cover"><div class="flex-1 font-bold">{p.name}</div>
<form action="/cart/update/{p.id}" method="post" class="flex gap-2">
<input type="number" name="quantity" value="{qty}" min="0" class="w-16 border rounded px-2 py-1 text-center"><button class="text-brand text-sm">OK</button></form>
<div class="font-bold w-20 text-right">{sub:,.0f}</div>
<a href="/cart/remove/{p.id}" class="text-red-400">✕</a></div>'''
    if items_html:
        content = f'''<div class="max-w-3xl mx-auto px-4 py-8"><h1 class="text-2xl font-extrabold mb-6">Предзаказ</h1>
<div class="bg-white rounded-2xl border overflow-hidden">{items_html}
<div class="p-5 flex justify-between items-center bg-soft">
<span class="text-xl font-extrabold">{total:,.0f} сом</span>
<a href="/checkout" class="btn-orange text-white font-bold px-6 py-3 rounded-xl">Оставить предзаказ</a>
</div></div></div>'''
    else:
        content = '<div class="text-center py-20 text-gray-400"><p class="text-xl font-bold mb-4">Предзаказ пуст</p><a href="/catalog" class="btn-grad text-white px-6 py-3 rounded-full inline-block">В каталог</a></div>'
    return page('Предзаказ', content)

@app.route('/cart/add/<int:pid>', methods=['POST'])
def add_to_cart(pid):
    p = Product.query.get_or_404(pid)
    qty = int(request.form.get('quantity', 1))
    cart = get_cart(); cart[str(pid)] = cart.get(str(pid), 0) + qty; session['cart'] = cart
    flash(f'«{p.name}» добавлен в предзаказ', 'success')
    return redirect(request.referrer or url_for('catalog'))

@app.route('/cart/update/<int:pid>', methods=['POST'])
def update_cart(pid):
    qty = int(request.form.get('quantity', 1))
    cart = get_cart()
    if qty <= 0: cart.pop(str(pid), None)
    else: cart[str(pid)] = qty
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:pid>')
def remove_from_cart(pid):
    cart = get_cart(); cart.pop(str(pid), None); session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not get_cart():
        flash('Предзаказ пуст', 'warning'); return redirect(url_for('catalog'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        if not name or not phone:
            flash('Укажите имя и телефон', 'danger'); return redirect(url_for('checkout'))
        order = Order(customer_name=name, customer_phone=phone, total_price=cart_total())
        db.session.add(order); db.session.flush()
        for pid, qty in get_cart().items():
            p = Product.query.get(int(pid))
            if p: db.session.add(OrderItem(order_id=order.id, product_id=p.id, quantity=qty, price=p.price))
        db.session.commit(); session['cart'] = {}
        flash(f'Предзаказ #{order.id} принят!', 'success')
        return redirect(url_for('index'))
    content = '''<div class="max-w-lg mx-auto px-4 py-8"><h1 class="text-2xl font-extrabold mb-6">Предзаказ</h1>
<form method="post" class="bg-white border rounded-2xl p-6 space-y-4">
<input name="name" required placeholder="Имя" class="w-full border rounded-xl px-4 py-3">
<input name="phone" required placeholder="+996 ..." class="w-full border rounded-xl px-4 py-3">
<button class="w-full btn-orange text-white font-bold py-3 rounded-xl">Отправить</button>
</form></div>'''
    return page('Предзаказ', content)

# ===== ADMIN =====
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'): return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True; return redirect(url_for('admin_dashboard'))
        flash('Неверный пароль', 'danger')
    content = '''<div class="min-h-[50vh] flex items-center justify-center px-4">
<form method="post" class="bg-white border rounded-2xl p-8 w-full max-w-sm text-center">
<h1 class="font-extrabold text-xl mb-4">Админ</h1>
<input type="password" name="password" required class="w-full border rounded-xl px-4 py-3 mb-3 text-center" placeholder="Пароль">
<button class="w-full btn-grad text-white font-bold py-3 rounded-xl">Войти</button>
</form></div>'''
    return page('Вход', content)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None); return redirect('/')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    pc, oc = Product.query.count(), Order.query.count()
    content = f'''<div class="max-w-4xl mx-auto px-4 py-8">
<div class="flex gap-4 mb-6 text-sm"><a href="/admin/dashboard" class="font-bold text-brand">Дашборд</a>
<a href="/admin/products" class="text-gray-500">Товары</a>
<a href="/admin/orders" class="text-gray-500">Заявки</a>
<a href="/admin/logout" class="text-red-500 ml-auto">Выйти</a></div>
<h1 class="text-2xl font-extrabold mb-4">Дашборд</h1>
<p>Товаров: <b>{pc}</b> · Заявок: <b>{oc}</b></p>
</div>'''
    return page('Админ', content)

@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    rows = ''.join(f'<tr class="border-t"><td class="px-4 py-2">{p.name}</td><td class="px-4 py-2">{p.price:,.0f}</td>'
                   f'<td class="px-4 py-2"><a href="/admin/products/edit/{p.id}" class="text-brand">Изменить</a> '
                   f'<form action="/admin/products/delete/{p.id}" method="post" class="inline" onsubmit="return confirm(\'Удалить?\')">'
                   f'<button class="text-red-400">Удалить</button></form></td></tr>' for p in products)
    content = f'''<div class="max-w-4xl mx-auto px-4 py-8">
<a href="/admin/dashboard" class="text-sm text-brand">← Назад</a>
<div class="flex justify-between mb-4"><h1 class="text-2xl font-extrabold">Товары</h1>
<a href="/admin/products/add" class="btn-grad text-white px-4 py-2 rounded-xl text-sm font-bold">+ Добавить</a></div>
<table class="w-full text-sm bg-white border rounded-xl overflow-hidden"><tbody>{rows or "<tr><td class=p-8 text-center text-gray-400>Нет товаров</td></tr>"}</tbody></table></div>'''
    return page('Товары', content)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@app.route('/admin/products/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_product_form(pid=None):
    p = Product.query.get(pid) if pid else None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = float(request.form.get('price', 0) or 0)
        if not name or price <= 0:
            flash('Название и цена обязательны', 'danger'); return redirect(request.url)
        uploaded = save_upload(request.files.get('photo'))
        if p:
            p.name, p.description, p.price = name, request.form.get('description', ''), price
            if uploaded: p.image_url = uploaded
        else:
            db.session.add(Product(name=name, description=request.form.get('description', ''), price=price,
                                   image_url=uploaded or 'https://via.placeholder.com/400'))
        db.session.commit(); flash('Сохранено', 'success')
        return redirect(url_for('admin_products'))
    content = f'''<div class="max-w-lg mx-auto px-4 py-8">
<form method="post" enctype="multipart/form-data" class="bg-white border rounded-2xl p-6 space-y-3">
<input name="name" required value="{p.name if p else ''}" placeholder="Название" class="w-full border rounded-xl px-4 py-2.5">
<textarea name="description" rows="2" placeholder="Описание" class="w-full border rounded-xl px-4 py-2.5">{p.description if p else ''}</textarea>
<input name="price" type="number" step="0.01" required value="{p.price if p else ''}" placeholder="Цена" class="w-full border rounded-xl px-4 py-2.5">
<input type="file" name="photo" accept="image/*" class="w-full text-sm">
<button class="btn-grad text-white font-bold px-6 py-2.5 rounded-xl">Сохранить</button>
</form></div>'''
    return page('Товар', content)

@app.route('/admin/products/delete/<int:pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    p = Product.query.get_or_404(pid); db.session.delete(p); db.session.commit()
    flash('Удалено', 'success'); return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    rows = ''.join(f'<tr class="border-t"><td class="px-4 py-2">#{o.id}</td><td class="px-4 py-2">{o.customer_name}</td>'
                   f'<td class="px-4 py-2">{o.customer_phone}</td><td class="px-4 py-2">{o.total_price:,.0f}</td>'
                   f'<td class="px-4 py-2">{o.status}</td></tr>' for o in orders)
    content = f'''<div class="max-w-4xl mx-auto px-4 py-8">
<a href="/admin/dashboard" class="text-sm text-brand">← Назад</a>
<h1 class="text-2xl font-extrabold my-4">Заявки</h1>
<table class="w-full text-sm bg-white border rounded-xl"><tbody>{rows or "<tr><td class=p-8 text-center text-gray-400>Нет заявок</td></tr>"}</tbody></table></div>'''
    return page('Заявки', content)

# ===== TELEGRAM + GEMINI =====
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY')
ADMIN_IDS = [x.strip() for x in os.environ.get('TELEGRAM_ADMIN_IDS', '8569472160').split(',') if x.strip()]
DEFAULT_SITE = os.environ.get('SITE_URL', 'https://mircancelyarii-production.up.railway.app').rstrip('/')

def tg_api(method, data=None):
    if not TELEGRAM_TOKEN: return None
    try:
        r = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}', json=data or {}, timeout=30)
        return r.json()
    except Exception as e:
        print('TG error', e); return None

def tg_send(chat_id, text):
    return tg_api('sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'})

def get_bot_state(chat_id):
    st = BotState.query.filter_by(chat_id=str(chat_id)).first()
    if not st:
        st = BotState(chat_id=str(chat_id), step='idle')
        db.session.add(st); db.session.commit()
    return st

def ai_describe_product(image_path):
    """Google Gemini vision"""
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        return None
    try:
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = image_path.rsplit('.', 1)[-1].lower()
        mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                'webp': 'image/webp', 'gif': 'image/gif'}.get(ext, 'image/jpeg')
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}'
        payload = {
            'contents': [{
                'parts': [
                    {'text': 'Ты помощник магазина канцтоваров в Кыргызстане. По фото определи товар. Ответь ТОЛЬКО коротким названием на русском (2-6 слов), без кавычек и пояснений. Пример: Набор цветных карандашей 24 шт'},
                    {'inline_data': {'mime_type': mime, 'data': b64}}
                ]
            }]
        }
        resp = requests.post(url, json=payload, timeout=45)
        data = resp.json()
        name = data['candidates'][0]['content']['parts'][0]['text'].strip().strip('"').strip("'")
        if '\n' in name:
            name = name.split('\n')[0].strip()
        return name[:200] if name else None
    except Exception as e:
        print('Gemini error:', e)
        return None

def download_tg_photo(file_id):
    info = tg_api('getFile', {'file_id': file_id})
    if not info or not info.get('ok'): return None
    file_path = info['result']['file_path']
    url = f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}'
    try:
        r = requests.get(url, timeout=60)
        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else 'jpg'
        if ext not in ALLOWED_EXT: ext = 'jpg'
        name = f'{uuid.uuid4().hex}.{ext}'
        full = os.path.join(UPLOAD_FOLDER, name)
        with open(full, 'wb') as f: f.write(r.content)
        return f'/uploads/{name}', full
    except Exception as e:
        print('download error', e); return None

def is_admin(user_id):
    if not ADMIN_IDS: return True
    return str(user_id) in ADMIN_IDS

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    if not TELEGRAM_TOKEN:
        return 'ok', 200
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
        st.step = 'idle'; st.draft_name = ''; st.draft_image = ''; db.session.commit()
        tg_send(chat_id, '👋 Бот «Мир канцелярии»\n\nОтправьте <b>фото товара</b>.\nПосле — цену числом.\n\n/cancel — отмена')
        return 'ok', 200
    if text.startswith('/cancel'):
        st.step = 'idle'; st.draft_name = ''; st.draft_image = ''; db.session.commit()
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
        name = ai_describe_product(full_path)
        st.draft_image = web_path
        if name:
            st.draft_name = name; st.step = 'wait_price'; db.session.commit()
            tg_send(chat_id, f'✅ Похоже, это:\n<b>{name}</b>\n\nПришлите <b>цену</b> (число) или другое название')
        else:
            st.draft_name = ''; st.step = 'wait_name'; db.session.commit()
            key = os.environ.get('GEMINI_API_KEY', '').strip()
            extra = '' if key else '\n(Gemini не настроен — укажите название сами)'
            tg_send(chat_id, f'📷 Фото получено.{extra}\n\nНапишите <b>название</b> товара:')
        return 'ok', 200

    if st.step == 'wait_name' and text:
        st.draft_name = text[:200]; st.step = 'wait_price'; db.session.commit()
        tg_send(chat_id, f'Название: <b>{st.draft_name}</b>\n\nПришлите <b>цену</b> (число):')
        return 'ok', 200

    if st.step == 'wait_price' and text:
        price_txt = text.replace('сом', '').replace(',', '.').strip()
        try:
            price = float(price_txt)
            if price <= 0: raise ValueError()
        except ValueError:
            st.draft_name = text[:200]; db.session.commit()
            tg_send(chat_id, f'Название: <b>{st.draft_name}</b>\n\nПришлите <b>цену</b> (число):')
            return 'ok', 200
        product = Product(name=st.draft_name or 'Товар', description='', price=price,
                          image_url=st.draft_image or 'https://via.placeholder.com/400')
        db.session.add(product)
        st.step = 'idle'; st.draft_name = ''; st.draft_image = ''
        db.session.commit()
        tg_send(chat_id, f'🎉 Добавлено:\n<b>{product.name}</b>\n{product.price:,.0f} сом\n\n{DEFAULT_SITE}/product/{product.id}')
        return 'ok', 200

    if text:
        tg_send(chat_id, 'Пришлите <b>фото</b> или /start')
    return 'ok', 200

@app.route('/setup-webhook')
def setup_webhook():
    if not TELEGRAM_TOKEN:
        return 'Нет TELEGRAM_BOT_TOKEN', 400
    site = os.environ.get('SITE_URL', DEFAULT_SITE).rstrip('/')
    webhook_url = f'{site}/telegram-webhook'
    r = tg_api('setWebhook', {'url': webhook_url})
    return f'<pre>Webhook: {webhook_url}\n\n{json.dumps(r, indent=2, ensure_ascii=False)}</pre>'

with app.app_context():
    db.create_all()
    if Category.query.count() == 0:
        for n in ['Письменные принадлежности', 'Тетради и блокноты', 'Творчество', 'Школьные товары', 'Офис', 'Подарки']:
            db.session.add(Category(name=n))
        db.session.commit()

try:
    if TELEGRAM_TOKEN:
        site = os.environ.get('SITE_URL', DEFAULT_SITE).rstrip('/')
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook',
                      json={'url': f'{site}/telegram-webhook'}, timeout=15)
except Exception:
    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)