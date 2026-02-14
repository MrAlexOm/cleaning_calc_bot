# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from telebot.storage import StateMemoryStorage
import asyncio
import logging
from aiohttp import web
import time
from threading import Thread

# 1. ЛОГИРОВАНИЕ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. КОНФИГУРАЦИЯ
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
WHATSAPP_LINK = "https://wa.me/message/WGW3DA5VHIMTG1"
INSTAGRAM_LINK = "https://www.instagram.com/cleanteam.antalya?igsh=amdxcnZlaGRqN3Vl&utm_source=qr"

# 3. HEALTH CHECK SERVER
async def health(request):
    return web.Response(text="CleanTeam Kraken is Live")

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/healthz', health)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()

def start_health_server_sync():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_health_server())
    loop.run_forever()

# 4. БАЗА ДАННЫХ (Копия из оригинала)
MIN_TRAVEL_PER_PERSON = 1200
HOURLY_RATE = 450
DISTANCE_FEE = {"Кемер": 600, "Белек": 600, "Анталья": 0}
MAX_DISCOUNT_TL = 1500

PRICES = {
    "1+0": {"Экспресс": 1400, "Поддерживающая": 1800, "Генеральная": 2500, "VIP": 3000, "После ремонта": 5000},
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

STEAM_EXTRAS = {
    "Стул": 80, "Кресло": 100, "Диван (1 место)": 100, "Изголовье кровати": 80,
    "Матрас (сторона)": 250, "Подушка": 50, "Одеяло": 150, "Шторы (шт)": 250,
    "Ковер (м2)": 40, "Одежда (1 вещь)": 20
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
SESS = {} # Глобальное хранилище данных сессии

# 5. СИСТЕМА БЕЗОПАСНЫХ ОТПРАВОК
def send_safe(chat_id, text, parse_mode=None, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Send Error: {e}")
        return None

# 6. КАЛЬКУЛЯТОР
def calculate_total(chat_id):
    data = SESS.get(chat_id, {})
    service = data.get("service_type")

    if service == "Почасовая":
        hours = int(data.get("hours", 0))
        cleaners = int(data.get("cleaners", 1))
        total = max(hours * cleaners * HOURLY_RATE, MIN_TRAVEL_PER_PERSON * cleaners)
        dist_f = DISTANCE_FEE.get(data.get("city"), 0) * cleaners
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
    
    l_key = temp_layout
    if l_key == "2+1":
        l_key = "2+1_low" if area == "<100 м²" else "2+1_high"

    baths = int(data.get("bathrooms", 1))
    balcs = int(data.get("balconies", 1))
    rooms_surcharge = (max(0, baths - 1) * 400) + (max(0, balcs - 1) * 200)

    ex_p, ex_t = 0, 0
    for name, qty in data.get("extras", []):
        ex_p += EXTRAS[name]["price"] * qty
        ex_t += EXTRAS[name]["time"] * qty
    
    steam_floor_p = data.get("steam_floor_sqm", 0) * 30
    steam_items_p = 0
    for name, qty in data.get("steam_extras", []):
        steam_items_p += STEAM_EXTRAS[name] * qty

    base_key = service if service != "После ремонта" else "Генеральная"
    rec_c, rec_h = RECOMM_TABLE.get(l_key, {}).get(base_key, (1, 4))
    total_h = rec_h + (ex_t / 60 / rec_c)

    base_price = PRICES.get(l_key, {}).get(base_key, 0)
    total_before_multiplier = base_price + rooms_surcharge + ex_p
    
    if service == "После ремонта":
        total_before_multiplier *= 2
        
    grand_total_before_disc = total_before_multiplier + steam_floor_p + steam_items_p

    discounts = data.get("discounts_selected", {})
    disc_sum = 0
    discount_base = total_before_multiplier 
    
    if discounts.get("first_order"): disc_sum += min(discount_base * 0.1, 1000)
    elif discounts.get("second_order"): disc_sum += min(discount_base * 0.1, 1000)
    
    if discounts.get("provide_vac"): disc_sum += min(discount_base * 0.05, 250)
    if discounts.get("provide_cleaners"): disc_sum += min(discount_base * 0.05, 250)

    disc_capped = min(disc_sum, MAX_DISCOUNT_TL)
    dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
    
    final = max(grand_total_before_disc - disc_capped, MIN_TRAVEL_PER_PERSON * rec_c) + dist_f
    
    return {
        "total": int(final), "c": rec_c, "h": round(total_h, 1), 
        "is_hourly": False, "discount": int(disc_capped),
        "steam_floor": steam_floor_p, "steam_items": steam_items_p
    }

# 7. ОБРАБОТЧИКИ (DEV VERSION)

@bot.message_handler(commands=["start"])
def handle_start(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "steam_extras": [], "discounts_selected": {}, "steam_floor_sqm": 0}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ", "Правила")
    send_safe(m.chat.id, "👋 Привет! Я Чистюля.\nИсправил ошибки в логике. Попробуем еще раз?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔄 Заново")
def cmd_restart(m):
    handle_start(m)

@bot.message_handler(func=lambda m: m.text == "СТАРТ")
def start_calc(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "steam_extras": [], "discounts_selected": {}, "steam_floor_sqm": 0}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Анталья", "Кемер", "Белек")
    bot.send_message(m.chat.id, "📍 Выберите город:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Анталья", "Кемер", "Белек"])
def set_city(m):
    SESS[m.chat.id]["city"] = m.text
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add("Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая")
    bot.send_message(m.chat.id, "🧹 Тип уборки:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["Экспресс", "Поддерживающая", "Генеральная", "VIP", "После ремонта", "Почасовая"])
def set_service(m):
    SESS[m.chat.id]["service_type"] = m.text
    if m.text == "Почасовая":
        SESS[m.chat.id]["step"] = "cleaners_count"
        bot.send_message(m.chat.id, "👥 Сколько клинеров нужно?", reply_markup=types.ReplyKeyboardRemove())
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3).add("1+0", "1+1", "2+1", "3+1", "4+1", "5+1")
        bot.send_message(m.chat.id, "🏠 Планировка (спальни+салон):", reply_markup=kb)

# Логика для Почасовой
@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "cleaners_count")
def set_cl(m):
    if not m.text.isdigit(): return
    SESS[m.chat.id]["cleaners"] = m.text
    SESS[m.chat.id]["step"] = "hours_count"
    bot.send_message(m.chat.id, "⏳ На сколько часов?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "hours_count")
def set_hr(m):
    if not m.text.isdigit(): return
    SESS[m.chat.id]["hours"] = m.text
    SESS[m.chat.id]["step"] = "hourly_desc"
    bot.send_message(m.chat.id, "📝 Кратко опишите задачу:")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "hourly_desc")
def set_hourly_desc(m):
    SESS[m.chat.id]["task_desc"] = m.text
    finalize(m.chat.id)

# Логика для Фикс. пакетов
@bot.message_handler(func=lambda m: m.text in ["1+0", "1+1", "2+1", "3+1", "4+1", "5+1"])
def set_layout(m):
    SESS[m.chat.id]["layout"] = m.text
    if m.text == "2+1":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("<100 м²", ">100 м²")
        bot.send_message(m.chat.id, "📐 Площадь:", reply_markup=kb)
    else: ask_kitchen(m.chat.id)

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
    bot.send_message(m.chat.id, "🚽 Санузлов (число):", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "bathrooms")
def set_baths(m):
    if not m.text.isdigit(): return
    SESS[m.chat.id]["bathrooms"] = m.text
    SESS[m.chat.id]["step"] = "balconies"
    bot.send_message(m.chat.id, "🌅 Балконов (число):")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "balconies")
def set_balcs(m):
    if not m.text.isdigit(): return
    SESS[m.chat.id]["balconies"] = m.text
    show_extras(m.chat.id)

def show_extras(cid):
    SESS[cid]["step"] = "extras"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for k in NUM_EXTRA_KEYS.keys(): kb.add(k)
    kb.add("✅ Далее: ЭКО-Услуги")
    bot.send_message(cid, "➕ Стандартные допы:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extras")
def handle_ex(m):
    cid = m.chat.id
    if m.text == "✅ Далее: ЭКО-Услуги":
        ask_steam_mop(cid)
    elif m.text in NUM_EXTRA_KEYS:
        SESS[cid]["awaiting"] = NUM_EXTRA_KEYS[m.text]
        SESS[cid]["step"] = "ex_qty"
        bot.send_message(cid, f"Количество для {m.text}?", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "ex_qty")
def handle_ex_qty(m):
    cid = m.chat.id
    if not m.text.isdigit(): return
    qty = int(m.text)
    name = SESS[cid].pop("awaiting", "Неизвестно")
    if qty > 0: SESS[cid]["extras"].append((name, qty))
    show_extras(cid)

# ИСПРАВЛЕННЫЙ ПЕРЕХОД К ШВАБРЕ
def ask_steam_mop(cid):
    SESS[cid]["step"] = "steam_mop_ask"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("ДА, интересно", "НЕТ, пропустить")
    msg = ("✨ **NEW! Паровая швабра!** 🧼♨️\n\n💰 30 TL / м²\nДобавить?")
    send_safe(cid, msg, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "steam_mop_ask")
def handle_steam_mop_choice(m):
    cid = m.chat.id
    if "ДА" in m.text:
        SESS[cid]["step"] = "steam_mop_area"
        bot.send_message(cid, "Сколько м²?", reply_markup=types.ReplyKeyboardRemove())
    else: ask_steam_items(cid)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "steam_mop_area")
def handle_steam_mop_area(m):
    cid = m.chat.id
    if m.text.isdigit():
        SESS[cid]["steam_floor_sqm"] = int(m.text)
    ask_steam_items(cid)

def ask_steam_items(cid):
    SESS[cid]["step"] = "steam_items_ask"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("ДА, прайс", "НЕТ, скидки")
    bot.send_message(cid, "💨 **Дезинфекция мебели паром?**", parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "steam_items_ask")
def handle_steam_items_choice(m):
    cid = m.chat.id
    if "ДА" in m.text: show_steam_menu(cid)
    else: show_discounts(cid)

def show_steam_menu(cid):
    SESS[cid]["step"] = "steam_menu"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for k in STEAM_EXTRAS.keys(): kb.add(k)
    kb.add("✅ Готово, к скидкам")
    bot.send_message(cid, "💨 Выберите вещи:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "steam_menu")
def handle_steam_menu(m):
    cid = m.chat.id
    if m.text == "✅ Готово, к скидкам": show_discounts(cid)
    elif m.text in STEAM_EXTRAS:
        SESS[cid]["awaiting_steam"] = m.text
        SESS[cid]["step"] = "steam_qty"
        bot.send_message(cid, f"Сколько шт ({m.text})?", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "steam_qty")
def handle_steam_qty(m):
    cid = m.chat.id
    if m.text.isdigit():
        name = SESS[cid].pop("awaiting_steam", "")
        qty = int(m.text)
        if qty > 0: SESS[cid]["steam_extras"].append((name, qty))
    show_steam_menu(cid)

def show_discounts(cid):
    SESS[cid]["step"] = "discounts"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
        "Первый заказ (-10%)", "Второй заказ (-10%)", "Свой пылесос (-5%)", "Свои средства (-5%)", "➡️ ИТОГО"
    )
    bot.send_message(cid, "🎁 Скидки:", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "discounts")
def handle_disc(m):
    cid = m.chat.id
    if "ИТОГО" in m.text: finalize(cid); return
    sel = SESS[cid]["discounts_selected"]
    if "Первый" in m.text: sel["first_order"] = True; sel.pop("second_order", None)
    elif "Второй" in m.text: sel["second_order"] = True; sel.pop("first_order", None)
    elif "пылесос" in m.text: sel["provide_vac"] = True
    elif "средства" in m.text: sel["provide_cleaners"] = True
    send_safe(cid, "✅ Принято. Что-то еще или ИТОГО?")

def finalize(cid):
    res = calculate_total(cid)
    d = SESS[cid]
    SESS[cid]["step"] = "awaiting_order" # Важно! Устанавливаем шаг перед финальным выводом

    report = ["📋 *ВАШ ДЕТАЛЬНЫЙ ЧЕК:*"]
    report.append(f"📍 {d.get('city')} | ✨ {d.get('service_type')}")
    
    if res.get('is_hourly'):
        report.append(f"⏱ {d.get('hours')} ч. | 👥 {d.get('cleaners')} чел.")
    else:
        report.append(f"🏠 {d.get('layout')} | {d.get('area', '-')}")
    
    if d.get('steam_floor_sqm', 0) > 0:
        report.append(f"♨️ ЭКО-Пол: {d['steam_floor_sqm']} м²")
    if d.get('steam_extras'):
        report.append(f"💨 Отпаривание: {len(d['steam_extras'])} поз.")

    report.append("\n" + "—"*10)
    report.append(f"💰 *ИТОГО: {res['total']} TL*")
    
    full_text = "\n".join(report)
    SESS[cid]["last_report"] = full_text
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ ЗАКАЗАТЬ", "🔄 Заново")
    send_safe(cid, full_text, parse_mode="Markdown", reply_markup=kb)

# ИСПРАВЛЕННЫЙ ФИНАЛ
@bot.message_handler(func=lambda m: m.text == "✅ ЗАКАЗАТЬ")
def cmd_order(m):
    # Проверяем, есть ли данные в сессии, если нет — значит бот перезагрузился
    if m.chat.id not in SESS:
        send_safe(m.chat.id, "❌ Сессия истекла. Начните сначала.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ"))
        return
    SESS[m.chat.id]["step"] = "contact"
    bot.send_message(m.chat.id, "📞 Введите ваш телефон или @username:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "contact")
def finish_order(m):
    cid = m.chat.id
    report = SESS[cid].get("last_report", "Нет данных")
    if ADMIN_ID:
        send_safe(ADMIN_ID, f"🚀 *НОВЫЙ ЗАКАЗ!*\n👤 {m.text}\n\n{report}", parse_mode="Markdown")
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💬 WhatsApp", url=WHATSAPP_LINK))
    bot.send_message(cid, "✅ *Заявка принята!* Свяжемся в ближайшее время.", parse_mode="Markdown", reply_markup=kb)
    SESS.pop(cid, None) # Чистим сессию только после успешного заказа

if __name__ == "__main__":
    Thread(target=start_health_server_sync, daemon=True).start()
    while True:
        try:
            bot.polling(non_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Polling Error: {e}")
            time.sleep(5)