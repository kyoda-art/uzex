"""UZEX AI agent — Telegram bot (polling + monitor uchun HTTP javob)."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import threading

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.charts import make_chart
from core.data import load
from core.env import load_env
from core.export import to_csv_bytes
from core.formatter import detect_lang, format_result
from core.health import start_health_server
from core.router import chat_enabled, make_llm, run_question, run_tool

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("uzex_bot")

# Tugma matnlari: emoji + Bot API "style" rangi (primary = ko'k, success = yashil, danger = qizil)
MENUS = {
    "uz": [
        ["📊 Market Intelligence"], ["🔎 Anomaly Hunter"], ["🔮 Future Vision"], ["🌐 Trade Network"],
        ["📑 Smart Reports"], ["🧠 NEXUS AI"], ["🌍 Til / Language", "ℹ️ Yordam"], ["🔄 Asosiy menyu"],
    ],
    "ru": [
        ["📊 Market Intelligence"], ["🔎 Anomaly Hunter"], ["🔮 Future Vision"], ["🌐 Trade Network"],
        ["📑 Smart Reports"], ["🧠 NEXUS AI"], ["🌍 Язык / Til", "ℹ️ Помощь"], ["🔄 Главное меню"],
    ],
}

ACTION_BY_LABEL = {
    "📊 Market Intelligence": "market",
    "🔎 Anomaly Hunter": "anomaly",
    "🔮 Future Vision": "future",
    "🌐 Trade Network": "trade",
    "📑 Smart Reports": "reports",
    "🧠 NEXUS AI": "nexus",
    "🌍 Til / Language": "lang",
    "🌍 Язык / Til": "lang",
    "ℹ️ Yordam": "help",
    "ℹ️ Помощь": "help",
    "🔄 Asosiy menyu": "menu",
    "🔄 Главное меню": "menu",
}
# Emojisiz nom bo'yicha ham tanish (masalan foydalanuvchi "Market Intelligence" deb yozsa)
ACTION_BY_NAME = {label.split(" ", 1)[1]: act for label, act in ACTION_BY_LABEL.items()}

# Tugma ranglari: Telegram Bot API "style" (primary = ko'k, success = yashil, danger = qizil)
BUTTON_STYLE = {
    "📊 Market Intelligence": "primary",
    "🔎 Anomaly Hunter": "danger",
    "🔮 Future Vision": "success",
    "🌐 Trade Network": "primary",
    "📑 Smart Reports": "success",
    "🧠 NEXUS AI": "primary",
    "🌍 Til / Language": "primary",
    "🌍 Язык / Til": "primary",
    "ℹ️ Yordam": "success",
    "ℹ️ Помощь": "success",
    "🔄 Asosiy menyu": "danger",
    "🔄 Главное меню": "danger",
}


def _kb(label: str) -> KeyboardButton:
    style = BUTTON_STYLE.get(label)
    return KeyboardButton(label, api_kwargs={"style": style} if style else None)


MODULE_PLAN = {
    "market": [("summary", {})],
    "anomaly": [("anomalies", {"n": 5}), ("risky_sellers", {"n": 5})],
    "future": [("forecast", {"months": 3})],
    "trade": [("trade_network", {"n": 10})],
    "reports": [("summary", {}), ("top_brokers", {"n": 5})],
}

GREETINGS = {
    "salom", "assalomu alaykum", "assalomu alaykum!", "salom alik", "hello", "hi", "privet",
    "привет", "здравствуйте", "здравствуй", "салом", "ассалому алейкум", "qalaysiz", "qalesiz",
}

# Qaysi so'rovlar uchun fayl (CSV) yuboriladi
FILE_WORDS = ["excel", "xlsx", "csv", "fayl", "файл", "эксель", "yuklab ber", "скачать", "download"]

# "Oldingi yil bilan solishtirish" tugmasi ishlaydigan vositalar
PREV_TOOLS = {"summary", "top_sellers", "top_buyers", "top_brokers", "top_products", "top_regions",
              "price_trend", "anomalies", "risky_sellers", "trade_network"}

TEXT = {
    "uz": {
        "welcome": (
            "Assalomu alaykum! Men UZEX birja bitimlari bo'yicha AI-agentman.\n"
            "Savolingizni yozing yoki menyudan bo'lim tanlang. Birja raqamlari faqat ma'lumotlarga asoslanadi."
        ),
        "nexus": "🧠 Savolingizni yozing — men birja ma'lumotlari bo'yicha javob beraman.",
        "help": (
            "ℹ️ Yordam\n\n"
            "Misollar:\n"
            "• Umumiy statistika 2025\n"
            "• Eng yirik sotuvchilar 2026\n"
            "• Хлопок narxi dinamikasi 2025\n"
            "• Dollar kursi 30.10.2026\n"
            "• Anomal bitimlar 2025\n"
            "• Keyingi 3 oy prognoz\n"
            "• Eng yirik sotuvchilar 2025 excel (CSV fayl)\n\n"
            "Yilni yozsangiz (masalan 2026) o'sha yil xulosasi chiqadi. Javob tagidagi tugmalar boshqa yilga o'tkazadi."
        ),
        "lang_switched": "🌍 Til o'zgartirildi: O'zbekcha",
        "busy": "⏳ Hisoblanmoqda...",
        "loading": "⏳ Birja ma'lumotlari yuklanmoqda, bir necha daqiqa kuting va qayta yozing.",
        "error": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",

        "file_caption": "📎 CSV fayl (Excel'da ochish mumkin)",
    },
    "ru": {
        "welcome": (
            "Здравствуйте! Я AI-агент по сделкам биржи UZEX.\n"
            "Задайте вопрос или выберите раздел в меню. Цифры биржи основаны только на данных."
        ),
        "nexus": "🧠 Задайте вопрос — я отвечу по данным биржи.",
        "help": (
            "ℹ️ Помощь\n\n"
            "Примеры:\n"
            "• Общая статистика 2025\n"
            "• Крупнейшие продавцы 2026\n"
            "• Динамика цены хлопка 2025\n"
            "• Курс доллара 30.10.2026\n"
            "• Аномальные сделки 2025\n"
            "• Прогноз на 3 месяца\n"
            "• Крупнейшие продавцы 2025 excel (CSV файл)\n\n"
            "Если написать только год (например 2026), покажу сводку за этот год. Кнопки под ответом переключают год."
        ),
        "lang_switched": "🌍 Язык изменён: Русский",
        "busy": "⏳ Считаю...",
        "loading": "⏳ Данные биржи загружаются, подождите пару минут и напишите снова.",
        "error": "Произошла ошибка. Попробуйте ещё раз.",

        "file_caption": "📎 CSV файл (открывается в Excel)",
    },
}


def _ui(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("ui", "uz")


def _menu(lang: str) -> ReplyKeyboardMarkup:
    rows = [[_kb(label) for label in row] for row in MENUS[lang]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _split(text: str, limit: int = 4000):
    """Telegram 4096 belgi cheklovi uchun uzun javobni bo'lib yuboradi."""
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur)
    return parts


async def _send(target, text: str, lang: str, markup=None, rich: bool = False):
    """target: Update (xabar uchun) yoki Message (tugma javobi uchun).

    rich=True — matnda Telegram HTML teglari bor, parse_mode="HTML" bilan yuboriladi.
    """
    msg = target if hasattr(target, "reply_text") else target.message
    parts = _split(text)
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        await msg.reply_text(
            part,
            parse_mode="HTML" if rich else None,
            reply_markup=(markup if (last and markup) else _menu(lang)),
        )


def _year_markup(ds, tool: str | None, selected, lang: str, allow_any: bool = False):
    """Ma'lumot xabari tagida yil tugmalari. Tanlangan yil ✅ bilan belgilanadi.

    allow_any=True — vosita PREV_TOOLS da bo'lmasa ham tugmalar chiqadi (modul uchun).
    """
    if not ds.years:
        return None
    if not allow_any and (not tool or tool not in PREV_TOOLS):
        return None
    row = []
    for y in ds.years:
        on = y == selected
        row.append(InlineKeyboardButton(
            ("✅ " if on else "") + str(y), callback_data=f"yr:{y}",
            api_kwargs={"style": "success" if on else "primary"},
        ))
    return InlineKeyboardMarkup([row])


def _wants_file(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in FILE_WORDS)


def _module_has_year(module: str) -> bool:
    """Bo'limdagi vositalardan kamida bittasi yil bo'yicha filtrlanadimi."""
    return any(tool in PREV_TOOLS for tool, _ in MODULE_PLAN[module])


async def _send_chart(update_or_msg, ds, res: dict, lang: str):
    """Grafik bo'lsa rasm sifatida yuboradi. Xato bo'lsa jim o'tadi (matn baribir yuboriladi)."""
    if not res.get("tool") or not res.get("result"):
        return
    try:
        png = await asyncio.to_thread(make_chart, res["tool"], res["result"], lang)
    except Exception:
        log.exception("Grafik chizishda xato")
        return
    if png:
        await update_or_msg.reply_photo(photo=io.BytesIO(png))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Holatni ko'rsatadi: AI ulanganmi, ma'lumot yuklanganmi."""
    lang = _ui(context)
    ds = context.application.bot_data.get("ds")
    llm = context.application.bot_data.get("llm")
    if lang == "ru":
        text = (
            "🩺 Статус\n\n"
            f"AI (Gemini): {'подключён ✅' if llm else 'не подключён ❌ (нет GEMINI_API_KEY)'}\n"
            f"Данные биржи: {'загружены ✅ ' + format(len(ds.deals), ',') + ' сделок' if ds else 'загружаются ⏳'}\n"
            f"Свободный чат: {'включён' if chat_enabled() else 'выключен'}"
        )
    else:
        text = (
            "🩺 Holat\n\n"
            f"AI (Gemini): {'ulangan ✅' if llm else 'ulanmagan ❌ (GEMINI_API_KEY yo‘q)'}\n"
            f"Birja ma'lumoti: {'yuklangan ✅ ' + format(len(ds.deals), ',') + ' ta bitim' if ds else 'yuklanmoqda ⏳'}\n"
            f"Suhbat rejimi: {'yoqilgan' if chat_enabled() else 'o‘chirilgan'}"
        )
    await _send(update, text, lang)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _ui(context)
    await _send(update, TEXT[lang]["welcome"], lang)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suhbat tarixini tozalaydi — bot eski kontekstga qaytib ketmasligi uchun."""
    context.user_data.pop("history", None)
    context.user_data.pop("last", None)
    lang = _ui(context)
    text = ("🧹 Suhbat tarixi tozalandi. Yangi savoldan boshlaymiz." if lang == "uz"
            else "🧹 История диалога очищена. Начнём с нового вопроса.")
    await _send(update, text, lang)


async def run_module(update: Update, context: ContextTypes.DEFAULT_TYPE, module: str, year: int | None = None):
    """Menyudagi bo'lim: bir yoki bir nechta vositani ishlatib, matn + grafik yuboradi.

    year berilsa — barcha vositalar shu yil uchun qayta hisoblanadi (yil tugmalari uchun).
    """
    lang = _ui(context)
    ds = context.application.bot_data.get("ds")
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if ds is None:
        await _send(msg, TEXT[lang]["loading"], lang)
        return
    await msg.reply_text(TEXT[lang]["busy"])
    blocks, charts = [], []
    for tool, args in MODULE_PLAN[module]:
        a = dict(args)
        if year is not None:
            a["year"] = year
        result = await asyncio.to_thread(run_tool, ds, tool, a)
        blocks.append(format_result(tool, result, lang, rich=True))
        charts.append((tool, result))
    context.user_data["last"] = {"module": module, "year": year}
    # Yil tugmalari faqat yil bo'yicha filtrlanadigan vositalar bo'lsa chiqadi
    markup = _year_markup(ds, None, year, lang, allow_any=True) if _module_has_year(module) else None
    await _send(msg, "\n\n".join(blocks), lang, markup=markup, rich=True)
    for tool, result in charts:
        await _send_chart(msg, ds, {"tool": tool, "result": result}, lang)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    action = ACTION_BY_LABEL.get(text) or ACTION_BY_NAME.get(text)
    if action:
        if action == "lang":
            new = "ru" if _ui(context) == "uz" else "uz"
            context.user_data["ui"] = new
            await _send(update, TEXT[new]["lang_switched"], new)
        elif action == "help":
            await _send(update, TEXT[_ui(context)]["help"], _ui(context))
        elif action == "menu":
            await _send(update, TEXT[_ui(context)]["welcome"], _ui(context))
        elif action == "nexus":
            await _send(update, TEXT[_ui(context)]["nexus"], _ui(context))
        else:
            try:
                await run_module(update, context, action)
            except Exception:
                log.exception("Bo'lim xatosi: %s", action)
                await _send(update, TEXT[_ui(context)]["error"], _ui(context))
        return

    lang = detect_lang(text)
    if text.lower().strip(" !.,") in GREETINGS:
        await _send(update, TEXT[lang]["welcome"], lang)
        return

    ds = context.application.bot_data.get("ds")
    if ds is None:
        await _send(update, TEXT[lang]["loading"], lang)
        return

    llm = context.application.bot_data.get("llm")
    history = context.user_data.setdefault("history", [])
    await update.message.chat.send_action("typing")
    try:
        res = await asyncio.to_thread(run_question, ds, text, llm, list(history))
    except Exception:
        log.exception("Savolga javob berishda xato: %r", text)
        await _send(update, TEXT[lang]["error"], lang)
        return

    history.append(("user", text))
    history.append(("agent", str(res["text"])[:600]))
    del history[:-20]  # oxirgi 10 ta almashinuv saqlanadi

    if res["tool"]:
        context.user_data["last"] = {"tool": res["tool"], "args": res["args"]}

    # Vosita natijasi bo'lsa — kartali, chiroyli (HTML) ko'rinishda qayta yig'amiz.
    # Suhbat tarixiga esa oddiy matn yoziladi (res["text"]).
    shown = res["text"]
    rich = bool(res["tool"] and res["result"])
    if rich:
        shown = format_result(res["tool"], res["result"], res["lang"], rich=True)

    # CSV fayl so'ralgan bo'lsa
    if _wants_file(text) and res["result"] and res["result"].get("rows"):
        data = to_csv_bytes(res["result"])
        await _send(update, shown, res["lang"], markup=None, rich=rich)
        await update.message.reply_document(
            document=io.BytesIO(data), filename=f"{res['tool']}.csv",
            caption=TEXT[res["lang"]]["file_caption"],
        )
        return

    markup = _year_markup(ds, res["tool"], res["args"].get("year"), res["lang"])
    await _send(update, shown, res["lang"], markup=markup, rich=rich)
    await _send_chart(update.message, ds, res, res["lang"])


async def on_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yil tugmasi bosilganda o'sha yil uchun oxirgi so'rovni qayta hisoblaydi."""
    query = update.callback_query
    await query.answer()
    lang = _ui(context)
    ds = context.application.bot_data.get("ds")
    if ds is None:
        await query.message.reply_text(TEXT[lang]["loading"])
        return
    year = int(query.data.split(":")[1])
    last = context.user_data.get("last") or {"tool": "summary", "args": {}}

    # Menyudan ochilgan bo'lim bo'lsa — butun bo'lim shu yil uchun qayta hisoblanadi
    if "module" in last:
        await run_module(update, context, last["module"], year=year)
        return

    args = dict(last["args"])
    args["year"] = year
    result = await asyncio.to_thread(run_tool, ds, last["tool"], args)
    context.user_data["last"] = {"tool": last["tool"], "args": args}
    text = format_result(last["tool"], result, lang, rich=True)
    await _send(query.message, text, lang, markup=_year_markup(ds, last["tool"], year, lang), rich=True)
    await _send_chart(query.message, ds, {"tool": last["tool"], "result": result}, lang)


async def _post_init(app: Application):
    # Oldin webhook o'rnatilgan bo'lsa, polling ishlashi uchun uni o'chiramiz
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.info("Webhook o'chirildi, polling boshlandi")


def main():
    # .env bo'lsa o'qiymiz (Windows muhit o'zgaruvchilari ustuvor qoladi)
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan")

    app = Application.builder().token(token).post_init(_post_init).build()
    app.bot_data["ds"] = None
    app.bot_data["llm"] = make_llm()
    log.info("Gemini: %s", "ulangan" if app.bot_data["llm"] else "yo'q (qoidalar rejimi)")

    def _load_data():
        try:
            log.info("Birja ma'lumotlari yuklanmoqda...")
            app.bot_data["ds"] = load()
            log.info("Bitimlar tayyor: %d", len(app.bot_data["ds"].deals))
        except Exception:
            log.exception("Ma'lumot yuklanmadi")

    threading.Thread(target=_load_data, daemon=True).start()

    app.add_handler(CommandHandler(["start", "menu"], cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler(["reset", "clear"], cmd_reset))
    app.add_handler(CallbackQueryHandler(on_year, pattern=r"^yr:\d{4}$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    port = os.environ.get("PORT")
    if port:
        start_health_server(int(port))

    log.info("Polling rejimi boshlandi")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
