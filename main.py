# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from telebot.storage import StateMemoryStorage
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
    "мойка духовки": {"price": 500, "time": 60},
    "глажка (1 час)": {"price": 400, "time": 60},
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

# ---------- ЛОГИКА РАСЧЕТА ----------
def calculate_total(chat_id):
    data = SESS.get(chat_id, {})
    service = data.get("service_type")

    if service == "Почасовая":
        hours = int(data.get("hours", 0))
        cleaners = int(data.get("cleaners", 1))
        total = hours * cleaners * HOURLY_RATE
        dist_f = DISTANCE_FEE.get(data.get("city"), 0) * cleaners
        return {"total": total + dist_f, "is_hourly": True, "c": cleaners, "h": hours, "dist": dist_f}

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

    bathrooms = int(data.get("bathrooms", "1") or 1)
    balconies = int(data.get("balconies", "1") or 1)

    extra_bath_fee = max(0, bathrooms - 1) * 400
    extra_balcony_fee = max(0, balconies - 1) * 200
    rooms_surcharge = extra_bath_fee + extra_balcony_fee

    extras_p, extras_t = 0, 0
    for name, qty in data.get("extras", []):
        extras_p += EXTRAS[name]["price"] * qty
        extras_t += EXTRAS[name]["time"] * qty

    rec_c, rec_h = RECOMM_TABLE.get(layout_key, {}).get(service if service != "После ремонта" else "Генеральная", (1, 4))
    rec_h_total = rec_h + (extras_t / 60 / rec_c)

    if service == "После ремонта":
        general_base = PRICES.get(layout_key, {}).get("Генеральная", 0)
        doubled_base = (general_base + extras_p + extra_bath_fee) * 2
        
        discounts = data.get("discounts_selected", {})
        disc_sum = 0
        if discounts.get("first_order"):
            disc_sum += min(doubled_base * 0.1, 1000)
        if discounts.get("second_order"):
            disc_sum += min(doubled_base * 0.1, 1000)
        if discounts.get("provide_vac"):
            disc_sum += min(doubled_base * 0.05, 250)
        if discounts.get("provide_cleaners"):
            disc_sum += min(doubled_base * 0.05, 250)

        disc_capped = min(disc_sum, MAX_DISCOUNT_TL)
        dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
        final_total = max(doubled_base - disc_capped, MIN_TRAVEL_PER_PERSON * rec_c) + dist_f
        
        return {"total": int(final_total), "c": rec_c, "h": round(rec_h_total, 1), "dist": int(dist_f), "is_hourly": False}

    else:
        base = PRICES.get(layout_key, {}).get(service, 0)
        total_base = base + rooms_surcharge + extras_p

        discounts = data.get("discounts_selected", {})
        disc_sum = 0
        if discounts.get("first_order"):
            disc_sum += min(total_base * 0.1, 1000)
        if discounts.get("second_order"):
            disc_sum += min(total_base * 0.1, 1000)
        if discounts.get("provide_vac"):
            disc_sum += min(total_base * 0.05, 250)
        if discounts.get("provide_cleaners"):
            disc_sum += min(total_base * 0.05, 250)

        disc_capped = min(disc_sum, MAX_DISCOUNT_TL)
        dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
        final_total = max(total_base - disc_capped, MIN_TRAVEL_PER_PERSON * rec_c) + dist_f
        
        return {"total": int(final_total), "c": rec_c, "h": round(rec_h_total, 1), "dist": int(dist_f), "is_hourly": False}

# ---------- ОБРАБОТЧИКИ ----------

@bot.message_handler(commands=["start"])
def handle_start(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "discounts_selected": {}}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ", "Правила")
    bot.send_message(m.chat.id, "👋 Привет! Я Чистюля — бот компании CleanTeam.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "СТАРТ")
def start_calculation(m):
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
def set_service_type(m):
    SESS[m.chat.id]["service_type"] = m.text
    if m.text == "Почасовая":
        SESS[m.chat.id]["step"] = "hours"
        bot.send_message(m.chat.id, "⏳ На сколько часов нужна уборка?", reply_markup=types.ReplyKeyboardRemove())
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4).add("1+0", "1+1", "2+1", "3+1", "4+1", "5+1")
        bot.send_message(m.chat.id, "🏠 Выберите планировку:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["1+0", "1+1", "2+1", "3+1", "4+1", "5+1"])
def set_layout(m):
    SESS[m.chat.id]["layout"] = m.text
    if m.text == "2+1":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("<100 м²", ">100 м²")
        bot.send_message(m.chat.id, "📐 Укажите площадь квартиры:", reply_markup=kb)
    else:
        ask_kitchen(m.chat.id)

@bot.message_handler(func=lambda m: m.text in ["<100 м²", ">100 м²"])
def set_area(m):
    SESS[m.chat.id]["area"] = m.text
    ask_kitchen(m.chat.id)

def ask_kitchen(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Да, изолированная", "Нет, совмещенная")
    bot.send_message(chat_id, "🍽 Кухня изолированная?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Да, изолированная", "Нет, совмещенная"])
def set_kitchen(m):
    SESS[m.chat.id]["kitchen_isolated"] = (m.text == "Да, изолированная")
    SESS[m.chat.id]["step"] = "bathrooms"
    bot.send_message(m.chat.id, "🚽 Сколько санузлов в квартире?", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "bathrooms")
def set_bathrooms(m):
    if not m.text.isdigit():
        bot.send_message(m.chat.id, "Пожалуйста, введите число.")
        return
    SESS[m.chat.id]["bathrooms"] = m.text
    SESS[m.chat.id]["step"] = "balconies"
    bot.send_message(m.chat.id, "🌅 Сколько балконов/террас?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "balconies")
def set_balconies(m):
    if not m.text.isdigit():
        bot.send_message(m.chat.id, "Пожалуйста, введите число.")
        return
    SESS[m.chat.id]["balconies"] = m.text
    show_extras_menu(m.chat.id)

def show_extras_menu(chat_id):
    SESS[chat_id]["step"] = "extras"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for key in NUM_EXTRA_KEYS.keys():
        kb.add(key)
    kb.add("✅ Завершить выбор доп. услуг")
    bot.send_message(chat_id, "➕ Добавьте дополнительные услуги (по желанию):", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extras")
def handle_extras(m):
    chat_id = m.chat.id
    if m.text == "✅ Завершить выбор доп. услуг":
        show_discounts_menu(chat_id)
        return
    
    if m.text in NUM_EXTRA_KEYS:
        SESS[chat_id]["awaiting_qty_for"] = NUM_EXTRA_KEYS[m.text]
        SESS[chat_id]["step"] = "extra_qty"
        bot.send_message(chat_id, f"Укажите количество для: {m.text}", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extra_qty")
def handle_extra_qty(m):
    chat_id = m.chat.id
    if not m.text.isdigit():
        bot.send_message(chat_id, "Введите число.")
        return
    
    qty = int(m.text)
    extra_name = SESS[chat_id].pop("awaiting_qty_for")
    
    if qty > 0:
        SESS[chat_id]["extras"].append((extra_name, qty))
        bot.send_message(chat_id, f"✅ Добавлено: {extra_name} — {qty} шт.")
    
    show_extras_menu(chat_id)

def show_discounts_menu(chat_id):
    SESS[chat_id]["step"] = "discounts"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
        "Первый заказ -10%",
        "Каждый второй заказ -10%",
        "Предоставлю свой пылесос -5%",
        "Предоставлю свои средства и инвентарь -5%",
        "➡️ Перейти к расчету стоимости"
    )
    bot.send_message(chat_id, "🎁 Выберите доступные скидки:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "discounts")
def handle_discounts(m):
    chat = m.chat.id
    sel = SESS[chat]["discounts_selected"]
    
    if m.text == "➡️ Перейти к расчету стоимости":
        finalize_calculation(chat)
        return
    
    if "Первый заказ" in m.text:
        sel["first_order"] = True
        bot.send_message(chat, f"✅ Учтено: {m.text}")
    elif "второй заказ" in m.text:
        sel["second_order"] = True
        bot.send_message(chat, f"✅ Учтено: {m.text}")
    elif "пылесос" in m.text:
        sel["provide_vac"] = True
        bot.send_message(chat, f"✅ Учтено: {m.text}")
    elif "инвентарь" in m.text:
        sel["provide_cleaners"] = True
        bot.send_message(chat, f"✅ Учтено: {m.text}")

def finalize_calculation(cid):
    res = calculate_total(cid)
    SESS[cid]["result"] = res
    data = SESS[cid]
    
    if res.get("is_hourly"):
        msg = (f"📋 *ВАШ РАСЧЕТ (Почасовая)*\n"
               f"📍 Город: {data['city']}\n"
               f"⏳ Время: {res['h']} ч. | 👥 Клинеров: {res['c']}\n"
               f"🚗 Транспорт: {res['dist']} TL\n"
               f"💰 *ИТОГО: ~{res['total']} TL*")
    else:
        msg = (f"📋 *ВАШ РАСЧЕТ*\n"
               f"📍 {data['city']}, {data['layout']}, {data['service_type']}\n"
               f"🛁 Санузлов: {data['bathrooms']}, Балконов: {data['balconies']}\n")
        
        if data["extras"]:
            msg += "➕ Допы: " + ", ".join([f"{n} ({q})" for n, q in data["extras"]]) + "\n"
        
        msg += (f"f\"➖➖➖➖➖➖ \n\""
                f"💰 *Ориентировочная стоимость: {res['total']} TL*\n"
                f"f\"➖➖➖➖➖➖ \n\""
                f"👥 Рекомендуем: {res['c']} чел.\n"
                f"⏱ Примерное время: {res['h']} ч.")

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Отправить заявку менеджеру", "🔄 Начать заново")
    bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔄 Начать заново")
def restart(m):
    start_calculation(m)

@bot.message_handler(func=lambda m: m.text == "✅ Отправить заявку менеджеру")
def request_contact(m):
    SESS[m.chat.id]["step"] = "await_contact"
    bot.send_message(m.chat.id, "📱 Пожалуйста, введите ваш номер телефона или ник в Telegram для связи:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "await_contact")
def send_to_admin(m):
    cid = m.chat.id
    contact = m.text
    data = SESS[cid]
    price_val = data["result"]["total"]
    
    adm_msg = (f"🔔 *НОВАЯ ЗАЯВКА*\n"
               f"👤 Клиент: {contact}\n"
               f"📍 {data['city']}, {data['layout']}, {data['service_type']}\n"
               f"🛁 Санузлов: {data['bathrooms']}, Балконов: {data['balconies']}\n"
               f"💰 Сумма: {price_val}")
    try:
        bot.send_message(ADMIN_ID, adm_msg, parse_mode="Markdown")
        bot.send_message(cid, f"✅ **Заявка принята!** \nМенеджер свяжется с вами.\\n\\n"
                             f"📸 [Instagram](https://www.instagram.com/cleanteam.antalya)\\n"
                             f"⚡️ [WhatsApp]({WHATSAPP_LINK})",
                             parse_mode="Markdown", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ"))
    except Exception:
        bot.send_message(cid, f"Ошибка при отправке. Свяжитесь напрямую: {WHATSAPP_LINK}")
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
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, bot.infinity_polling)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())