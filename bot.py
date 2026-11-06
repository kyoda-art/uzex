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
from core.export import to_csv_bytes
from core.formatter import detect_lang, format_result
from core.health import start_health_server
from core.router import make_llm, run_question, run_tool

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("uzex_bot")

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
            "Javobdagi \"◀️ Oldingi yil\" tugmasi o'tgan yil bilan solishtiradi."
        ),
        "lang_switched": "🌍 Til o'zgartirildi: O'zbekcha",
        "busy": "⏳ Hisoblanmoqda...",
        "loading": "⏳ Birja ma'lumotlari yuklanmoqda, bir necha daqiqa kuting va qayta yozing.",
        "error": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
        "prev_btn": "◀️ Oldingi yil bilan solishtirish",
        "prev_none": "Bu bo'yicha oldingi yil ma'lumoti yo'q.",
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
            "Кнопка \"◀️ Предыдущий год\" сравнивает с прошлым годом."
        ),
        "lang_switched": "🌍 Язык изменён: Русский",
        "busy": "⏳ Считаю...",
        "loading": "⏳ Данные биржи загружаются, подождите пару минут и напишите снова.",
        "error": "Произошла ошибка. Попробуйте ещё раз.",
        "prev_btn": "◀️ Сравнить с предыдущим годом",
        "prev_none": "Данных за предыдущий год по этому запросу нет.",
        "file_caption": "📎 CSV файл (открывается в Excel)",
    },
}


def _ui(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("ui", "uz")


def _menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(MENUS[lang], resize_keyboard=True)


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


async def _send(target, text: str, lang: str, markup=None):
    """target: Update (xabar uchun) yoki Message (tugma javobi uchun)."""
    msg = target if hasattr(target, "reply_text") else target.message
    parts = _split(text)
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        await msg.reply_text(part, reply_markup=(markup if (last and markup) else _menu(lang)))


def _prev_markup(ds, tool: str | None, args: dict, lang: str):
    if not tool or tool not in PREV_TOOLS or not args.get("year"):
        return None
    if args["year"] - 1 not in ds.years:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(TEXT[lang]["prev_btn"], callback_data="prev")]])


def _wants_file(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in FILE_WORDS)


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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _ui(context)
    await _send(update, TEXT[lang]["welcome"], lang)


async def run_module(update: Update, context: ContextTypes.DEFAULT_TYPE, module: str):
    lang = _ui(context)
    ds = context.application.bot_data.get("ds")
    if ds is None:
        await _send(update, TEXT[lang]["loading"], lang)
        return
    await update.message.reply_text(TEXT[lang]["busy"])
    blocks = []
    for tool, args in MODULE_PLAN[module]:
        result = await asyncio.to_thread(run_tool, ds, tool, args)
        blocks.append(format_result(tool, result, lang))
    await _send(update, "\n\n".join(blocks), lang)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    action = ACTION_BY_LABEL.get(text)
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
    history.append(("agent", res["text"]))
    del history[:-10]

    if res["tool"]:
        context.user_data["last"] = {"tool": res["tool"], "args": res["args"]}

    # CSV fayl so'ralgan bo'lsa
    if _wants_file(text) and res["result"] and res["result"].get("rows"):
        data = to_csv_bytes(res["result"])
        await _send(update, res["text"], res["lang"], markup=None)
        await update.message.reply_document(
            document=io.BytesIO(data), filename=f"{res['tool']}.csv",
            caption=TEXT[res["lang"]]["file_caption"],
        )
        return

    markup = _prev_markup(ds, res["tool"], res["args"], res["lang"])
    await _send(update, res["text"], res["lang"], markup=markup)
    await _send_chart(update.message, ds, res, res["lang"])


async def on_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = _ui(context)
    ds = context.application.bot_data.get("ds")
    last = context.user_data.get("last")
    if ds is None or not last:
        await query.message.reply_text(TEXT[lang]["loading"] if ds is None else TEXT[lang]["error"])
        return
    args = dict(last["args"])
    if not args.get("year") or args["year"] - 1 not in ds.years:
        await query.message.reply_text(TEXT[lang]["prev_none"])
        return
    args["year"] -= 1
    result = await asyncio.to_thread(run_tool, ds, last["tool"], args)
    context.user_data["last"] = {"tool": last["tool"], "args": args}
    text = format_result(last["tool"], result, lang)
    markup = _prev_markup(ds, last["tool"], args, lang)
    await _send(query.message, text, lang, markup=markup)
    await _send_chart(query.message, ds, {"tool": last["tool"], "result": result}, lang)


async def _post_init(app: Application):
    # Oldin webhook o'rnatilgan bo'lsa, polling ishlashi uchun uni o'chiramiz
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.info("Webhook o'chirildi, polling boshlandi")


def main():
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
    app.add_handler(CallbackQueryHandler(on_prev, pattern="^prev$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    port = os.environ.get("PORT")
    if port:
        start_health_server(int(port))

    log.info("Polling rejimi boshlandi")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
