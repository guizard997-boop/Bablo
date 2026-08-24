from flask import Flask, request, redirect, url_for, flash, session, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
import os, uuid, json, requests

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

# ==================== MODELS ====================
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

def get_setting(key, default=''):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default

def set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s: s.value = value
    else: db.session.add(Setting(key=key, value=value))
    db.session.commit()

class BotState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    step = db.Column(db.String(50), default='idle')  # idle, wait_name, wait_price
    draft_name = db.Column(db.String(300), default='')
    draft_image = db.Column(db.String(500), default='')


# ==================== HELPERS ====================
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

# ==================== LAYOUT ====================
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
.hero-grad{background:linear-gradient(135deg,#f8f7ff 0%,#fff 50%,#fff5f0 100%)}
.btn-grad{background:linear-gradient(135deg,#6C5CE7,#A66CFF)}
.btn-orange{background:linear-gradient(135deg,#FF6B35,#FF8F66)}
</style>
</head>
<body class="bg-white min-h-screen flex flex-col">
<!-- HEADER -->
<header class="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-100 shadow-sm">
<div class="max-w-7xl mx-auto px-4 h-16 flex items-center gap-3">
  <a href="/" class="flex items-center gap-2 flex-shrink-0">
    <div class="w-10 h-10 rounded-xl btn-grad flex items-center justify-center text-white font-extrabold text-lg">М</div>
    <div class="hidden sm:block leading-tight">
      <div class="font-extrabold text-brand text-sm">МИР</div>
      <div class="text-[10px] text-gray-500 -mt-0.5 tracking-wide">КАНЦЕЛЯРИИ</div>
    </div>
  </a>
  <a href="/catalog" class="hidden md:inline-flex items-center gap-1.5 bg-brand text-white text-sm font-semibold px-4 py-2 rounded-xl hover:opacity-90 transition">
    <i class="fas fa-th-large"></i> Каталог
  </a>
  <form action="/catalog" method="get" class="flex-1 max-w-xl">
    <div class="relative">
      <input type="text" name="q" value="{{ request.args.get('q','') }}" placeholder="Поиск товаров..."
        class="w-full pl-4 pr-10 py-2.5 bg-gray-50 border border-gray-200 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand">
      <button type="submit" class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand"><i class="fas fa-search"></i></button>
    </div>
  </form>
  <a href="/cart" class="relative p-2 rounded-xl hover:bg-soft transition" title="Предзаказ">
    <i class="fas fa-shopping-bag text-xl text-gray-600"></i>
    {% if cart_count %}<span class="absolute -top-0.5 -right-0.5 bg-accent text-white text-[10px] font-bold rounded-full h-5 w-5 flex items-center justify-center">{{ cart_count }}</span>{% endif %}
  </a>
</div>
</header>

{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}<div class="max-w-7xl mx-auto px-4 mt-3 space-y-1">
{% for cat,msg in messages %}
<div class="px-4 py-2.5 rounded-xl text-sm font-medium {% if cat=='success' %}bg-green-50 text-green-700 border border-green-100{% elif cat=='danger' %}bg-red-50 text-red-700 border border-red-100{% else %}bg-blue-50 text-blue-700 border border-blue-100{% endif %}">{{ msg }}</div>
{% endfor %}</div>{% endif %}{% endwith %}

<main class="flex-1">{{ content|safe }}</main>

<footer class="bg-gray-900 text-gray-400 mt-16">
<div class="max-w-7xl mx-auto px-4 py-10 grid sm:grid-cols-3 gap-8 text-sm">
  <div>
    <div class="flex items-center gap-2 mb-3">
      <div class="w-8 h-8 rounded-lg btn-grad flex items-center justify-center text-white font-bold">М</div>
      <span class="text-white font-bold">Мир канцелярии</span>
    </div>
    <p class="text-gray-500">Всё для учёбы, творчества и вдохновения. Предзаказ по Кыргызстану.</p>
  </div>
  <div>
    <h4 class="text-white font-semibold mb-3">Каталог</h4>
    <ul class="space-y-1">
    {% for c in categories %}
    <li><a href="/catalog?category={{ c.id }}" class="hover:text-white transition">{{ c.name }}</a></li>
    {% endfor %}
    </ul>
  </div>
  <div>
    <h4 class="text-white font-semibold mb-3">Контакты</h4>
    <p class="text-gray-500">Оставьте предзаказ — мы свяжемся с вами</p>
  </div>
</div>
<div class="border-t border-gray-800 text-center text-xs text-gray-600 py-4">© 2026 Мир канцелярии · Кыргызстан</div>
</footer>
</body></html>
'''

def page(title, content, **ctx):
    from flask import get_flashed_messages, request as req
    ctx.update(title=title, content=content, cart_count=cart_count(),
               categories=Category.query.all(), get_flashed_messages=get_flashed_messages, request=req)
    return render_template_string(LAYOUT, **ctx)

def product_card(p):
    cat = f'<span class="text-[10px] font-semibold text-brand bg-soft px-2 py-0.5 rounded-full">{p.category.name}</span>' if p.category else ''
    return f'''<div class="card bg-white rounded-2xl overflow-hidden border border-gray-100 shadow-sm">
<a href="/product/{p.id}"><div class="aspect-square bg-gray-50 overflow-hidden">
<img src="{p.image_url}" class="w-full h-full object-cover" onerror="this.src='https://via.placeholder.com/400x400?text=Фото'"></div></a>
<div class="p-3.5">{cat}
<a href="/product/{p.id}"><h3 class="font-bold text-gray-800 mt-1.5 text-sm line-clamp-2 hover:text-brand transition">{p.name}</h3></a>
<div class="flex justify-between items-center mt-2.5">
<span class="font-extrabold text-brand">{p.price:,.0f} <span class="text-xs font-semibold">сом</span></span>
<form action="/cart/add/{p.id}" method="post">
<button class="w-9 h-9 rounded-xl btn-grad text-white flex items-center justify-center shadow-md hover:opacity-90"><i class="fas fa-plus text-xs"></i></button>
</form></div></div></div>'''

# ==================== PUBLIC ====================
@app.route('/')
def index():
    products = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    cats = Category.query.all()
    cat_colors = ['bg-violet-50','bg-pink-50','bg-sky-50','bg-amber-50','bg-emerald-50','bg-rose-50']
    cat_html = ''
    for i, c in enumerate(cats):
        cnt = Product.query.filter_by(category_id=c.id).count()
        cat_html += f'''<a href="/catalog?category={c.id}" class="card {cat_colors[i%len(cat_colors)]} rounded-2xl p-5 text-center border border-white/50">
<div class="w-14 h-14 mx-auto mb-3 rounded-2xl bg-white shadow-sm flex items-center justify-center text-2xl">📦</div>
<div class="font-bold text-gray-800 text-sm">{c.name}</div>
<div class="text-xs text-gray-400 mt-1">{cnt} товар(ов)</div></a>'''
    cards = ''.join(product_card(p) for p in products) or '<div class="col-span-full text-center py-16 text-gray-400"><i class="fas fa-box-open text-5xl mb-3"></i><p class="font-semibold text-lg">Каталог пока пуст</p><p class="text-sm">Товары появятся скоро</p></div>'
    content = f'''
<!-- HERO -->
<section class="hero-grad overflow-hidden">
<div class="max-w-7xl mx-auto px-4 py-12 md:py-20 grid md:grid-cols-2 gap-8 items-center">
  <div>
    <h1 class="text-3xl sm:text-4xl lg:text-5xl font-extrabold leading-tight mb-4">
      Мир канцелярии —<br>
      <span class="text-brand">всё для учёбы,</span><br>
      <span class="text-brand2">творчества</span><br>
      <span class="text-accent">и вдохновения!</span>
    </h1>
    <p class="text-gray-500 mb-6 max-w-md">Качественные товары для школы, офиса и творчества. Оформите предзаказ — мы свяжемся с вами.</p>
    <a href="/catalog" class="inline-flex items-center gap-2 btn-orange text-white font-bold px-6 py-3 rounded-full shadow-lg hover:opacity-90 transition">
      Перейти в каталог <i class="fas fa-arrow-right text-sm"></i>
    </a>
  </div>
  <div class="hidden md:flex justify-center">
    <div class="relative w-80 h-80">
      <div class="absolute inset-0 bg-gradient-to-br from-violet-200 to-orange-100 rounded-full blur-2xl opacity-60"></div>
      <div class="relative text-center text-8xl leading-none pt-12">✏️📚🎨</div>
    </div>
  </div>
</div>
</section>

<!-- BENEFITS -->
<div class="max-w-7xl mx-auto px-4 -mt-6 relative z-10">
<div class="bg-white rounded-2xl shadow-lg border border-gray-100 grid grid-cols-2 md:grid-cols-4 divide-x divide-gray-100 overflow-hidden">
  <div class="p-4 text-center"><div class="text-brand text-xl mb-1"><i class="fas fa-th"></i></div><div class="font-bold text-sm">Широкий ассортимент</div><div class="text-xs text-gray-400">Много товаров</div></div>
  <div class="p-4 text-center"><div class="text-amber-500 text-xl mb-1"><i class="fas fa-star"></i></div><div class="font-bold text-sm">Качество</div><div class="text-xs text-gray-400">Проверенные товары</div></div>
  <div class="p-4 text-center"><div class="text-emerald-500 text-xl mb-1"><i class="fas fa-clipboard-check"></i></div><div class="font-bold text-sm">Предзаказ</div><div class="text-xs text-gray-400">Удобно и быстро</div></div>
  <div class="p-4 text-center"><div class="text-sky-500 text-xl mb-1"><i class="fas fa-headset"></i></div><div class="font-bold text-sm">На связи</div><div class="text-xs text-gray-400">Всегда ответим</div></div>
</div></div>

<!-- CATEGORIES -->
{"<section class='max-w-7xl mx-auto px-4 py-14'><h2 class='text-2xl font-extrabold text-center mb-2'>Популярные категории</h2><div class='w-16 h-1 bg-brand mx-auto rounded mb-8'></div><div class='grid grid-cols-2 sm:grid-cols-3 md:grid-cols-"+str(min(len(cats),6))+" gap-4'>"+cat_html+"</div></section>" if cats else ""}

<!-- PRODUCTS -->
<section class="max-w-7xl mx-auto px-4 py-8">
<div class="flex justify-between items-end mb-6">
  <div><h2 class="text-2xl font-extrabold">Товары</h2><p class="text-gray-400 text-sm">Выберите и оставьте предзаказ</p></div>
  <a href="/catalog" class="text-brand font-semibold text-sm hover:underline">Весь каталог →</a>
</div>
<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">{cards}</div>
</section>

<!-- CTA -->
<section class="max-w-7xl mx-auto px-4 py-8">
<div class="rounded-2xl bg-gradient-to-r from-violet-50 to-orange-50 border border-violet-100 p-6 md:p-8 flex flex-col md:flex-row items-center gap-4 justify-between">
  <div class="flex items-center gap-4">
    <div class="text-4xl">🎁</div>
    <div><div class="font-extrabold text-lg">Оформите предзаказ прямо сейчас!</div>
    <div class="text-sm text-gray-500">Выберите товары — мы свяжемся с вами для уточнения</div></div>
  </div>
  <a href="/catalog" class="btn-grad text-white font-bold px-6 py-3 rounded-full whitespace-nowrap">В каталог</a>
</div></section>
'''
    return page('Главная', content)

@app.route('/catalog')
def catalog():
    q = request.args.get('q', '').strip()
    cat_id = request.args.get('category', type=int)
    sort = request.args.get('sort', 'newest')
    query = Product.query
    if q: query = query.filter(Product.name.ilike(f'%{q}%') | Product.description.ilike(f'%{q}%'))
    if cat_id: query = query.filter(Product.category_id == cat_id)
    if sort == 'price_asc': query = query.order_by(Product.price.asc())
    elif sort == 'price_desc': query = query.order_by(Product.price.desc())
    else: query = query.order_by(Product.created_at.desc())
    products = query.all()
    cats = Category.query.all()
    cat_opts = ''.join(f'<option value="{c.id}" {"selected" if cat_id==c.id else ""}>{c.name}</option>' for c in cats)
    cards = ''.join(product_card(p) for p in products) or '<div class="col-span-full text-center py-16 text-gray-400">Ничего не найдено</div>'
    title = f'Поиск: {q}' if q else 'Каталог'
    content = f'''<div class="max-w-7xl mx-auto px-4 py-8">
<div class="flex flex-col lg:flex-row gap-6">
<aside class="lg:w-60 flex-shrink-0">
<div class="bg-soft rounded-2xl border border-violet-100 p-5 sticky top-20">
<h3 class="font-bold mb-3 flex items-center gap-2"><i class="fas fa-filter text-brand"></i> Фильтры</h3>
<form method="get" class="space-y-3">
<input name="q" value="{q}" placeholder="Поиск..." class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-brand/30 focus:outline-none">
<select name="category" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm"><option value="">Все категории</option>{cat_opts}</select>
<select name="sort" class="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm">
<option value="newest" {"selected" if sort=="newest" else ""}>Сначала новые</option>
<option value="price_asc" {"selected" if sort=="price_asc" else ""}>Цена: по возрастанию</option>
<option value="price_desc" {"selected" if sort=="price_desc" else ""}>Цена: по убыванию</option>
</select>
<button class="w-full btn-grad text-white py-2.5 rounded-xl text-sm font-bold">Применить</button>
<a href="/catalog" class="block text-center text-xs text-gray-400 mt-2 hover:text-brand">Сбросить</a>
</form></div></aside>
<div class="flex-1">
<div class="flex justify-between items-center mb-5">
<h1 class="text-2xl font-extrabold">{title}</h1>
<span class="text-sm text-gray-400">{len(products)} товар(ов)</span>
</div>
<div class="grid grid-cols-2 sm:grid-cols-2 xl:grid-cols-3 gap-4">{cards}</div>
</div></div></div>'''
    return page(title, content)

@app.route('/product/<int:pid>')
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    cat = f'<span class="text-xs font-semibold text-brand bg-soft px-3 py-1 rounded-full">{p.category.name}</span>' if p.category else ''
    content = f'''<div class="max-w-7xl mx-auto px-4 py-8">
<nav class="text-sm text-gray-400 mb-6"><a href="/" class="hover:text-brand">Главная</a> / <a href="/catalog" class="hover:text-brand">Каталог</a> / <span class="text-gray-700">{p.name}</span></nav>
<div class="grid md:grid-cols-2 gap-10">
<div class="bg-gray-50 rounded-3xl overflow-hidden border border-gray-100">
<img src="{p.image_url}" class="w-full aspect-square object-cover" onerror="this.src='https://via.placeholder.com/600'"></div>
<div class="flex flex-col justify-center">
{cat}
<h1 class="text-3xl font-extrabold mt-3 mb-3 text-gray-900">{p.name}</h1>
<div class="text-3xl font-extrabold text-brand mb-5">{p.price:,.0f} <span class="text-lg">сом</span></div>
<p class="text-gray-500 mb-8 leading-relaxed">{p.description or "Описание скоро появится"}</p>
<form action="/cart/add/{p.id}" method="post" class="flex flex-wrap gap-3 items-center">
<input type="number" name="quantity" value="1" min="1" class="w-20 border border-gray-200 rounded-xl px-3 py-3 text-center font-semibold">
<button class="btn-grad text-white font-bold px-8 py-3 rounded-xl shadow-lg hover:opacity-90 flex items-center gap-2">
<i class="fas fa-shopping-bag"></i> В предзаказ</button>
</form></div></div></div>'''
    return page(p.name, content)

@app.route('/cart')
def cart():
    items_html, total = '', 0
    for pid, qty in get_cart().items():
        p = Product.query.get(int(pid))
        if not p: continue
        sub = p.price * qty; total += sub
        items_html += f'''<div class="p-4 flex flex-col sm:flex-row gap-4 items-center border-b border-gray-50">
<img src="{p.image_url}" class="w-20 h-20 object-cover rounded-xl bg-gray-50" onerror="this.src='https://via.placeholder.com/80'">
<div class="flex-1 text-center sm:text-left"><a href="/product/{p.id}" class="font-bold hover:text-brand">{p.name}</a>
<p class="text-sm text-gray-400">{p.price:,.0f} сом</p></div>
<form action="/cart/update/{p.id}" method="post" class="flex gap-2 items-center">
<input type="number" name="quantity" value="{qty}" min="0" class="w-16 border rounded-lg px-2 py-1.5 text-center text-sm">
<button class="text-sm text-brand font-semibold">OK</button></form>
<div class="font-extrabold text-brand w-24 text-right">{sub:,.0f} сом</div>
<a href="/cart/remove/{p.id}" class="text-red-400 hover:text-red-600 text-sm ml-2"><i class="fas fa-times"></i></a></div>'''
    if items_html:
        content = f'''<div class="max-w-3xl mx-auto px-4 py-8"><h1 class="text-2xl font-extrabold mb-6">Ваш предзаказ</h1>
<div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">{items_html}
<div class="p-5 bg-soft flex flex-col sm:flex-row justify-between items-center gap-3">
<a href="/catalog" class="text-brand text-sm font-semibold">← Продолжить выбор</a>
<span class="text-2xl font-extrabold text-brand">{total:,.0f} сом</span>
<a href="/checkout" class="btn-orange text-white font-bold px-6 py-3 rounded-xl shadow">Оставить предзаказ →</a>
</div></div></div>'''
    else:
        content = '''<div class="max-w-3xl mx-auto px-4 py-20 text-center">
<div class="text-6xl mb-4">🛍️</div>
<h2 class="text-xl font-extrabold mb-2">Предзаказ пуст</h2>
<p class="text-gray-400 mb-6">Добавьте товары из каталога</p>
<a href="/catalog" class="btn-grad text-white font-bold px-6 py-3 rounded-full inline-block">В каталог</a></div>'''
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
        flash(f'Предзаказ #{order.id} принят! Мы свяжемся с вами.', 'success')
        return redirect(url_for('index'))
    items, total = '', 0
    for pid, qty in get_cart().items():
        p = Product.query.get(int(pid))
        if p:
            sub = p.price * qty; total += sub
            items += f'<div class="flex justify-between text-sm py-1"><span class="text-gray-600">{p.name} × {qty}</span><span class="font-semibold">{sub:,.0f} сом</span></div>'
    phones = get_setting('phones', '')
    rekvizity = get_setting('rekvizity', '')
    rekvizity_image = get_setting('rekvizity_image', '')
    phones_html = ''
    if phones:
        phones_html = '<div class="mt-4 pt-4 border-t"><h4 class="font-bold text-sm mb-2">Связаться с нами</h4>' + ''.join(
            f'<a href="tel:{l.strip()}" class="block text-brand text-sm mb-1 font-semibold"><i class="fas fa-phone mr-1"></i>{l.strip()}</a>'
            for l in phones.strip().splitlines() if l.strip()) + '</div>'
    rekv_html = ''
    if rekvizity or rekvizity_image:
        rekv_html = '<div class="mt-4 pt-4 border-t"><h4 class="font-bold text-sm mb-2">Реквизиты для оплаты</h4>'
        if rekvizity: rekv_html += f'<pre class="text-xs text-gray-600 whitespace-pre-wrap bg-gray-50 p-3 rounded-xl">{rekvizity}</pre>'
        if rekvizity_image: rekv_html += '<img src="' + rekvizity_image + '" class="mt-2 max-h-40 rounded-xl border" onerror="this.style.display=\'none\'">'
        rekv_html += '</div>'
    content = f'''<div class="max-w-3xl mx-auto px-4 py-8">
<h1 class="text-2xl font-extrabold mb-6">Оставить предзаказ</h1>
<div class="grid md:grid-cols-5 gap-6">
<div class="md:col-span-3 bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
<p class="text-sm text-gray-400 mb-4">Укажите имя и телефон — мы свяжемся с вами</p>
<form method="post" class="space-y-4">
<div><label class="text-sm font-bold">Имя *</label>
<input name="name" required class="w-full border border-gray-200 rounded-xl px-4 py-3 mt-1 focus:ring-2 focus:ring-brand/30 focus:outline-none" placeholder="Как к вам обращаться"></div>
<div><label class="text-sm font-bold">Телефон *</label>
<input name="phone" required class="w-full border border-gray-200 rounded-xl px-4 py-3 mt-1 focus:ring-2 focus:ring-brand/30 focus:outline-none" placeholder="+996 XXX XXX XXX"></div>
<button class="w-full btn-orange text-white font-bold py-3.5 rounded-xl shadow-lg mt-2">Отправить предзаказ</button>
</form></div>
<div class="md:col-span-2 bg-soft rounded-2xl border border-violet-100 p-6 h-fit">
<h3 class="font-bold mb-3">Состав</h3><div class="space-y-1 mb-3">{items}</div>
<div class="border-t pt-3 flex justify-between font-extrabold text-lg"><span>Итого</span><span class="text-brand">{total:,.0f} сом</span></div>
{phones_html}{rekv_html}
</div></div></div>'''
    return page('Предзаказ', content)

# ==================== ADMIN ====================
def admin_nav(active=''):
    links = [('dashboard','Дашборд'),('products','Товары'),('orders','Заявки'),('categories','Категории'),('settings','Реквизиты')]
    html = '<div class="flex gap-3 mb-6 flex-wrap text-sm">'
    for key, label in links:
        cls = 'font-bold text-brand' if active == key else 'text-gray-500 hover:text-brand'
        html += f'<a href="/admin/{key if key!="dashboard" else "dashboard"}" class="{cls}">{label}</a>'
    html += '<a href="/admin/logout" class="text-red-500 ml-auto">Выйти</a></div>'
    return html

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'): return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True; return redirect(url_for('admin_dashboard'))
        flash('Неверный пароль', 'danger')
    content = '''<div class="min-h-[60vh] flex items-center justify-center px-4">
<div class="bg-white rounded-3xl border shadow-lg p-8 w-full max-w-sm text-center">
<div class="w-14 h-14 mx-auto mb-4 rounded-2xl btn-grad flex items-center justify-center text-white text-2xl"><i class="fas fa-lock"></i></div>
<h1 class="text-xl font-extrabold mb-1">Админ-панель</h1>
<p class="text-sm text-gray-400 mb-5">Введите пароль</p>
<form method="post"><input type="password" name="password" required autofocus class="w-full border rounded-xl px-4 py-3 mb-3 text-center" placeholder="••••••••">
<button class="w-full btn-grad text-white font-bold py-3 rounded-xl">Войти</button></form>
</div></div>'''
    return page('Вход', content)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None); return redirect('/')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    pc, oc, nc = Product.query.count(), Order.query.count(), Order.query.filter_by(status='Новый').count()
    orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    rows = ''.join(f'<tr class="border-t"><td class="px-4 py-2"><a href="/admin/orders/{o.id}" class="text-brand font-semibold">#{o.id}</a></td><td class="px-4 py-2">{o.customer_name}</td><td class="px-4 py-2 font-semibold">{o.total_price:,.0f} сом</td><td class="px-4 py-2"><span class="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-brand font-semibold">{o.status}</span></td><td class="px-4 py-2 text-gray-400 text-sm">{o.created_at.strftime("%d.%m %H:%M")}</td></tr>' for o in orders)
    content = f'''<div class="max-w-6xl mx-auto px-4 py-8">{admin_nav("dashboard")}
<h1 class="text-2xl font-extrabold mb-6">Дашборд</h1>
<div class="grid grid-cols-3 gap-4 mb-8">
<div class="bg-soft rounded-2xl border border-violet-100 p-5 text-center"><div class="text-3xl font-extrabold text-brand">{pc}</div><div class="text-sm text-gray-400">Товаров</div></div>
<div class="bg-soft rounded-2xl border border-violet-100 p-5 text-center"><div class="text-3xl font-extrabold text-brand">{oc}</div><div class="text-sm text-gray-400">Заявок</div></div>
<div class="bg-orange-50 rounded-2xl border border-orange-100 p-5 text-center"><div class="text-3xl font-extrabold text-accent">{nc}</div><div class="text-sm text-gray-400">Новых</div></div>
</div>
<div class="bg-white rounded-2xl border overflow-hidden"><div class="px-4 py-3 font-bold border-b">Последние заявки</div>
<table class="w-full text-sm"><thead class="bg-gray-50 text-gray-400"><tr><th class="text-left px-4 py-2">#</th><th class="text-left px-4 py-2">Клиент</th><th class="text-left px-4 py-2">Сумма</th><th class="text-left px-4 py-2">Статус</th><th class="text-left px-4 py-2">Дата</th></tr></thead>
<tbody>{rows if rows else '<tr><td colspan="5" class="px-4 py-10 text-center text-gray-300">Пока нет заявок</td></tr>'}</tbody></table></div></div>'''
    return page('Админ', content)

@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    rows = ''.join(f'''<tr class="border-t"><td class="px-4 py-3"><div class="flex items-center gap-3"><img src="{p.image_url}" class="w-10 h-10 rounded-lg object-cover bg-gray-50" onerror="this.src='https://via.placeholder.com/40'"><span class="font-semibold">{p.name}</span></div></td>
<td class="px-4 py-3 text-gray-400">{p.category.name if p.category else "—"}</td>
<td class="px-4 py-3 font-bold">{p.price:,.0f} сом</td>
<td class="px-4 py-3 text-right"><a href="/admin/products/edit/{p.id}" class="text-brand text-sm font-semibold mr-3">Изменить</a>
<form action="/admin/products/delete/{p.id}" method="post" class="inline" onsubmit="return confirm('Удалить?')"><button class="text-red-400 text-sm">Удалить</button></form></td></tr>''' for p in products)
    content = f'''<div class="max-w-6xl mx-auto px-4 py-8">{admin_nav("products")}
<div class="flex justify-between items-center mb-6"><h1 class="text-2xl font-extrabold">Товары</h1>
<a href="/admin/products/add" class="btn-grad text-white font-bold px-4 py-2 rounded-xl text-sm">+ Добавить</a></div>
<div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-sm">
<thead class="bg-gray-50 text-gray-400"><tr><th class="text-left px-4 py-2">Товар</th><th class="text-left px-4 py-2">Категория</th><th class="text-left px-4 py-2">Цена</th><th class="text-right px-4 py-2">Действия</th></tr></thead>
<tbody>{rows if rows else '<tr><td colspan="4" class="px-4 py-12 text-center text-gray-300">Нет товаров</td></tr>'}</tbody></table></div></div>'''
    return page('Товары', content)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@app.route('/admin/products/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_product_form(pid=None):
    p = Product.query.get(pid) if pid else None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = float(request.form.get('price', 0))
        if not name or price <= 0:
            flash('Название и цена обязательны', 'danger'); return redirect(request.url)
        uploaded = save_upload(request.files.get('photo'))
        url_fallback = request.form.get('image_url', '').strip()
        if p:
            p.name, p.description, p.price = name, request.form.get('description', ''), price
            if uploaded: p.image_url = uploaded
            elif url_fallback: p.image_url = url_fallback
            p.category_id = request.form.get('category_id', type=int) or None
        else:
            img = uploaded or url_fallback or 'https://via.placeholder.com/400x300?text=Product'
            p = Product(name=name, description=request.form.get('description', ''), price=price,
                        image_url=img, category_id=request.form.get('category_id', type=int) or None)
            db.session.add(p)
        db.session.commit(); flash('Сохранено', 'success')
        return redirect(url_for('admin_products'))
    cats = Category.query.all()
    cat_opts = ''.join(f'<option value="{c.id}" {"selected" if p and p.category_id==c.id else ""}>{c.name}</option>' for c in cats)
    preview = ('<img src="' + p.image_url + '" class="mt-2 h-24 rounded-xl object-cover" onerror="this.style.display=\'none\'">') if p and p.image_url else ''
    content = f'''<div class="max-w-xl mx-auto px-4 py-8">
<a href="/admin/products" class="text-sm text-brand font-semibold">← Назад</a>
<h1 class="text-2xl font-extrabold mt-2 mb-6">{"Редактировать" if p else "Добавить"} товар</h1>
<form method="post" enctype="multipart/form-data" class="bg-white rounded-2xl border p-6 space-y-4">
<div><label class="text-sm font-bold">Название *</label><input name="name" required value="{p.name if p else ""}" class="w-full border rounded-xl px-4 py-2.5 mt-1"></div>
<div><label class="text-sm font-bold">Описание</label><textarea name="description" rows="3" class="w-full border rounded-xl px-4 py-2.5 mt-1">{p.description if p else ""}</textarea></div>
<div><label class="text-sm font-bold">Цена, сом *</label><input name="price" type="number" step="0.01" required value="{p.price if p else ""}" class="w-full border rounded-xl px-4 py-2.5 mt-1"></div>
<div><label class="text-sm font-bold">Категория</label><select name="category_id" class="w-full border rounded-xl px-4 py-2.5 mt-1"><option value="">Без категории</option>{cat_opts}</select></div>
<div><label class="text-sm font-bold">Фото товара</label>
<input type="file" name="photo" accept="image/*" class="w-full border rounded-xl px-4 py-2.5 mt-1 text-sm">
<p class="text-xs text-gray-400 mt-1">Выберите фото с телефона или компьютера</p>{preview}</div>
<div><label class="text-sm font-bold text-gray-400">или ссылка (необязательно)</label>
<input name="image_url" value="" class="w-full border rounded-xl px-4 py-2.5 mt-1" placeholder="https://..."></div>
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
    status = request.args.get('status')
    q = Order.query.order_by(Order.created_at.desc())
    if status: q = q.filter_by(status=status)
    orders = q.all()
    filters = ''.join(f'<a href="/admin/orders?status={s}" class="px-3 py-1 rounded-full text-sm font-semibold {"bg-brand text-white" if status==s else "bg-gray-100 text-gray-600"}">{s}</a>' for s in ['Новый','В обработке','Готов','Выдан','Отменён'])
    rows = ''.join(f'<tr class="border-t"><td class="px-4 py-2"><a href="/admin/orders/{o.id}" class="text-brand font-semibold">#{o.id}</a></td><td class="px-4 py-2">{o.customer_name}</td><td class="px-4 py-2">{o.customer_phone}</td><td class="px-4 py-2 font-bold">{o.total_price:,.0f} сом</td><td class="px-4 py-2"><span class="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-brand font-semibold">{o.status}</span></td><td class="px-4 py-2 text-gray-400 text-sm">{o.created_at.strftime("%d.%m.%Y %H:%M")}</td></tr>' for o in orders)
    content = f'''<div class="max-w-6xl mx-auto px-4 py-8">{admin_nav("orders")}
<div class="flex justify-between items-center mb-4 flex-wrap gap-2"><h1 class="text-2xl font-extrabold">Заявки</h1>
<div class="flex gap-1 flex-wrap"><a href="/admin/orders" class="px-3 py-1 rounded-full text-sm font-semibold {"bg-brand text-white" if not status else "bg-gray-100 text-gray-600"}">Все</a>{filters}</div></div>
<div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-sm">
<thead class="bg-gray-50 text-gray-400"><tr><th class="text-left px-4 py-2">#</th><th class="text-left px-4 py-2">Клиент</th><th class="text-left px-4 py-2">Телефон</th><th class="text-left px-4 py-2">Сумма</th><th class="text-left px-4 py-2">Статус</th><th class="text-left px-4 py-2">Дата</th></tr></thead>
<tbody>{rows if rows else '<tr><td colspan="6" class="px-4 py-12 text-center text-gray-300">Нет заявок</td></tr>'}</tbody></table></div></div>'''
    return page('Заявки', content)

@app.route('/admin/orders/<int:oid>')
@admin_required
def admin_order_detail(oid):
    o = Order.query.get_or_404(oid)
    items = ''.join(f'<div class="flex justify-between py-2 border-b text-sm"><span>{i.product.name if i.product else "?"} × {i.quantity}</span><span class="font-semibold">{i.quantity*i.price:,.0f} сом</span></div>' for i in o.items)
    opts = ''.join(f'<option value="{s}" {"selected" if o.status==s else ""}>{s}</option>' for s in ['Новый','В обработке','Готов','Выдан','Отменён'])
    content = f'''<div class="max-w-3xl mx-auto px-4 py-8">
<a href="/admin/orders" class="text-sm text-brand font-semibold">← Назад</a>
<h1 class="text-2xl font-extrabold mt-2 mb-6">Заявка #{o.id}</h1>
<div class="grid md:grid-cols-3 gap-6">
<div class="md:col-span-2 bg-white rounded-2xl border p-5"><h3 class="font-bold mb-3">Состав</h3>{items}
<div class="flex justify-between font-extrabold pt-3 mt-2 text-lg"><span>Итого</span><span class="text-brand">{o.total_price:,.0f} сом</span></div></div>
<div class="space-y-4">
<div class="bg-soft rounded-2xl border border-violet-100 p-5 text-sm space-y-2">
<div><span class="text-gray-400">Имя:</span> <strong>{o.customer_name}</strong></div>
<div><span class="text-gray-400">Телефон:</span> <strong>{o.customer_phone}</strong></div>
<div><span class="text-gray-400">Дата:</span> {o.created_at.strftime("%d.%m.%Y %H:%M")}</div></div>
<div class="bg-white rounded-2xl border p-5">
<form action="/admin/orders/{o.id}/status" method="post">
<select name="status" class="w-full border rounded-xl px-3 py-2 text-sm mb-3">{opts}</select>
<button class="w-full btn-grad text-white font-bold py-2.5 rounded-xl text-sm">Обновить статус</button>
</form></div></div></div></div>'''
    return page(f'Заявка #{oid}', content)

@app.route('/admin/orders/<int:oid>/status', methods=['POST'])
@admin_required
def admin_update_status(oid):
    o = Order.query.get_or_404(oid)
    s = request.form.get('status')
    if s in ['Новый','В обработке','Готов','Выдан','Отменён']:
        o.status = s; db.session.commit(); flash('Статус обновлён', 'success')
    return redirect(url_for('admin_order_detail', oid=oid))

@app.route('/admin/categories', methods=['GET', 'POST'])
@admin_required
def admin_categories():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name and not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name)); db.session.commit(); flash('Добавлено', 'success')
        return redirect(url_for('admin_categories'))
    cats = Category.query.all()
    rows = ''.join(
        f'<div class="flex justify-between items-center px-4 py-3 border-b"><span class="font-semibold">{c.name}</span>'
        f'<form action="/admin/categories/delete/{c.id}" method="post" onsubmit="return confirm(\'Удалить?\')">'
        f'<button class="text-red-400 text-sm">Удалить</button></form></div>'
        for c in cats)
    content = f'''<div class="max-w-xl mx-auto px-4 py-8">{admin_nav("categories")}
<h1 class="text-2xl font-extrabold mb-6">Категории</h1>
<form method="post" class="flex gap-2 mb-6"><input name="name" required placeholder="Новая категория" class="flex-1 border rounded-xl px-4 py-2.5">
<button class="btn-grad text-white font-bold px-5 py-2.5 rounded-xl">Добавить</button></form>
<div class="bg-white rounded-2xl border overflow-hidden">{rows if rows else '<p class="p-8 text-center text-gray-300">Нет категорий</p>'}</div></div>'''
    return page('Категории', content)

@app.route('/admin/categories/delete/<int:cid>', methods=['POST'])
@admin_required
def admin_delete_category(cid):
    c = Category.query.get_or_404(cid); db.session.delete(c); db.session.commit()
    flash('Удалено', 'success'); return redirect(url_for('admin_categories'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        set_setting('phones', request.form.get('phones', '').strip())
        set_setting('rekvizity', request.form.get('rekvizity', '').strip())
        uploaded = save_upload(request.files.get('rekvizity_photo'))
        if uploaded: set_setting('rekvizity_image', uploaded)
        else:
            url = request.form.get('rekvizity_image', '').strip()
            if url: set_setting('rekvizity_image', url)
        flash('Настройки сохранены', 'success')
        return redirect(url_for('admin_settings'))
    phones = get_setting('phones', '')
    rekvizity = get_setting('rekvizity', '')
    rekvizity_image = get_setting('rekvizity_image', '')
    preview = ('<img src="' + rekvizity_image + '" class="mt-3 max-h-48 rounded-xl border" onerror="this.style.display=\'none\'">') if rekvizity_image else ''
    content = f'''<div class="max-w-xl mx-auto px-4 py-8">{admin_nav("settings")}
<h1 class="text-2xl font-extrabold mb-6">Реквизиты и контакты</h1>
<form method="post" enctype="multipart/form-data" class="bg-white rounded-2xl border p-6 space-y-5">
<div><label class="text-sm font-bold">Номера для связи</label>
<p class="text-xs text-gray-400 mb-1">Каждый номер с новой строки</p>
<textarea name="phones" rows="3" class="w-full border rounded-xl px-4 py-2.5 mt-1" placeholder="+996 700 123 456">{phones}</textarea></div>
<div><label class="text-sm font-bold">Реквизиты (текст)</label>
<textarea name="rekvizity" rows="5" class="w-full border rounded-xl px-4 py-2.5 mt-1" placeholder="Банк, счёт, ФИО...">{rekvizity}</textarea></div>
<div><label class="text-sm font-bold">Фото / QR реквизитов</label>
<input type="file" name="rekvizity_photo" accept="image/*" class="w-full border rounded-xl px-4 py-2.5 mt-1 text-sm">
<p class="text-xs text-gray-400 mt-1">Загрузите фото с телефона</p>{preview}</div>
<div><label class="text-sm font-bold text-gray-400">или ссылка (необязательно)</label>
<input name="rekvizity_image" value="" class="w-full border rounded-xl px-4 py-2.5 mt-1" placeholder="https://..."></div>
<button class="btn-grad text-white font-bold px-6 py-2.5 rounded-xl">Сохранить</button>
</form></div>'''
    return page('Реквизиты', content)


# ==================== TELEGRAM BOT ====================
# --- Настройки бота ---
# Токены лучше задавать в Railway Variables. Ниже — запасные значения.
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY')
ADMIN_IDS = [x.strip() for x in os.environ.get('TELEGRAM_ADMIN_IDS', '8569472160').split(',') if x.strip()]
# OpenAI — ТОЛЬКО из Variables (OPENAI_API_KEY), в код не вшиваем
OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
DEFAULT_SITE = os.environ.get('SITE_URL', 'https://mircancelyarii-production.up.railway.app').rstrip('/')

def tg_api(method, data=None, files=None):
    if not TELEGRAM_TOKEN:
        return None
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}'
    try:
        if files:
            r = requests.post(url, data=data or {}, files=files, timeout=60)
        else:
            r = requests.post(url, json=data or {}, timeout=30)
        return r.json()
    except Exception as e:
        print('TG API error:', e)
        return None

def tg_send(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return tg_api('sendMessage', payload)

def get_bot_state(chat_id):
    st = BotState.query.filter_by(chat_id=str(chat_id)).first()
    if not st:
        st = BotState(chat_id=str(chat_id), step='idle')
        db.session.add(st)
        db.session.commit()
    return st

def ai_describe_product(image_path):
    """Определяет товар по фото через OpenAI Vision. Без ключа возвращает None."""
    if not OPENAI_KEY:
        return None
    try:
        import base64
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = image_path.rsplit('.', 1)[-1].lower()
        mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif'}.get(ext, 'image/jpeg')
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o-mini',
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'Ты помощник магазина канцтоваров в Кыргызстане. По фото определи товар. Ответь ТОЛЬКО коротким названием товара на русском (2-6 слов), без кавычек и пояснений. Пример: Набор цветных карандашей 24 шт'},
                        {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}}
                    ]
                }],
                'max_tokens': 80
            },
            timeout=45
        )
        data = resp.json()
        name = data['choices'][0]['message']['content'].strip().strip('"').strip("'")
        # убрать лишнее если модель добавила текст
        if '\n' in name:
            name = name.split('\n')[0].strip()
        return name[:200] if name else None
    except Exception as e:
        print('AI vision error:', e)
        return None

def download_tg_photo(file_id):
    """Скачать фото из Telegram, сохранить в uploads, вернуть /uploads/xxx"""
    info = tg_api('getFile', {'file_id': file_id})
    if not info or not info.get('ok'):
        return None
    file_path = info['result']['file_path']
    url = f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}'
    try:
        r = requests.get(url, timeout=60)
        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else 'jpg'
        if ext not in ALLOWED_EXT:
            ext = 'jpg'
        name = f'{uuid.uuid4().hex}.{ext}'
        full = os.path.join(UPLOAD_FOLDER, name)
        with open(full, 'wb') as f:
            f.write(r.content)
        return f'/uploads/{name}', full
    except Exception as e:
        print('download photo error:', e)
        return None

def is_admin(user_id):
    if not ADMIN_IDS:
        return True  # если список пуст — разрешаем всем (для теста)
    return str(user_id) in ADMIN_IDS

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    if not TELEGRAM_TOKEN:
        return 'bot not configured', 200
    try:
        update = request.get_json(force=True, silent=True) or {}
    except Exception:
        return 'ok', 200

    message = update.get('message') or update.get('edited_message')
    if not message:
        return 'ok', 200

    chat_id = message['chat']['id']
    user_id = message.get('from', {}).get('id')
    text = (message.get('text') or '').strip()

    if not is_admin(user_id):
        tg_send(chat_id, '⛔ У вас нет доступа к добавлению товаров.')
        return 'ok', 200

    st = get_bot_state(chat_id)

    # /start
    if text.startswith('/start'):
        st.step = 'idle'
        st.draft_name = ''
        st.draft_image = ''
        db.session.commit()
        tg_send(chat_id,
            '👋 <b>Бот магазина «Мир канцелярии»</b>\n\n'
            'Отправьте <b>фото товара</b> — я определю, что это, и добавлю в каталог.\n\n'
            'После фото пришлите <b>цену в сомах</b> (только число).\n\n'
            'Команды:\n/cancel — отменить\n/help — помощь')
        return 'ok', 200

    if text.startswith('/cancel'):
        st.step = 'idle'
        st.draft_name = ''
        st.draft_image = ''
        db.session.commit()
        tg_send(chat_id, '❌ Отменено. Пришлите новое фото товара.')
        return 'ok', 200

    if text.startswith('/help'):
        tg_send(chat_id, '1) Пришлите фото\n2) Подтвердите или исправьте название\n3) Пришлите цену (число)\n4) Товар появится на сайте')
        return 'ok', 200

    # Фото
    photos = message.get('photo')
    if photos:
        # берём самое большое
        file_id = photos[-1]['file_id']
        tg_send(chat_id, '🔍 Смотрю на фото...')
        result = download_tg_photo(file_id)
        if not result:
            tg_send(chat_id, 'Не удалось скачать фото. Попробуйте ещё раз.')
            return 'ok', 200
        web_path, full_path = result
        name = ai_describe_product(full_path)
        st.draft_image = web_path
        if name:
            st.draft_name = name
            st.step = 'wait_price'
            db.session.commit()
            tg_send(chat_id,
                f'✅ Похоже, это:\n\n<b>{name}</b>\n\n'
                f'Пришлите <b>цену в сомах</b> (только число, например <code>150</code>).\n'
                f'Или напишите другое название — тогда спросим цену после.')
        else:
            st.draft_name = ''
            st.step = 'wait_name'
            db.session.commit()
            msg = '📷 Фото получено.'
            if not OPENAI_KEY:
                msg += '\n(AI не настроен — укажите название сами)'
            else:
                msg += '\nНе удалось распознать. Напишите название товара:'
            msg += '\n\nНапишите <b>название</b> товара:'
            tg_send(chat_id, msg)
        return 'ok', 200

    # Текст в зависимости от шага
    if st.step == 'wait_name' and text:
        st.draft_name = text[:200]
        st.step = 'wait_price'
        db.session.commit()
        tg_send(chat_id, f'Название: <b>{st.draft_name}</b>\n\nТеперь пришлите <b>цену в сомах</b> (число):')
        return 'ok', 200

    if st.step == 'wait_price' and text:
        # если это не число — считаем что пользователь меняет название
        price_txt = text.replace('сом', '').replace('с', '').replace(',', '.').strip()
        try:
            price = float(price_txt)
            if price <= 0:
                raise ValueError()
        except ValueError:
            # смена названия
            st.draft_name = text[:200]
            db.session.commit()
            tg_send(chat_id, f'Название обновлено: <b>{st.draft_name}</b>\n\nПришлите <b>цену</b> (число):')
            return 'ok', 200

        # создаём товар
        product = Product(
            name=st.draft_name or 'Товар',
            description='Добавлено через Telegram-бот',
            price=price,
            image_url=st.draft_image or 'https://via.placeholder.com/400x300?text=Product',
            category_id=None
        )
        db.session.add(product)
        st.step = 'idle'
        st.draft_name = ''
        st.draft_image = ''
        db.session.commit()

        site = os.environ.get('SITE_URL', DEFAULT_SITE).rstrip('/')
        link = f'{site}/product/{product.id}' if site else f'/product/{product.id}'
        tg_send(chat_id,
            f'🎉 Товар добавлен в каталог!\n\n'
            f'<b>{product.name}</b>\n'
            f'{product.price:,.0f} сом\n\n'
            f'🔗 {link}\n\n'
            f'Можете прислать следующее фото.')
        return 'ok', 200

    if text:
        tg_send(chat_id, 'Пришлите <b>фото товара</b> или /help')
    return 'ok', 200

@app.route('/setup-webhook')
def setup_webhook():
    """Один раз открыть этот URL после деплоя, чтобы привязать бота."""
    if not TELEGRAM_TOKEN:
        return 'Укажите TELEGRAM_BOT_TOKEN в переменных Railway', 400
    site = os.environ.get('SITE_URL', DEFAULT_SITE).rstrip('/') or request.url_root.rstrip('/')
    webhook_url = f'{site}/telegram-webhook'
    r = tg_api('setWebhook', {'url': webhook_url})
    return f'<pre>Webhook: {webhook_url}\n\nОтвет Telegram:\n{json.dumps(r, indent=2, ensure_ascii=False)}</pre>'


# ==================== INIT ====================
with app.app_context():
    db.create_all()
    if Category.query.count() == 0:
        for n in ['Письменные принадлежности', 'Тетради и блокноты', 'Творчество и рисование',
                  'Школьные товары', 'Офисные принадлежности', 'Подарки и сувениры']:
            db.session.add(Category(name=n))
        db.session.commit()


# Авто-привязка webhook при старте
def _auto_webhook():
    if not TELEGRAM_TOKEN:
        return
    try:
        site = os.environ.get('SITE_URL', DEFAULT_SITE).rstrip('/')
        url = f'{site}/telegram-webhook'
        r = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook',
            json={'url': url},
            timeout=15
        )
        print('Webhook setup:', r.json())
    except Exception as e:
        print('Webhook setup failed:', e)

try:
    _auto_webhook()
except Exception:
    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
