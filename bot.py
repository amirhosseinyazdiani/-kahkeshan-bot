import hashlib
import html
import logging
import os
import re
import secrets
from typing import Final

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Reservation conversation states
FULL_NAME, PHONE, CITY, RESERVATION_CONFIRM = range(4)

# Anonymous message conversation states
ANONYMOUS_TEXT, ANONYMOUS_CONFIRM = range(10, 12)

# Support conversation state
SUPPORT_TEXT = 20

# Admin reply conversation state
ADMIN_REPLY_TEXT = 30

BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_IDS_RAW: Final[str] = os.getenv("ADMIN_CHAT_IDS", "").strip()
RENDER_EXTERNAL_URL: Final[str] = (
    os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
)
PORT: Final[int] = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def parse_admin_ids(raw_value: str) -> list[int]:
    admin_ids: list[int] = []

    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue

        try:
            admin_ids.append(int(item))
        except ValueError:
            logger.warning("Invalid ADMIN_CHAT_IDS value: %s", item)

    return admin_ids


ADMIN_CHAT_IDS: Final[list[int]] = parse_admin_ids(ADMIN_CHAT_IDS_RAW)


def is_admin(chat_id: int | None) -> bool:
    return chat_id is not None and chat_id in ADMIN_CHAT_IDS


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎓 رزرو مشاوره تحصیلی",
                    callback_data="reserve_consultation",
                )
            ],
            [
                InlineKeyboardButton(
                    "💌 ارسال پیام ناشناس",
                    callback_data="anonymous_message",
                )
            ],
            [
                InlineKeyboardButton(
                    "💬 ارتباط با پشتیبانی",
                    callback_data="contact_support",
                )
            ],
        ]
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 ارسال شماره تماس من", request_contact=True)],
            [KeyboardButton("❌ انصراف")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def reservation_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ ثبت نهایی",
                    callback_data="confirm_reservation",
                ),
                InlineKeyboardButton(
                    "✏️ شروع دوباره",
                    callback_data="restart_reservation",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ انصراف",
                    callback_data="cancel_reservation",
                )
            ],
        ]
    )


def anonymous_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ ارسال ناشناس",
                    callback_data="confirm_anonymous",
                ),
                InlineKeyboardButton(
                    "✏️ ویرایش پیام",
                    callback_data="restart_anonymous",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ انصراف",
                    callback_data="cancel_anonymous",
                )
            ],
        ]
    )


def support_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✉️ پاسخ به کاربر",
                    callback_data=f"support_reply:{user_id}",
                )
            ]
        ]
    )


def normalize_phone(value: str) -> str | None:
    value = (
        value.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if value.startswith("0098"):
        value = "0" + value[4:]
    elif value.startswith("+98"):
        value = "0" + value[3:]
    elif value.startswith("98") and len(value) == 12:
        value = "0" + value[2:]

    if re.fullmatch(r"09\d{9}", value):
        return value

    if re.fullmatch(r"\+\d{8,15}", value):
        return value

    return None


async def send_to_admins(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    delivered = False

    for admin_id in ADMIN_CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            delivered = True
        except Exception:
            logger.exception("Could not send message to admin %s", admin_id)

    return delivered


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "سلام و خوش اومدی 🌱\n\n"
            "از منوی زیر گزینه موردنظرت رو انتخاب کن:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            "منوی خدمات:",
            reply_markup=main_menu(),
        )


async def show_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message or not update.effective_chat:
        return

    await update.message.reply_text(
        "شناسه این چت:\n"
        f"<code>{update.effective_chat.id}</code>\n\n"
        "این عدد را در Render داخل متغیر "
        "<code>ADMIN_CHAT_IDS</code> قرار بده.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------
# Reservation
# ---------------------------

async def begin_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    context.user_data.clear()

    await query.message.reply_text(
        "برای رزرو مشاوره تحصیلی، ابتدا "
        "<b>نام و نام خانوادگی</b> خودت رو بنویس.",
        parse_mode=ParseMode.HTML,
    )
    return FULL_NAME


async def receive_full_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return FULL_NAME

    full_name = " ".join(update.message.text.split())

    if full_name == "❌ انصراف":
        return await cancel_reservation_text(update, context)

    if len(full_name) < 3 or len(full_name) > 80:
        await update.message.reply_text(
            "لطفاً نام و نام خانوادگی رو کامل و درست وارد کن."
        )
        return FULL_NAME

    context.user_data["full_name"] = full_name

    await update.message.reply_text(
        "حالا شماره تماست رو با دکمه زیر ارسال کن؛ "
        "یا شماره رو به‌صورت دستی بنویس.",
        reply_markup=phone_keyboard(),
    )
    return PHONE


async def receive_contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.contact:
        return PHONE

    contact = update.message.contact

    if (
        contact.user_id is not None
        and update.effective_user is not None
        and contact.user_id != update.effective_user.id
    ):
        await update.message.reply_text(
            "لطفاً شماره تماس خودت رو ارسال کن، نه شماره شخص دیگری."
        )
        return PHONE

    raw_phone = contact.phone_number
    if raw_phone.startswith("98") and not raw_phone.startswith("+"):
        raw_phone = "+" + raw_phone

    context.user_data["phone"] = normalize_phone(raw_phone) or raw_phone

    await update.message.reply_text(
        "در کدام شهر زندگی می‌کنی؟ نام شهر رو بنویس.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CITY


async def receive_phone_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return PHONE

    text = update.message.text.strip()

    if text == "❌ انصراف":
        return await cancel_reservation_text(update, context)

    phone = normalize_phone(text)
    if not phone:
        await update.message.reply_text(
            "شماره معتبر نیست. نمونه صحیح:\n"
            "<code>09123456789</code>\n\n"
            "می‌تونی از دکمه «ارسال شماره تماس من» هم استفاده کنی.",
            parse_mode=ParseMode.HTML,
            reply_markup=phone_keyboard(),
        )
        return PHONE

    context.user_data["phone"] = phone

    await update.message.reply_text(
        "در کدام شهر زندگی می‌کنی؟ نام شهر رو بنویس.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CITY


async def receive_city(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return CITY

    city = " ".join(update.message.text.split())

    if city == "❌ انصراف":
        return await cancel_reservation_text(update, context)

    if len(city) < 2 or len(city) > 60:
        await update.message.reply_text("لطفاً نام شهر رو درست وارد کن.")
        return CITY

    context.user_data["city"] = city

    full_name = html.escape(context.user_data["full_name"])
    phone = html.escape(context.user_data["phone"])
    safe_city = html.escape(context.user_data["city"])

    await update.message.reply_text(
        "لطفاً اطلاعاتت رو بررسی کن:\n\n"
        f"👤 <b>نام و نام خانوادگی:</b> {full_name}\n"
        f"📱 <b>شماره تماس:</b> <code>{phone}</code>\n"
        f"🏙 <b>شهر:</b> {safe_city}\n\n"
        "اطلاعات درسته؟",
        parse_mode=ParseMode.HTML,
        reply_markup=reservation_confirmation_keyboard(),
    )
    return RESERVATION_CONFIRM


async def confirm_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END

    await query.answer()

    if not ADMIN_CHAT_IDS:
        await query.message.reply_text(
            "تنظیمات دریافت درخواست هنوز توسط مدیر کامل نشده است.",
            reply_markup=main_menu(),
        )
        logger.error("No valid ADMIN_CHAT_IDS configured.")
        return ConversationHandler.END

    user = update.effective_user
    username = f"@{user.username}" if user.username else "ندارد"

    full_name = html.escape(
        context.user_data.get("full_name", "ثبت نشده")
    )
    phone = html.escape(context.user_data.get("phone", "ثبت نشده"))
    city = html.escape(context.user_data.get("city", "ثبت نشده"))
    safe_username = html.escape(username)

    admin_message = (
        "🔔 <b>درخواست جدید مشاوره تحصیلی</b>\n\n"
        f"👤 <b>نام و نام خانوادگی:</b> {full_name}\n"
        f"📱 <b>شماره تماس:</b> <code>{phone}</code>\n"
        f"🏙 <b>شهر:</b> {city}\n\n"
        f"🆔 <b>شناسه تلگرام:</b> <code>{user.id}</code>\n"
        f"🔗 <b>نام کاربری:</b> {safe_username}"
    )

    delivered = await send_to_admins(context, admin_message)

    await query.edit_message_reply_markup(reply_markup=None)

    if delivered:
        await query.message.reply_text(
            "درخواستت با موفقیت ثبت شد ✅\n\n"
            "به‌زودی برای هماهنگی مشاوره باهات تماس گرفته می‌شه.",
            reply_markup=main_menu(),
        )
    else:
        await query.message.reply_text(
            "ثبت درخواست با خطا مواجه شد. لطفاً دوباره امتحان کن.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def restart_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    context.user_data.clear()
    await query.edit_message_reply_markup(reply_markup=None)

    await query.message.reply_text(
        "باشه؛ دوباره شروع می‌کنیم.\n"
        "لطفاً نام و نام خانوادگی خودت رو بنویس."
    )
    return FULL_NAME


async def cancel_reservation_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query

    if query:
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "رزرو لغو شد.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_reservation_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "رزرو لغو شد.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            "منوی خدمات:",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END


# ---------------------------
# Anonymous message
# ---------------------------

async def begin_anonymous_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    context.user_data.clear()

    await query.message.reply_text(
        "پیام ناشناست رو بنویس 💌\n\n"
        "نام، شماره، نام کاربری و شناسه تلگرامت در پیامی که "
        "برای مدیر ارسال می‌شه نمایش داده نمی‌شه.\n"
        "این بخش برای پیام‌های یک‌طرفه است و امکان پاسخ مستقیم ندارد."
    )
    return ANONYMOUS_TEXT


async def receive_anonymous_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return ANONYMOUS_TEXT

    text = update.message.text.strip()

    if text == "❌ انصراف":
        return await cancel_anonymous_text(update, context)

    if len(text) < 2:
        await update.message.reply_text(
            "لطفاً متن پیام رو کامل‌تر بنویس."
        )
        return ANONYMOUS_TEXT

    if len(text) > 3000:
        await update.message.reply_text(
            "پیام خیلی طولانیه. لطفاً در کمتر از ۳۰۰۰ کاراکتر ارسالش کن."
        )
        return ANONYMOUS_TEXT

    context.user_data["anonymous_text"] = text
    safe_text = html.escape(text)

    await update.message.reply_text(
        "متن پیام ناشناس:\n\n"
        f"<blockquote>{safe_text}</blockquote>\n\n"
        "ارسال بشه؟",
        parse_mode=ParseMode.HTML,
        reply_markup=anonymous_confirmation_keyboard(),
    )
    return ANONYMOUS_CONFIRM


async def confirm_anonymous_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    if not ADMIN_CHAT_IDS:
        await query.message.reply_text(
            "تنظیمات دریافت پیام هنوز توسط مدیر کامل نشده است.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    raw_text = context.user_data.get("anonymous_text", "")
    safe_text = html.escape(raw_text)
    ticket = secrets.token_hex(3).upper()

    admin_message = (
        f"💌 <b>پیام ناشناس جدید</b> <code>#{ticket}</code>\n\n"
        f"<blockquote>{safe_text}</blockquote>\n\n"
        "🔒 اطلاعات هویتی فرستنده نمایش داده نشده است."
    )

    delivered = await send_to_admins(context, admin_message)

    await query.edit_message_reply_markup(reply_markup=None)

    if delivered:
        await query.message.reply_text(
            "پیام ناشناست با موفقیت ارسال شد ✅",
            reply_markup=main_menu(),
        )
    else:
        await query.message.reply_text(
            "ارسال پیام با خطا مواجه شد. لطفاً دوباره امتحان کن.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def restart_anonymous_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    context.user_data.clear()
    await query.edit_message_reply_markup(reply_markup=None)

    await query.message.reply_text(
        "پیام جدیدت رو بنویس:"
    )
    return ANONYMOUS_TEXT


async def cancel_anonymous_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query

    if query:
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "ارسال پیام ناشناس لغو شد.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_anonymous_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "ارسال پیام ناشناس لغو شد.",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END


# ---------------------------
# Support
# ---------------------------

async def begin_support(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    context.user_data.clear()

    await query.message.reply_text(
        "پیامت برای پشتیبانی رو بنویس 💬\n\n"
        "پشتیبانی می‌تونه پاسخ رو از همین ربات برات ارسال کنه."
    )
    return SUPPORT_TEXT


async def receive_support_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if (
        not update.message
        or not update.message.text
        or not update.effective_user
    ):
        return SUPPORT_TEXT

    text = update.message.text.strip()

    if text == "❌ انصراف":
        return await cancel_support(update, context)

    if len(text) < 2:
        await update.message.reply_text(
            "لطفاً متن پیام رو کامل‌تر بنویس."
        )
        return SUPPORT_TEXT

    if len(text) > 3000:
        await update.message.reply_text(
            "پیام خیلی طولانیه. لطفاً در کمتر از ۳۰۰۰ کاراکتر ارسالش کن."
        )
        return SUPPORT_TEXT

    user = update.effective_user
    full_name = html.escape(user.full_name or "بدون نام")
    username = (
        f"@{html.escape(user.username)}"
        if user.username
        else "ندارد"
    )
    safe_text = html.escape(text)

    admin_message = (
        "💬 <b>پیام جدید برای پشتیبانی</b>\n\n"
        f"👤 <b>کاربر:</b> {full_name}\n"
        f"🔗 <b>نام کاربری:</b> {username}\n"
        f"🆔 <b>شناسه:</b> <code>{user.id}</code>\n\n"
        f"<b>متن پیام:</b>\n"
        f"<blockquote>{safe_text}</blockquote>"
    )

    delivered = await send_to_admins(
        context,
        admin_message,
        reply_markup=support_reply_keyboard(user.id),
    )

    if delivered:
        await update.message.reply_text(
            "پیامت برای پشتیبانی ارسال شد ✅\n"
            "پاسخ از همین ربات برات میاد.",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            "ارسال پیام با خطا مواجه شد. لطفاً دوباره امتحان کن.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_support(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "ارتباط با پشتیبانی لغو شد.",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END


# ---------------------------
# Admin replies to support messages
# ---------------------------

async def begin_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if not query or not update.effective_chat:
        return ConversationHandler.END

    if not is_admin(update.effective_chat.id):
        await query.answer("شما اجازه این کار را ندارید.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    callback_data = query.data or ""
    try:
        target_user_id = int(callback_data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.message.reply_text("شناسه کاربر نامعتبر است.")
        return ConversationHandler.END

    context.user_data["support_reply_target"] = target_user_id

    await query.message.reply_text(
        "پاسخت رو بنویس تا برای کاربر ارسال بشه.\n"
        "برای لغو، دستور /cancel رو بفرست."
    )
    return ADMIN_REPLY_TEXT


async def send_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if (
        not update.message
        or not update.message.text
        or not update.effective_chat
    ):
        return ADMIN_REPLY_TEXT

    if not is_admin(update.effective_chat.id):
        return ConversationHandler.END

    target_user_id = context.user_data.get("support_reply_target")
    if not isinstance(target_user_id, int):
        await update.message.reply_text(
            "کاربر مقصد پیدا نشد. دوباره روی دکمه پاسخ بزن."
        )
        return ConversationHandler.END

    reply_text = update.message.text.strip()

    if len(reply_text) < 1:
        await update.message.reply_text("پاسخ نمی‌تونه خالی باشه.")
        return ADMIN_REPLY_TEXT

    if len(reply_text) > 3500:
        await update.message.reply_text(
            "پاسخ خیلی طولانیه. لطفاً کوتاه‌ترش کن."
        )
        return ADMIN_REPLY_TEXT

    safe_reply = html.escape(reply_text)

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                "💬 <b>پاسخ پشتیبانی</b>\n\n"
                f"<blockquote>{safe_reply}</blockquote>\n\n"
                "برای فرستادن پیام جدید، از منوی ربات گزینه "
                "«ارتباط با پشتیبانی» رو انتخاب کن."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
    except Exception:
        logger.exception(
            "Could not send support reply to user %s",
            target_user_id,
        )
        await update.message.reply_text(
            "ارسال پاسخ ناموفق بود. ممکنه کاربر ربات رو مسدود کرده باشه."
        )
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text("پاسخ با موفقیت ارسال شد ✅")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text("ارسال پاسخ لغو شد.")

    return ConversationHandler.END


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.exception(
        "Unhandled exception while processing an update",
        exc_info=context.error,
    )


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add it in Render Environment."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(False)
        .build()
    )

    reservation_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                begin_reservation,
                pattern=r"^reserve_consultation$",
            )
        ],
        states={
            FULL_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_full_name,
                )
            ],
            PHONE: [
                MessageHandler(filters.CONTACT, receive_contact),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_phone_text,
                ),
            ],
            CITY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_city,
                )
            ],
            RESERVATION_CONFIRM: [
                CallbackQueryHandler(
                    confirm_reservation,
                    pattern=r"^confirm_reservation$",
                ),
                CallbackQueryHandler(
                    restart_reservation,
                    pattern=r"^restart_reservation$",
                ),
                CallbackQueryHandler(
                    cancel_reservation_callback,
                    pattern=r"^cancel_reservation$",
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_reservation_text),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    anonymous_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                begin_anonymous_message,
                pattern=r"^anonymous_message$",
            )
        ],
        states={
            ANONYMOUS_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_anonymous_text,
                )
            ],
            ANONYMOUS_CONFIRM: [
                CallbackQueryHandler(
                    confirm_anonymous_message,
                    pattern=r"^confirm_anonymous$",
                ),
                CallbackQueryHandler(
                    restart_anonymous_message,
                    pattern=r"^restart_anonymous$",
                ),
                CallbackQueryHandler(
                    cancel_anonymous_callback,
                    pattern=r"^cancel_anonymous$",
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_anonymous_text),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    support_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                begin_support,
                pattern=r"^contact_support$",
            )
        ],
        states={
            SUPPORT_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_support_text,
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_support),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    admin_reply_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                begin_admin_reply,
                pattern=r"^support_reply:\d+$",
            )
        ],
        states={
            ADMIN_REPLY_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    send_admin_reply,
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin_reply),
        ],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("id", show_chat_id))

    application.add_handler(reservation_conversation)
    application.add_handler(anonymous_conversation)
    application.add_handler(support_conversation)
    application.add_handler(admin_reply_conversation)

    application.add_error_handler(error_handler)
    return application


def main() -> None:
    application = build_application()

    if RENDER_EXTERNAL_URL:
        path_hash = hashlib.sha256(
            BOT_TOKEN.encode("utf-8")
        ).hexdigest()[:32]
        webhook_path = f"telegram/{path_hash}"
        webhook_url = f"{RENDER_EXTERNAL_URL}/{webhook_path}"
        webhook_secret = hashlib.sha256(
            f"secret:{BOT_TOKEN}".encode("utf-8")
        ).hexdigest()

        logger.info("Starting webhook server on port %s", PORT)

        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        logger.info("Running locally with polling.")

        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
