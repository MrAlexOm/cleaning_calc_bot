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

# 1. ГЛОБАЛЬНОЕ ЛОГИРОВАНИЕ
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

# 3. HEALTH CHECK SERVER (Для Render)
async def health(request):
    return web.Response(text="CleanTeam Bot is Live")

async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logger.info(f"Health server started on port {port}")

# 4. ДАННЫЕ И ЦЕНЫ
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
    """Безопасная отправка сообщений с повторами"""
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

    # Доплаты за помещения (санузлы и балконы сверх 1)
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
    
    # Формула: (База + Доплата за комнаты + Допы)
    total_before = base_price + rooms_surcharge + extras_p
    
    # Если ремонт -> Умножаем всё на 2
    if service == "После ремонта":
        total_before *= 2

    # Скидки
    discounts = data.get("discounts_selected", {})
    disc_sum = 0
    
    # Лимиты на скидки
    if discounts.get("first_order"): 
        disc_sum += min(total_before * 0.1, 1000)
    elif discounts.get("second_order"): 
        disc_sum += min(total_before * 0.1, 1000)
    
    if discounts.get("provide_vac"): disc_sum += min(total_before * 0.05, 250)
    if discounts.get("provide_cleaners"): disc_sum += min(total_before * 0.05, 250)

    disc_capped = min(disc_sum, MAX_DISCOUNT_TL)
    
    dist_f = DISTANCE_FEE.get(data.get("city"), 0) * rec_c
    
    final_total = max(total_before - disc_capped, MIN_TRAVEL_PER_PERSON * rec_c) + dist_f
    
    return {
        "total": int(final_total), 
        "c": rec_c, 
        "h": round(rec_h_total, 1), 
        "is_hourly": False,
        "discount": int(disc_capped)
    }

# 6. HANDLERS (ОБРАБОТЧИКИ)

@bot.message_handler(commands=["start"])
def handle_start(m):
    SESS[m.chat.id] = {"step": "city", "extras": [], "discounts_selected": {}}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ", "Правила")
    send_safe(m.chat.id, "👋 Привет! Я Чистюля — бот CleanTeam.\n\nНажмите СТАРТ для расчета.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Правила")
def handle_rules(m):
    rules_text = (
        "📜 *Правила CleanTeam:*\n\n"
        "• **Акцепт**: Оформление заказа или оплата означают согласие с договором оферты.\n"
        "• **Инфо**: Заказчик несет ответственность за точность данных о площади и состоянии объекта.\n"
        "• **Минимальный заказ**: 1200 TL.\n"
        "• **Отмена**: Бесплатно более чем за 14ч. Менее чем за 14ч — компенсация **1000 TL**.\n"
        "• **Ожидание**: Первые 30 мин бесплатно, далее **150 TL** за каждые 30 мин.\n"
        "• **Простой**: Если работа невозможна по вине клиента (нет воды/света) — **1200 TL**.\n"
        "• **Приемка**: Все замечания озвучиваются **до оплаты**. Оплата подтверждает отсутствие претензий.\n"
        "• **Оборудование**: При использовании техники клиента, Исполнитель не отвечает за её износ или скрытые дефекты."
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
        bot.send_message(m.chat.id, "🏠 Выберите планировку:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["1+0", "1+1", "2+1", "3+1", "4+1", "5+1"])
def set_layout(m):
    SESS[m.chat.id]["layout"] = m.text
    if m.text == "2+1":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("<100 м²", ">100 м²")
        bot.send_message(m.chat.id, "📐 Уточните площадь:", reply_markup=kb)
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
    bot.send_message(m.chat.id, "🚽 Введите количество санузлов:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "bathrooms")
def set_baths(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Пожалуйста, введите число.")
    SESS[m.chat.id]["bathrooms"] = m.text
    SESS[m.chat.id]["step"] = "balconies"
    bot.send_message(m.chat.id, "🌅 Введите количество балконов/террас:")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "balconies")
def set_balcs(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Пожалуйста, введите число.")
    SESS[m.chat.id]["balconies"] = m.text
    show_extras(m.chat.id)

def show_extras(cid):
    SESS[cid]["step"] = "extras"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for k in NUM_EXTRA_KEYS.keys(): kb.add(k)
    kb.add("✅ ПЕРЕЙТИ К РАСЧЕТУ")
    bot.send_message(cid, "➕ Выберите доп. услуги (можно несколько):", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "extras")
def handle_ex(m):
    if m.text == "✅ ПЕРЕЙТИ К РАСЧЕТУ":
        show_discounts(m.chat.id)
    elif m.text in NUM_EXTRA_KEYS:
        SESS[m.chat.id]["awaiting"] = NUM_EXTRA_KEYS[m.text]
        SESS[m.chat.id]["step"] = "ex_qty"
        bot.send_message(m.chat.id, f"Введите количество для: {m.text}", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "ex_qty")
def handle_ex_qty(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "Введите число.")
    qty = int(m.text)
    name = SESS[m.chat.id].pop("awaiting", "Неизвестно")
    if qty > 0:
        SESS[m.chat.id]["extras"].append((name, qty))
    show_extras(m.chat.id)

def show_discounts(cid):
    SESS[cid]["step"] = "discounts"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
        "Скидка 10% (Первый заказ)", 
        "Скидка 10% (Второй заказ)",
        "Свой пылесос (-5%)", 
        "Свои средства (-5%)", 
        "➡️ ПОКАЗАТЬ РЕЗУЛЬТАТ"
    )
    bot.send_message(cid, "🎁 Доступные скидки (выберите нужные):", reply_markup=kb)

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "discounts")
def handle_disc(m):
    cid = m.chat.id
    sel = SESS[cid]["discounts_selected"]
    if "РЕЗУЛЬТАТ" in m.text: 
        finalize(cid)
        return
    
    # Взаимоисключение скидок на заказ
    if "Первый заказ" in m.text:
        sel["first_order"] = True
        sel.pop("second_order", None)
        bot.send_message(cid, "✅ Скидка 'Первый заказ' применена")
    elif "Второй заказ" in m.text:
        sel["second_order"] = True
        sel.pop("first_order", None)
        bot.send_message(cid, "✅ Скидка 'Второй заказ' применена")
    elif "пылесос" in m.text: 
        sel["provide_vac"] = True
        bot.send_message(cid, "✅ Скидка 'Свой пылесос' применена")
    elif "средства" in m.text: 
        sel["provide_cleaners"] = True
        bot.send_message(cid, "✅ Скидка 'Свои средства' применена")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "cleaners_count")
def set_cl_h(m):
    SESS[m.chat.id]["cleaners"] = m.text if m.text.isdigit() else "1"
    SESS[m.chat.id]["step"] = "hours_count"
    bot.send_message(m.chat.id, "⏳ На сколько часов нужна уборка?")

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "hours_count")
def set_hr_h(m):
    SESS[m.chat.id]["hours"] = m.text if m.text.isdigit() else "4"
    finalize(m.chat.id)

def finalize(cid):
    res = calculate_total(cid)
    SESS[cid]["result"] = res
    d = SESS[cid]
    
    # Формируем чек
    report = ["📋 *ВАШ ДЕТАЛЬНЫЙ РАСЧЕТ:*"]
    report.append(f"📍 *Город:* {d.get('city')}")
    report.append(f"✨ *Тип:* {d.get('service_type')}")
    
    if res.get('is_hourly'):
        report.append(f"👥 *Клинеров:* {d.get('cleaners')}")
        report.append(f"⏳ *Время:* {d.get('hours')} ч.")
    else:
        report.append(f"🏠 *Планировка:* {d.get('layout')}")
        if d.get('area'): report.append(f"📐 *Площадь:* {d.get('area')}")
        
        kitchen = "Изолированная" if d.get('kitchen_isolated') else "Совмещенная"
        report.append(f"🍽 *Кухня:* {kitchen}")
        report.append(f"🚽 *Санузлы:* {d.get('bathrooms')} шт.")
        report.append(f"🌅 *Балконы:* {d.get('balconies')} шт.")
        
        if d.get('extras'):
            report.append("\n➕ *Доп. услуги:*")
            for name, qty in d.get('extras'):
                report.append(f" • {name}: {qty} шт.")

    report.append("\n" + "—" * 15)
    
    if res.get('discount', 0) > 0:
        report.append(f"🎁 *Ваша скидка:* -{res['discount']} TL")
        
    report.append(f"💰 *ИТОГО К ОПЛАТЕ: {res['total']} TL*")
    if not res.get('is_hourly'):
        report.append(f"⏱️ *Время:* ~{res['h']} ч. | 👥 *Рекомендуем:* {res['c']} чел.")
    
    full_text = "\n".join(report)
    SESS[cid]["last_report"] = full_text # Сохраняем для админа

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ ЗАКАЗАТЬ", "🔄 Заново")
    send_safe(cid, full_text, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ ЗАКАЗАТЬ")
def ask_contact(m):
    SESS[m.chat.id]["step"] = "contact"
    bot.send_message(m.chat.id, "📞 Введите ваш телефон или @username для связи:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: SESS.get(m.chat.id, {}).get("step") == "contact")
def finish(m):
    cid = m.chat.id
    contact = m.text
    report = SESS[cid].get("last_report", "Нет данных")
    
    # 1. Админу
    adm_msg = f"🔔 *НОВАЯ ЗАЯВКА!*\n👤 *Клиент:* {contact}\n\n{report}"
    send_safe(ADMIN_ID, adm_msg, parse_mode="Markdown")
    
    # 2. Клиенту
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📸 Наш Instagram (Акции)", url=INSTAGRAM_LINK),
        types.InlineKeyboardButton("💬 Менеджер в WhatsApp", url=WHATSAPP_LINK)
    )
    
    success_text = (
        "✅ *Заявка отправлена! Скоро свяжемся.*\n\n"
        "Подпишитесь на наш Instagram, чтобы быть в курсе наших акций!\n"
        "Если есть срочные вопросы — пишите менеджеру в WhatsApp."
    )
    
    bot.send_message(cid, success_text, parse_mode="Markdown", reply_markup=kb)
    bot.send_message(cid, "Меню:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("СТАРТ"))
    SESS.pop(cid, None)

@bot.message_handler(func=lambda m: m.text == "🔄 Заново")
def restart(m): handle_start(m)

# 7. MAIN LOOP
async def main():
    logger.info("CleanTeam Bot Starting...")
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