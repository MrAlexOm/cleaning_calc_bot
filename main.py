# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from telebot.storage import StateMemoryStorage
import asyncio
import logging
from aiohttp import web
import time
from requests.exceptions import ConnectionError as RequestsConnectionError, ReadTimeout
from urllib3.exceptions import ProtocolError

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
    logging.info(f"Health server running on port {port}")

# ---------- ДАННЫЕ И ЦЕНЫ ----------
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

def send_safe(chat_id, text, parse_mode=None, reply_markup=None, max_retries=3):
    """Безопасная отправка сообщений с повторами"""
    for attempt in range(max_retries):
        try:
            return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True)
        except (RequestsConnectionError, ReadTimeout, ProtocolError) as e:
            logging.warning(f"send_safe retry {attempt+1}/{max_retries} due to network error: {e}")
            time.sleep(0.3)
        except Exception as e:
            logging.error(f"send_safe aborted due to non-network error: {e}")
            break
    try:
        return bot.send_message(chat_id, text)
    except Exception as e:
        logging.error(f"send_safe final failure: {e}")
        return None

# ---------- ЛОГИКА РАСЧЕТА ----------
def calculate_total(chat_id):
    data = SESS.get(chat_id, {})
    service = data.get("service_type")

    if service == "Почасовая":
        hours = int(data.get("hours", 0))
        cleaners = int(data.get("cleaners", 1))
        total = hours * cleaners * HOURLY_RATE
        dist_f = DISTANCE_FEE.get(data.get("city"), 0) * cleaners
        # Проверка на минимальный выезд
        total = max(total, MIN_TRAVEL_PER_PERSON * cleaners)
        return {"total": int(total + dist_f), "is_hourly": True, "c": cleaners, "h": hours, "dist": dist_f}

    layout = data.get("layout")
    area = data.get("area")
    kitchen_isolated = data.get("kitchen_isolated", False)

    # Логика изменения планировки при изолированной кухне
    temp_layout = layout
    if kitchen_isolated:
        if layout == "1+0": temp_layout = "1+1"
        elif layout in ["1+1", "2+1", "3+1", "4+1"]:
            rooms = int(layout.split("+")[0])
            temp_layout = f"{rooms + 1}+1"

    layout_key = temp_layout
    if layout_key == "2+1":
        layout_key = "2+1_low" if area == "<100 м²" else "2+1_high"

    bathrooms = int(data.get("bathrooms", "1") or 1)
    balconies = int(data.get("balconies", "1") or 1)

    # Считаем доплату за комнаты заранее (для базы)
    extra_bath_fee = max(0, bathrooms - 1) * 400
    extra_balcony_fee = max(0, balconies - 1) * 200
    rooms_surcharge = extra_bath_fee + extra_balcony_fee

    extras_p, extras_t = 0, 0
    for name, qty in data.get("extras", []):
        extras_p += EXTRAS[name]["price"] * qty
        extras_t += EXTRAS[name]["time"] * qty

    rec_c, rec_h = RECOMM_TABLE.get(layout_key, {}).get(service if service != "После ремонта" else "Генеральная", (1, 4))
    rec_h_total = rec_h + (extras_t / 60 / rec_c)

    base_price_key = service if service != "После ремонта" else "Генеральная"
    base = PRICES.get(layout_key, {}).get(base_price_key, 0)
    
    if service == "После ремонта":
        # Удваиваем базу + допы + доплату за комнаты
        total_before = (base + extras_p + rooms_surcharge) * 2
    else:
        total_before = base + rooms_surcharge + extras_p

    discounts = data.get("discounts_selected", {})
    disc_sum = 0
    if discounts.get("first_order"): disc_sum += min(total_before * 0.1, 1000)
    elif discounts.get("second_order"): disc_sum += min(total_before * 0.1, 1000)
    
    if discounts.get("provide_vac"): disc_sum += min(total_before * 0.05, 250)
    if discounts.get("provide_cleaners"): disc_sum += min(total_base * 0.05, 250)

    disc_capped = min(disc_sum, MAX_DISCOUNT_TL)
    dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
    
    final_total = max(total_before - disc_capped, MIN_TRAVEL_PER_PERSON * rec_c) + dist_f
    
    return {"total": int(final_total), "c": rec_c, "h": round(rec_h_total, 1), "dist": int(dist_f), "is_hourly": False}

# ---------- ОБРАБОТЧИКИ (HANDLERS) ----------

@bot.message_handler(commands=["start"])
def handle_start(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "discounts_selected": {}}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ", "Правила")
    send_safe(m.chat.id, "👋 Привет! Я Чистюля — бот компании CleanTeam.\n\nЯ помогу рассчитать стоимость уборки и оформить заказ.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Правила")
def handle_rules(m):
    rules_text = (
        "📜 *Наши правила и условия:*\n\n"
        "1. Мы работаем в Анталье, Кемере и Белеке.\n"
        "2. Минимальный выезд на одного клинера — 1200 TL.\n"
        "3. Вы можете получить скидку за предоставление своего пылесоса или средств.\n"
        "4. Отмена заказа менее чем за 24 часа может повлечь удержание.\n"
        "5. Оплата производится после завершения работ.\n\n"
        "Менеджер в WhatsApp: " + WHATSAPP_LINK
    )
    send_safe(m.chat.id, rules_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "СТАРТ")
def start_calc(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "discounts_selected": {}}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Анталья", "Кемер", "Белек")
    bot.send_message(m.chat.id, "📍 Выберите город:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Анталья", "Кемер", "Белек"])
def set_city(m):
    SESS[m.chat.id]["city"] = m.text
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
        "Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая"
    )
    bot.send_message(m.chat.id, "🧹 Выберите тип уборки:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая"])
def set_service(m):
    SESS[m.chat.id]["service_type"] = m.text
    if m.text == "Почасовая":
        SESS[m.chat.id]["step"] = "cleaners_count"
        bot.send_message(m.chat.id, "👥 Сколько клинеров требуется?", reply_markup=types.ReplyKeyboardRemove())
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3).add("1+0", "1+1", "2+1", "3+1", "4+1", "5+1")
        bot.send_message(m.chat.id, "🏠 Планировка (комнаты+салон):", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "cleaners_count")
def set_cleaners(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Введите число клинеров.")
    SESS[m.chat.id]["cleaners"] = m.text
    SESS[m.chat.id]["step"] = "hours_count"
    bot.send_message(m.chat.id, "⏳ На сколько часов?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "hours_count")
def set_hours(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Введите число часов.")
    SESS[m.chat.id]["hours"] = m.text
    finalize(m.chat.id)

@bot.message_handler(func=lambda m: m.text in ["1+0", "1+1", "2+1", "3+1", "4+1", "5+1"])
def set_layout(m):
    SESS[m.chat.id]["layout"] = m.text
    if m.text == "2+1":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("<100 м²", ">100 м²")
        bot.send_message(m.chat.id, "📐 Примерная площадь:", reply_markup=kb)
    else:
        ask_kitchen(m.chat.id)

@bot.message_handler(func=lambda m: m.text in ["<100 м²", ">100 м²"])
def set_area(m):
    SESS[m.chat.id]["area"] = m.text
    ask_kitchen(m.chat.id)

def ask_kitchen(cid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Да, изолированная", "Нет, совмещенная")
    bot.send_message(cid, "🍽 Кухня отдельная (изолированная)?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Да, изолированная", "Нет, совмещенная"])
def set_kitchen(m):
    SESS[m.chat.id]["kitchen_isolated"] = (m.text == "Да, изолированная")
    SESS[m.chat.id]["step"] = "bathrooms"
    bot.send_message(m.chat.id, "🚽 Сколько санузлов?", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "bathrooms")
def set_baths(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Пожалуйста, введите число.")
    SESS[m.chat.id]["bathrooms"] = m.text
    SESS[m.chat.id]["step"] = "balconies"
    bot.send_message(m.chat.id, "🌅 Сколько балконов?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "balconies")
def set_balcs(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Пожалуйста, введите число.")
    SESS[m.chat.id]["balconies"] = m.text
    show_extras(m.chat.id)

def show_extras(cid):
    SESS[cid]["step"] = "extras"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for k in NUM_EXTRA_KEYS.keys(): kb.add(k)
    kb.add("✅ Все, к расчету")
    bot.send_message(cid, "➕ Добавьте дополнительные услуги (если нужно):", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extras")
def handle_ex(m):
    if m.text == "✅ Все, к расчету":
        show_discounts(m.chat.id)
    elif m.text in NUM_EXTRA_KEYS:
        SESS[m.chat.id]["awaiting"] = NUM_EXTRA_KEYS[m.text]
        SESS[m.chat.id]["step"] = "ex_qty"
        bot.send_message(m.chat.id, f"Введите количество для: {m.text}", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "ex_qty")
def handle_ex_qty(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Введите число.")
    name = SESS[m.chat.id].pop("awaiting")
    qty = int(m.text)
    if qty > 0:
        SESS[m.chat.id]["extras"].append((name, qty))
    show_extras(m.chat.id)

def show_discounts(cid):
    SESS[cid]["step"] = "discounts"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
        "🎁 Скидка 10% (Первый заказ)", 
        "🎁 Скидка 10% (Второй заказ)",
        "🧹 Свой пылесос (-5%)", 
        "🧼 Свои средства (-5%)", 
        "➡️ ПОКАЗАТЬ РЕЗУЛЬТАТ"
    )
    bot.send_message(cid, "🎁 Доступные скидки (выберите нужные):", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "discounts")
def handle_disc(m):
    cid = m.chat.id
    sel = SESS[cid]["discounts_selected"]
    if "РЕЗУЛЬТАТ" in m.text: 
        finalize(cid)
    elif "Первый заказ" in m.text: 
        sel["first_order"] = True
        if sel.get("second_order"): 
            sel.pop("second_order", None)
            send_safe(cid, "⚠️ Скидки взаимоисключающие. Применена -10% (Первый).")
        else:
            send_safe(cid, "✅ Скидка 10% (Первый) применена")
    elif "Второй заказ" in m.text:
        sel["second_order"] = True
        if sel.get("first_order"): 
            sel.pop("first_order", None)
            send_safe(cid, "⚠️ Скидки взаимоисключающие. Применена -10% (Второй).")
        else:
            send_safe(cid, "✅ Скидка 10% (Второй) применена")
    elif "пылесос" in m.text: 
        sel["provide_vac"] = True
        send_safe(cid, "✅ Скидка 5% за пылесос применена")
    elif "средства" in m.text: 
        sel["provide_cleaners"] = True
        send_safe(cid, "✅ Скидка 5% за средства применена")

def finalize(cid):
    res = calculate_total(cid)
    SESS[cid]["result"] = res
    d = SESS[cid]
    
    if res.get("is_hourly"):
        summary = (
            f"📋 *ВАШ РАСЧЕТ (ПОЧАСОВАЯ)*\n"
            f"📍 Город: {d['city']}\n"
            f"👥 Кол-во клинеров: {res['c']}\n"
            f"⏳ Время: {res['h']} ч.\n"
            f"--- --- ---\n"
            f"💰 *ИТОГО: {res['total']} TL*\n"
        )
    else:
        summary = (
            f"📋 *ВАШ РАСЧЕТ*\n"
            f"📍 Город: {d['city']}\n"
            f"✨ Тип: {d['service_type']}\n"
            f"🏠 Планировка: {d.get('layout', '-')}\n"
            f"--- --- ---\n"
            f"💰 *ИТОГО: {res['total']} TL*\n"
            f"⏱ Время: ~{res['h']} ч. | 👥 {res['c']} чел.\n"
        )
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Оформить заявку", "🔄 Рассчитать заново")
    send_safe(cid, summary, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔄 Рассчитать заново")
def restart_bot(m):
    handle_start(m)

@bot.message_handler(func=lambda m: m.text == "✅ Оформить заявку")
def get_contact(m):
    SESS[m.chat.id]["step"] = "contact"
    bot.send_message(m.chat.id, "📞 Оставьте ваш номер телефона или ник в Telegram, чтобы менеджер связался с вами:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "contact")
def finish(m):
    cid = m.chat.id
    contact = m.text
    res = SESS[cid].get("result", {})
    d = SESS[cid]
    
    # Отправка админу (тебе)
    adm_msg = (
        f"🔔 *НОВАЯ ЗАЯВКА*\n"
        f"👤 Клиент: {contact}\n"
        f"📍 Город: {d.get('city')}\n"
        f"🧹 Уборка: {d.get('service_type')}\n"
        f"💰 Сумма: {res.get('total')} TL\n"
        f"🆔 ID пользователя: {cid}"
    )
    send_safe(ADMIN_ID, adm_msg, parse_mode="Markdown")
    
    # Ответ пользователю
    bot.send_message(cid, "✅ Заявка успешно отправлена! Менеджер свяжется с вами в ближайшее время.", 
                     reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ"))
    SESS.pop(cid, None)

# ---------- ЗАПУСК И ОБРАБОТКА ОШИБОК ----------

async def main():
    # Запускаем сервер для Render (health check)
    asyncio.create_task(start_health_server())
    
    while True:
        try:
            logger.info("Starting bot polling...")
            # Принудительно сбрасываем вебхуки для исключения конфликтов
            bot.remove_webhook()
            await asyncio.sleep(1)
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            if "Conflict" in str(e):
                logger.warning("409 Conflict detected. Another instance is running. Waiting 15s...")
                await asyncio.sleep(15)
            else:
                logger.error(f"Error during polling: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    if not TOKEN or not ADMIN_ID:
        logger.error("BOT_TOKEN or ADMIN_ID is missing in Environment Variables!")
    else:
        asyncio.run(main())