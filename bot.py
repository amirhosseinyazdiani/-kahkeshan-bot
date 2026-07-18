import hashlib
import html
import logging
import os
import re
import secrets
from typing import Final

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
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

# ---------------------------
# Text labels
# ---------------------------

MENU_RESERVATION: Final[str] = "🎓 رزرو مشاوره تحصیلی"
MENU_ANONYMOUS: Final[str] = "💌 ارسال پیام ناشناس"
MENU_SUPPORT: Final[str] = "💬 ارتباط با پشتیبانی"

BOT_VERSION: Final[str] = "4.3-selection-only-school-fields"

SHARE_PHONE: Final[str] = "📱 ارسال شماره تماس من"
CANCEL: Final[str] = "❌ انصراف"
CONFIRM_RESERVATION: Final[str] = "✅ ثبت نهایی"
RESTART_RESERVATION: Final[str] = "✏️ شروع دوباره"

LEVEL_MIDDLE_SCHOOL: Final[str] = "دوره اول"
LEVEL_TENTH: Final[str] = "پایه دهم"
LEVEL_ELEVENTH: Final[str] = "پایه یازدهم"
LEVEL_TWELFTH: Final[str] = "پایه دوازدهم"
LEVEL_GRADUATE: Final[str] = "فارغ‌التحصیل"

FIELD_EXPERIMENTAL: Final[str] = "علوم تجربی"
FIELD_MATH: Final[str] = "ریاضی و فیزیک"
FIELD_HUMANITIES: Final[str] = "علوم انسانی"
FIELD_ART: Final[str] = "هنر"
FIELD_LANGUAGE: Final[str] = "زبان"
FIELD_NOT_APPLICABLE: Final[str] = "ندارد (دوره اول)"
CONFIRM_ANONYMOUS: Final[str] = "✅ ارسال ناشناس"
EDIT_ANONYMOUS: Final[str] = "✏️ ویرایش پیام"

# ---------------------------
# Conversation states
# ---------------------------

(
    FULL_NAME,
    PHONE,
    CITY,
    EDUCATION_LEVEL,
    FIELD_OF_STUDY,
    RESERVATION_CONFIRM,
) = range(6)

ANONYMOUS_TEXT, ANONYMOUS_CONFIRM = range(10, 12)
SUPPORT_TEXT = 20
ADMIN_REPLY_TEXT = 30

# ---------------------------
# Environment
# ---------------------------

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


# ---------------------------
# Reply keyboards
# ---------------------------

def main_menu() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard, similar to the user's reference image."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    MENU_RESERVATION,
                    style="primary",
                )
            ],
            [
                KeyboardButton(MENU_ANONYMOUS),
                KeyboardButton(
                    MENU_SUPPORT,
                    style="success",
                ),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="یکی از گزینه‌ها را انتخاب کنید",
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    CANCEL,
                    style="danger",
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    SHARE_PHONE,
                    request_contact=True,
                    style="primary",
                )
            ],
            [
                KeyboardButton(
                    CANCEL,
                    style="danger",
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def education_level_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(LEVEL_MIDDLE_SCHOOL),
            ],
            [
                KeyboardButton(LEVEL_TENTH),
                KeyboardButton(LEVEL_ELEVENTH),
            ],
            [
                KeyboardButton(LEVEL_TWELFTH),
                KeyboardButton(LEVEL_GRADUATE),
            ],
            [
                KeyboardButton(
                    CANCEL,
                    style="danger",
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="مقطع تحصیلی را انتخاب کنید",
    )


def field_of_study_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(FIELD_EXPERIMENTAL),
                KeyboardButton(FIELD_MATH),
            ],
            [
                KeyboardButton(FIELD_HUMANITIES),
                KeyboardButton(FIELD_ART),
            ],
            [
                KeyboardButton(FIELD_LANGUAGE),
            ],
            [
                KeyboardButton(
                    CANCEL,
                    style="danger",
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="رشته تحصیلی را انتخاب کنید",
    )


def reservation_confirmation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    CONFIRM_RESERVATION,
                    style="success",
                ),
                KeyboardButton(RESTART_RESERVATION),
            ],
            [
                KeyboardButton(
                    CANCEL,
                    style="danger",
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def anonymous_confirmation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    CONFIRM_ANONYMOUS,
                    style="success",
                ),
                KeyboardButton(EDIT_ANONYMOUS),
            ],
            [
                KeyboardButton(
                    CANCEL,
                    style="danger",
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def support_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Inline button is kept only for the admin's contextual reply action."""
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


# ---------------------------
# Utilities
# ---------------------------

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


async def post_init(application: Application) -> None:
    """Creates Telegram's blue Menu button and command list."""
    try:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "شروع ربات"),
                BotCommand("menu", "نمایش منوی خدمات"),
                BotCommand("id", "نمایش شناسه عددی چت"),
                BotCommand("version", "نمایش نسخه فعال ربات"),
            ]
        )
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonCommands()
        )
    except Exception:
        logger.exception("Could not configure bot commands/menu button.")


# ---------------------------
# General commands
# ---------------------------

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "سلام و خوش اومدی 🌱\n\n"
            "از منوی پایین صفحه، گزینه موردنظرت رو انتخاب کن:\n"
            "نسخه جدید منوی خدمات فعال است ✅",
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
        "این عدد باید در Render داخل متغیر "
        "<code>ADMIN_CHAT_IDS</code> قرار بگیره.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


async def show_version(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message:
        await update.message.reply_text(
            "نسخه فعال ربات:\n"
            f"<code>{BOT_VERSION}</code>\n\n"
            "✅ منوی کیبوردی پایین صفحه\n"
            "✅ دریافت مقطع تحصیلی\n"
            "✅ دریافت رشته تحصیلی",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


async def unknown_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های منوی پایین صفحه رو انتخاب کن.",
            reply_markup=main_menu(),
        )


# ---------------------------
# Reservation
# ---------------------------

async def begin_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "برای رزرو مشاوره تحصیلی، ابتدا "
            "<b>نام و نام خانوادگی</b> خودت رو بنویس.",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(),
        )

    return FULL_NAME


async def receive_full_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return FULL_NAME

    full_name = " ".join(update.message.text.split())

    if full_name == CANCEL:
        return await cancel_reservation(update, context)

    if len(full_name) < 3 or len(full_name) > 80:
        await update.message.reply_text(
            "لطفاً نام و نام خانوادگی رو کامل و درست وارد کن.",
            reply_markup=cancel_keyboard(),
        )
        return FULL_NAME

    context.user_data["full_name"] = full_name

    await update.message.reply_text(
        "حالا شماره تماست رو با دکمه پایین ارسال کن؛ "
        "یا شماره رو دستی بنویس.",
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
            "لطفاً شماره تماس خودت رو ارسال کن، نه شماره شخص دیگری.",
            reply_markup=phone_keyboard(),
        )
        return PHONE

    raw_phone = contact.phone_number
    if raw_phone.startswith("98") and not raw_phone.startswith("+"):
        raw_phone = "+" + raw_phone

    context.user_data["phone"] = normalize_phone(raw_phone) or raw_phone

    await update.message.reply_text(
        "در کدام شهر زندگی می‌کنی؟ نام شهر رو بنویس.",
        reply_markup=cancel_keyboard(),
    )
    return CITY


async def receive_phone_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return PHONE

    text = update.message.text.strip()

    if text == CANCEL:
        return await cancel_reservation(update, context)

    if text == SHARE_PHONE:
        await update.message.reply_text(
            "برای ارسال شماره، خود دکمه «ارسال شماره تماس من» رو بزن "
            "و دسترسی اشتراک شماره رو تأیید کن.",
            reply_markup=phone_keyboard(),
        )
        return PHONE

    phone = normalize_phone(text)

    if not phone:
        await update.message.reply_text(
            "شماره معتبر نیست. نمونه صحیح:\n"
            "<code>09123456789</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=phone_keyboard(),
        )
        return PHONE

    context.user_data["phone"] = phone

    await update.message.reply_text(
        "در کدام شهر زندگی می‌کنی؟ نام شهر رو بنویس.",
        reply_markup=cancel_keyboard(),
    )
    return CITY


async def show_reservation_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message:
        return RESERVATION_CONFIRM

    full_name = html.escape(context.user_data["full_name"])
    phone = html.escape(context.user_data["phone"])
    city = html.escape(context.user_data["city"])
    education_level = html.escape(
        context.user_data["education_level"]
    )
    field_of_study = html.escape(
        context.user_data["field_of_study"]
    )

    await update.message.reply_text(
        "لطفاً اطلاعاتت رو بررسی کن:\n\n"
        f"👤 <b>نام و نام خانوادگی:</b> {full_name}\n"
        f"📱 <b>شماره تماس:</b> <code>{phone}</code>\n"
        f"🏙 <b>شهر:</b> {city}\n"
        f"🎓 <b>مقطع تحصیلی:</b> {education_level}\n"
        f"📚 <b>رشته تحصیلی:</b> {field_of_study}\n\n"
        "اطلاعات درسته؟",
        parse_mode=ParseMode.HTML,
        reply_markup=reservation_confirmation_keyboard(),
    )
    return RESERVATION_CONFIRM


async def receive_city(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return CITY

    city = " ".join(update.message.text.split())

    if city == CANCEL:
        return await cancel_reservation(update, context)

    if len(city) < 2 or len(city) > 60:
        await update.message.reply_text(
            "لطفاً نام شهر رو درست وارد کن.",
            reply_markup=cancel_keyboard(),
        )
        return CITY

    context.user_data["city"] = city

    await update.message.reply_text(
        "مقطع تحصیلی فعلیت رو فقط از دکمه‌های زیر انتخاب کن 🎓\n"
        "در این مرحله نیازی به تایپ کردن نیست.",
        reply_markup=education_level_keyboard(),
    )
    return EDUCATION_LEVEL


async def receive_education_level(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return EDUCATION_LEVEL

    education_level = update.message.text.strip()

    if education_level == CANCEL:
        return await cancel_reservation(update, context)

    valid_levels = {
        LEVEL_MIDDLE_SCHOOL,
        LEVEL_TENTH,
        LEVEL_ELEVENTH,
        LEVEL_TWELFTH,
        LEVEL_GRADUATE,
    }

    if education_level not in valid_levels:
        await update.message.reply_text(
            "این گزینه قابل تایپ نیست؛ لطفاً مقطع رو فقط از دکمه‌های پایین انتخاب کن.",
            reply_markup=education_level_keyboard(),
        )
        return EDUCATION_LEVEL

    context.user_data["education_level"] = education_level

    # Students in middle school do not have an academic field yet.
    if education_level == LEVEL_MIDDLE_SCHOOL:
        context.user_data["field_of_study"] = FIELD_NOT_APPLICABLE
        return await show_reservation_summary(update, context)

    await update.message.reply_text(
        "رشته تحصیلیت رو فقط از دکمه‌های زیر انتخاب کن 📚\n"
        "در این مرحله نیازی به تایپ کردن نیست.",
        reply_markup=field_of_study_keyboard(),
    )
    return FIELD_OF_STUDY


async def receive_field_of_study(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return FIELD_OF_STUDY

    field_of_study = update.message.text.strip()

    if field_of_study == CANCEL:
        return await cancel_reservation(update, context)

    valid_fields = {
        FIELD_EXPERIMENTAL,
        FIELD_MATH,
        FIELD_HUMANITIES,
        FIELD_ART,
        FIELD_LANGUAGE,
    }

    if field_of_study not in valid_fields:
        await update.message.reply_text(
            "این گزینه قابل تایپ نیست؛ لطفاً رشته رو فقط از دکمه‌های پایین انتخاب کن.",
            reply_markup=field_of_study_keyboard(),
        )
        return FIELD_OF_STUDY

    context.user_data["field_of_study"] = field_of_study
    return await show_reservation_summary(update, context)


async def confirm_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if (
        not update.message
        or not update.effective_user
        or not update.message.text
    ):
        return RESERVATION_CONFIRM

    if update.message.text != CONFIRM_RESERVATION:
        return RESERVATION_CONFIRM

    if not ADMIN_CHAT_IDS:
        await update.message.reply_text(
            "تنظیمات دریافت درخواست هنوز توسط مدیر کامل نشده است.",
            reply_markup=main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    user = update.effective_user
    username = f"@{user.username}" if user.username else "ندارد"

    full_name = html.escape(
        context.user_data.get("full_name", "ثبت نشده")
    )
    phone = html.escape(
        context.user_data.get("phone", "ثبت نشده")
    )
    city = html.escape(
        context.user_data.get("city", "ثبت نشده")
    )
    education_level = html.escape(
        context.user_data.get("education_level", "ثبت نشده")
    )
    field_of_study = html.escape(
        context.user_data.get("field_of_study", "ثبت نشده")
    )
    safe_username = html.escape(username)

    admin_message = (
        "🔔 <b>درخواست جدید مشاوره تحصیلی</b>\n\n"
        f"👤 <b>نام و نام خانوادگی:</b> {full_name}\n"
        f"📱 <b>شماره تماس:</b> <code>{phone}</code>\n"
        f"🏙 <b>شهر:</b> {city}\n"
        f"🎓 <b>مقطع تحصیلی:</b> {education_level}\n"
        f"📚 <b>رشته تحصیلی:</b> {field_of_study}\n\n"
        f"🆔 <b>شناسه تلگرام:</b> <code>{user.id}</code>\n"
        f"🔗 <b>نام کاربری:</b> {safe_username}"
    )

    delivered = await send_to_admins(context, admin_message)

    if delivered:
        await update.message.reply_text(
            "درخواستت با موفقیت ثبت شد ✅\n\n"
            "به‌زودی برای هماهنگی مشاوره باهات تماس گرفته می‌شه.",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            "ثبت درخواست با خطا مواجه شد. لطفاً دوباره امتحان کن.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def restart_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "باشه؛ دوباره شروع می‌کنیم.\n"
            "لطفاً نام و نام خانوادگی خودت رو بنویس.",
            reply_markup=cancel_keyboard(),
        )

    return FULL_NAME


async def invalid_reservation_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if update.message:
        await update.message.reply_text(
            "برای ادامه از دکمه‌های پایین صفحه استفاده کن.",
            reply_markup=reservation_confirmation_keyboard(),
        )
    return RESERVATION_CONFIRM


async def cancel_reservation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "رزرو مشاوره لغو شد.",
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
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "پیام ناشناست رو بنویس 💌\n\n"
            "نام، شماره، نام کاربری و شناسه تلگرامت در پیام ارسالی "
            "برای مدیر نمایش داده نمی‌شه.\n"
            "این بخش یک‌طرفه است و امکان پاسخ مستقیم ندارد.",
            reply_markup=cancel_keyboard(),
        )

    return ANONYMOUS_TEXT


async def receive_anonymous_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.message or not update.message.text:
        return ANONYMOUS_TEXT

    text = update.message.text.strip()

    if text == CANCEL:
        return await cancel_anonymous(update, context)

    if len(text) < 2:
        await update.message.reply_text(
            "لطفاً متن پیام رو کامل‌تر بنویس.",
            reply_markup=cancel_keyboard(),
        )
        return ANONYMOUS_TEXT

    if len(text) > 3000:
        await update.message.reply_text(
            "پیام خیلی طولانیه. لطفاً کمتر از ۳۰۰۰ کاراکتر بنویس.",
            reply_markup=cancel_keyboard(),
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
    if not update.message or not update.message.text:
        return ANONYMOUS_CONFIRM

    if update.message.text != CONFIRM_ANONYMOUS:
        return ANONYMOUS_CONFIRM

    if not ADMIN_CHAT_IDS:
        await update.message.reply_text(
            "تنظیمات دریافت پیام هنوز توسط مدیر کامل نشده است.",
            reply_markup=main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    safe_text = html.escape(
        context.user_data.get("anonymous_text", "")
    )
    ticket = secrets.token_hex(3).upper()

    admin_message = (
        f"💌 <b>پیام ناشناس جدید</b> <code>#{ticket}</code>\n\n"
        f"<blockquote>{safe_text}</blockquote>\n\n"
        "🔒 اطلاعات هویتی فرستنده در این پیام نمایش داده نشده است."
    )

    delivered = await send_to_admins(context, admin_message)

    if delivered:
        await update.message.reply_text(
            "پیام ناشناست با موفقیت ارسال شد ✅",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            "ارسال پیام با خطا مواجه شد. لطفاً دوباره امتحان کن.",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def edit_anonymous_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.pop("anonymous_text", None)

    if update.message:
        await update.message.reply_text(
            "پیام جدیدت رو بنویس:",
            reply_markup=cancel_keyboard(),
        )

    return ANONYMOUS_TEXT


async def invalid_anonymous_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if update.message:
        await update.message.reply_text(
            "برای ادامه از دکمه‌های پایین صفحه استفاده کن.",
            reply_markup=anonymous_confirmation_keyboard(),
        )
    return ANONYMOUS_CONFIRM


async def cancel_anonymous(
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
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "پیامت برای پشتیبانی رو بنویس 💬\n\n"
            "پشتیبانی می‌تونه پاسخ رو از همین ربات برات ارسال کنه.",
            reply_markup=cancel_keyboard(),
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

    if text == CANCEL:
        return await cancel_support(update, context)

    if len(text) < 2:
        await update.message.reply_text(
            "لطفاً متن پیام رو کامل‌تر بنویس.",
            reply_markup=cancel_keyboard(),
        )
        return SUPPORT_TEXT

    if len(text) > 3000:
        await update.message.reply_text(
            "پیام خیلی طولانیه. لطفاً کمتر از ۳۰۰۰ کاراکتر بنویس.",
            reply_markup=cancel_keyboard(),
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
# Admin reply to support
# ---------------------------

async def begin_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query

    if not query or not update.effective_chat:
        return ConversationHandler.END

    if not is_admin(update.effective_chat.id):
        await query.answer(
            "شما اجازه این کار رو ندارید.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    try:
        target_user_id = int((query.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await query.message.reply_text("شناسه کاربر نامعتبره.")
        return ConversationHandler.END

    context.user_data["support_reply_target"] = target_user_id

    await query.message.reply_text(
        "پاسخت رو بنویس تا برای کاربر ارسال بشه.",
        reply_markup=cancel_keyboard(),
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

    reply_text = update.message.text.strip()

    if reply_text == CANCEL:
        return await cancel_admin_reply(update, context)

    target_user_id = context.user_data.get("support_reply_target")

    if not isinstance(target_user_id, int):
        await update.message.reply_text(
            "کاربر مقصد پیدا نشد. دوباره روی دکمه پاسخ بزن.",
            reply_markup=main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    if len(reply_text) < 1:
        await update.message.reply_text(
            "پاسخ نمی‌تونه خالی باشه.",
            reply_markup=cancel_keyboard(),
        )
        return ADMIN_REPLY_TEXT

    if len(reply_text) > 3500:
        await update.message.reply_text(
            "پاسخ خیلی طولانیه. لطفاً کوتاه‌ترش کن.",
            reply_markup=cancel_keyboard(),
        )
        return ADMIN_REPLY_TEXT

    safe_reply = html.escape(reply_text)

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                "💬 <b>پاسخ پشتیبانی</b>\n\n"
                f"<blockquote>{safe_reply}</blockquote>\n\n"
                "برای ارسال پیام جدید، از منوی پایین صفحه "
                "گزینه «ارتباط با پشتیبانی» رو انتخاب کن."
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
            "ارسال پاسخ ناموفق بود. ممکنه کاربر ربات رو مسدود کرده باشه.",
            reply_markup=main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(
        "پاسخ با موفقیت ارسال شد ✅",
        reply_markup=main_menu(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "ارسال پاسخ لغو شد.",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END


# ---------------------------
# Error handling & application
# ---------------------------

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.exception(
        "Unhandled exception while processing an update",
        exc_info=context.error,
    )


def exact_text_filter(text: str):
    return filters.Regex(rf"^{re.escape(text)}$")


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add it in Render Environment."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(False)
        .build()
    )

    reservation_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                exact_text_filter(MENU_RESERVATION),
                begin_reservation,
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
            EDUCATION_LEVEL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_education_level,
                )
            ],
            FIELD_OF_STUDY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_field_of_study,
                )
            ],
            RESERVATION_CONFIRM: [
                MessageHandler(
                    exact_text_filter(CONFIRM_RESERVATION),
                    confirm_reservation,
                ),
                MessageHandler(
                    exact_text_filter(RESTART_RESERVATION),
                    restart_reservation,
                ),
                MessageHandler(
                    exact_text_filter(CANCEL),
                    cancel_reservation,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    invalid_reservation_confirmation,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_reservation),
            CommandHandler("start", start),
            CommandHandler("menu", start),
        ],
        allow_reentry=True,
    )

    anonymous_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                exact_text_filter(MENU_ANONYMOUS),
                begin_anonymous_message,
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
                MessageHandler(
                    exact_text_filter(CONFIRM_ANONYMOUS),
                    confirm_anonymous_message,
                ),
                MessageHandler(
                    exact_text_filter(EDIT_ANONYMOUS),
                    edit_anonymous_message,
                ),
                MessageHandler(
                    exact_text_filter(CANCEL),
                    cancel_anonymous,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    invalid_anonymous_confirmation,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_anonymous),
            CommandHandler("start", start),
            CommandHandler("menu", start),
        ],
        allow_reentry=True,
    )

    support_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                exact_text_filter(MENU_SUPPORT),
                begin_support,
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
            CommandHandler("menu", start),
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
            CommandHandler("start", start),
            CommandHandler("menu", start),
        ],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("id", show_chat_id))
    application.add_handler(CommandHandler("version", show_version))

    application.add_handler(reservation_conversation)
    application.add_handler(anonymous_conversation)
    application.add_handler(support_conversation)
    application.add_handler(admin_reply_conversation)

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unknown_text,
        )
    )

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
