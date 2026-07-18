from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
import os

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_CHAT_ID = 6668536109

NAME, PHONE, CITY, GRADE, FIELD = range(5)

menu = ReplyKeyboardMarkup(
    [
        ["🎓 رزرو مشاوره تحصیلی"],
    ],
    resize_keyboard=True,
)

grades = ReplyKeyboardMarkup(
    [
        ["نهم"],
        ["دهم"],
        ["یازدهم"],
        ["دوازدهم"],
        ["فارغ التحصیل"],
    ],
    resize_keyboard=True,
)

fields = ReplyKeyboardMarkup(
    [
        ["تجربی"],
        ["ریاضی"],
        ["انسانی"],
        ["هنر"],
        ["فنی"],
    ],
    resize_keyboard=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌟 به ربات آموزشی کهکشان خوش آمدید.",
        reply_markup=menu,
    )


async def reservation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 نام و نام خانوادگی خود را وارد کنید:"
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text

    button = KeyboardButton(
        "📱 ارسال شماره تماس",
        request_contact=True,
    )

    keyboard = ReplyKeyboardMarkup(
        [[button]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "شماره تماس خود را ارسال کنید.",
        reply_markup=keyboard,
    )

    return PHONE
