# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from telebot.storage import StateMemoryStorage
from threading import Thread
import asyncio
import logging
from aiohttp import web

# ---------- CONFIG (Берем из настроек Render) ----------
TOKEN = os.environ.get("BOT_TOKEN", "8162969073:AAFH5BPDIWNHqVuzfzbHrqFZsBTxIsmYpK4")
ADMIN_ID = os.environ.get("ADMIN_ID", "6181649972")
WHATSAPP_LINK = "https://wa.me/message/WGW3DA5VHIMTG1"

# aiohttp health server
async def health(request):
    return web.Response(text="Cleaning Bot is Live")

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logging.info(f"Health server running on 0.0.0.0:{port}")

# Константы из твоего кода
MIN_TRAVEL_PER_PERSON = 1200
HOURLY_RATE = 450
DISTANCE_FEE = {"Кемер": 600, "Белек": 600, "Анталья": 0}
MAX_DISCOUNT_TL = 1500

PRICES = {
    "1+0": {"Экспресс": 1400, "Поддерживающая": 1800, "Генеральная": 2500, "VIP": 3000, "После ремонта": 2800},
    "1+1": {"Экспресс": 1800, "Поддерживающая": 2600, "Генеральная": 3200, "VIP": 4000, "После ремонта": 6400},
    "2+1_low": {"Экспресс": 2200, "Поддерживающая": 3200, "Генеральная": 3900, "VIP": 5600, "После ремонта": 7800},
    "2+1_high": {"Экспресс": 2600, "Поддерживающая": 3800, "Генеральная": 4500, "VIP": 6200, "После ремонта": 9000},
    "3+1": {"Экспресс": 3200, "Поддерживающая": 4300, "Генеральная": 5300, "VIP": 7800, "После ремонта": 10600},
    "4+1": {"Экспресс": 3900, "Поддерживающая": 5000, "Генеральная": 6500, "VIP": 8800, "После ремонта": 13000},
    "5+1": {"Экспресс": 4800, "Поддерживающая": 7000, "Генеральная": 9000, "VIP": 12900, "После ремонта": 18000}
}

RECOMM_TABLE = {
    "1+0": {"Экспресс": (1, 1.5), "Поддерживающая": (1, 2), "Генеральная": (1, 3), "VIP": (1, 4)},
    "1+1": {"Экспресс": (1, 2), "Поддерживающая": (1, 3), "Генеральная": (1, 4), "VIP": (1, 5)},
    "2+1_low": {"Экспресс": (1, 3), "Поддерживающая": (1, 4), "Генеральная": (1, 6), "VIP": (1, 7)},
    "2+1_high": {"Экспресс": (1, 3), "Поддерживающая": (1, 4), "Генеральная": (1, 6), "VIP": (1, 7)},
    "3+1": {"Экспресс": (1, 4), "Поддерживающая": (2, 4), "Генеральная": (2, 4), "VIP": (2, 6)},
    "4+1": {"Экспресс": (2, 4), "Поддерживающая": (2, 5), "Генеральная": (2, 6), "VIP": (3, 6)},
    "5+1": {"Экспресс": (2, 5), "Поддерживающая": (2, 7), "Генеральная": (3, 5), "VIP": (3, 8)}
}

EXTRAS = {
    "стандартные окна (1 створка)": {"price": 100, "time": 6},
    "панорамные окна (1 створка)": {"price": 190, "time": 7.5},
    "остекление парапета (1 м)": {"price": 150, "time": 10},
    "мойка холодильника": {"price": 500, "time": 60},
    "мойка морозильной камеры": {"price": 200, "time": 30},
    "мойка духовки": {"price": 500, "time": 60},
    "мойка посудомойки": {"price": 200, "time": 30},
    "мойка стиральной машины": {"price": 150, "time": 30},
    "мойка лестничного пролета": {"price": 400, "time": 60},
    "шторы снять+постирать+повесить (1м)": {"price": 100, "time": 6},
    "глажка (1 час)": {"price": 400, "time": 60},
    "паровая швабра (1 кв.м.)": {"price": 30, "time": 0.5},
}

NUM_EXTRA_KEYS = {
    "Стандартные окна (створки)": "стандартные окна (1 створка)",
    "Панорамные окна (створки)": "панорамные окна (1 створка)",
    "Остекление парапета (м.п.)": "остекление парапета (1 м)",
    "Холодильник (шт)": "мойка холодильника",
    "Духовка (шт)": "мойка духовки",
    "Глажка (часы)": "глажка (1 час)",
}

storage = StateMemoryStorage()
bot = telebot.TeleBot(TOKEN, state_storage=storage)
SESS = {}

# ---------- ЛОГИКА РАСЧЕТА (Оригинальная) ----------

def calculate_total(chat_id):
    data = SESS.get(chat_id, {})
    service = data.get("service_type")
    if service == "Почасовая":
        return {"is_hourly": True}

    layout = data.get("layout")
    area = data.get("area")
    kitchen_isolated = data.get("kitchen_isolated", False)
    
    temp_layout = layout
    if kitchen_isolated:
        if layout == "1+0":
            temp_layout = "1+1"
        elif layout in ["1+1", "2+1", "3+1", "4+1"]:
            rooms = int(layout.split("+")[0])
            temp_layout = f"{rooms + 1}+1"

    layout_key = temp_layout
    if layout_key == "2+1":
        layout_key = "2+1_low" if area == "<100 м²" else "2+1_high"

    base_price = PRICES.get(layout_key, {}).get(service, 0)
    if base_price == 0:
        return None

    # Множитель для "После ремонта"
    repair_multiplier = 2 if service == "После ремонта" else 1
    base_with_repair = base_price * repair_multiplier

    # Доплаты за санузлы и балконы сверх 1-го
    bathrooms = int(data.get("bathrooms", "0") or 0)
    balconies = int(data.get("balconies", "0") or 0)
    extra_bath_fee = max(0, bathrooms - 1) * 400
    extra_balcony_fee = max(0, balconies - 1) * 200
    rooms_surcharge = extra_bath_fee + extra_balcony_fee

    # Подсчет доп. услуг
    extras_p, extras_t = 0, 0
    for name, qty in data.get("extras", []):
        extras_p += EXTRAS[name]["price"] * qty
        extras_t += EXTRAS[name]["time"] * qty

    # База для скидок
    discounts_base = base_with_repair + rooms_surcharge + extras_p

    # Многоуровневые скидки с лимитами
    discounts = data.get("discounts_selected", {})
    disc_first = min(discounts_base * 0.10, 1000) if discounts.get("first_order") else 0
    disc_second = min(discounts_base * 0.10, 1000) if discounts.get("second_order") else 0
    disc_vac = min(discounts_base * 0.05, 250) if discounts.get("provide_vac") else 0
    disc_clean = min(discounts_base * 0.05, 250) if discounts.get("provide_cleaners") else 0

    disc_sum = disc_first + disc_second + disc_vac + disc_clean
    disc_capped = min(disc_sum, MAX_DISCOUNT_TL)

    # Рекомендации по людям и времени (оставляем прежнюю таблицу)
    rec_c, rec_h = RECOMM_TABLE.get(layout_key, {}).get(service, (1, 4))
    rec_h_total = rec_h + (extras_t / 60 / rec_c)

    # Итог без учета удаленности, но с минимумом за выезд
    subtotal = discounts_base - disc_capped
    subtotal_with_min = max(subtotal, MIN_TRAVEL_PER_PERSON * rec_c)

    # Удаленность: добавляется в самом конце
    dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
    final_total = subtotal_with_min + dist_f

    return {
        "base": int(base_with_repair),
        "extras": int(extras_p),
        "dist": int(dist_f),
        "disc": int(disc_capped),
        "rooms_surcharge": int(rooms_surcharge),
        "total": int(final_total),
        "c": rec_c,
        "h": round(rec_h_total, 1),
        "pct": 0,
        "is_hourly": False,
    }

# ---------- ОБРАБОТЧИКИ (Оригинальные) ----------

@bot.message_handler(commands=["start"])
def handle_start(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "discounts_selected": {}}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ", "Правила")
    bot.send_message(m.chat.id, "👋 Привет! Я **Чистюля** — помощник CleanTeam.", parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Правила")
def handle_rules(m):
    bot.send_message(m.chat.id, """📜 *Краткие правила:*
• Отмена за 14ч без штрафа.
• Мин. выезд: 1200₺.
• Оплата: TRY, IBAN, USDT.""", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "СТАРТ")
def start_proc(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Анталья", "Кемер", "Белек")
    bot.send_message(m.chat.id, "📍 Выберите город:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Анталья", "Кемер", "Белек"])
def city_set(m):
    if m.chat.id not in SESS:
        handle_start(m)
        return
    
    SESS[m.chat.id]["city"] = m.text
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая")
    bot.send_message(m.chat.id, "🧹 Тип уборки:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая"])
def type_set(m):
    if m.chat.id not in SESS:
        handle_start(m)
        return
        
    SESS[m.chat.id]["service_type"] = m.text
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    kb.add("1+0", "1+1", "2+1", "3+1", "4+1", "5+1", "6+1", "7+1")
    bot.send_message(m.chat.id, "🏠 Планировка:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["1+0","1+1","2+1","3+1","4+1","5+1","6+1","7+1"])
def layout_set(m):
    if m.chat.id not in SESS:
        handle_start(m)
        return
    SESS[m.chat.id]["layout"] = m.text
    if m.text in ["6+1", "7+1"]:
        bot.send_message(m.chat.id, f"🏢 Большая площадь! Для точного расчета напишите менеджеру: {WHATSAPP_LINK}")
        return
    if m.text == "2+1":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("<100 м²", ">100 м²")
        bot.send_message(m.chat.id, "📐 Площадь:", reply_markup=kb)
    else: ask_k(m.chat.id)

@bot.message_handler(func=lambda m: m.text in ["<100 м²", ">100 м²"])
def area_set(m):
    if m.chat.id not in SESS:
        handle_start(m)
        return
    SESS[m.chat.id]["area"] = m.text
    ask_k(m.chat.id)

def ask_k(cid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Да, изолированная", "Нет, совмещенная")
    bot.send_message(cid, "🍽 Кухня изолированная?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Да, изолированная", "Нет, совмещенная"])
def k_set(m):
    if m.chat.id not in SESS:
        handle_start(m)
        return
    SESS[m.chat.id]["kitchen_isolated"] = (m.text == "Да, изолированная")
    SESS[m.chat.id]["step"] = "bathrooms"
    bot.send_message(m.chat.id, "🚽 Количество санузлов?", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "bathrooms")
def b_set(m):
    if not m.text.isdigit(): bot.send_message(m.chat.id, "Введите число."); return
    SESS[m.chat.id]["bathrooms"] = m.text
    SESS[m.chat.id]["step"] = "balconies"
    bot.send_message(m.chat.id, "🌅 Количество балконов?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "balconies")
def bal_set(m):
    if not m.text.isdigit(): bot.send_message(m.chat.id, "Введите число."); return
    SESS[m.chat.id]["balconies"] = m.text
    show_ex(m.chat.id)

def show_ex(cid):
    SESS[cid]["step"] = "extras"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for k in NUM_EXTRA_KEYS: kb.add(k)
    kb.add("✅ Завершить выбор")
    bot.send_message(cid, "➕ Доп. услуги:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extras")
def ex_hand(m):
    if m.text == "✅ Завершить выбор": show_disc(m.chat.id); return
    if m.text in NUM_EXTRA_KEYS:
        SESS[m.chat.id]["await_extra"] = NUM_EXTRA_KEYS[m.text]
        SESS[m.chat.id]["step"] = "extra_q"
        bot.send_message(m.chat.id, f"Кол-во для: {m.text}", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extra_q")
def ex_q_hand(m):
    if not m.text.isdigit(): return
    name = SESS[m.chat.id].pop("await_extra")
    SESS[m.chat.id]["extras"].append((name, int(m.text)))
    show_ex(m.chat.id)

def show_disc(cid):
    SESS[cid]["step"] = "discounts"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Первый заказ -10%", "Каждый второй заказ -10%", "Свой пылесос -5%", "Своя химия -5%", "➡️ К расчету")
    bot.send_message(cid, "🎁 Скидки:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "discounts")
def disc_hand(m):
    chat = m.chat.id
    sel = SESS[chat]["discounts_selected"]
    if m.text == "➡️ К расчету": finalize(chat); return
    elif "Первый" in m.text: sel["first_order"] = True
    elif "второй" in m.text: sel["second_order"] = True
    elif "пылесос" in m.text: sel["provide_vac"] = True
    elif "химия" in m.text: sel["provide_cleaners"] = True
    bot.send_message(chat, f"✅ Учтено: {m.text}")

def finalize(cid):
    res = calculate_total(cid)
    SESS[cid]["result"] = res
    SESS[cid]["step"] = "final"
    data = SESS[cid]
    ext_s = "\n".join([f"• {n}: {q}" for n, q in data["extras"]]) if data["extras"] else "Нет"
    
    if res.get("is_hourly"):
        price_text = "💰 *ИТОГО: Индивидуальный расчет*"
        footer = "ℹ️ _Для почасовой уборки стоимость зависит от времени работы. Отправьте заявку для связи с менеджером._"
    else:
        price_text_lines = [f"💰 *ИТОГО: ~{res['total']} TL*"]
        if res.get('dist', 0) > 0:
            price_text_lines.append(f"_(в т.ч. доплата за удаленность: {res['dist']} TL)_")
        price_text_lines.append(f"👥 Рекомендуем: {res['c']} чел. на {res['h']} ч.")
        price_text = "\n".join(price_text_lines)
        footer = "ℹ️ _Цена предварительная. Конечная стоимость может быть скорректирована на месте._"

    msg = (f"📋 *ВАШ РАСЧЕТ*\n"
           f"📍 {data['city']}, {data['service_type']}, {data['layout']}\n"
           f"🍽 Кухня изолир: {'Да' if data['kitchen_isolated'] else 'Нет'}\n"
           f"🛁 {data['bathrooms']} санузла, {data['balconies']} балкона\n"
           f"➖➖➖➖➖➖\n"
           f"{price_text}\n"
           f"➖➖➖➖➖➖\n"
           f"📝 Допы: {ext_s}\n\n"
           f"{footer}")
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Отправить заявку", "🔄 В начало")
    bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ Отправить заявку")
def ask_con(m):
    if m.chat.id not in SESS:
        handle_start(m)
        return
    SESS[m.chat.id]["step"] = "contact"
    bot.send_message(m.chat.id, "📞 Напишите ваш номер WhatsApp для связи:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "contact")
def send_adm(m):
    cid = m.chat.id
    data = SESS[cid]
    res = data["result"]
    contact = m.text
    price_val = "Почасовая (индивидуально)" if res.get("is_hourly") else f"{res['total']} TL"
    
    adm_msg = (f"🔔 *НОВАЯ ЗАЯВКА*\n"
               f"👤 Клиент: {contact}\n"
               f"📍 {data['city']}, {data['layout']}, {data['service_type']}\n"
               f"🛁 Санузлов: {data['bathrooms']}, Балконов: {data['balconies']}\n"
               f"💰 Сумма: {price_val}")
    try:
        bot.send_message(ADMIN_ID, adm_msg, parse_mode="Markdown")
        bot.send_message(cid, f"✅ **Заявка принята!**\nМенеджер свяжется с вами.\n\n"
                             f"📸 [Instagram](https://www.instagram.com/cleanteam.antalya)\n"
                             f"⚡️ [WhatsApp]({WHATSAPP_LINK})", 
                             parse_mode="Markdown", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ"))
    except Exception:
        bot.send_message(cid, f"Ошибка. Свяжитесь: {WHATSAPP_LINK}")
    SESS.pop(cid, None)

# ---------- ГЛАВНЫЙ ЗАПУСК ----------
async def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("CleanTeam Bot is starting...")

    # Запускаем health-сервер до старта опроса
    asyncio.create_task(start_health_server())

    # Бесконечный защищенный цикл опроса
    while True:
        try:
            # infinity_polling блокирующая — выносим в отдельный поток исполнителя
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, bot.infinity_polling)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())