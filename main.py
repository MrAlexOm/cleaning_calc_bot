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

# 1. GLOBAL LOGGING
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. CONFIG
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
WHATSAPP_LINK = "https://wa.me/message/WGW3DA5VHIMTG1"

# 3. HEALTH CHECK SERVER (For Render stability)
async def health(request):
    return web.Response(text="CleanTeam Bot is Live and Healthy")

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logger.info(f"Health server started on port {port}")

# 4. DATA AND PRICES
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
    "Стандартное окно": {"price": 100, "time": 6},
    "Панорамное окно": {"price": 190, "time": 7.5},
    "Остекление парапета (м)": {"price": 150, "time": 10},
    "Холодильник": {"price": 500, "time": 60},
    "Духовка": {"price": 500, "time": 60},
    "Глажка (час)": {"price": 400, "time": 60},
}

NUM_EXTRA_KEYS = {
    "Стандартные окна (створки)": "Стандартное окно",
    "Панорамные окна (створки)": "Панорамное окно",
    "Остекление парапета (м.п.)": "Остекление парапета (м)",
    "Холодильник (шт)": "Холодильник",
    "Духовка (шт)": "Духовка",
    "Глажка (часы)": "Глажка (час)",
}

storage = StateMemoryStorage()
bot = telebot.TeleBot(TOKEN, state_storage=storage)
SESS = {}

# 5. HELPER FUNCTIONS
def send_safe(chat_id, text, parse_mode=None, reply_markup=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True)
        except (RequestsConnectionError, ReadTimeout, ProtocolError):
            time.sleep(1)
        except Exception as e:
            logger.error(f"Send Error: {e}")
            break
    return None

def calculate_total(chat_id):
    data = SESS.get(chat_id, {})
    service = data.get("service_type")

    if service == "Почасовая":
        hours = int(data.get("hours", 0))
        cleaners = int(data.get("cleaners", 1))
        total = hours * cleaners * HOURLY_RATE
        dist_f = DISTANCE_FEE.get(data.get("city"), 0) * cleaners
        total = max(total, MIN_TRAVEL_PER_PERSON * cleaners)
        return {"total": int(total + dist_f), "is_hourly": True, "c": cleaners, "h": hours}

    layout = data.get("layout")
    area = data.get("area")
    kitchen_isolated = data.get("kitchen_isolated", False)

    temp_layout = layout
    if kitchen_isolated:
        if layout == "1+0": temp_layout = "1+1"
        elif layout in ["1+1", "2+1", "3+1", "4+1"]:
            rooms = int(layout.split("+")[0])
            temp_layout = f"{rooms + 1}+1"

    layout_key = temp_layout
    if layout_key == "2+1":
        layout_key = "2+1_low" if area == "<100 м²" else "2+1_high"

    bathrooms = int(data.get("bathrooms", "1"))
    balconies = int(data.get("balconies", "1"))

    extra_bath_fee = max(0, bathrooms - 1) * 400
    extra_balcony_fee = max(0, balconies - 1) * 200
    rooms_surcharge = extra_bath_fee + extra_balcony_fee

    extras_p, extras_t = 0, 0
    for name, qty in data.get("extras", []):
        extras_p += EXTRAS[name]["price"] * qty
        extras_t += EXTRAS[name]["time"] * qty

    base_key = service if service != "После ремонта" else "Генеральная"
    rec_c, rec_h = RECOMM_TABLE.get(layout_key, {}).get(base_key, (1, 4))
    rec_h_total = rec_h + (extras_t / 60 / rec_c)

    base_price = PRICES.get(layout_key, {}).get(base_key, 0)
    
    if service == "После ремонта":
        total_before = (base_price + extras_p + rooms_surcharge) * 2
    else:
        total_before = base_price + rooms_surcharge + extras_p

    discounts = data.get("discounts_selected", {})
    disc_sum = 0
    if discounts.get("first_order") or discounts.get("second_order"): 
        disc_sum += min(total_before * 0.1, 1000)
    
    if discounts.get("provide_vac"): disc_sum += min(total_before * 0.05, 250)
    if discounts.get("provide_cleaners"): disc_sum += min(total_before * 0.05, 250)

    disc_capped = min(disc_sum, MAX_DISCOUNT_TL)
    dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
    
    final_total = max(total_before - disc_capped, MIN_TRAVEL_PER_PERSON * rec_c) + dist_f
    
    return {"total": int(final_total), "c": rec_c, "h": round(rec_h_total, 1), "is_hourly": False}

# 6. HANDLERS
@bot.message_handler(commands=["start"])
def handle_start(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "discounts_selected": {}}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ", "Правила")
    send_safe(m.chat.id, "👋 Привет! Я бот CleanTeam.\n\nПомогу рассчитать уборку за 1 минуту.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Правила")
def handle_rules(m):
    rules = (
        "📜 *Правила CleanTeam:*\n\n"
        "• **Отмена**: Менее чем за 14ч — штраф 1000 TL.\n"
        "• **Ожидание**: После 30 мин ожидания клиента — 150 TL/30 мин.\n"
        "• **Простой**: Нет воды/света по вине клиента — 1200 TL.\n"
        "• **Приемка**: Все претензии принимаются до оплаты.\n"
        "• **Минимальный заказ**: 1200 TL.\n"
        "• **Оплата**: Сразу после завершения работ."
    )
    send_safe(m.chat.id, rules, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "СТАРТ")
def start_calc(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Анталья", "Кемер", "Белек")
    bot.send_message(m.chat.id, "📍 Город:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Анталья", "Кемер", "Белек"])
def set_city(m):
    SESS[m.chat.id]["city"] = m.text
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
        "Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая"
    )
    bot.send_message(m.chat.id, "🧹 Тип уборки:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая"])
def set_service(m):
    SESS[m.chat.id]["service_type"] = m.text
    if m.text == "Почасовая":
        SESS[m.chat.id]["step"] = "cleaners_count"
        bot.send_message(m.chat.id, "👥 Сколько клинеров?", reply_markup=types.ReplyKeyboardRemove())
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3).add("1+0", "1+1", "2+1", "3+1", "4+1", "5+1")
        bot.send_message(m.chat.id, "🏠 Планировка:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["1+0", "1+1", "2+1", "3+1", "4+1", "5+1"])
def set_layout(m):
    SESS[m.chat.id]["layout"] = m.text
    if m.text == "2+1":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("<100 м²", ">100 м²")
        bot.send_message(m.chat.id, "📐 Площадь:", reply_markup=kb)
    else:
        ask_kitchen(m.chat.id)

@bot.message_handler(func=lambda m: m.text in ["<100 м²", ">100 м²"])
def set_area(m):
    SESS[m.chat.id]["area"] = m.text
    ask_kitchen(m.chat.id)

def ask_kitchen(cid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Да, изолированная", "Нет, совмещенная")
    bot.send_message(cid, "🍽 Кухня отдельная?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Да, изолированная", "Нет, совмещенная"])
def set_kitchen(m):
    SESS[m.chat.id]["kitchen_isolated"] = (m.text == "Да, изолированная")
    SESS[m.chat.id]["step"] = "bathrooms"
    bot.send_message(m.chat.id, "🚽 Кол-во санузлов:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "bathrooms")
def set_baths(m):
    SESS[m.chat.id]["bathrooms"] = m.text if m.text.isdigit() else "1"
    SESS[m.chat.id]["step"] = "balconies"
    bot.send_message(m.chat.id, "🌅 Кол-во балконов:")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "balconies")
def set_balcs(m):
    SESS[m.chat.id]["balconies"] = m.text if m.text.isdigit() else "1"
    show_extras(m.chat.id)

def show_extras(cid):
    SESS[cid]["step"] = "extras"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for k in NUM_EXTRA_KEYS.keys(): kb.add(k)
    kb.add("✅ К расчету")
    bot.send_message(cid, "➕ Доп. услуги:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extras")
def handle_ex(m):
    if m.text == "✅ К расчету":
        show_discounts(m.chat.id)
    elif m.text in NUM_EXTRA_KEYS:
        SESS[m.chat.id]["awaiting"] = NUM_EXTRA_KEYS[m.text]
        SESS[m.chat.id]["step"] = "ex_qty"
        bot.send_message(m.chat.id, f"Сколько: {m.text}?", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "ex_qty")
def handle_ex_qty(m):
    qty = int(m.text) if m.text.isdigit() else 0
    name = SESS[m.chat.id].pop("awaiting", "Неизвестно")
    if qty > 0: SESS[m.chat.id]["extras"].append((name, qty))
    show_extras(m.chat.id)

def show_discounts(cid):
    SESS[cid]["step"] = "discounts"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Скидка 10%", "Свой пылесос (-5%)", "Свои средства (-5%)", "➡️ РЕЗУЛЬТАТ")
    bot.send_message(cid, "🎁 Скидки:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "discounts")
def handle_disc(m):
    cid = m.chat.id
    if "РЕЗУЛЬТАТ" in m.text: finalize(cid)
    elif "10%" in m.text: SESS[cid]["discounts_selected"]["first_order"] = True
    elif "пылесос" in m.text: SESS[cid]["discounts_selected"]["provide_vac"] = True
    elif "средства" in m.text: SESS[cid]["discounts_selected"]["provide_cleaners"] = True
    bot.send_message(cid, "Принято! Что-то еще или смотрим результат?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "cleaners_count")
def set_cl_h(m):
    SESS[m.chat.id]["cleaners"] = m.text if m.text.isdigit() else "1"
    SESS[m.chat.id]["step"] = "hours_count"
    bot.send_message(m.chat.id, "⏳ На сколько часов?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "hours_count")
def set_hr_h(m):
    SESS[m.chat.id]["hours"] = m.text if m.text.isdigit() else "4"
    finalize(m.chat.id)

def finalize(cid):
    res = calculate_total(cid)
    SESS[cid]["result"] = res
    d = SESS[cid]
    
    text = f"📋 *РАСЧЕТ:*\n📍 {d['city']} | ✨ {d['service_type']}\n"
    if not res['is_hourly']: text += f"🏠 {d.get('layout')} | 👥 {res['c']} чел.\n"
    text += f"--- --- ---\n💰 *ИТОГО: {res['total']} TL*\n⏱ ~{res['h']} ч."
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Заказать", "🔄 Заново")
    send_safe(cid, text, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ Заказать")
def get_contact(m):
    SESS[m.chat.id]["step"] = "contact"
    bot.send_message(m.chat.id, "📞 Введите ваш телефон или @username:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "contact")
def finish(m):
    res = SESS[m.chat.id].get("result", {})
    adm_msg = f"🔔 *ЗАЯВКА!*\n👤 {m.text}\n📍 {SESS[m.chat.id].get('city')}\n🧹 {SESS[m.chat.id].get('service_type')}\n💰 {res.get('total')} TL"
    send_safe(ADMIN_ID, adm_msg, parse_mode="Markdown")
    bot.send_message(m.chat.id, "✅ Отправлено! Скоро свяжемся.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ"))
    SESS.pop(m.chat.id, None)

@bot.message_handler(func=lambda m: m.text == "🔄 Заново")
def restart(m): handle_start(m)

# 7. MAIN LOOP
async def main():
    logger.info("Starting CleanTeam Bot...")
    asyncio.create_task(start_health_server())

    while True:
        try:
            bot.remove_webhook()
            await asyncio.sleep(1)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: bot.infinity_polling(timeout=20, long_polling_timeout=10))
        except Exception as e:
            if "Conflict" in str(e):
                logger.warning("Conflict (409). Sleeping 10s...")
                await asyncio.sleep(10)
            else:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    if TOKEN and ADMIN_ID:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass
    else:
        logger.error("Environment variables missing!")