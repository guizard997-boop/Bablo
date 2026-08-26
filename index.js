/**
 * WhatsApp-бот для Railway (неофициальный, whatsapp-web.js).
 * Работает 24/7 в контейнере, QR-код для подключения открывается в браузере
 * по адресу вашего Railway-проекта: https://<ваш-проект>.up.railway.app/qr
 *
 * Переменные окружения (задаются в Railway -> Variables):
 *   GEMINI_API_KEY      - бесплатный ключ с https://aistudio.google.com/apikey
 *   SITE_BASE_URL        - адрес сайта (по умолчанию уже подставлен ваш)
 *   SITE_ADMIN_PASSWORD  - пароль от /admin вашего сайта
 *   ALLOWED_NUMBERS      - (необязательно) номера через запятую, кому разрешено писать боту
 *   SESSION_PATH          - путь к volume для хранения сессии WhatsApp (по умолчанию /app/session)
 */

const express = require('express');
const QRCode = require('qrcode');
const { Client, LocalAuth } = require('whatsapp-web.js');
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');
const path = require('path');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';
const SITE_BASE_URL = (process.env.SITE_BASE_URL || 'https://mircancelyarii-production.up.railway.app').replace(/\/$/, '');
const SITE_ADMIN_PASSWORD = process.env.SITE_ADMIN_PASSWORD || '';
const ALLOWED_NUMBERS = (process.env.ALLOWED_NUMBERS || '').split(',').map((s) => s.trim()).filter(Boolean);
const SESSION_PATH = process.env.SESSION_PATH || '/app/session';
const PORT = process.env.PORT || 3000;

const mediaDir = path.join(__dirname, 'media');
if (!fs.existsSync(mediaDir)) fs.mkdirSync(mediaDir);

let lastQr = null;
let clientReady = false;
let siteSessionCookie = null;
const pendingDrafts = new Map();

// ---------- Веб-страница для сканирования QR ----------
const app = express();

app.get('/', (req, res) => {
  res.send(clientReady ? '✅ Бот подключён и работает.' : '⏳ Бот не подключён. Откройте /qr, чтобы отсканировать код.');
});

app.get('/qr', async (req, res) => {
  if (clientReady) return res.send('✅ Уже подключено, QR не нужен.');
  if (!lastQr) return res.send('QR ещё не сгенерирован, обновите страницу через несколько секунд.');
  try {
    const png = await QRCode.toBuffer(lastQr, { width: 400 });
    res.set('Content-Type', 'image/png');
    res.send(png);
  } catch (e) {
    res.status(500).send('Ошибка генерации QR: ' + e.message);
  }
});

app.listen(PORT, () => console.log(`HTTP сервер запущен на порту ${PORT}`));

// ---------- WhatsApp клиент ----------
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  puppeteer: {
    headless: true,
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

client.on('qr', (qr) => {
  lastQr = qr;
  console.log('Новый QR сгенерирован. Откройте /qr на публичном адресе Railway, чтобы отсканировать.');
});

client.on('ready', () => {
  clientReady = true;
  console.log('✅ Бот подключён и готов принимать фото!');
});

client.on('auth_failure', (msg) => console.error('Ошибка авторизации:', msg));
client.on('disconnected', (reason) => {
  clientReady = false;
  console.log('Клиент отключён:', reason);
});

// ---------- Обработка сообщений ----------
client.on('message', async (msg) => {
  try {
    if (ALLOWED_NUMBERS.length > 0) {
      const from = msg.from.replace('@c.us', '');
      if (!ALLOWED_NUMBERS.includes(from)) return;
    }

    const chatId = msg.from;

    if (msg.hasMedia) {
      const media = await msg.downloadMedia();
      if (!media || !media.mimetype.startsWith('image/')) return;

      await msg.reply('📸 Фото получено, генерирую название и описание...');

      const ext = media.mimetype.split('/')[1] || 'jpg';
      const fileName = `product_${Date.now()}.${ext}`;
      const filePath = path.join(mediaDir, fileName);
      fs.writeFileSync(filePath, Buffer.from(media.data, 'base64'));

      const { title, description } = await generateProductInfo(media.data, media.mimetype);

      pendingDrafts.set(chatId, { filePath, mimetype: media.mimetype, title, description });

      await msg.reply(
        `✅ Похоже, это:\n\n*Название:* ${title}\n*Описание:* ${description}\n\n` +
          `Пришлите цену в сомах (например: 150), чтобы опубликовать товар на сайте.\n` +
          `Если хотите другое название — просто напишите его.`
      );
      return;
    }

    const draft = pendingDrafts.get(chatId);
    if (draft && msg.body) {
      const text = msg.body.trim();
      const priceMatch = text.replace(',', '.').match(/^\d+(\.\d+)?$/);

      if (priceMatch) {
        const price = parseFloat(priceMatch[0]);
        await msg.reply('🚀 Публикую товар на сайте...');
        await publishToSite({ ...draft, price });
        pendingDrafts.delete(chatId);
        await msg.reply(`✅ Товар «${draft.title}» опубликован на сайте за ${price} сом!`);
      } else {
        draft.title = text;
        pendingDrafts.set(chatId, draft);
        await msg.reply(`Название обновлено: *${text}*\n\nТеперь пришлите цену в сомах (число):`);
      }
    }
  } catch (err) {
    console.error('Ошибка обработки сообщения:', err);
    await msg.reply('⚠️ Что-то пошло не так. Попробуйте ещё раз или проверьте логи.');
  }
});

// ---------- Генерация названия и описания через Gemini (бесплатно) ----------
async function generateProductInfo(base64Data, mimetype) {
  if (!GEMINI_API_KEY) {
    throw new Error('Не задан GEMINI_API_KEY в переменных окружения Railway.');
  }

  const prompt =
    'Ты — помощник интернет-магазина канцтоваров. По фото товара придумай короткое ' +
    'привлекательное название (до 60 символов) и продающее описание (2-4 предложения) ' +
    'на русском языке. Ответь СТРОГО в формате:\n' +
    'НАЗВАНИЕ: ...\nОПИСАНИЕ: ...';

  const models = ['gemini-2.0-flash', 'gemini-1.5-flash'];
  let lastError;

  for (const model of models) {
    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${GEMINI_API_KEY}`;
      const payload = {
        contents: [
          {
            parts: [
              { text: prompt },
              { inline_data: { mime_type: mimetype, data: base64Data } },
            ],
          },
        ],
      };

      const res = await axios.post(url, payload, { timeout: 45000 });
      const raw = res.data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
      if (!raw) continue;

      let title = null;
      let description = null;
      for (const line of raw.split('\n')) {
        const l = line.trim();
        if (l.toUpperCase().startsWith('НАЗВАНИЕ:')) title = l.split(':').slice(1).join(':').trim();
        else if (l.toUpperCase().startsWith('ОПИСАНИЕ:')) description = l.split(':').slice(1).join(':').trim();
      }
      if (title) return { title, description: description || '' };
    } catch (err) {
      lastError = err;
      console.error(`Gemini (${model}) ошибка:`, err.response?.data || err.message);
    }
  }

  throw lastError || new Error('Gemini не вернул результат');
}

// ---------- Логин в админку сайта ----------
async function loginToSite() {
  if (!SITE_ADMIN_PASSWORD) {
    throw new Error('Не задан SITE_ADMIN_PASSWORD в переменных окружения Railway.');
  }

  const params = new URLSearchParams();
  params.append('password', SITE_ADMIN_PASSWORD);

  const res = await axios.post(`${SITE_BASE_URL}/admin`, params, {
    maxRedirects: 0,
    validateStatus: (s) => s === 302 || s === 200,
  });

  if (res.status !== 302) {
    throw new Error('Не удалось войти в админку сайта — проверьте SITE_ADMIN_PASSWORD.');
  }

  const setCookie = res.headers['set-cookie'];
  if (!setCookie) throw new Error('Сайт не вернул сессионную куку при логине.');
  siteSessionCookie = setCookie.map((c) => c.split(';')[0]).join('; ');
}

// ---------- Публикация товара на сайт ----------
async function publishToSite({ filePath, mimetype, title, description, price }) {
  if (!siteSessionCookie) await loginToSite();

  const form = new FormData();
  form.append('name', title);
  form.append('description', description);
  form.append('price', String(price));
  form.append('photo', fs.createReadStream(filePath), {
    contentType: mimetype,
    filename: path.basename(filePath),
  });

  const doPost = () =>
    axios.post(`${SITE_BASE_URL}/admin/products/add`, form, {
      maxRedirects: 0,
      validateStatus: (s) => s === 302 || s === 200,
      headers: { ...form.getHeaders(), Cookie: siteSessionCookie },
    });

  let res;
  try {
    res = await doPost();
  } catch (err) {
    res = err.response;
  }

  if (!res || res.status !== 302) {
    await loginToSite();
    res = await doPost();
  }

  if (res.status !== 302) {
    throw new Error('Не удалось опубликовать товар — сайт не подтвердил сохранение.');
  }
}

client.initialize();
