import threading
import time
import random
import sys
import os
import shutil
from datetime import datetime, timedelta
from bson import ObjectId
import asyncio
from flask import Flask, jsonify

# Event loop initialization
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Simple fix
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import telebot.types


def _safe_inline_keyboard_button(*args, **kwargs):
    """Compatibility wrapper: ignore unsupported `style` kwarg."""
    kwargs.pop("style", None)
    return telebot.types.InlineKeyboardButton(*args, **kwargs)


InlineKeyboardButton = _safe_inline_keyboard_button


@classmethod
def _disable_story(cls, obj):
    # Telegram stories completely ignored
    return None

telebot.types.Story.de_json = _disable_story
from pymongo import MongoClient
import os
import requests
from pyrogram import Client, enums
from pyrogram.errors import (
    ApiIdInvalid, PhoneNumberInvalid, PhoneCodeInvalid,
    PhoneCodeExpired, SessionPasswordNeeded, PasswordHashInvalid,
    FloodWait, PhoneCodeEmpty
)


# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

BOT_TOKEN = os.getenv('BOT_TOKEN', '8588199256:AAGUjtP_MvXCUGctOoBfMX1-eG2nV3ATCwY')
ADMIN_ID = int(os.getenv('ADMIN_ID', '6042317029, 8441236350'))
MONGO_URL = os.getenv('MONGO_URL', 'mongodb+srv://bsdk:betichod@cluster0.fgj1r9z.mongodb.net/?retryWrites=true&w=majority' )
API_ID = int(os.getenv('API_ID', '36326629'))
API_HASH = os.getenv('API_HASH', '823e6e8c081fe363e6d739b39dc19e07')

# Multiple owners support (up to 5, comma-separated in OWNER_IDS env var)
# e.g. OWNER_IDS=8316947415,6509168409,987654321
_raw_owner_ids = os.getenv('OWNER_IDS', '')
OWNER_IDS = [int(x.strip()) for x in _raw_owner_ids.split(',') if x.strip().isdigit()]
if ADMIN_ID not in OWNER_IDS:
    OWNER_IDS.insert(0, ADMIN_ID)
OWNER_IDS = OWNER_IDS[:5]  # Max 5 owners

# Recharge QR and UPI settings (configurable via env vars)
QR_IMAGE_URL = os.getenv('QR_IMAGE_URL', 'https://files.catbox.moe/0mkr56.jpeg')
UPI_ID = os.getenv('UPI_ID', 'shubh412@fam')

# MUST JOIN CHANNELS - TWO CHANNELS
MUST_JOIN_CHANNEL_1 = "@GMS_COMEBACK_SOON1"
MUST_JOIN_CHANNEL_2 = "@GMS_GMS_GMS"
# LOG CHANNEL
LOG_CHANNEL_ID = "-1003802534246"

# Referral commission percentage
REFERRAL_COMMISSION = 1.5

# Global API Credentials for Pyrogram Login
GLOBAL_API_ID = 36326629
GLOBAL_API_HASH = "823e6e8c081fe363e6d739b39dc19e07"

# Normal emoji constants
E_DEVIL = "😈"
E_CROWN = "👑"
E_DIAMOND = "💎"
E_BUTTERFLY = "🦋"
E_MAGIC = "✨"
E_HEART = "🩷"

# ---------------------------------------------------------------------
# INIT
# ---------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
START_TIME = time.time()
AUTO_DELETE_SECONDS = 300

bot = telebot.TeleBot(BOT_TOKEN)
flask_app = Flask(__name__)


def _schedule_delete(chat_id, message_id, delay=AUTO_DELETE_SECONDS):
    """Auto-delete a Telegram message after delay seconds."""
    def _delete():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    timer = threading.Timer(delay, _delete)
    timer.daemon = True
    timer.start()


def _get_ram_usage_mb():
    """Return current process RAM usage in MB (Linux-friendly)."""
    try:
        with open("/proc/self/statm", "r", encoding="utf-8") as f:
            rss_pages = int(f.read().split()[1])
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (rss_pages * page_size) / (1024 * 1024)
    except Exception:
        return 0.0


@flask_app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@flask_app.get("/")
def health_root():
    return jsonify({"status": "ok", "service": "otp-bot"})


def start_flask_server():
    """Run lightweight Flask health server in background."""
    try:
        port = int(os.getenv("PORT", "8080"))
        flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

# MongoDB Setup
try:
    client = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True)
    db = client['otp_bot']
    users_col = db['users']
    accounts_col = db['accounts']
    orders_col = db['orders']
    wallets_col = db['wallets']
    recharges_col = db['recharges']
    otp_sessions_col = db['otp_sessions']
    referrals_col = db['referrals']
    countries_col = db['countries']
    banned_users_col = db['banned_users']
    transactions_col = db['transactions']
    coupons_col = db['coupons']
    admins_col = db['admins']  # New collection for multiple admins
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")

# Store temporary data
user_states = {}
pending_messages = {}
active_chats = {}
user_stage = {}
user_last_message = {}
user_orders = {}
order_messages = {}
cancellation_trackers = {}
order_timers = {}
change_number_requests = {}
whatsapp_number_timers = {}
payment_orders = {}
admin_deduct_state = {}
referral_data = {}
broadcast_data = {}
edit_price_state = {}
coupon_state = {}
recharge_method_state = {}
upi_payment_states = {}
admin_add_state = {}  # For /addadmin flow
admin_remove_state = {}  # For /removeadmin flow

# add this line for bordcast 
IS_BROADCASTING = False

# Pyrogram login states
login_states = {}

# BULK ADD STATES
bulk_add_states = {}

# Recharge approval tracking
recharge_approvals = {}  # Track who approved/rejected which recharge

# Import account management
try:
    from account import AccountManager
    account_manager = AccountManager(GLOBAL_API_ID, GLOBAL_API_HASH)
    logger.info("✅ Account manager loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load account module: {e}")
    account_manager = None

# Import logging module
try:
    from logs import init_logger, log_purchase_async, log_otp_received_async, log_recharge_approved_async
    init_logger(BOT_TOKEN, LOG_CHANNEL_ID)
    logger.info(f"✅ Telegram logger initialized for channel: {LOG_CHANNEL_ID}")
except ImportError as e:
    logger.error(f"❌ Failed to load logging module: {e}")

# Async manager for background tasks
async_manager = None
if account_manager:
    async_manager = account_manager.async_manager

# Initialize admin in database
def init_admin():
    """Initialize the first admin in database"""
    try:
        # Check if admins collection exists and has any admins
        if 'admins' not in db.list_collection_names():
            db.create_collection('admins')
        
        admin_count = admins_col.count_documents({})
        if admin_count == 0:
            # Add all owners from OWNER_IDS as super admins
            for owner_id in OWNER_IDS:
                admin_data = {
                    "user_id": owner_id,
                    "added_by": "SYSTEM",
                    "added_at": datetime.utcnow(),
                    "is_super_admin": True
                }
                admins_col.update_one({"user_id": owner_id}, {"$setOnInsert": admin_data}, upsert=True)
                logger.info(f"✅ Owner {owner_id} added to database")
        else:
            # Ensure all owners are always in the admins collection
            for owner_id in OWNER_IDS:
                admins_col.update_one(
                    {"user_id": owner_id},
                    {"$set": {"is_super_admin": True, "added_by": "SYSTEM"}},
                    upsert=True
                )
    except Exception as e:
        logger.error(f"❌ Failed to initialize admin: {e}")

# Call init_admin
init_admin()

# ---------------------------------------------------------------------
# ADMIN MANAGEMENT FUNCTIONS
# ---------------------------------------------------------------------
def get_admin_info(user_id):
    """Get admin info by user ID"""
    try:
        # Check if it's one of the owners
        if int(user_id) in OWNER_IDS:
            user = users_col.find_one({"user_id": user_id})
            return {
                "user_id": user_id,
                "is_super_admin": True,
                "name": user.get("name", "Owner") if user else "Owner"
            }
        
        # Check in admins collection
        admin = admins_col.find_one({"user_id": user_id})
        if admin:
            user = users_col.find_one({"user_id": user_id})
            admin["name"] = user.get("name", "Admin") if user else "Admin"
            return admin
        return None
    except Exception as e:
        logger.error(f"Error in get_admin_info: {e}")
        return None
        
def is_admin(user_id):
    """Check if user is an admin"""
    try:
        # Check if it's one of the owners
        if int(user_id) in OWNER_IDS:
            return True
        
        # Check in admins collection
        admin = admins_col.find_one({"user_id": user_id})
        return admin is not None
    except:
        return False

def is_super_admin(user_id):
    """Check if user is one of the owners (super admins)"""
    try:
        return int(user_id) in OWNER_IDS
    except:
        return str(user_id) == str(ADMIN_ID)

def add_admin(user_id, added_by):
    """Add a new admin (max 5 admins)"""
    try:
        # Check if already admin
        if is_admin(user_id):
            return False, "User is already an admin"
        
        # Count current admins (excluding super admin if counting separately)
        admin_count = admins_col.count_documents({})
        if admin_count >= 5:
            return False, "Maximum 5 admins reached"
        
        # Add new admin
        admin_data = {
            "user_id": user_id,
            "added_by": added_by,
            "added_at": datetime.utcnow(),
            "is_super_admin": False
        }
        admins_col.insert_one(admin_data)
        
        # Get user info
        user = users_col.find_one({"user_id": user_id})
        username = user.get("username", "No username") if user else "Unknown"
        
        return True, f"✅ Admin added successfully!"
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        return False, f"Error: {str(e)}"

def remove_admin(user_id, removed_by):
    """Remove an admin"""
    try:
        # Check if user is admin
        admin = admins_col.find_one({"user_id": user_id})
        if not admin:
            return False, "User is not an admin"
        
        # Check if trying to remove an owner
        if int(user_id) in OWNER_IDS:
            return False, "Cannot remove an owner"
        
        # Remove admin
        result = admins_col.delete_one({"user_id": user_id})
        
        if result.deleted_count > 0:
            return True, f"✅ Admin removed successfully!"
        else:
            return False, "Failed to remove admin"
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        return False, f"Error: {str(e)}"

def get_all_admins():
    """Get list of all admins"""
    try:
        admins = list(admins_col.find({}))
        # Also include main admin if not in collection
        main_admin_exists = any(str(a.get("user_id")) == str(ADMIN_ID) for a in admins)
        
        admin_list = []
        
        # Add main admin first
        if not main_admin_exists:
            admin_list.append({
                "user_id": ADMIN_ID,
                "username": "Main Admin",
                "name": "Main Admin",
                "added_at": datetime.utcnow(),
                "added_by": "SYSTEM",
                "is_super_admin": True
            })
        
        # Add other admins
        for admin in admins:
            user_id = admin["user_id"]
            user = users_col.find_one({"user_id": user_id})
            username = user.get("username", "No username") if user else "Unknown"
            name = user.get("name", "Unknown") if user else "Unknown"
            
            admin_list.append({
                "user_id": user_id,
                "username": username,
                "name": name,
                "added_at": admin.get("added_at"),
                "added_by": admin.get("added_by"),
                "is_super_admin": admin.get("is_super_admin", False)
            })
        return admin_list
    except Exception as e:
        logger.error(f"Error getting admins: {e}")
        return []

def get_admin_count():
    """Get total number of admins"""
    try:
        return admins_col.count_documents({}) + 1  # +1 for main admin
    except:
        return 1

# ---------------------------------------------------------------------
# ADMIN COMMAND HANDLERS
# ---------------------------------------------------------------------

@bot.message_handler(commands=['addadmin'])
def add_admin_command(msg):
    """Add a new admin - Only main admin can use"""
    user_id = msg.from_user.id
    
    # Only main admin can add admins
    if not is_super_admin(user_id):
        bot.reply_to(msg, "❌ Sirf main admin hi addadmin use kar sakta hai!")
        return
    
    # Start the add admin flow
    admin_add_state[user_id] = {"step": "waiting_user_id"}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_add_admin"))
    
    bot.reply_to(
        msg,
        "👤 **Add New Admin**\n\n"
        "Please enter the User ID of the person you want to make admin:\n\n"
        "📝 User ID milne ke liye:\n"
        "• User ko /start karna hoga bot mein\n"
        "• Ya admin panel se user search karo\n\n"
        "Example: `123456789`",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(msg):
    """Remove an admin - Only main admin can use"""
    user_id = msg.from_user.id
    
    # Only main admin can remove admins
    if not is_super_admin(user_id):
        bot.reply_to(msg, "❌ Sirf main admin hi removeadmin use kar sakta hai!")
        return
    
    # Get list of admins
    admins = get_all_admins()
    
    if len(admins) <= 1:  # Only main admin
        bot.reply_to(
            msg,
            "📋 **Admin List**\n\n"
            "Koi aur admin nahi hai remove karne ke liye.\n\n"
            f"👑 Main Admin: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )
        return
    
    # Show list of admins
    admin_list_text = "📋 **Existing Admins:**\n\n"
    for admin in admins:
        if not admin.get("is_super_admin", False):
            admin_list_text += f"• `{admin['user_id']}` - {admin['name']}\n"
    
    admin_list_text += "\nPlease enter the User ID of the admin you want to remove:"
    
    admin_remove_state[user_id] = {"step": "waiting_user_id"}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_remove_admin"))
    
    bot.reply_to(
        msg,
        admin_list_text,
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data in ["cancel_add_admin", "cancel_remove_admin"])
def handle_cancel_admin(call):
    user_id = call.from_user.id
    
    if call.data == "cancel_add_admin":
        if user_id in admin_add_state:
            del admin_add_state[user_id]
        bot.edit_message_text(
            "❌ Add admin cancelled.",
            call.message.chat.id,
            call.message.message_id
        )
    elif call.data == "cancel_remove_admin":
        if user_id in admin_remove_state:
            del admin_remove_state[user_id]
        bot.edit_message_text(
            "❌ Remove admin cancelled.",
            call.message.chat.id,
            call.message.message_id
        )

@bot.message_handler(func=lambda m: m.from_user.id in admin_add_state and admin_add_state[m.from_user.id]["step"] == "waiting_user_id")
def handle_add_admin_userid(msg):
    user_id = msg.from_user.id
    
    try:
        target_user_id = int(msg.text.strip())
        
        # Check if trying to add self
        if target_user_id == user_id:
            bot.reply_to(msg, "❌ Aap khudko admin nahi bana sakte! Aap already main admin ho.")
            del admin_add_state[user_id]
            return
        
        # Check if user exists
        user = users_col.find_one({"user_id": target_user_id})
        if not user:
            bot.reply_to(
                msg,
                f"❌ User `{target_user_id}` database mein nahi mila.\n\n"
                f"Pehle user ko /start karwaiye bot mein.",
                parse_mode="Markdown"
            )
            del admin_add_state[user_id]
            return
        
        # Check if already admin
        if is_admin(target_user_id):
            bot.reply_to(
                msg,
                f"⚠️ User `{target_user_id}` already admin hai!",
                parse_mode="Markdown"
            )
            del admin_add_state[user_id]
            return
        
        # Check max admins
        admin_count = admins_col.count_documents({})
        if admin_count >= 5:
            bot.reply_to(
                msg,
                "❌ Maximum 5 admins ho chuke hain. Pehle kisi admin ko remove karo.",
                parse_mode="Markdown"
            )
            del admin_add_state[user_id]
            return
        
        # Add admin
        success, message = add_admin(target_user_id, user_id)
        
        if success:
            # Get updated admin count
            new_count = admins_col.count_documents({})
            
            bot.reply_to(
                msg,
                f"✅ **Admin Added Successfully!**\n\n"
                f"👤 User ID: `{target_user_id}`\n"
                f"👤 Name: {user.get('name', 'Unknown')}\n"
                f"📊 Total Admins: {new_count + 1}/6 (Main Admin + {new_count})\n\n"
                f"Ab ye admin panel access kar sakte hain!",
                parse_mode="Markdown"
            )
            
            # Notify new admin
            try:
                bot.send_message(
                    target_user_id,
                    f"🎉 **Congratulations! You've Been Promoted to Admin!**\n\n"
                    f"Ab aap admin panel use kar sakte hain:\n"
                    f"• Recharge Approve/Reject\n"
                    f"• Add/Remove Countries\n"
                    f"• Add Accounts\n"
                    f"• Broadcast Messages\n"
                    f"• And more!\n\n"
                    f"Admin panel ke liye /start karo.",
                    parse_mode="Markdown"
                )
            except:
                bot.reply_to(msg, "⚠️ New admin ko notification nahi bhej sakte (unhone bot block kar diya hai)")
        else:
            bot.reply_to(msg, f"❌ {message}")
        
        del admin_add_state[user_id]
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid User ID. Sirf numbers daalo.")
    except Exception as e:
        logger.error(f"Add admin error: {e}")
        bot.reply_to(msg, f"❌ Error: {str(e)}")
        del admin_add_state[user_id]

@bot.message_handler(func=lambda m: m.from_user.id in admin_remove_state and admin_remove_state[m.from_user.id]["step"] == "waiting_user_id")
def handle_remove_admin_userid(msg):
    user_id = msg.from_user.id
    
    try:
        target_user_id = int(msg.text.strip())
        
        # Check if trying to remove self
        if target_user_id == user_id:
            bot.reply_to(msg, "❌ Aap khudko remove nahi kar sakte! Aap main admin ho.")
            del admin_remove_state[user_id]
            return
        
        # Check if user is admin
        if not is_admin(target_user_id):
            bot.reply_to(
                msg,
                f"❌ User `{target_user_id}` admin nahi hai!",
                parse_mode="Markdown"
            )
            del admin_remove_state[user_id]
            return
        
        # Remove admin
        success, message = remove_admin(target_user_id, user_id)
        
        if success:
            # Get user info
            user = users_col.find_one({"user_id": target_user_id})
            name = user.get('name', 'Unknown') if user else 'Unknown'
            
            # Get updated admin count
            new_count = admins_col.count_documents({})
            
            bot.reply_to(
                msg,
                f"✅ **Admin Removed Successfully!**\n\n"
                f"👤 User ID: `{target_user_id}`\n"
                f"👤 Name: {name}\n"
                f"📊 Remaining Admins: {new_count + 1}/6 (Main Admin + {new_count})\n\n"
                f"Ab ye admin nahi rahe.",
                parse_mode="Markdown"
            )
            
            # Notify removed admin
            try:
                bot.send_message(
                    target_user_id,
                    f"⚠️ **Your Admin Access Has Been Removed**\n\n"
                    f"Aap ab admin nahi rahe. Bot use karne ke liye /start karo.",
                    parse_mode="Markdown"
                )
            except:
                pass
        else:
            bot.reply_to(msg, f"❌ {message}")
        
        del admin_remove_state[user_id]
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid User ID. Sirf numbers daalo.")
    except Exception as e:
        logger.error(f"Remove admin error: {e}")
        bot.reply_to(msg, f"❌ Error: {str(e)}")
        del admin_remove_state[user_id]

# ---------------------------------------------------------------------
# UTILITY FUNCTIONS - UPDATED FOR TWO CHANNELS
# ---------------------------------------------------------------------

def ensure_user_exists(user_id, user_name=None, username=None, referred_by=None):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user_data = {
            "user_id": user_id,
            "name": user_name or "Unknown",
            "username": username,
            "referred_by": referred_by,
            "referral_code": f"REF{user_id}",
            "total_commission_earned": 0.0,
            "total_referrals": 0,
            "created_at": datetime.utcnow()
        }
        users_col.insert_one(user_data)
        
        if referred_by:
            referral_record = {
                "referrer_id": referred_by,
                "referred_id": user_id,
                "referral_code": user_data['referral_code'],
                "status": "pending",
                "created_at": datetime.utcnow()
            }
            referrals_col.insert_one(referral_record)
            users_col.update_one(
                {"user_id": referred_by},
                {"$inc": {"total_referrals": 1}}
            )
            logger.info(f"Referral recorded: {referred_by} -> {user_id}")
    
    wallets_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "balance": 0.0}},
        upsert=True
    )

def get_balance(user_id):
    rec = wallets_col.find_one({"user_id": user_id})
    return float(rec.get("balance", 0.0)) if rec else 0.0

def add_balance(user_id, amount):
    wallets_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": float(amount)}},
        upsert=True
    )

def deduct_balance(user_id, amount):
    wallets_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": -float(amount)}},
        upsert=True
    )

def format_currency(x):
    try:
        x = float(x)
        if x.is_integer():
            return f"₹{int(x)}"
        return f"₹{x:.2f}"
    except:
        return "₹0"

def get_available_accounts_count(country):
    return accounts_col.count_documents({"country": country, "status": "active", "used": False})

def is_user_banned(user_id):
    banned = banned_users_col.find_one({"user_id": user_id, "status": "active"})
    return banned is not None

def get_all_countries():
    return list(countries_col.find({"status": "active"}))

def get_country_by_name(country_name):
    return countries_col.find_one({
        "name": {"$regex": f"^{country_name}$", "$options": "i"},
        "status": "active"
    })

def add_referral_commission(referrer_id, recharge_amount, recharge_id):
    try:
        commission = (recharge_amount * REFERRAL_COMMISSION) / 100
        add_balance(referrer_id, commission)
        
        transaction_id = f"COM{referrer_id}{int(time.time())}"
        transaction_record = {
            "transaction_id": transaction_id,
            "user_id": referrer_id,
            "amount": commission,
            "type": "referral_commission",
            "description": f"Referral commission from recharge #{recharge_id}",
            "timestamp": datetime.utcnow(),
            "recharge_id": str(recharge_id)
        }
        transactions_col.insert_one(transaction_record)
        
        users_col.update_one(
            {"user_id": referrer_id},
            {"$inc": {"total_commission_earned": commission}}
        )
        
        referrals_col.update_one(
            {"referred_id": recharge_id.get("user_id"), "referrer_id": referrer_id},
            {"$set": {"status": "completed", "commission": commission, "completed_at": datetime.utcnow()}}
        )
        
        try:
            bot.send_message(
                referrer_id,
                f"💰 **Referral Commission Earned!**\n\n"
                f"✅ You earned {format_currency(commission)} commission!\n"
                f"📊 From: {format_currency(recharge_amount)} recharge\n"
                f"📈 Commission Rate: {REFERRAL_COMMISSION}%\n"
                f"💳 New Balance: {format_currency(get_balance(referrer_id))}\n\n"
                f"Keep referring to earn more! 🎉"
            )
        except:
            pass
        
        logger.info(f"Referral commission added: {referrer_id} - {format_currency(commission)}")
    except Exception as e:
        logger.error(f"Error adding referral commission: {e}")

# ---------------------------------------------------------------------
# UPDATED: CHECK BOTH CHANNELS MEMBERSHIP
# ---------------------------------------------------------------------

def has_user_joined_channels(user_id):
    """Check if user has joined both mandatory channels"""
    try:
        # Check first channel
        member1 = bot.get_chat_member(MUST_JOIN_CHANNEL_1, user_id)
        status1 = member1.status in ['member', 'administrator', 'creator']
        
        # Check second channel
        member2 = bot.get_chat_member(MUST_JOIN_CHANNEL_2, user_id)
        status2 = member2.status in ['member', 'administrator', 'creator']
        
        return status1 and status2
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return False

def get_missing_channels(user_id):
    """Get list of channels user hasn't joined yet"""
    missing = []
    try:
        # Check first channel
        try:
            member1 = bot.get_chat_member(MUST_JOIN_CHANNEL_1, user_id)
            if member1.status not in ['member', 'administrator', 'creator']:
                missing.append(MUST_JOIN_CHANNEL_1)
        except:
            missing.append(MUST_JOIN_CHANNEL_1)
        
        # Check second channel
        try:
            member2 = bot.get_chat_member(MUST_JOIN_CHANNEL_2, user_id)
            if member2.status not in ['member', 'administrator', 'creator']:
                missing.append(MUST_JOIN_CHANNEL_2)
        except:
            missing.append(MUST_JOIN_CHANNEL_2)
        
        return missing
    except Exception as e:
        logger.error(f"Error getting missing channels: {e}")
        return [MUST_JOIN_CHANNEL_1, MUST_JOIN_CHANNEL_2]

# ---------------------------------------------------------------------
# COUPON UTILITY FUNCTIONS
# ---------------------------------------------------------------------

def get_coupon(code):
    return coupons_col.find_one({"coupon_code": code})

def is_coupon_claimed_by_user(coupon_code, user_id):
    coupon = get_coupon(coupon_code)
    if not coupon:
        return False
    claimed_users = coupon.get("claimed_users", [])
    return user_id in claimed_users

def claim_coupon(coupon_code, user_id):
    try:
        coupon = get_coupon(coupon_code)
        if not coupon:
            return False, "Coupon not found"
        
        if user_id in coupon.get("claimed_users", []):
            return False, "Already claimed"
        
        if coupon.get("status") != "active":
            status = coupon.get("status", "inactive")
            return False, f"Coupon {status}"
        
        total_claimed = coupon.get("total_claimed_count", 0)
        max_users = coupon.get("max_users", 0)
        if total_claimed >= max_users:
            coupons_col.update_one(
                {"coupon_code": coupon_code},
                {"$set": {"status": "expired"}}
            )
            return False, "Fully claimed"
        
        result = coupons_col.update_one(
            {
                "coupon_code": coupon_code,
                "status": "active",
                "total_claimed_count": {"$lt": max_users}
            },
            {
                "$inc": {"total_claimed_count": 1},
                "$push": {"claimed_users": user_id},
                "$set": {
                    "last_claimed_at": datetime.utcnow(),
                    "last_claimed_by": user_id
                }
            }
        )
        
        if result.modified_count == 0:
            return False, "Coupon no longer available"
        
        amount = coupon.get("amount", 0)
        add_balance(user_id, amount)
        
        transaction_id = f"CPN{user_id}{int(time.time())}"
        transaction_record = {
            "transaction_id": transaction_id,
            "user_id": user_id,
            "amount": amount,
            "type": "coupon_redeem",
            "description": f"Coupou redeem: {coupon_code}",
            "coupon_code": coupon_code,
            "timestamp": datetime.utcnow()
        }
        transactions_col.insert_one(transaction_record)
        
        updated_coupon = get_coupon(coupon_code)
        if updated_coupon and updated_coupon.get("total_claimed_count", 0) >= max_users:
            coupons_col.update_one(
                {"coupon_code": coupon_code},
                {"$set": {"status": "expired"}}
            )
        
        return True, amount
    except Exception as e:
        logger.error(f"Error claiming coupon: {e}")
        return False, "Error processing coupon"

def create_coupon(code, amount, max_users, created_by):
    try:
        if amount < 1:
            return False, "Amount must be at least ₹1"
        if max_users < 1:
            return False, "Max users must be at least 1"
        
        existing = get_coupon(code)
        if existing:
            return False, "Coupon code already exists"
        
        coupon_data = {
            "coupon_code": code,
            "amount": float(amount),
            "max_users": int(max_users),
            "total_claimed_count": 0,
            "claimed_users": [],
            "status": "active",
            "created_at": datetime.utcnow(),
            "created_by": created_by
        }
        coupons_col.insert_one(coupon_data)
        return True, "Coupon created successfully"
    except Exception as e:
        logger.error(f"Error creating coupon: {e}")
        return False, f"Error: {str(e)}"

def remove_coupon(code, removed_by):
    try:
        coupon = get_coupon(code)
        if not coupon:
            return False, "Coupon not found"
        
        result = coupons_col.update_one(
            {"coupon_code": code},
            {"$set": {
                "status": "removed",
                "removed_at": datetime.utcnow(),
                "removed_by": removed_by
            }}
        )
        
        if result.modified_count == 0:
            return False, "Failed to remove coupon"
        return True, "Coupon removed successfully"
    except Exception as e:
        logger.error(f"Error removing coupon: {e}")
        return False, f"Error: {str(e)}"

def get_coupon_status(code):
    coupon = get_coupon(code)
    if not coupon:
        return None
    
    claimed = coupon.get("total_claimed_count", 0)
    max_users = coupon.get("max_users", 0)
    remaining = max(0, max_users - claimed)
    
    return {
        "code": coupon.get("coupon_code"),
        "amount": coupon.get("amount", 0),
        "max_users": max_users,
        "claimed": claimed,
        "remaining": remaining,
        "status": coupon.get("status", "unknown"),
        "created_at": coupon.get("created_at"),
        "created_by": coupon.get("created_by"),
        "claimed_users": coupon.get("claimed_users", [])[:10]
    }

# ---------------------------------------------------------------------
# ENHANCED RECHARGE APPROVAL FUNCTIONS
# ---------------------------------------------------------------------

def process_recharge_approval(admin_id, req_id, action):
    """Process recharge approval/rejection with tracking"""
    try:
        # Get recharge request
        req = recharges_col.find_one({"req_id": req_id})
        if not req:
            return False, "Request not found", None
        
        # Check if already processed
        if req.get("status") != "pending":
            return False, f"Request already {req.get('status')}", None
        
        # Get admin info
        admin_info = get_admin_info(admin_id)
        admin_name = f"Admin {admin_id}"
        if admin_info:
            user = users_col.find_one({"user_id": admin_id})
            if user:
                admin_name = user.get("name", f"Admin {admin_id}")
        
        user_target = req.get("user_id")
        amount = float(req.get("amount", 0))
        
        # Track this approval
        approval_key = f"{req_id}_{action}"
        
        # Check if another admin already processed this (via tracking)
        if approval_key in recharge_approvals:
            prev_admin = recharge_approvals[approval_key]
            return False, f"Already {action}ed by {prev_admin['admin_name']}", None
        
        if action == "approve":
            # Add balance to user
            add_balance(user_target, amount)
            
            # Update recharge status
            recharges_col.update_one(
                {"req_id": req_id},
                {"$set": {
                    "status": "approved", 
                    "processed_at": datetime.utcnow(), 
                    "processed_by": admin_id,
                    "processed_by_name": admin_name
                }}
            )
            
            # Log approval
            try:
                from logs import log_recharge_approved_async
                log_recharge_approved_async(
                    user_id=user_target,
                    amount=amount,
                    method=req.get("method", "UPI"),
                    utr=req.get("utr")
                )
            except:
                pass
            
            # Add referral commission if applicable
            user_data = users_col.find_one({"user_id": user_target})
            if user_data and user_data.get("referred_by"):
                add_referral_commission(user_data["referred_by"], amount, req)
            
            # Mark this approval in tracking
            recharge_approvals[approval_key] = {
                "admin_id": admin_id,
                "admin_name": admin_name,
                "timestamp": datetime.utcnow()
            }
            
            return True, f"✅ Recharge approved by {admin_name}", {
                "admin_name": admin_name,
                "admin_id": admin_id,
                "action": "approved"
            }
            
        else:  # cancel/reject
            # Update recharge status
            recharges_col.update_one(
                {"req_id": req_id},
                {"$set": {
                    "status": "cancelled", 
                    "processed_at": datetime.utcnow(), 
                    "processed_by": admin_id,
                    "processed_by_name": admin_name
                }}
            )
            
            # Mark this rejection in tracking
            recharge_approvals[approval_key] = {
                "admin_id": admin_id,
                "admin_name": admin_name,
                "timestamp": datetime.utcnow()
            }
            
            return True, f"❌ Recharge rejected by {admin_name}", {
                "admin_name": admin_name,
                "admin_id": admin_id,
                "action": "rejected"
            }
            
    except Exception as e:
        logger.error(f"Error in recharge approval: {e}")
        return False, f"Error: {str(e)}", None

# ---------------------------------------------------------------------
# UI HELPER FUNCTIONS - FIXED
# ---------------------------------------------------------------------

def edit_or_resend(chat_id, message_id, text, markup=None, parse_mode=None, photo_url=None):
    """Edit message if possible, otherwise delete and send new"""
    try:
        if photo_url:
            # For photos, we need to send new message
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            return bot.send_photo(chat_id, photo_url, caption=text, parse_mode=parse_mode, reply_markup=markup)
        else:
            # For text messages, try to edit first
            try:
                return bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode=parse_mode,
                    reply_markup=markup
                )
            except Exception as e:
                # If edit fails, delete and send new
                try:
                    bot.delete_message(chat_id, message_id)
                except:
                    pass
                return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in edit_or_resend: {e}")
        return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=markup)

def clean_ui_and_send_menu(chat_id, user_id, text=None, markup=None):
    """Clean UI and send main menu - FIXED: Always deletes old message"""
    try:
        # ALWAYS try to delete the previous message
        if user_id in user_last_message:
            try:
                bot.delete_message(chat_id, user_last_message[user_id])
            except:
                pass
        
        # Main menu caption with expandable blockquotes
        caption = (
    '🌟 <b>Welcome To GMS OTP Bot</b> 🌟\n'
    "<blockquote expandable>\n"
    '✨ Automatic OTPs — Instant & Fast\n'
    '💎 Easy to Use — Simple Interface\n'
    '🔥 24/7 Support — Always Here\n'
    '⚡ Instant Payment Approvals\n'
    "</blockquote>\n"
    "<blockquote expandable>\n"
    '👑 <b>How to use GMS Bot:</b>\n'
    "1️⃣ Add Funds to Wallet\n"
    "2️⃣ Select Country\n"
    "3️⃣ Buy Account\n"
    "4️⃣ Login via Telegram / Telegram X / Tarbotel\n"
    "5️⃣ Receive OTP & Done ✅\n"
    "</blockquote>\n"
    '⚡ <b>GMS — Fast. Reliable. Always On!</b>'
)
        
        if markup is None:
            markup = InlineKeyboardMarkup(row_width=2)
            # Row 1: 2 buttons
            markup.add(
                InlineKeyboardButton("🛍️ Buy Account", callback_data="buy_account", style="success"),
                InlineKeyboardButton("💎 My Balance", callback_data="balance", style="primary")
            )
            # Row 2: 1 button
            markup.add(
                InlineKeyboardButton("💸 Add Funds", callback_data="recharge", style="success")
            )
            # Row 3: 2 buttons
            markup.add(
                InlineKeyboardButton("🤝 Refer & Earn", callback_data="refer_friends", style="primary"),
                InlineKeyboardButton("🎁 Redeem Coupon", callback_data="redeem_coupon", style="danger")
            )
            # Row 4: 1 button
            markup.add(
                InlineKeyboardButton("🆘 Support", callback_data="support", style="primary")
            )
            # Row 5: 1 button (only for admin)
            if is_admin(user_id):
                markup.add(InlineKeyboardButton("⚡ Admin Panel", callback_data="admin_panel", style="danger"))
        
        # Send new message (TEXT ONLY - NO PHOTO)
        sent_msg = bot.send_message(
            chat_id,
            text or caption,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True
        )
        user_last_message[user_id] = sent_msg.message_id
        return sent_msg
    except Exception as e:
        logger.error(f"Error in clean_ui_and_send_menu: {e}")
        # Fallback
        try:
            sent_msg = bot.send_message(chat_id, text or caption, parse_mode="HTML", reply_markup=markup)
            user_last_message[user_id] = sent_msg.message_id
            return sent_msg
        except:
            pass

# ---------------------------------------------------------------------
# BALANCE TRANSFER FUNCTIONS
# ---------------------------------------------------------------------

def transfer_balance(sender_id, receiver_id, amount):
    """Balance transfer function"""
    try:
        # Sender ka balance check
        sender_balance = get_balance(sender_id)
        
        if sender_balance < amount:
            return False, "Insufficient balance"
        
        if amount <= 0:
            return False, "Amount must be greater than 0"
        
        if sender_id == receiver_id:
            return False, "Cannot send to yourself"
        
        # Check if receiver exists
        receiver = users_col.find_one({"user_id": receiver_id})
        if not receiver:
            return False, "Receiver user not found"
        
        # Transfer balance
        deduct_balance(sender_id, amount)
        add_balance(receiver_id, amount)
        
        # Transaction record
        transaction_id = f"TRF{int(time.time())}{sender_id}"
        transaction_record = {
            "transaction_id": transaction_id,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "amount": amount,
            "type": "transfer",
            "timestamp": datetime.utcnow()
        }
        transactions_col.insert_one(transaction_record)
        
        return True, f"✅ {format_currency(amount)} transferred successfully!"
        
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        return False, f"Error: {str(e)}"

# ---------------------------------------------------------------------
# NORMAL INTRO FUNCTION (NO PREMIUM EMOJI)
# ---------------------------------------------------------------------

# Normal emojis instead of tg-emoji
E_MAGIC     = "✨"
E_DEVIL     = "😈"
E_CROWN     = "👑"
E_DIAMOND   = "💎"
E_BUTTERFLY = "🦋"
E_HEART     = "🩷"

# Cache sticker file_ids from the pack
_cached_sticker_ids = []

def _get_random_sticker_file_id():
    """Fetch sticker set once via Bot API and return a random sticker file_id"""
    global _cached_sticker_ids
    if not _cached_sticker_ids:
        try:
            sticker_set = bot.get_sticker_set(PREMIUM_STICKER_PACK)
            _cached_sticker_ids = [s.file_id for s in sticker_set.stickers]
            logger.info(f"✅ Loaded {len(_cached_sticker_ids)} stickers from {PREMIUM_STICKER_PACK}")
        except Exception as e:
            logger.error(f"Failed to fetch sticker set: {e}")
    if _cached_sticker_ids:
        return random.choice(_cached_sticker_ids)
    return None

def run_premium_intro(user_id):
    """Send animated intro with normal emojis + random sticker"""
    try:
        m1 = bot.send_message(user_id, f"{E_MAGIC} Hlo Sir......")
        time.sleep(1)
        bot.delete_message(user_id, m1.message_id)

        m2 = bot.send_message(user_id, f"{E_DEVIL} Ping Pong........")
        time.sleep(1)
        bot.delete_message(user_id, m2.message_id)

        m3 = bot.send_message(user_id, f"{E_CROWN} Gms OP......")
        time.sleep(1)
        bot.delete_message(user_id, m3.message_id)

        # Send a random sticker
        sticker_file_id = _get_random_sticker_file_id()
        if sticker_file_id:
            bot.send_sticker(user_id, sticker_file_id)

    except Exception as e:
        logger.error(f"Intro error: {e}")
        try:
            m1 = bot.send_message(user_id, '✨ Hlo Sir......')
            time.sleep(1)
            bot.delete_message(user_id, m1.message_id)

            m2 = bot.send_message(user_id, '🔥 Ping Pong........')
            time.sleep(1)
            bot.delete_message(user_id, m2.message_id)

            m3 = bot.send_message(user_id, '💎 Gms OP......')
            time.sleep(1)
            bot.delete_message(user_id, m3.message_id)
        except:
            pass
# ---------------------------------------------------------------------
# BOT HANDLERS - UPDATED WITH TWO CHANNELS
# ---------------------------------------------------------------------

@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    logger.info(f"Start command from user {user_id}")
    
    if is_user_banned(user_id):
        try:
            bot.delete_message(msg.chat.id, msg.message_id)
        except:
            pass
        return
    
    # Check if user has joined BOTH channels
    if not has_user_joined_channels(user_id):
        missing_channels = get_missing_channels(user_id)
        
        caption = """<b>🚀 Join Both Channels First!</b> 

📢 To use this bot, you must join our official channels.

👉 Get updates, new features & support from our channels.

Click the buttons below to join both channels, then press VERIFY ✅"""
        
        markup = InlineKeyboardMarkup(row_width=2)
        
        # Add buttons for both channels
        for channel in missing_channels:
            markup.add(InlineKeyboardButton(
                f"📢 Join {channel}",
               url=f"https://t.me/{channel[1:]}"
            ))
        
        markup.add(InlineKeyboardButton("✅ Verify Join", callback_data="verify_join" ,  style="success"))
        
        try:
            bot.send_message(
                user_id,
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error sending join message: {e}")
        return
    
    referred_by = None
    if len(msg.text.split()) > 1:
        referral_code = msg.text.split()[1]
        if referral_code.startswith('REF'):
            try:
                referrer_id = int(referral_code[3:])
                referrer = users_col.find_one({"user_id": referrer_id})
                if referrer:
                    referred_by = referrer_id
                    logger.info(f"Referral detected: {referrer_id} -> {user_id}")
            except:
                pass
    
    ensure_user_exists(user_id, msg.from_user.first_name, msg.from_user.username, referred_by)

    # Animated intro with real premium emoji via premium account
    run_premium_intro(user_id)

    clean_ui_and_send_menu(user_id, user_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 Your account is banned", show_alert=True)
        return
    
    logger.info(f"Callback received: {data} from user {user_id}")
    
    try:
        if data == "verify_join":
            # Check if user has joined BOTH channels
            if has_user_joined_channels(user_id):
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                clean_ui_and_send_menu(call.message.chat.id, user_id)
                bot.answer_callback_query(call.id, "✅ Verified! Welcome to the bot.", show_alert=True)
            else:
                missing_channels = get_missing_channels(user_id)
                
                caption = """<b>🚀 Join Both Channels First!</b> 

📢 To use this bot, you must join our official channels.

👉 Get updates, new features & support from our channels.

Click the buttons below to join both channels, then press VERIFY ✅"""
                
                markup = InlineKeyboardMarkup(row_width=2)
                
                # Add buttons for both channels
                for channel in missing_channels:
                    markup.add(InlineKeyboardButton(
                        f"📢 Join {channel}",
                        url=f"https://t.me/{channel[1:]}"
                    ))
                
                markup.add(InlineKeyboardButton("✅ Verify Join", callback_data="verify_join" ,  style="success"))
                
                try:
                    bot.edit_message_text(
                        caption,
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode="HTML",
                        reply_markup=markup
                    )
                except:
                    pass
                
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join these channels first:\n{missing_list}", 
                    show_alert=True
                )
        
        elif data == "buy_account":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            show_countries(call.message.chat.id)
        
        elif data == "balance":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            balance = get_balance(user_id)
            user_data = users_col.find_one({"user_id": user_id}) or {}
            commission_earned = user_data.get("total_commission_earned", 0)
            
            message = f"💰 **Your Balance:** {format_currency(balance)}\n\n"
            message += f"📊 **Referral Stats:**\n"
            message += f"• Total Commission Earned: {format_currency(commission_earned)}\n"
            message += f"• Total Referrals: {user_data.get('total_referrals', 0)}\n"
            message += f"• Commission Rate: {REFERRAL_COMMISSION}%\n\n"
            message += f"Your Referral Code: `{user_data.get('referral_code', 'REF' + str(user_id))}`"
            
            # Sirf Send Balance aur Back button
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("📤 Send Balance", callback_data="send_balance_menu" ,  style="success")
            )
            markup.add(
                InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu" ,  style="primary")
            )
            
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            sent_msg = bot.send_message(
                call.message.chat.id,
                message,
                parse_mode="Markdown",
                reply_markup=markup
            )
            user_last_message[user_id] = sent_msg.message_id
        
        elif data == "send_balance_menu":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            balance = get_balance(user_id)
            
            message = f"📤 **Send Balance - Step 1/2**\n\n"
            message += f"💰 Your Current Balance: {format_currency(balance)}\n\n"
            message += f"Please enter the **Receiver's User ID**:\n"
            message += f"_(Only numeric ID, e.g., 123456789)_"
            
            # Sirf Back button
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back to Balance", callback_data="balance"))
            
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                message,
                markup=markup,
                parse_mode="Markdown"
            )
            
            # Set user state for user ID input
            user_stage[user_id] = "waiting_receiver_id"
        
        elif data == "transfer_confirm":
            # Transfer confirmation screen
            transfer_data = user_states.get(user_id, {})
            if not transfer_data or "receiver_id" not in transfer_data or "amount" not in transfer_data:
                bot.answer_callback_query(call.id, "❌ Session expired", show_alert=True)
                clean_ui_and_send_menu(call.message.chat.id, user_id)
                return
            
            receiver_id = transfer_data["receiver_id"]
            receiver_name = transfer_data.get("receiver_name", f"ID: {receiver_id}")
            amount = transfer_data["amount"]
            sender_balance = get_balance(user_id)
            
            message = f"📤 **Confirm Transfer**\n\n"
            message += f"👤 Receiver: {receiver_name}\n"
            message += f"🆔 Receiver ID: `{receiver_id}`\n"
            message += f"💰 Amount: {format_currency(amount)}\n"
            message += f"💳 Your Balance: {format_currency(sender_balance)}\n\n"
            message += f"Are you sure you want to proceed?"
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ Confirm", callback_data="transfer_execute"),
                InlineKeyboardButton("❌ Cancel", callback_data="balance")
            )
            
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                message,
                markup=markup,
                parse_mode="Markdown"
            )
        
        elif data == "transfer_execute":
            # Execute transfer
            transfer_data = user_states.get(user_id, {})
            if not transfer_data or "receiver_id" not in transfer_data or "amount" not in transfer_data:
                bot.answer_callback_query(call.id, "❌ Session expired", show_alert=True)
                clean_ui_and_send_menu(call.message.chat.id, user_id)
                return
            
            receiver_id = transfer_data["receiver_id"]
            receiver_name = transfer_data.get("receiver_name", f"ID: {receiver_id}")
            amount = transfer_data["amount"]
            
            success, message_text = transfer_balance(user_id, receiver_id, amount)
            
            if success:
                # Get updated balances
                sender_new_balance = get_balance(user_id)
                receiver_new_balance = get_balance(receiver_id)
                
                # Message for sender
                sender_message = f"✅ **Transfer Successful!**\n\n"
                sender_message += f"👤 Sent to: {receiver_name}\n"
                sender_message += f"🆔 Receiver ID: `{receiver_id}`\n"
                sender_message += f"💰 Amount Sent: {format_currency(amount)}\n"
                sender_message += f"💳 Your New Balance: {format_currency(sender_new_balance)}\n\n"
                
                # Sirf Back to Balance button
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("⬅️ Back to Balance", callback_data="balance"))
                
                edit_or_resend(
                    call.message.chat.id,
                    call.message.message_id,
                    sender_message,
                    markup=markup,
                    parse_mode="Markdown"
                )
                
                # Send notification to receiver
                try:
                    # Get sender name
                    sender = users_col.find_one({"user_id": user_id})
                    sender_name = sender.get("name", "Unknown") if sender else "Unknown"
                    
                    receiver_message = f"📥 **Balance Received!**\n\n"
                    receiver_message += f"👤 From: {sender_name}\n"
                    receiver_message += f"🆔 Sender ID: `{user_id}`\n"
                    receiver_message += f"💰 Amount Received: {format_currency(amount)}\n"
                    receiver_message += f"💳 Your New Balance: {format_currency(receiver_new_balance)}\n\n"
                    
                    # Sirf Close button for receiver
                    receiver_markup = InlineKeyboardMarkup()
                    receiver_markup.add(InlineKeyboardButton("❌ Close", callback_data="back_to_menu"))
                    
                    bot.send_message(
                        receiver_id,
                        receiver_message,
                        parse_mode="Markdown",
                        reply_markup=receiver_markup
                    )
                except Exception as e:
                    logger.warning(f"Could not notify receiver {receiver_id}: {e}")
                
            else:
                # Transfer failed
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("🔄 Try Again", callback_data="send_balance_menu"),
                    InlineKeyboardButton("⬅️ Back to Balance", callback_data="balance")
                )
                
                edit_or_resend(
                    call.message.chat.id,
                    call.message.message_id,
                    f"❌ **Transfer Failed!**\n\n{message_text}",
                    markup=markup,
                    parse_mode="Markdown"
                )
            
            # Clear transfer state
            if user_id in user_states:
                user_states.pop(user_id, None)
            if user_id in user_stage:
                user_stage.pop(user_id, None)
        
        elif data == "redeem_coupon":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            msg_text = "🎟 **Redeem Coupon**\n\nEnter your coupon code:"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
            
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            sent_msg = bot.send_message(
                call.message.chat.id,
                msg_text,
                parse_mode="Markdown",
                reply_markup=markup
            )
            user_last_message[user_id] = sent_msg.message_id
            user_stage[user_id] = "waiting_coupon"
        
        elif data == "recharge":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            show_recharge_methods(call.message.chat.id, call.message.message_id, user_id)
        
        elif data == "refer_friends":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            show_referral_info(user_id, call.message.chat.id)
        
        elif data == "support":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            msg_text = "🛠️ Support:@MADARA_X_DISTROYER"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
            
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            sent_msg = bot.send_message(
                call.message.chat.id,
                msg_text,
                reply_markup=markup
            )
            user_last_message[user_id] = sent_msg.message_id
        
        elif data == "admin_panel":
            if is_admin(user_id):
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                show_admin_panel(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data.startswith("bulk_account_"):
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
                return
            
            country_name = data.replace("bulk_account_", "")
            
            bulk_add_states[user_id] = {
                "mode": "bulk",
                "country": country_name,
                "phone_numbers": [],
                "current_index": 0,
                "total_numbers": 0,
                "success_count": 0,
                "failed_count": 0,
                "failed_numbers": [],
                "current_client": None,
                "current_phone_code_hash": None,
                "current_phone": None,
                "current_manager": None,
                "password_attempts": 0,
                "message_id": call.message.message_id,
                "step": "waiting_numbers",
                "chat_id": call.message.chat.id,
                "is_processing": False
            }
            
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                f"📦 **Bulk Account Addition**\n\n"
                f"🌍 Country: {country_name}\n\n"
                "📱 Enter phone numbers (one per line):\n"
                "Format:\n"
                "+91XXXXXXXXXX\n"
                "+91828XXXXXXX\n"
                "+91999XXXXXXX\n\n"
                "⚠️ Max 50 numbers at once\n"
                "⚠️ Include country code\n"
                "⚠️ One number per line",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk")
                )
            )
        
        elif data.startswith("single_account_"):
            country_name = data.replace("single_account_", "")
            login_states[user_id]["country"] = country_name
            login_states[user_id]["step"] = "phone"
            login_states[user_id]["mode"] = "single"
            
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                f"🌍 Country: {country_name}\n\n"
                "📱 Enter phone number with country code:\n"
                "Example: +919876543210",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")
                )
            )
        
        elif data == "start_bulk_add":
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
                return
            
            if user_id not in bulk_add_states:
                bot.answer_callback_query(call.id, "❌ Session expired", show_alert=True)
                return
            
            state = bulk_add_states[user_id]
            if not state.get("phone_numbers"):
                bot.answer_callback_query(call.id, "❌ No phone numbers to process", show_alert=True)
                return
            
            bot.answer_callback_query(call.id, "🚀 Starting bulk account addition...")
            start_bulk_processing(user_id)
        
        elif data == "cancel_bulk":
            handle_cancel_bulk(call)
        
        elif data == "pause_bulk":
            if user_id in bulk_add_states:
                bulk_add_states[user_id]["is_processing"] = False
                bot.answer_callback_query(call.id, "⏸️ Processing paused", show_alert=True)
        
        elif data == "resume_bulk":
            if user_id in bulk_add_states:
                bulk_add_states[user_id]["is_processing"] = True
                bot.answer_callback_query(call.id, "▶️ Processing resumed", show_alert=True)
                process_next_bulk_number(user_id)
        
        elif data == "skip_bulk_number":
            if user_id in bulk_add_states:
                state = bulk_add_states[user_id]
                state["failed_count"] += 1
                state["failed_numbers"].append({
                    "number": state.get("current_phone", "Unknown"),
                    "reason": "Skipped by admin"
                })
                
                if state.get("current_client") and account_manager:
                    try:
                        asyncio.run(account_manager.pyrogram_manager.safe_disconnect(state["current_client"]))
                    except:
                        pass
                
                state["current_index"] += 1
                state["password_attempts"] = 0
                bot.answer_callback_query(call.id, "⏭️ Number skipped", show_alert=True)
                process_next_bulk_number(user_id)
        
        elif data.startswith("country_raw_"):
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            country_name = data.replace("country_raw_", "")
            show_country_details(user_id, country_name, call.message.chat.id, call.message.message_id, call.id)
        
        elif data.startswith("buy_"):
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            account_id = data.split("_", 1)[1]
            process_purchase(user_id, account_id, call.message.chat.id, call.message.message_id, call.id)
        
        elif data.startswith("logout_session_"):
            session_id = data.split("_", 2)[2]
            handle_logout_session(user_id, session_id, call.message.chat.id, call.id)
        
        elif data.startswith("get_otp_"):
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            session_id = data.split("_", 2)[2]
            get_latest_otp(user_id, session_id, call.message.chat.id, call.id)
        
        elif data == "back_to_countries":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            show_countries(call.message.chat.id)
        
        elif data == "back_to_menu":
            clean_ui_and_send_menu(call.message.chat.id, user_id)
        
        elif data == "recharge_upi":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            recharge_method_state[user_id] = "upi"
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                "💳 Enter recharge amount for UPI (minimum ₹1):",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
                )
            )
            bot.register_next_step_handler(call.message, process_recharge_amount)
        
        elif data == "recharge_crypto":
            if not has_user_joined_channels(user_id):
                missing_channels = get_missing_channels(user_id)
                missing_list = "\n".join([f"• {ch}" for ch in missing_channels])
                bot.answer_callback_query(
                    call.id, 
                    f"❌ Please join:\n{missing_list}", 
                    show_alert=True
                )
                start(call.message)
                return
            
            recharge_method_state[user_id] = "crypto"
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                "💳 Enter recharge amount in INR for Crypto (minimum ₹1):",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
                )
            )
            bot.register_next_step_handler(call.message, process_recharge_amount)
        
        elif data == "upi_deposited":
            user_id = call.from_user.id
            amount = upi_payment_states.get(user_id, {}).get("amount", 0)
            if amount <= 0:
                bot.answer_callback_query(call.id, "❌ Invalid amount", show_alert=True)
                return
            
            bot.answer_callback_query(call.id, "📝 Please send your 12-digit UTR number", show_alert=False)
            
            upi_payment_states[user_id] = {
                "step": "waiting_utr",
                "amount": amount,
                "chat_id": call.message.chat.id
            }
            
            bot.send_message(
                call.message.chat.id,
                "📝 **Step 1: Enter UTR**\n\n"
                "Please send your 12-digit UTR number:\n"
                "_(Sent by your bank after payment)_"
            )
        
        elif data.startswith("approve_rech|") or data.startswith("cancel_rech|"):
            if is_admin(user_id):
                parts = data.split("|")
                action = parts[0]
                req_id = parts[1] if len(parts) > 1 else None
                
                # Process approval/rejection
                success, message, admin_info = process_recharge_approval(user_id, req_id, 
                                                                        "approve" if action == "approve_rech" else "reject")
                
                if success:
                    bot.answer_callback_query(call.id, message, show_alert=True)
                    
                    # Delete the original admin message
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                    except:
                        pass
                    
                    # Send new message showing which admin approved/rejected
                    admin_action_msg = f"✅ **Recharge Request Processed**\n\n"
                    admin_action_msg += f"📋 Request ID: `{req_id}`\n"
                    admin_action_msg += f"👤 Processed by: {admin_info['admin_name']}\n"
                    admin_action_msg += f"🆔 Admin ID: `{admin_info['admin_id']}`\n"
                    admin_action_msg += f"📌 Action: **{admin_info['action'].upper()}**\n"
                    admin_action_msg += f"⏰ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
                    
                    bot.send_message(
                        call.message.chat.id,
                        admin_action_msg,
                        parse_mode="Markdown"
                    )
                else:
                    bot.answer_callback_query(call.id, f"❌ {message}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "add_account":
            logger.info(f"Add account button clicked by user {user_id}")
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
                return
            
            login_states[user_id] = {
                "step": "select_country",
                "message_id": call.message.message_id,
                "chat_id": call.message.chat.id
            }
            
            countries = get_all_countries()
            if not countries:
                bot.answer_callback_query(call.id, "❌ No countries available. Add a country first.", show_alert=True)
                return
            
            markup = InlineKeyboardMarkup(row_width=2)
            for country in countries:
                markup.add(InlineKeyboardButton(
                    country['name'],
                    callback_data=f"login_country_{country['name']}"
                ))
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_login"))
            
            edit_or_resend(
                call.message.chat.id,
                call.message.message_id,
                "🌍 **Select Country for Account**\n\nChoose country:",
                markup=markup
            )
        
        elif data.startswith("login_country_"):
            handle_login_country_selection(call)
        
        elif data == "cancel_login":
            handle_cancel_login(call)
        
        elif data == "out_of_stock":
            bot.answer_callback_query(call.id, "❌ Out of Stock! No accounts available.", show_alert=True)
        
        elif data == "edit_price":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                show_edit_price_country_selection(call.message.chat.id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data.startswith("edit_price_country_"):
            if is_admin(user_id):
                country_name = data.replace("edit_price_country_", "")
                show_edit_price_details(call.message.chat.id, call.message.message_id, country_name)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data.startswith("edit_price_confirm_"):
            if is_admin(user_id):
                country_name = data.replace("edit_price_confirm_", "")
                edit_price_state[user_id] = {"country": country_name, "step": "waiting_price"}
                try:
                    country = get_country_by_name(country_name)
                    if country:
                        current_price = country.get("price", 0)
                        edit_or_resend(
                            call.message.chat.id,
                            call.message.message_id,
                            f"🌍 Country: {country_name}\n💰 Current Price: {format_currency(current_price)}\n\n"
                            f"Enter new price for {country_name}:",
                            markup=InlineKeyboardMarkup().add(
                                InlineKeyboardButton("❌ Cancel", callback_data="manage_countries")
                            )
                        )
                    else:
                        bot.answer_callback_query(call.id, "❌ Country not found", show_alert=True)
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "cancel_edit_price":
            if is_admin(user_id):
                show_country_management(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "admin_coupon_menu":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "🎟 Coupon Management")
                show_coupon_management(call.message.chat.id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "admin_create_coupon":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Creating coupon...")
                coupon_state[user_id] = {"step": "ask_code"}
                edit_or_resend(
                    call.message.chat.id,
                    call.message.message_id,
                    "🎟 **Create Coupon**\n\nEnter coupon code:",
                    markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("❌ Cancel", callback_data="admin_coupon_menu")
                    ),
                    parse_mode="Markdown"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "admin_remove_coupon":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Removing coupon...")
                coupon_state[user_id] = {"step": "ask_remove_code"}
                edit_or_resend(
                    call.message.chat.id,
                    call.message.message_id,
                    "🗑 **Remove Coupon**\n\nEnter coupon code to remove:",
                    markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("❌ Cancel", callback_data="admin_coupon_menu")
                    ),
                    parse_mode="Markdown"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "admin_coupon_status":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Checking coupon status...")
                coupon_state[user_id] = {"step": "ask_status_code"}
                edit_or_resend(
                    call.message.chat.id,
                    call.message.message_id,
                    "📊 **Coupon Status**\n\nEnter coupon code to check:",
                    markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("❌ Cancel", callback_data="admin_coupon_menu")
                    ),
                    parse_mode="Markdown"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "broadcast_menu":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "📢 Reply any photo / document / video / text with /sendbroadcast")
                bot.send_message(call.message.chat.id, "📢 **Broadcast Instructions**\n\nReply to any message (photo / document / video / text) with /sendbroadcast\n\n✅ The message will be forwarded as-is to all users.")
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "refund_start":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                msg = bot.send_message(call.message.chat.id, "💸 Enter user ID for refund:")
                bot.register_next_step_handler(msg, ask_refund_user)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "ranking":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "📊 Generating ranking...")
                show_user_ranking(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "message_user":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "👤 Enter user ID to send message:")
                msg = bot.send_message(call.message.chat.id, "👤 Enter user ID to send message:")
                bot.register_next_step_handler(msg, ask_message_content)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "admin_deduct_start":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                admin_deduct_state[user_id] = {"step": "ask_user_id"}
                msg = bot.send_message(call.message.chat.id, "👤 Enter User ID whose balance you want to deduct:")
                if user_id in broadcast_data:
                    del broadcast_data[user_id]
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "ban_user":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                msg = bot.send_message(call.message.chat.id, "🚫 Enter User ID to ban:")
                bot.register_next_step_handler(msg, ask_ban_user)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "unban_user":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                msg = bot.send_message(call.message.chat.id, "✅ Enter User ID to unban:")
                bot.register_next_step_handler(msg, ask_unban_user)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "manage_countries":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                show_country_management(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "add_country":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                msg = bot.send_message(call.message.chat.id, "🌍 Enter country name to add:")
                bot.register_next_step_handler(msg, ask_country_name)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "remove_country":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "Processing...")
                show_country_removal(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data.startswith("remove_country_"):
            if is_admin(user_id):
                country_name = data.split("_", 2)[2]
                result = remove_country(country_name, call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id, result, show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        else:
            bot.answer_callback_query(call.id, "❌ Unknown action", show_alert=True)
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Error occurred", show_alert=True)
            if is_admin(user_id):
                bot.send_message(call.message.chat.id, f"Callback handler error:\n{e}")
        except:
            pass

# ---------------------------------------------------------------------
# BULK ACCOUNT FUNCTIONS
# ---------------------------------------------------------------------

def handle_cancel_bulk(call):
    user_id = call.from_user.id
    
    if user_id in bulk_add_states:
        state = bulk_add_states[user_id]
        
        if state.get("current_client") and account_manager:
            try:
                asyncio.run(account_manager.pyrogram_manager.safe_disconnect(state["current_client"]))
            except:
                pass
        
        del bulk_add_states[user_id]
    
    edit_or_resend(
        call.message.chat.id,
        call.message.message_id,
        "❌ Bulk account addition cancelled.",
        markup=None
    )
    show_admin_panel(call.message.chat.id)

@bot.message_handler(func=lambda m: bulk_add_states.get(m.from_user.id, {}).get("step") == "waiting_numbers")
def handle_bulk_numbers_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    if state.get("step") != "waiting_numbers":
        return
    
    text = msg.text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    valid_numbers = []
    invalid_numbers = []
    
    for line in lines[:50]:
        if re.match(r'^\+\d{10,15}$', line):
            valid_numbers.append(line)
        else:
            invalid_numbers.append(line)
    
    if not valid_numbers:
        bot.send_message(
            msg.chat.id,
            "❌ No valid phone numbers found.\n"
            "Please enter numbers in format: +91XXXXXXXXXX\n"
            "One per line."
        )
        return
    
    state["phone_numbers"] = valid_numbers
    state["total_numbers"] = len(valid_numbers)
    state["step"] = "confirm_numbers"
    
    message = f"📦 **Bulk Account Addition**\n\n"
    message += f"🌍 Country: {state['country']}\n"
    message += f"📱 Total Numbers: {len(valid_numbers)}\n"
    
    if invalid_numbers:
        message += f"⚠️ Invalid (skipped): {len(invalid_numbers)}\n"
    
    message += f"\n**First 5 numbers:**\n"
    for i, num in enumerate(valid_numbers[:5], 1):
        message += f"{i}. `{num}`\n"
    
    if len(valid_numbers) > 5:
        message += f"... and {len(valid_numbers) - 5} more\n"
    
    message += f"\nClick below to start adding accounts:"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("▶️ Start Adding Accounts", callback_data="start_bulk_add"),
        InlineKeyboardButton("✏️ Edit Numbers", callback_data="edit_bulk_numbers")
    )
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk"))
    
    sent_msg = bot.send_message(msg.chat.id, message, parse_mode="Markdown", reply_markup=markup)
    state["message_id"] = sent_msg.message_id
    user_last_message[user_id] = sent_msg.message_id

def start_bulk_processing(user_id):
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    state["is_processing"] = True
    
    edit_or_resend(
        state["chat_id"],
        state["message_id"],
        f"🚀 **Bulk Processing Started**\n\n"
        f"🌍 Country: {state['country']}\n"
        f"📱 Total: {state['total_numbers']} numbers\n"
        f"⏳ Processing first number...",
        markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⏸️ Pause", callback_data="pause_bulk"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk")
        )
    )
    
    process_next_bulk_number(user_id)

def process_next_bulk_number(user_id):
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    
    if not state.get("is_processing", True):
        return
    
    if state["current_index"] >= state["total_numbers"]:
        show_bulk_summary(user_id)
        return
    
    phone_number = state["phone_numbers"][state["current_index"]]
    state["current_phone"] = phone_number
    state["password_attempts"] = 0
    
    progress = state["current_index"] + 1
    total = state["total_numbers"]
    percentage = (progress / total) * 100
    
    edit_or_resend(
        state["chat_id"],
        state["message_id"],
        f"🔄 **Processing Number {progress}/{total}**\n\n"
        f"📱 Phone: `{phone_number}`\n"
        f"📊 Progress: {progress}/{total} ({percentage:.1f}%)\n"
        f"✅ Success: {state['success_count']}\n"
        f"❌ Failed: {state['failed_count']}\n\n"
        f"⏳ Sending OTP...",
        markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⏸️ Pause", callback_data="pause_bulk"),
            InlineKeyboardButton("⏭️ Skip", callback_data="skip_bulk_number"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk")
        )
    )
    
    send_bulk_otp(user_id, phone_number)

def send_bulk_otp(user_id, phone_number):
    try:
        if not account_manager:
            bulk_number_failed(user_id, "Account module not loaded")
            return
        
        state = bulk_add_states[user_id]
        
        result = account_manager.bulk_send_code_sync(phone_number)
        
        if result.get("success"):
            state["current_client"] = result["client"]
            state["current_phone_code_hash"] = result["phone_code_hash"]
            state["current_manager"] = result["manager"]
            state["step"] = "waiting_bulk_otp"
            
            edit_or_resend(
                state["chat_id"],
                state["message_id"],
                f"📱 Phone: `{phone_number}`\n\n"
                f"✅ OTP sent!\n"
                f"Please enter the OTP received for this number:\n\n"
                f"_(Type 'skip' to skip this number)_",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⏭️ Skip This Number", callback_data="skip_bulk_number"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk")
                )
            )
        else:
            error_msg = result.get("error", "Unknown error")
            bulk_number_failed(user_id, f"Failed to send OTP: {error_msg}")
    
    except Exception as e:
        logger.error(f"Bulk send OTP error: {e}")
        bulk_number_failed(user_id, f"Error: {str(e)}")

def bulk_number_failed(user_id, reason):
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    state["failed_count"] += 1
    state["failed_numbers"].append({
        "number": state.get("current_phone", "Unknown"),
        "reason": reason
    })
    
    if state.get("current_client") and account_manager:
        try:
            asyncio.run(account_manager.pyrogram_manager.safe_disconnect(state["current_client"]))
        except:
            pass
    
    state["current_index"] += 1
    state["password_attempts"] = 0
    process_next_bulk_number(user_id)

def bulk_number_success(user_id):
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    state["success_count"] += 1
    
    if state.get("current_client") and account_manager:
        try:
            asyncio.run(account_manager.pyrogram_manager.safe_disconnect(state["current_client"]))
        except:
            pass
    
    state["current_index"] += 1
    state["password_attempts"] = 0
    process_next_bulk_number(user_id)

@bot.message_handler(func=lambda m: bulk_add_states.get(m.from_user.id, {}).get("step") == "waiting_bulk_otp")
def handle_bulk_otp_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    if state.get("step") != "waiting_bulk_otp":
        return
    
    otp_code = msg.text.strip()
    
    if otp_code.lower() == 'skip':
        bulk_number_failed(user_id, "Skipped by admin")
        return
    
    if not otp_code.isdigit() or len(otp_code) != 5:
        bot.send_message(
            msg.chat.id,
            "❌ Invalid OTP format. Please enter 5-digit OTP or type 'skip' to skip:"
        )
        return
    
    try:
        result = account_manager.bulk_verify_otp_sync(
            state["current_client"],
            state["current_phone"],
            state["current_phone_code_hash"],
            otp_code,
            state["current_manager"]
        )
        
        if result.get("success"):
            save_bulk_account(user_id)
        
        elif result.get("status") == "password_required":
            state["step"] = "waiting_bulk_password"
            state["password_attempts"] = 0
            
            edit_or_resend(
                state["chat_id"],
                state["message_id"],
                f"📱 Phone: `{state['current_phone']}`\n\n"
                f"🔐 2FA Password required!\n"
                f"Enter your 2-step verification password:\n\n"
                f"_(Type 'skip' to skip this number)_",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⏭️ Skip This Number", callback_data="skip_bulk_number"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk")
                )
            )
        
        else:
            error_msg = result.get("error", "OTP verification failed")
            bulk_number_failed(user_id, f"OTP error: {error_msg}")
    
    except Exception as e:
        logger.error(f"Bulk OTP verification error: {e}")
        bulk_number_failed(user_id, f"OTP error: {str(e)}")

@bot.message_handler(func=lambda m: bulk_add_states.get(m.from_user.id, {}).get("step") == "waiting_bulk_password")
def handle_bulk_password_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    if state.get("step") != "waiting_bulk_password":
        return
    
    password = msg.text.strip()
    
    if password.lower() == 'skip':
        bulk_number_failed(user_id, "Skipped by admin")
        return
    
    if not password:
        bot.send_message(
            msg.chat.id,
            "❌ Password cannot be empty. Enter 2FA password or type 'skip' to skip:"
        )
        return
    
    state["password_attempts"] = state.get("password_attempts", 0) + 1
    
    if state["password_attempts"] > 2:
        bulk_number_failed(user_id, "Max password attempts exceeded")
        return
    
    try:
        result = account_manager.bulk_verify_password_sync(
            state["current_client"],
            password,
            state["current_manager"]
        )
        
        if result.get("success"):
            save_bulk_account(user_id, password)
        else:
            error_msg = result.get("error", "Incorrect password")
            
            if state["password_attempts"] >= 2:
                bulk_number_failed(user_id, f"Password error: {error_msg}")
            else:
                attempts_left = 2 - state["password_attempts"]
                bot.send_message(
                    msg.chat.id,
                    f"❌ Incorrect password. {attempts_left} attempt(s) left.\n"
                    f"Enter password again or type 'skip' to skip:"
                )
    
    except Exception as e:
        logger.error(f"Bulk password verification error: {e}")
        bulk_number_failed(user_id, f"Password error: {str(e)}")

def save_bulk_account(user_id, password=None):
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    
    try:
        success, message = account_manager.bulk_save_account_sync(
            state["current_client"],
            state["current_phone"],
            state["country"],
            user_id,
            state["current_manager"],
            accounts_col,
            password
        )
        
        if success:
            progress = state["current_index"] + 1
            total = state["total_numbers"]
            
            edit_or_resend(
                state["chat_id"],
                state["message_id"],
                f"✅ **Number {progress}/{total} Added Successfully!**\n\n"
                f"📱 Phone: `{state['current_phone']}`\n"
                f"🌍 Country: {state['country']}\n"
                f"🔐 2FA: {'✅ Enabled' if password else '❌ Disabled'}\n\n"
                f"📊 Progress: {progress}/{total}\n"
                f"✅ Success: {state['success_count'] + 1}\n"
                f"❌ Failed: {state['failed_count']}\n\n"
                f"⏳ Moving to next number...",
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⏸️ Pause", callback_data="pause_bulk"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_bulk")
                )
            )
            
            bulk_number_success(user_id)
        
        else:
            bulk_number_failed(user_id, f"Save error: {message}")
    
    except Exception as e:
        logger.error(f"Bulk save account error: {e}")
        bulk_number_failed(user_id, f"Save error: {str(e)}")

def show_bulk_summary(user_id):
    if user_id not in bulk_add_states:
        return
    
    state = bulk_add_states[user_id]
    
    summary = f"📊 **Bulk Processing Complete!**\n\n"
    summary += f"🌍 Country: {state['country']}\n"
    summary += f"📱 Total Numbers: {state['total_numbers']}\n"
    summary += f"✅ Successfully Added: {state['success_count']}\n"
    summary += f"❌ Failed/Skipped: {state['failed_count']}\n\n"
    
    if state['failed_numbers']:
        summary += f"**Failed Numbers:**\n"
        for i, failed in enumerate(state['failed_numbers'][:10], 1):
            summary += f"{i}. {failed['number']} - {failed['reason']}\n"
        
        if len(state['failed_numbers']) > 10:
            summary += f"... and {len(state['failed_numbers']) - 10} more\n"
    
    summary += f"\n⏰ Completed at: {datetime.utcnow().strftime('%H:%M:%S')}"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚡ Admin Panel", callback_data="admin_panel"))
    
    edit_or_resend(
        state["chat_id"],
        state["message_id"],
        summary,
        markup=markup
    )
    
    del bulk_add_states[user_id]

# ---------------------------------------------------------------------
# EXISTING FUNCTIONS
# ---------------------------------------------------------------------

def handle_login_country_selection(call):
    user_id = call.from_user.id
    
    if user_id not in login_states:
        bot.answer_callback_query(call.id, "❌ Session expired", show_alert=True)
        return
    
    country_name = call.data.replace("login_country_", "")
    
    login_states[user_id]["country"] = country_name
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Single Account", callback_data=f"single_account_{country_name}"),
        InlineKeyboardButton("📦 Bulk Accounts", callback_data=f"bulk_account_{country_name}")
    )
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_login"))
    
    edit_or_resend(
        call.message.chat.id,
        call.message.message_id,
        f"🌍 Country: {country_name}\n\n"
        "📱 Select account adding mode:",
        markup=markup
    )

def handle_cancel_login(call):
    user_id = call.from_user.id
    
    if user_id in login_states:
        state = login_states[user_id]
        if "client" in state:
            try:
                if account_manager and account_manager.pyrogram_manager:
                    import asyncio
                    asyncio.run(account_manager.pyrogram_manager.safe_disconnect(state["client"]))
            except:
                pass
        login_states.pop(user_id, None)
    
    edit_or_resend(
        call.message.chat.id,
        call.message.message_id,
        "❌ Login cancelled.",
        markup=None
    )
    show_admin_panel(call.message.chat.id)

def handle_logout_session(user_id, session_id, chat_id, callback_id):
    try:
        if not account_manager:
            bot.answer_callback_query(callback_id, "❌ Account module not loaded", show_alert=True)
            return
        
        bot.answer_callback_query(callback_id, "🔄 Logging out...", show_alert=False)
        success, message = account_manager.logout_session_sync(
            session_id, user_id, otp_sessions_col, accounts_col, orders_col
        )
        
        if success:
            try:
                bot.delete_message(chat_id, callback_id.message.message_id)
            except:
                pass
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu"))
            
            sent_msg = bot.send_message(
                chat_id,
                "✅ **Logged Out Successfully!**\n\n"
                "You have been logged out from this session.\n"
                "Order marked as completed.\n\n"
                "Thank you for using our service!",
                reply_markup=markup
            )
            user_last_message[user_id] = sent_msg.message_id
        else:
            bot.answer_callback_query(callback_id, f"❌ {message}", show_alert=True)
    except Exception as e:
        logger.error(f"Logout handler error: {e}")
        bot.answer_callback_query(callback_id, "❌ Error logging out", show_alert=True)

def get_latest_otp(user_id, session_id, chat_id, callback_id):
    try:
        session_data = otp_sessions_col.find_one({"session_id": session_id})
        if not session_data:
            bot.answer_callback_query(callback_id, "❌ Session not found", show_alert=True)
            return
        
        # ALWAYS fetch fresh OTP, don't use cached
        bot.answer_callback_query(callback_id, "🔍 Searching for latest OTP...", show_alert=False)
        
        session_string = session_data.get("session_string")
        if not session_string:
            bot.answer_callback_query(callback_id, "❌ No session string found", show_alert=True)
            return
        
        # Always fetch new OTP
        otp_code = account_manager.get_latest_otp_sync(session_string)
        
        if not otp_code:
            bot.answer_callback_query(callback_id, "❌ No OTP received yet. Please wait...", show_alert=True)
            return
        
        # Update database with the new OTP
        otp_sessions_col.update_one(
            {"session_id": session_id},
            {"$set": {
                "has_otp": True,
                "last_otp": otp_code,
                "last_otp_time": datetime.utcnow(),
                "status": "otp_received"
            }}
        )
        
        try:
            from logs import log_otp_received_async
            order = orders_col.find_one({"session_id": session_id})
            if order:
                log_otp_received_async(
                    user_id=user_id,
                    phone=session_data.get('phone', 'N/A'),
                    otp_code=otp_code,
                    country=order.get('country', 'Unknown'),
                    price=order.get('price', 0)
                )
        except:
            pass
        
        account_id = session_data.get("account_id")
        account = None
        two_step_password = ""
        if account_id:
            try:
                account = accounts_col.find_one({"_id": ObjectId(account_id)})
                if account:
                    two_step_password = account.get("two_step_password", "")
            except:
                pass
        
        message = f"✅ **Latest OTP**\n\n"
        message += f"📱 Phone: `{session_data.get('phone', 'N/A')}`\n"
        message += f"🔢 OTP Code: `{otp_code}`\n"
        if two_step_password:
            message += f"🔐 2FA Password: `{two_step_password}`\n"
        elif account and account.get("two_step_password"):
            message += f"🔐 2FA Password: `{account.get('two_step_password')}`\n"
        message += f"\n⏰ Time: {datetime.utcnow().strftime('%H:%M:%S')}"
        message += f"\n\nEnter this code in Telegram X app."
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🔄 Get OTP Again", callback_data=f"get_otp_{session_id}"),
            InlineKeyboardButton("🚪 Logout", callback_data=f"logout_session_{session_id}")
        )
        
        try:
            bot.edit_message_text(
                message,
                chat_id,
                callback_id.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
        except:
            sent_msg = bot.send_message(
                chat_id,
                message,
                parse_mode="Markdown",
                reply_markup=markup
            )
            user_last_message[user_id] = sent_msg.message_id
        
        bot.answer_callback_query(callback_id, "✅ Latest OTP fetched!", show_alert=False)
    except Exception as e:
        logger.error(f"Get OTP error: {e}")
        bot.answer_callback_query(callback_id, "❌ Error getting OTP", show_alert=True)

# ---------------------------------------------------------------------
# COUPON MANAGEMENT FUNCTIONS
# ---------------------------------------------------------------------

def show_coupon_management(chat_id, message_id=None):
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    text = "🎟 **Coupon Management**\n\nChoose an option:"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Add Coupon", callback_data="admin_create_coupon"),
        InlineKeyboardButton("❌ Remove Coupon", callback_data="admin_remove_coupon")
    )
    markup.add(
        InlineKeyboardButton("📊 Coupon Status", callback_data="admin_coupon_status"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")
    )
    
    if message_id:
        edit_or_resend(
            chat_id,
            message_id,
            text,
            markup=markup,
            parse_mode="Markdown"
        )
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

# ---------------------------------------------------------------------
# COUPON MESSAGE HANDLERS
# ---------------------------------------------------------------------

@bot.message_handler(func=lambda m: user_stage.get(m.from_user.id) == "waiting_coupon")
def handle_coupon_input(msg):
    user_id = msg.from_user.id
    
    if user_stage.get(user_id) != "waiting_coupon":
        return
    
    coupon_code = msg.text.strip().upper()
    user_stage.pop(user_id, None)
    
    success, result = claim_coupon(coupon_code, user_id)
    
    if success:
        amount = result
        new_balance = get_balance(user_id)
        text = f"✅ **Coupon Redeemed Successfully!**\n\n"
        text += f"🎟 Coupon Code: `{coupon_code}`\n"
        text += f"💰 Amount Added: {format_currency(amount)}\n"
        text += f"💳 New Balance: {format_currency(new_balance)}\n\n"
        text += f"Thank you for using our service! 🎉"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu"))
        
        sent_msg = bot.send_message(
            msg.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=markup
        )
        user_last_message[user_id] = sent_msg.message_id
    else:
        error_msg = result
        if error_msg == "Coupon not found":
            response = "❌ **Invalid Coupon Code**\n\n"
            response += "The coupon code you entered does not exist.\n"
            response += "Please check the code and try again."
        elif error_msg == "Already claimed":
            response = "⚠️ **Coupon Already Claimed**\n\n"
            response += "You have already claimed this coupon code.\n"
            response += "Each coupon can only be claimed once per user."
        elif error_msg == "Fully claimed":
            response = "🚫 **Coupon Fully Claimed**\n\n"
            response += "This coupon has been claimed by all eligible users.\n"
            response += "No more claims are available."
        elif error_msg in ["removed", "expired"]:
            response = f"🚫 **Coupon {error_msg.capitalize()}**\n\n"
            response += "This coupon is no longer valid for redemption.\n"
            response += "It may have been removed or expired."
        else:
            response = f"❌ **Error:** {error_msg}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
        
        sent_msg = bot.send_message(
            msg.chat.id,
            response,
            parse_mode="Markdown",
            reply_markup=markup
        )
        user_last_message[user_id] = sent_msg.message_id

@bot.message_handler(func=lambda m: coupon_state.get(m.from_user.id, {}).get("step") == "ask_code")
def handle_coupon_code_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in coupon_state or coupon_state[user_id]["step"] != "ask_code":
        return
    
    if not is_admin(user_id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        coupon_state.pop(user_id, None)
        return
    
    code = msg.text.strip().upper()
    if not code:
        bot.send_message(msg.chat.id, "❌ Coupon code cannot be empty. Enter coupon code:")
        return
    
    existing = get_coupon(code)
    if existing:
        bot.send_message(
            msg.chat.id,
            f"❌ Coupon code `{code}` already exists.\n\nEnter a different coupon code:"
        )
        return
    
    coupon_state[user_id] = {
        "step": "ask_amount",
        "code": code
    }
    
    bot.send_message(
        msg.chat.id,
        f"🎟 Coupon Code: `{code}`\n\n"
        f"💰 Enter coupon amount (minimum ₹1):"
    )

@bot.message_handler(func=lambda m: coupon_state.get(m.from_user.id, {}).get("step") == "ask_amount")
def handle_coupon_amount_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in coupon_state or coupon_state[user_id]["step"] != "ask_amount":
        return
    
    if not is_admin(user_id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        coupon_state.pop(user_id, None)
        return
    
    try:
        amount = float(msg.text.strip())
        if amount < 1:
            bot.send_message(msg.chat.id, "❌ Amount must be at least ₹1. Enter amount:")
            return
        
        coupon_state[user_id] = {
            "step": "ask_max_users",
            "code": coupon_state[user_id]["code"],
            "amount": amount
        }
        
        bot.send_message(
            msg.chat.id,
            f"🎟 Coupon Code: `{coupon_state[user_id]['code']}`\n"
            f"💰 Amount: {format_currency(amount)}\n\n"
            f"👥 Enter number of users who can claim this coupon (minimum 1):"
        )
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Invalid amount. Enter numbers only (e.g., 100):")

@bot.message_handler(func=lambda m: coupon_state.get(m.from_user.id, {}).get("step") == "ask_max_users")
def handle_coupon_max_users_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in coupon_state or coupon_state[user_id]["step"] != "ask_max_users":
        return
    
    if not is_admin(user_id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        coupon_state.pop(user_id, None)
        return
    
    try:
        max_users = int(msg.text.strip())
        if max_users < 1:
            bot.send_message(msg.chat.id, "❌ Must be at least 1 user. Enter number:")
            return
        
        code = coupon_state[user_id]["code"]
        amount = coupon_state[user_id]["amount"]
        
        success, message = create_coupon(code, amount, max_users, user_id)
        
        if success:
            text = f"✅ **Coupon Created Successfully!**\n\n"
            text += f"🎟 Code: `{code}`\n"
            text += f"💰 Amount: {format_currency(amount)}\n"
            text += f"👥 Max Users: {max_users}\n\n"
            text += f"Coupon is now active and ready for users to redeem."
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🎟 Coupon Management", callback_data="admin_coupon_menu"))
            
            bot.send_message(
                msg.chat.id,
                text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(
                msg.chat.id,
                f"❌ Failed to create coupon: {message}\n\n"
                f"Try again or contact support."
            )
        
        coupon_state.pop(user_id, None)
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Invalid number. Enter whole numbers only (e.g., 100):")

@bot.message_handler(func=lambda m: coupon_state.get(m.from_user.id, {}).get("step") == "ask_remove_code")
def handle_coupon_remove_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in coupon_state or coupon_state[user_id]["step"] != "ask_remove_code":
        return
    
    if not is_admin(user_id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        coupon_state.pop(user_id, None)
        return
    
    code = msg.text.strip().upper()
    
    success, message = remove_coupon(code, user_id)
    
    if success:
        text = f"✅ **Coupon Removed Successfully!**\n\n"
        text += f"🎟 Code: `{code}`\n"
        text += f"🚫 Status: Removed\n\n"
        text += f"This coupon can no longer be claimed by users."
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎟 Coupon Management", callback_data="admin_coupon_menu"))
        
        bot.send_message(
            msg.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        if message == "Coupon not found":
            response = f"❌ **Coupon Not Found**\n\n"
            response += f"Coupon code `{code}` does not exist.\n"
            response += f"Please check the code and try again."
        else:
            response = f"❌ **Error:** {message}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎟 Coupon Management", callback_data="admin_coupon_menu"))
        
        bot.send_message(
            msg.chat.id,
            response,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    coupon_state.pop(user_id, None)

@bot.message_handler(func=lambda m: coupon_state.get(m.from_user.id, {}).get("step") == "ask_status_code")
def handle_coupon_status_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in coupon_state or coupon_state[user_id]["step"] != "ask_status_code":
        return
    
    if not is_admin(user_id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        coupon_state.pop(user_id, None)
        return
    
    code = msg.text.strip().upper()
    
    status = get_coupon_status(code)
    
    if not status:
        text = f"❌ **Coupon Not Found**\n\n"
        text += f"Coupon code `{code}` does not exist.\n"
        text += f"Please check the code and try again."
    else:
        status_text = status["status"].capitalize()
        if status["status"] == "active":
            status_text = "🟢 Active"
        elif status["status"] == "expired":
            status_text = "🔴 Expired"
        elif status["status"] == "removed":
            status_text = "⚫ Removed"
        
        text = f"📊 **Coupon Details**\n\n"
        text += f"🎟 Code: `{status['code']}`\n"
        text += f"💰 Amount: {format_currency(status['amount'])}\n"
        text += f"👥 Max Users: {status['max_users']}\n"
        text += f"✅ Claimed: {status['claimed']}\n"
        text += f"🔄 Remaining: {status['remaining']}\n"
        text += f"📊 Status: {status_text}\n"
        text += f"📅 Created: {status['created_at'].strftime('%Y-%m-%d %H:%M') if status['created_at'] else 'N/A'}\n"
        
        if status['claimed'] > 0:
            text += f"\n👤 Recent Users (first 10):\n"
            for i, uid in enumerate(status['claimed_users'][:10], 1):
                text += f"{i}. User ID: {uid}\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎟 Coupon Management", callback_data="admin_coupon_menu"))
    
    bot.send_message(
        msg.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=markup
    )
    
    coupon_state.pop(user_id, None)

# ---------------------------------------------------------------------
# RECHARGE METHODS FUNCTIONS - UPDATED WITH TOTAL AND TODAY RECHARGE
# ---------------------------------------------------------------------

def show_recharge_methods(chat_id, message_id, user_id):
    # Calculate total recharge and today's recharge for this user
    total_recharge = 0
    today_recharge = 0
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get all approved recharges for this user
    user_recharges = recharges_col.find({
        "user_id": user_id,
        "status": "approved"
    })
    
    for recharge in user_recharges:
        amount = float(recharge.get("amount", 0))
        total_recharge += amount
        
        # Check if recharge was done today
        recharge_date = recharge.get("created_at") or recharge.get("submitted_at")
        if recharge_date and recharge_date >= today_start:
            today_recharge += amount
    
    text = f"💳 **Recharge**\n\n"
    text += f"💰 **Total Recharge:** {format_currency(total_recharge)}\n"
    text += f"📅 **Today's Recharge:** {format_currency(today_recharge)}\n\n"
    text += f"⬇️ **Select Payment Method:**"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 UPI Payment", callback_data="recharge_upi", style="success")
    )
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_menu", style="primary"))
    
    edit_or_resend(
        chat_id,
        message_id,
        text,
        markup=markup,
        parse_mode="Markdown"
    )

# ---------------------------------------------------------------------
# PROCESS RECHARGE AMOUNT FUNCTION - FIXED DATABASE ISSUE
# ---------------------------------------------------------------------

def process_recharge_amount(msg):
    try:
        amount = float(msg.text)
        if amount < 1:
            bot.send_message(msg.chat.id, "❌ Minimum recharge is ₹1. Enter amount again:")
            bot.register_next_step_handler(msg, process_recharge_amount)
            return
        
        user_id = msg.from_user.id
        
        caption = f"""<blockquote>💳 <b>UPI Payment Details</b> 

💰 Amount: {format_currency(amount)}
📱 UPI ID: {UPI_ID}

📋 Instructions:
1. Scan QR code OR send {format_currency(amount)} to above UPI
2. After payment, click **Deposited ✅** button
3. Follow the steps to submit proof

</blockquote>"""
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ I've Paid — Confirm", callback_data="upi_deposited", style="success"))
        
        upi_payment_states[user_id] = {
            "amount": amount,
            "step": "qr_shown"
        }
        
        bot.send_photo(
            msg.chat.id,
            QR_IMAGE_URL,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Invalid amount. Enter numbers only:")
        bot.register_next_step_handler(msg, process_recharge_amount)

# FIXED UTR HANDLER - Now properly checks and stores in database
@bot.message_handler(func=lambda m: upi_payment_states.get(m.from_user.id, {}).get("step") == "waiting_utr")
def handle_utr_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in upi_payment_states or upi_payment_states[user_id]["step"] != "waiting_utr":
        return
    
    utr = msg.text.strip()
    
    if not utr.isdigit() or len(utr) != 12:
        bot.send_message(msg.chat.id, "❌ Invalid UTR. Please enter a valid 12-digit UTR number:")
        return
    
    # Store UTR and move to screenshot step
    upi_payment_states[user_id]["utr"] = utr
    upi_payment_states[user_id]["step"] = "waiting_screenshot"
    
    bot.send_message(
        msg.chat.id,
        "✅ UTR Received!\n\n"
        "📸 Step 2: Send Screenshot\n\n"
        "Now please send the payment screenshot from your bank app:\n"
        "_(Make sure screenshot shows amount, date, and UTR)_"
    )

# FIXED SCREENSHOT HANDLER - Now properly saves to database
@bot.message_handler(content_types=['photo'], func=lambda m: upi_payment_states.get(m.from_user.id, {}).get("step") == "waiting_screenshot")
def handle_screenshot_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in upi_payment_states or upi_payment_states[user_id]["step"] != "waiting_screenshot":
        return
    
    try:
        screenshot_file_id = msg.photo[-1].file_id
        
        amount = upi_payment_states[user_id]["amount"]
        utr = upi_payment_states[user_id].get("utr", "")
        
        # Generate unique request ID
        req_id = f"R{int(time.time())}{user_id}"
        
        # Save to database with proper fields
        recharge_data = {
            "user_id": user_id,
            "amount": amount,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "method": "upi",
            "utr": utr,
            "screenshot": screenshot_file_id,
            "submitted_at": datetime.utcnow(),
            "req_id": req_id
        }
        
        recharge_id = recharges_col.insert_one(recharge_data).inserted_id
        
        # Update with req_id
        recharges_col.update_one(
            {"_id": ObjectId(recharge_id)},
            {"$set": {"req_id": req_id}}
        )
        
        # Get all admins to send notification
        all_admins = get_all_admins()
        
        admin_caption = f"""📋 **UPI Payment Request** 

👤 User: {user_id}
💰 Amount: {format_currency(amount)}
🔢 UTR: {utr}
📅 Submitted: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}
🆔 Request ID: {req_id}

✅ Both UTR and Screenshot received."""

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_rech|{req_id}", style="success"),
            InlineKeyboardButton("❌ Reject", callback_data=f"cancel_rech|{req_id}", style="danger")
        )
        
        # Send to all admins
        for admin in all_admins:
            admin_user_id = admin["user_id"]
            try:
                bot.send_photo(
                    admin_user_id,
                    screenshot_file_id,
                    caption=admin_caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except Exception as e:
                logger.error(f"Failed to send recharge notification to admin {admin_user_id}: {e}")
        
        bot.send_message(
            msg.chat.id,
            f"✅ **Payment Proof Submitted Successfully!**\n\n"
            f"📋 **Details:**\n"
            f"💰 Amount: {format_currency(amount)}\n"
            f"🔢 UTR: {utr}\n"
            f"📸 Screenshot: ✅ Received\n\n"
            f"⏳ **Status:** Admin verification pending\n"
            f"🆔 Request ID: `{req_id}`\n\n"
            f"Admin will review and approve soon. Thank you! 🎉"
        )
        
        # Clear state after successful submission
        upi_payment_states.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Screenshot handler error: {e}")
        bot.send_message(msg.chat.id, f"❌ Error submitting payment: {str(e)}")

# =============================================================
# RECEIVER ID INPUT HANDLER - FIXED NAME DISPLAY
# =============================================================

@bot.message_handler(func=lambda m: user_stage.get(m.from_user.id) == "waiting_receiver_id")
def handle_receiver_id(msg):
    user_id = msg.from_user.id
    
    if user_stage.get(user_id) != "waiting_receiver_id":
        return
    
    try:
        receiver_id = int(msg.text.strip())
        
        # Check if receiver exists in database
        receiver = users_col.find_one({"user_id": receiver_id})
        if not receiver:
            bot.send_message(
                msg.chat.id,
                f"❌ User ID `{receiver_id}` not found in database!\n\nPlease enter a valid User ID:",
                parse_mode="Markdown"
            )
            return
        
        # Get receiver's name - properly formatted
        receiver_name = receiver.get("name", "Unknown")
        receiver_username = receiver.get("username", "")
        
        if receiver_username:
            receiver_display = f"{receiver_name} (@{receiver_username})"
        else:
            receiver_display = receiver_name
        
        # Store receiver info in user_states
        user_states[user_id] = {
            "receiver_id": receiver_id,
            "receiver_name": receiver_display
        }
        
        # Move to amount input
        user_stage[user_id] = "waiting_transfer_amount"
        
        balance = get_balance(user_id)
        
        message = f"📤 **Send Balance - Step 2/2**\n\n"
        message += f"👤 Receiver: {receiver_display}\n"
        message += f"🆔 Receiver ID: `{receiver_id}`\n"
        message += f"💰 Your Balance: {format_currency(balance)}\n\n"
        message += f"Please enter the **Amount** to send:"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="send_balance_menu"))
        
        bot.send_message(
            msg.chat.id,
            message,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    except ValueError:
        bot.send_message(
            msg.chat.id,
            "❌ Invalid User ID! Please enter a numeric ID only:\nExample: `123456789`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Receiver ID error: {e}")
        bot.send_message(msg.chat.id, f"❌ Error: {str(e)}")

# =============================================================
# TRANSFER AMOUNT INPUT HANDLER
# =============================================================

@bot.message_handler(func=lambda m: user_stage.get(m.from_user.id) == "waiting_transfer_amount")
def handle_transfer_amount(msg):
    user_id = msg.from_user.id
    
    if user_stage.get(user_id) != "waiting_transfer_amount":
        return
    
    try:
        amount = float(msg.text.strip())
        
        # Get stored data
        transfer_data = user_states.get(user_id, {})
        receiver_id = transfer_data.get("receiver_id")
        receiver_name = transfer_data.get("receiver_name", f"ID: {receiver_id}")
        
        if not receiver_id:
            bot.send_message(msg.chat.id, "❌ Session expired! Please start again.")
            user_stage.pop(user_id, None)
            user_states.pop(user_id, None)
            return
        
        # Validate amount
        if amount <= 0:
            bot.send_message(msg.chat.id, "❌ Amount must be greater than 0!\nPlease enter valid amount:")
            return
        
        sender_balance = get_balance(user_id)
        if amount > sender_balance:
            bot.send_message(
                msg.chat.id, 
                f"❌ Insufficient balance! You have {format_currency(sender_balance)}\nPlease enter smaller amount:"
            )
            return
        
        # Update transfer data with amount
        transfer_data["amount"] = amount
        user_states[user_id] = transfer_data
        
        # Show confirmation
        confirm_message = f"📤 **Confirm Transfer**\n\n"
        confirm_message += f"👤 Receiver: {receiver_name}\n"
        confirm_message += f"🆔 Receiver ID: `{receiver_id}`\n"
        confirm_message += f"💰 Amount to Send: {format_currency(amount)}\n"
        confirm_message += f"💳 Your Balance: {format_currency(sender_balance)}\n"
        confirm_message += f"💳 Balance After: {format_currency(sender_balance - amount)}\n\n"
        confirm_message += f"Are you sure you want to proceed?"
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Confirm Transfer", callback_data="transfer_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="balance")
        )
        
        bot.send_message(
            msg.chat.id,
            confirm_message,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        user_stage.pop(user_id, None)
        
    except ValueError:
        bot.send_message(
            msg.chat.id,
            "❌ Invalid amount! Please enter numbers only:\nExample: `100`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Transfer amount error: {e}")
        bot.send_message(msg.chat.id, f"❌ Error: {str(e)}")

# ---------------------------------------------------------------------
# EDIT PRICE FUNCTIONS
# ---------------------------------------------------------------------

def show_edit_price_country_selection(chat_id, message_id=None):
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    countries = get_all_countries()
    if not countries:
        text = "❌ No countries available to edit."
        if message_id:
            edit_or_resend(
                chat_id,
                message_id,
                text,
                markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Back", callback_data="manage_countries")
                )
            )
        else:
            bot.send_message(chat_id, text)
        return
    
    text = "✏️ **Edit Country Price**\n\nSelect a country to edit its price:"
    markup = InlineKeyboardMarkup(row_width=2)
    for country in countries:
        markup.add(InlineKeyboardButton(
            f"{country['name']} - {format_currency(country['price'])}",
            callback_data=f"edit_price_country_{country['name']}"
        ))
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="manage_countries"))
    
    if message_id:
        edit_or_resend(
            chat_id,
            message_id,
            text,
            markup=markup,
            parse_mode="Markdown"
        )
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def show_edit_price_details(chat_id, message_id, country_name):
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    country = get_country_by_name(country_name)
    if not country:
        edit_or_resend(
            chat_id,
            message_id,
            f"❌ Country '{country_name}' not found.",
            markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Back", callback_data="edit_price")
            )
        )
        return
    
    text = f"✏️ **Edit Price for {country_name}**\n\n"
    text += f"🌍 Country: {country_name}\n"
    text += f"💰 Current Price: {format_currency(country['price'])}\n"
    text += f"📊 Available Accounts: {get_available_accounts_count(country_name)}\n\n"
    text += f"Click below to edit the price:"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        "✏️ Edit Price",
        callback_data=f"edit_price_confirm_{country_name}"
    ))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_edit_price"))
    
    edit_or_resend(
        chat_id,
        message_id,
        text,
        markup=markup,
        parse_mode="Markdown"
    )

# ---------------------------------------------------------------------
# MESSAGE HANDLER FOR LOGIN FLOW
# ---------------------------------------------------------------------

@bot.message_handler(func=lambda m: login_states.get(m.from_user.id, {}).get("step") in ["phone", "waiting_otp", "waiting_password"])
def handle_login_flow_messages(msg):
    user_id = msg.from_user.id
    
    if user_id not in login_states:
        return
    
    state = login_states[user_id]
    step = state["step"]
    chat_id = state["chat_id"]
    message_id = state["message_id"]
    
    if step == "phone":
        phone = msg.text.strip()
        if not re.match(r'^\+\d{10,15}$', phone):
            bot.send_message(chat_id, "❌ Invalid phone number format. Please enter with country code:\nExample: +919876543210")
            return
        
        if not account_manager:
            try:
                bot.edit_message_text(
                    "❌ Account module not loaded. Please contact admin.",
                    chat_id, message_id
                )
            except:
                pass
            login_states.pop(user_id, None)
            return
        
        try:
            success, message = account_manager.pyrogram_login_flow_sync(
                login_states, accounts_col, user_id, phone, chat_id, message_id, state["country"]
            )
            
            if success:
                try:
                    bot.edit_message_text(
                        f"📱 Phone: {phone}\n\n"
                        "📩 OTP sent! Enter the OTP you received:",
                        chat_id, message_id,
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")
                        )
                    )
                except:
                    pass
            else:
                try:
                    bot.edit_message_text(
                        f"❌ Failed to send OTP: {message}\n\nPlease try again.",
                        chat_id, message_id
                    )
                except:
                    pass
                login_states.pop(user_id, None)
        
        except Exception as e:
            logger.error(f"Login flow error: {e}")
            try:
                bot.edit_message_text(
                    f"❌ Error: {str(e)}\n\nPlease try again.",
                    chat_id, message_id
                )
            except:
                pass
            login_states.pop(user_id, None)
    
    elif step == "waiting_otp":
        otp = msg.text.strip()
        if not otp.isdigit() or len(otp) != 5:
            bot.send_message(chat_id, "❌ Invalid OTP format. Please enter 5-digit OTP:")
            return
        
        if not account_manager:
            try:
                bot.edit_message_text(
                    "❌ Account module not loaded. Please contact admin.",
                    chat_id, message_id
                )
            except:
                pass
            login_states.pop(user_id, None)
            return
        
        try:
            success, message = account_manager.verify_otp_and_save_sync(
                login_states, accounts_col, user_id, otp
            )
            
            if success:
                country = state["country"]
                phone = state["phone"]
                try:
                    bot.edit_message_text(
                        f"✅ **Account Added Successfully!**\n\n"
                        f"🌍 Country: {country}\n"
                        f"📱 Phone: {phone}\n"
                        f"🔐 Session: Generated\n\n"
                        f"Account is now available for purchase!",
                        chat_id, message_id
                    )
                except:
                    pass
                login_states.pop(user_id, None)
            
            elif message == "password_required":
                try:
                    bot.edit_message_text(
                        f"📱 Phone: {state['phone']}\n\n"
                        "🔐 2FA Password required!\n"
                        "Enter your 2-step verification password:",
                        chat_id, message_id,
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")
                        )
                    )
                except:
                    pass
            
            else:
                try:
                    bot.edit_message_text(
                        f"❌ OTP verification failed: {message}\n\nPlease try again.",
                        chat_id, message_id
                    )
                except:
                    pass
                login_states.pop(user_id, None)
        
        except Exception as e:
            logger.error(f"OTP verification error: {e}")
            try:
                bot.edit_message_text(
                    f"❌ Error: {str(e)}\n\nPlease try again.",
                    chat_id, message_id
                )
            except:
                pass
            login_states.pop(user_id, None)
    
    elif step == "waiting_password":
        password = msg.text.strip()
        if not password:
            bot.send_message(chat_id, "❌ Password cannot be empty. Enter 2FA password:")
            return
        
        if not account_manager:
            try:
                bot.edit_message_text(
                    "❌ Account module not loaded. Please contact admin.",
                    chat_id, message_id
                )
            except:
                pass
            login_states.pop(user_id, None)
            return
        
        try:
            success, message = account_manager.verify_2fa_password_sync(
                login_states, accounts_col, user_id, password
            )
            
            if success:
                country = state["country"]
                phone = state["phone"]
                try:
                    bot.edit_message_text(
                        f"✅ **Account Added Successfully!**\n\n"
                        f"🌍 Country: {country}\n"
                        f"📱 Phone: {phone}\n"
                        f"🔐 2FA: Enabled\n"
                        f"🔐 Session: Generated\n\n"
                        f"Account is now available for purchase!",
                        chat_id, message_id
                    )
                except:
                    pass
                login_states.pop(user_id, None)
            
            else:
                try:
                    bot.edit_message_text(
                        f"❌ 2FA password failed: {message}\n\nPlease try again.",
                        chat_id, message_id
                    )
                except:
                    pass
                login_states.pop(user_id, None)
        
        except Exception as e:
            logger.error(f"2FA verification error: {e}")
            try:
                bot.edit_message_text(
                    f"❌ Error: {str(e)}\n\nPlease try again.",
                    chat_id, message_id
                )
            except:
                pass
            login_states.pop(user_id, None)

# ---------------------------------------------------------------------
# EDIT PRICE MESSAGE HANDLER
# ---------------------------------------------------------------------

@bot.message_handler(func=lambda m: edit_price_state.get(m.from_user.id, {}).get("step") == "waiting_price")
def handle_edit_price_input(msg):
    user_id = msg.from_user.id
    
    if user_id not in edit_price_state or edit_price_state[user_id]["step"] != "waiting_price":
        return
    
    if not is_admin(user_id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        edit_price_state.pop(user_id, None)
        return
    
    try:
        new_price = float(msg.text.strip())
        if new_price <= 0:
            bot.send_message(msg.chat.id, "❌ Price must be greater than 0. Enter valid price:")
            return
        
        country_name = edit_price_state[user_id]["country"]
        
        result = countries_col.update_one(
            {"name": country_name, "status": "active"},
            {"$set": {"price": new_price, "updated_at": datetime.utcnow(), "updated_by": user_id}}
        )
        
        if result.modified_count > 0:
            bot.send_message(
                msg.chat.id,
                f"✅ Price updated successfully!\n\n"
                f"🌍 Country: {country_name}\n"
                f"💰 New Price: {format_currency(new_price)}\n\n"
                f"Price has been updated for all users."
            )
        else:
            bot.send_message(
                msg.chat.id,
                f"❌ Failed to update price. Country '{country_name}' not found or already has same price."
            )
        
        edit_price_state.pop(user_id, None)
        show_country_management(msg.chat.id)
    
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Invalid price format. Enter numbers only (e.g., 99.99):")

# ---------------------------------------------------------------------
# REFERRAL SYSTEM FUNCTIONS
# ---------------------------------------------------------------------

def show_referral_info(user_id, chat_id):
    user_data = users_col.find_one({"user_id": user_id}) or {}
    referral_code = user_data.get('referral_code', f'REF{user_id}')
    total_commission = user_data.get('total_commission_earned', 0)
    total_referrals = user_data.get('total_referrals', 0)
    
    referral_link = f"https://t.me/{bot.get_me().username}?start={referral_code}"
    
    message = f"👥 **Refer & Earn {REFERRAL_COMMISSION}% Commission!**\n\n"
    message += f"📊 **Your Stats:**\n"
    message += f"• Total Referrals: {total_referrals}\n"
    message += f"• Total Commission Earned: {format_currency(total_commission)}\n"
    message += f"• Commission Rate: {REFERRAL_COMMISSION}% per recharge\n\n"
    message += f"🔗 **Your Referral Link:**\n`{referral_link}`\n\n"
    message += f"📝 **How it works:**\n"
    message += f"1. Share your referral link with friends\n"
    message += f"2. When they join using your link\n"
    message += f"3. You earn {REFERRAL_COMMISSION}% of EVERY recharge they make!\n"
    message += f"4. Commission credited instantly\n\n"
    message += f"💰 **Example:** If a friend recharges ₹1000, you earn ₹{1000 * REFERRAL_COMMISSION / 100}!\n\n"
    message += f"Start sharing and earning today! 🎉"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={referral_link}&text=Join%20GMS%20OTP%20Bot%20%E2%80%94%20Fast%2C%20Reliable%20Telegram%20Account%20Buying!", style="success"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_menu", style="primary"))
    
    sent_msg = bot.send_message(chat_id, message, parse_mode="Markdown", reply_markup=markup)
    user_last_message[user_id] = sent_msg.message_id

# ---------------------------------------------------------------------
# ADMIN MANAGEMENT FUNCTIONS
# ---------------------------------------------------------------------

def show_admin_panel(chat_id):
    user_id = chat_id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    total_accounts = accounts_col.count_documents({})
    active_accounts = accounts_col.count_documents({"status": "active", "used": False})
    total_users = users_col.count_documents({})
    total_orders = orders_col.count_documents({})
    banned_users = banned_users_col.count_documents({"status": "active"})
    active_countries = countries_col.count_documents({"status": "active"})
    total_admins = get_admin_count()
    
    text = (
        f"⚡ **GMS Admin Panel**\n\n"
        f"📊 **Statistics:**\n"
        f"• 📦 Total Accounts: {total_accounts}\n"
        f"• ✅ Active Accounts: {active_accounts}\n"
        f"• 👥 Total Users: {total_users}\n"
        f"• 🛒 Total Orders: {total_orders}\n"
        f"• 🔒 Banned Users: {banned_users}\n"
        f"• 🌍 Active Countries: {active_countries}\n"
        f"• 👑 Total Admins: {total_admins}/6\n\n"
        f"🛠️ **Management Tools:**"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📲 Add Account", callback_data="add_account", style="success"),
        InlineKeyboardButton("📣 Broadcast", callback_data="broadcast_menu", style="primary")
    )
    markup.add(
        InlineKeyboardButton("🔄 Refund", callback_data="refund_start", style="primary"),
        InlineKeyboardButton("🏆 Ranking", callback_data="ranking", style="primary")
    )
    markup.add(
        InlineKeyboardButton("📨 Message User", callback_data="message_user", style="primary"),
        InlineKeyboardButton("➖ Deduct Balance", callback_data="admin_deduct_start", style="danger")
    )
    markup.add(
        InlineKeyboardButton("🔒 Ban User", callback_data="ban_user", style="danger"),
        InlineKeyboardButton("🔓 Unban User", callback_data="unban_user", style="success")
    )
    markup.add(
        InlineKeyboardButton("🗺️ Countries", callback_data="manage_countries", style="primary"),
        InlineKeyboardButton("🎫 Coupons", callback_data="admin_coupon_menu", style="success")
    )
    
    # Show admin list for main admin
    if is_super_admin(user_id):
        admins = get_all_admins()
        admin_text = "\n\n👥 **Current Admins:**\n"
        for admin in admins:
            if admin.get("is_super_admin", False):
                admin_text += f"👑 Main: `{admin['user_id']}`\n"
            else:
                admin_text += f"👤 Admin: `{admin['user_id']}`\n"
        text += admin_text
    
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    user_last_message[user_id] = sent_msg.message_id

def show_country_management(chat_id):
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    countries = get_all_countries()
    if not countries:
        text = "🌍 **Country Management**\n\nNo countries available. Add a country first."
    else:
        text = "🌍 **Country Management**\n\n**Available Countries:**\n"
        for country in countries:
            accounts_count = get_available_accounts_count(country['name'])
            text += f"• {country['name']} - Price: {format_currency(country['price'])} - Accounts: {accounts_count}\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🌐 Add Country", callback_data="add_country", style="success"),
        InlineKeyboardButton("💱 Edit Price", callback_data="edit_price", style="primary")
    )
    markup.add(
        InlineKeyboardButton("🗑️ Remove Country", callback_data="remove_country", style="danger")
    )
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel", style="primary"))
    
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    user_last_message[chat_id] = sent_msg.message_id

def ask_country_name(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    country_name = message.text.strip()
    user_states[message.chat.id] = {
        "step": "ask_country_price",
        "country_name": country_name
    }
    bot.send_message(message.chat.id, f"💰 Enter price for {country_name}:")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "ask_country_price")
def ask_country_price(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    try:
        price = float(message.text.strip())
        user_data = user_states.get(message.chat.id)
        country_name = user_data.get("country_name")
        
        country_data = {
            "name": country_name,
            "price": price,
            "status": "active",
            "created_at": datetime.utcnow(),
            "created_by": message.from_user.id
        }
        countries_col.insert_one(country_data)
        
        del user_states[message.chat.id]
        bot.send_message(
            message.chat.id,
            f"✅ **Country Added Successfully!**\n\n"
            f"🌍 Country: {country_name}\n"
            f"💰 Price: {format_currency(price)}\n\n"
            f"Country is now available for users to purchase accounts."
        )
        show_country_management(message.chat.id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid price. Please enter a number:")

def show_country_removal(chat_id):
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    countries = get_all_countries()
    if not countries:
        bot.send_message(chat_id, "❌ No countries available to remove.")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for country in countries:
        markup.add(InlineKeyboardButton(
            f"❌ {country['name']}",
            callback_data=f"remove_country_{country['name']}"
        ))
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="manage_countries"))
    
    sent_msg = bot.send_message(
        chat_id,
        "🗑️ **Remove Country**\n\nSelect a country to remove:",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    user_last_message[chat_id] = sent_msg.message_id

def remove_country(country_name, chat_id, message_id=None):
    if not is_admin(chat_id):
        return "❌ Unauthorized access"
    
    try:
        result = countries_col.update_one(
            {"name": country_name, "status": "active"},
            {"$set": {"status": "inactive", "removed_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            accounts_col.delete_many({"country": country_name})
            
            if message_id:
                try:
                    bot.delete_message(chat_id, message_id)
                except:
                    pass
            
            bot.send_message(chat_id, f"✅ Country '{country_name}' and all its accounts have been removed.")
            show_country_management(chat_id)
            return f"✅ {country_name} removed successfully"
        else:
            return f"❌ Country '{country_name}' not found or already removed"
    except Exception as e:
        logger.error(f"Error removing country: {e}")
        return f"❌ Error removing country: {str(e)}"

def ask_ban_user(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    try:
        user_id_to_ban = int(message.text.strip())
        
        user = users_col.find_one({"user_id": user_id_to_ban})
        if not user:
            bot.send_message(message.chat.id, "❌ User not found in database.")
            return
        
        already_banned = banned_users_col.find_one({"user_id": user_id_to_ban, "status": "active"})
        if already_banned:
            bot.send_message(message.chat.id, "⚠️ User is already banned.")
            return
        
        ban_record = {
            "user_id": user_id_to_ban,
            "banned_by": message.from_user.id,
            "reason": "Admin banned",
            "status": "active",
            "banned_at": datetime.utcnow()
        }
        banned_users_col.insert_one(ban_record)
        
        bot.send_message(message.chat.id, f"✅ User {user_id_to_ban} has been banned.")
        
        try:
            bot.send_message(
                user_id_to_ban,
                "🚫 **Your Account Has Been Banned**\n\n"
                "You have been banned from using this bot.\n"
                "Contact admin @DHRUV_PAPAHERE if you believe this is a mistake."
            )
        except:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Please enter numeric ID only.")

def ask_unban_user(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    try:
        user_id_to_unban = int(message.text.strip())
        
        ban_record = banned_users_col.find_one({"user_id": user_id_to_unban, "status": "active"})
        if not ban_record:
            bot.send_message(message.chat.id, "⚠️ User is not banned.")
            return
        
        banned_users_col.update_one(
            {"user_id": user_id_to_unban, "status": "active"},
            {"$set": {"status": "unbanned", "unbanned_at": datetime.utcnow(), "unbanned_by": message.from_user.id}}
        )
        
        bot.send_message(message.chat.id, f"✅ User {user_id_to_unban} has been unbanned.")
        
        try:
            bot.send_message(
                user_id_to_unban,
                "✅ **Your Account Has Been Unbanned**\n\n"
                "Your account access has been restored.\n"
                "You can now use the bot normally."
            )
        except:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Please enter numeric ID only.")

def show_user_ranking(chat_id):
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    try:
        users_ranking = []
        all_wallets = wallets_col.find()
        
        for wallet in all_wallets:
            user_id_rank = wallet.get("user_id")
            balance = float(wallet.get("balance", 0))
            
            if balance > 0:
                user = users_col.find_one({"user_id": user_id_rank}) or {}
                name = user.get("name", "Unknown")
                username_db = user.get("username")
                users_ranking.append({
                    "user_id": user_id_rank,
                    "balance": balance,
                    "name": name,
                    "username": username_db
                })
        
        users_ranking.sort(key=lambda x: x["balance"], reverse=True)
        
        ranking_text = "📊 **User Ranking by Wallet Balance**\n\n"
        if not users_ranking:
            ranking_text = "📊 No users found with balance greater than zero."
        else:
            for index, user_data in enumerate(users_ranking[:20], 1):
                user_link = f"<a href='tg://user?id={user_data['user_id']}'>{user_data['user_id']}</a>"
                username_display = f"@{user_data['username']}" if user_data['username'] else "No Username"
                ranking_text += f"{index}. {user_link} - {username_display}\n"
                ranking_text += f" 💰 Balance: {format_currency(user_data['balance'])}\n\n"
        
        bot.send_message(chat_id, ranking_text, parse_mode="HTML")
    except Exception as e:
        logger.exception("Error in ranking:")
        bot.send_message(chat_id, f"❌ Error generating ranking: {str(e)}")

# ---------------------------------------------------------------------
# BROADCAST FUNCTION - PERFECT FORWARD (PURE TELEBOT)
# ---------------------------------------------------------------------

@bot.message_handler(commands=['sendbroadcast'])
def handle_sendbroadcast_command(msg):
    """Handle /sendbroadcast command - EXACT FORWARD"""
    global IS_BROADCASTING
    
    if not is_admin(msg.from_user.id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        return
    
    if IS_BROADCASTING:
        bot.send_message(msg.chat.id, "⚠️ Another broadcast is already in progress. Please wait...")
        return
    
    if not msg.reply_to_message:
        bot.send_message(
            msg.chat.id,
            "❌ Please reply to a message with /sendbroadcast\n\n"
            "📝 **Options:**\n"
            "• `/sendbroadcast` - Normal broadcast\n"
            "• `/sendbroadcast -pin` - Auto-pin (silent)\n"
            "• `/sendbroadcast -pinloud` - Auto-pin (with notification)\n"
            "• `/sendbroadcast -user` - Also send to users\n"
            "• `/sendbroadcast -pin -user` - Combine options",
            parse_mode="Markdown"
        )
        return
    
    # Parse options
    cmd_text = msg.text.lower()
    pin_silent = '-pin' in cmd_text and '-pinloud' not in cmd_text
    pin_loud = '-pinloud' in cmd_text
    send_to_users = '-user' in cmd_text
    
    source = msg.reply_to_message
    
    # Send confirmation
    status_msg = bot.send_message(
        msg.chat.id,
        f"📡 **Broadcast Started**\n\n"
        f"📨 Forwarding EXACT message...\n"
        f"👥 Groups: Yes\n"
        f"👤 Users: {'Yes' if send_to_users else 'No'}\n"
        f"📌 Pin: {'🔊 Loud' if pin_loud else '🔇 Silent' if pin_silent else '❌ No'}\n\n"
        f"⏳ Processing...",
        parse_mode="Markdown"
    )
    
    IS_BROADCASTING = True
    
    # Start broadcast thread
    threading.Thread(
        target=broadcast_worker,
        args=(
            source,
            pin_silent,
            pin_loud,
            send_to_users,
            msg.chat.id,
            status_msg.message_id,
            msg.from_user.id
        ),
        daemon=True
    ).start()

def broadcast_worker(source_msg, pin_silent, pin_loud, send_to_users, admin_chat_id, status_msg_id, admin_id):
    """Broadcast worker - EXACT FORWARD to all groups and users"""
    global IS_BROADCASTING
    
    try:
        # Get all unique chat IDs from database
        all_chats = []
        chat_ids = set()
        
        # 1. Get all users (negative IDs are groups)
        all_users = list(users_col.find())
        for user in all_users:
            uid = user.get("user_id")
            if uid and uid != ADMIN_ID and uid != admin_id:
                chat_ids.add(uid)
        
        # 2. Get all served chats if collection exists
        try:
            if 'served_chats' in db.list_collection_names():
                served = db['served_chats'].find()
                for chat in served:
                    cid = chat.get("chat_id")
                    if cid:
                        chat_ids.add(cid)
        except:
            pass
        
        all_chats = list(chat_ids)
        
        # Separate groups and users
        groups = [cid for cid in all_chats if str(cid).startswith('-')]
        users = [cid for cid in all_chats if not str(cid).startswith('-') and cid != ADMIN_ID and cid != admin_id]
        
        # Update status
        bot.edit_message_text(
            f"📡 **Broadcasting to Groups...**\n\n"
            f"👥 Total Groups: {len(groups)}",
            admin_chat_id,
            status_msg_id,
            parse_mode="Markdown"
        )
        
        # ----- BROADCAST TO GROUPS -----
        groups_sent = 0
        groups_pinned = 0
        groups_failed = 0
        
        for chat_id in groups:
            try:
                # EXACT FORWARD - Telegram API ka original forward
                forwarded_msg = bot.forward_message(
                    chat_id,
                    source_msg.chat.id,
                    source_msg.message_id
                )
                groups_sent += 1
                
                # Pin if option enabled
                if pin_silent or pin_loud:
                    try:
                        bot.pin_chat_message(
                            chat_id,
                            forwarded_msg.message_id,
                            disable_notification=(not pin_loud)
                        )
                        groups_pinned += 1
                    except:
                        pass
                
                # Update progress every 10 messages
                if groups_sent % 10 == 0:
                    bot.edit_message_text(
                        f"📡 **Broadcasting...**\n\n"
                        f"👥 Groups: {groups_sent}/{len(groups)} sent\n"
                        f"📌 Pinned: {groups_pinned}",
                        admin_chat_id,
                        status_msg_id,
                        parse_mode="Markdown"
                    )
                
                time.sleep(0.25)  # Anti-flood
                
            except Exception as e:
                groups_failed += 1
                logger.error(f"Group broadcast failed for {chat_id}: {e}")
                continue
        
        # ----- BROADCAST TO USERS (if option enabled) -----
        users_sent = 0
        users_failed = 0
        
        if send_to_users and users:
            bot.edit_message_text(
                f"📡 **Groups Done: {groups_sent} sent**\n\n"
                f"👤 Now broadcasting to users...\n"
                f"👥 Total Users: {len(users)}",
                admin_chat_id,
                status_msg_id,
                parse_mode="Markdown"
            )
            
            for user_id in users:
                try:
                    # EXACT FORWARD to users
                    bot.forward_message(
                        user_id,
                        source_msg.chat.id,
                        source_msg.message_id
                    )
                    users_sent += 1
                    
                    # Update progress every 20 users
                    if users_sent % 20 == 0:
                        bot.edit_message_text(
                            f"📡 **Broadcasting to Users...**\n\n"
                            f"👤 Users: {users_sent}/{len(users)} sent",
                            admin_chat_id,
                            status_msg_id,
                            parse_mode="Markdown"
                        )
                    
                    time.sleep(0.2)  # Anti-flood
                    
                except Exception as e:
                    users_failed += 1
                    logger.error(f"User broadcast failed for {user_id}: {e}")
                    continue
        
        # ----- FINAL REPORT -----
        report = (
            f"🎯 **Broadcast Completed!**\n\n"
            f"📊 **Groups:**\n"
            f"✅ Sent: {groups_sent}\n"
            f"📌 Pinned: {groups_pinned}\n"
            f"❌ Failed: {groups_failed}\n"
            f"👥 Total: {len(groups)}\n\n"
        )
        
        if send_to_users:
            report += (
                f"👤 **Users:**\n"
                f"✅ Sent: {users_sent}\n"
                f"❌ Failed: {users_failed}\n"
                f"👥 Total: {len(users)}\n\n"
            )
        
        report += f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
        
        bot.edit_message_text(
            report,
            admin_chat_id,
            status_msg_id,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ **Broadcast Failed**\n\nError: {str(e)}",
            admin_chat_id,
            status_msg_id,
            parse_mode="Markdown"
        )
        logger.error(f"Broadcast worker error: {e}")
    
    finally:
        IS_BROADCASTING = False

# ---------------------------------------------------------------------
# OTHER FUNCTIONS
# ---------------------------------------------------------------------

@bot.message_handler(commands=['ping'])
def ping_command(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return

    try:
        ping_start = time.time()
        me = bot.get_me()
        ping_ms = (time.time() - ping_start) * 1000

        uptime_seconds = int(time.time() - START_TIME)
        uptime_str = str(timedelta(seconds=uptime_seconds))

        ram_mb = _get_ram_usage_mb()
        try:
            cpu_usage = os.getloadavg()[0]
            cpu_text = f"{cpu_usage:.2f} load"
        except Exception:
            cpu_text = "N/A"

        disk = shutil.disk_usage("/")
        disk_used_percent = (disk.used / disk.total) * 100 if disk.total else 0

        text = (
            f"● ᴘɪɴɢ : {ping_ms:.0f} ms\n\n"
            f"{me.first_name} sᴛᴀᴛɪsᴛɪᴄs :\n\n"
            f"● ᴜᴩᴛɪᴍᴇ : {uptime_str}\n"
            f"● ʀᴀᴍ ᴜsᴀɢᴇ : {ram_mb:.2f} MB\n"
            f"● ᴄᴩᴜ ᴜsᴀɢᴇ : {cpu_text}\n"
            f"● ᴅɪsᴋ ᴜsᴀɢᴇ : {disk_used_percent:.2f}%"
        )

        sent = bot.reply_to(message, text)
        _schedule_delete(message.chat.id, sent.message_id)
    except Exception as e:
        logger.error(f"/ping command error: {e}")
        sent = bot.reply_to(message, "❌ Failed to fetch ping stats.")
        _schedule_delete(message.chat.id, sent.message_id)


@bot.message_handler(commands=['flask'])
def flask_command(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Unauthorized access")
        return

    port = os.getenv("PORT", "8080")
    sent = bot.reply_to(
        message,
        f"✅ Flask health server is running.\n🌐 Port: {port}\n🔒 Security headers enabled."
    )
    _schedule_delete(message.chat.id, sent.message_id)


def ask_refund_user(message):
    try:
        refund_user_id = int(message.text)
        msg = bot.send_message(message.chat.id, "💰 Enter refund amount:")
        bot.register_next_step_handler(msg, process_refund, refund_user_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Please enter numeric ID only.")

def process_refund(message, refund_user_id):
    try:
        amount = float(message.text)
        user = users_col.find_one({"user_id": refund_user_id})
        
        if not user:
            bot.send_message(message.chat.id, "⚠️ User not found in database.")
            return
        
        add_balance(refund_user_id, amount)
        new_balance = get_balance(refund_user_id)
        bot.send_message(
            message.chat.id,
            f"✅ Refunded {format_currency(amount)} to user {refund_user_id}\n"
            f"💰 New Balance: {format_currency(new_balance)}"
        )
        
        try:
            bot.send_message(
                refund_user_id,
                f"💸 {format_currency(amount)} refunded to your wallet!\n"
                f"💰 New Balance: {format_currency(new_balance)} ✅"
            )
        except Exception:
            bot.send_message(message.chat.id, "⚠️ Could not DM the user (maybe blocked).")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount entered. Please enter a number.")
    except Exception as e:
        logger.exception("Error in process_refund:")
        bot.send_message(message.chat.id, f"Error processing refund: {e}")

def ask_message_content(msg):
    try:
        target_user_id = int(msg.text)
        user_exists = users_col.find_one({"user_id": target_user_id})
        if not user_exists:
            bot.send_message(msg.chat.id, "❌ User not found in database.")
            return
        
        bot.send_message(msg.chat.id, f"💬 Now send the message (text, photo, video, or document) for user {target_user_id}:")
        bot.register_next_step_handler(msg, process_user_message, target_user_id)
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Invalid user ID. Please enter numeric ID only.")

def process_user_message(msg, target_user_id):
    try:
        text = getattr(msg, "text", None) or getattr(msg, "caption", "") or ""
        is_photo = bool(getattr(msg, "photo", None))
        is_video = getattr(msg, "video", None) is not None
        is_document = getattr(msg, "document", None) is not None
        
        try:
            if is_photo and getattr(msg, "photo", None):
                bot.send_photo(target_user_id, photo=msg.photo[-1].file_id, caption=text or "")
            elif is_video and getattr(msg, "video", None):
                bot.send_video(target_user_id, video=msg.video.file_id, caption=text or "")
            elif is_document and getattr(msg, "document", None):
                bot.send_document(target_user_id, document=msg.document.file_id, caption=text or "")
            else:
                bot.send_message(target_user_id, f"💌 Message from Admin:\n{text}")
            bot.send_message(msg.chat.id, f"✅ Message sent successfully to user {target_user_id}")
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Failed to send message to user {target_user_id}. User may have blocked the bot.")
    except Exception as e:
        logger.exception("Error in process_user_message:")
        bot.send_message(msg.chat.id, f"Error sending message: {e}")

# ---------------------------------------------------------------------
# COUNTRY SELECTION FUNCTIONS
# ---------------------------------------------------------------------

def show_countries(chat_id):
    if not has_user_joined_channels(chat_id):
        start(bot.send_message(chat_id, "/start"))
        return
    
    countries = get_all_countries()
    if not countries:
        text = "🌍 **Select Country**\n\n❌ No countries available right now. Please check back later."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
        
        sent_msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        user_last_message[chat_id] = sent_msg.message_id
        return
    
    text = "🌍 **Select Country**\n\nChoose your country:"
    markup = InlineKeyboardMarkup(row_width=2)
    
    row = []
    for i, country in enumerate(countries):
        row.append(InlineKeyboardButton(
            country['name'],
            callback_data=f"country_raw_{country['name']}"
        ))
        if len(row) == 2:
            markup.add(*row)
            row = []
    
    if row:
        markup.add(*row)
    
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
    
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    user_last_message[chat_id] = sent_msg.message_id

def show_country_details(user_id, country_name, chat_id, message_id, callback_id):
    try:
        country = get_country_by_name(country_name)
        if not country:
            bot.answer_callback_query(callback_id, "❌ Country not found", show_alert=True)
            return
        
        accounts_count = get_available_accounts_count(country_name)
        
        # WITH EXPANDABLE BLOCKQUOTE - UI STYLE
        text = f"""⚡ <b>Telegram Account Info</b>

<blockquote>🌍 Country : {country_name}
💸 Price : {format_currency(country['price'])}
📦 Available : {accounts_count}

🔍 Reliable | Affordable | Good Quality

⚠️ Use Telegram X only to login.
🚫 Not responsible for freeze / ban.</blockquote>"""
        
        markup = InlineKeyboardMarkup(row_width=2)
        
        if accounts_count > 0:
            accounts = list(accounts_col.find({
                "country": country_name,
                "status": "active",
                "used": False
            }))
            markup.add(InlineKeyboardButton(
                "🛒 Buy Account",
                callback_data=f"buy_{accounts[0]['_id']}" if accounts else "out_of_stock"
            ))
        else:
            markup.add(InlineKeyboardButton(
                "🛒 Buy Account",
                callback_data="out_of_stock"
            ))
        
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_countries"))
        
        edit_or_resend(
            chat_id,
            message_id,
            text,
            markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Country details error: {e}")
        bot.answer_callback_query(callback_id, "❌ Error loading country details", show_alert=True)

# ---------------------------------------------------------------------
# PROCESS PURCHASE FUNCTION
# ---------------------------------------------------------------------

def process_purchase(user_id, account_id, chat_id, message_id, callback_id):
    try:
        try:
            account = accounts_col.find_one({"_id": ObjectId(account_id)})
        except Exception:
            account = accounts_col.find_one({"_id": account_id})
        
        if not account:
            bot.answer_callback_query(callback_id, "❌ Account not available", show_alert=True)
            return
        
        if account.get('used', False):
            bot.answer_callback_query(callback_id, "❌ Account already sold out", show_alert=True)
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            show_countries(chat_id)
            return
        
        country = get_country_by_name(account['country'])
        if not country:
            bot.answer_callback_query(callback_id, "❌ Country not found", show_alert=True)
            return
        
        price = country['price']
        balance = get_balance(user_id)
        
        if balance < price:
            needed = price - balance
            bot.answer_callback_query(
                callback_id,
                f"❌ Insufficient balance!\nNeed: {format_currency(price)}\nHave: {format_currency(balance)}\nRequired: {format_currency(needed)} more",
                show_alert=True
            )
            return
        
        deduct_balance(user_id, price)
        
        try:
            from logs import log_purchase_async
            log_purchase_async(
                user_id=user_id,
                country=account['country'],
                price=price,
                phone=account.get('phone', 'N/A')
            )
        except:
            pass
        
        session_id = f"otp_{user_id}_{int(time.time())}"
        otp_session = {
            "session_id": session_id,
            "user_id": user_id,
            "phone": account['phone'],
            "session_string": account.get('session_string', ''),
            "status": "active",
            "created_at": datetime.utcnow(),
            "account_id": str(account['_id']),
            "has_otp": False,
            "last_otp": None,
            "last_otp_time": None
        }
        otp_sessions_col.insert_one(otp_session)
        
        order = {
            "user_id": user_id,
            "account_id": str(account.get('_id')),
            "country": account['country'],
            "price": price,
            "phone_number": account.get('phone', 'N/A'),
            "session_id": session_id,
            "status": "waiting_otp",
            "created_at": datetime.utcnow(),
            "monitoring_duration": 1800
        }
        order_id = orders_col.insert_one(order).inserted_id
        
        try:
            accounts_col.update_one(
                {"_id": account.get('_id')},
                {"$set": {"used": True, "used_at": datetime.utcnow()}}
            )
        except Exception:
            accounts_col.update_one(
                {"_id": ObjectId(account_id)},
                {"$set": {"used": True, "used_at": datetime.utcnow()}}
            )
        
        def start_simple_monitoring():
            try:
                account_manager.start_simple_monitoring_sync(
                    account.get('session_string', ''),
                    session_id,
                    1800
                )
            except Exception as e:
                logger.error(f"Simple monitoring error: {e}")
        
        thread = threading.Thread(target=start_simple_monitoring, daemon=True)
        thread.start()
        
        account_details = f"""✅ **Purchase Successful!** 

🌍 Country: {account['country']}
💸 Price: {format_currency(price)}
📱 Phone Number: {account.get('phone', 'N/A')}"""
        
        if account.get('two_step_password'):
            account_details += f"\n🔒 2FA Password: `{account.get('two_step_password', 'N/A')}`"
        
        account_details += f"\n\n📲 **Instructions:**\n"
        account_details += f"1. Open Telegram X app\n"
        account_details += f"2. Enter phone number: `{account.get('phone', 'N/A')}`\n"
        account_details += f"3. Click 'Next'\n"
        account_details += f"4. **Click 'Get OTP' button below when you need OTP**\n\n"
        account_details += f"⏳ OTP available for 30 minutes"
        
        get_otp_markup = InlineKeyboardMarkup()
        get_otp_markup.add(InlineKeyboardButton("🔢 Get OTP", callback_data=f"get_otp_{session_id}"))
        
        account_details += f"\n💰 Remaining Balance: {format_currency(get_balance(user_id))}"
        
        sent_msg = edit_or_resend(
            chat_id,
            message_id,
            account_details,
            markup=get_otp_markup,
            parse_mode="Markdown"
        )
        
        if sent_msg:
            user_last_message[user_id] = sent_msg.message_id
        
        bot.answer_callback_query(callback_id, "✅ Purchase successful! Click Get OTP when needed.", show_alert=True)
    
    except Exception as e:
        logger.error(f"Purchase error: {e}")
        try:
            bot.answer_callback_query(callback_id, "❌ Purchase failed", show_alert=True)
        except:
            pass

# =============================================================
# RESTART COMMAND (VPS + HEROKU SAFE)
# =============================================================

@bot.message_handler(commands=['restart'])
def restart_bot(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        bot.reply_to(message, "❌ Sirf admin use kar sakta hai!")
        return

    bot.reply_to(message, "♻️ Restarting bot...")

    logger.info(f"Admin {user_id} triggered restart")

    time.sleep(1)

    # Clean restart
    os.execv(sys.executable, ['python'] + sys.argv)

# ---------------------------------------------------------------------
# MESSAGE HANDLER FOR ADMIN DEDUCT
# ---------------------------------------------------------------------

@bot.message_handler(func=lambda m: True, content_types=['text','photo','video','document'])
def chat_handler(msg):
    user_id = msg.from_user.id
    _schedule_delete(msg.chat.id, msg.message_id)
    
    # Check if user is in admin add flow
    if user_id in admin_add_state:
        handle_add_admin_userid(msg)
        return
    
    # Check if user is in admin remove flow
    if user_id in admin_remove_state:
        handle_remove_admin_userid(msg)
        return
    
    if user_id == ADMIN_ID and user_id in admin_deduct_state:
        pass
    
    if is_user_banned(user_id):
        return
    
    ensure_user_exists(
        user_id,
        msg.from_user.first_name or "Unknown",
        msg.from_user.username
    )
    
    if (
        msg.text and msg.text.startswith('/') and
        not (user_id == ADMIN_ID and user_id in admin_deduct_state)
    ):
        return
    
    if user_id == ADMIN_ID and user_id in admin_deduct_state:
        state = admin_deduct_state[user_id]
        
        if state["step"] == "ask_user_id":
            try:
                target_user_id = int(msg.text.strip())
                user_exists = users_col.find_one({"user_id": target_user_id})
                if not user_exists:
                    bot.send_message(ADMIN_ID, "❌ User not found. Enter valid User ID:")
                    return
                
                current_balance = get_balance(target_user_id)
                admin_deduct_state[user_id] = {
                    "step": "ask_amount",
                    "target_user_id": target_user_id,
                    "current_balance": current_balance
                }
                bot.send_message(
                    ADMIN_ID,
                    f"👤 User ID: {target_user_id}\n"
                    f"💰 Current Balance: {format_currency(current_balance)}\n\n"
                    f"💸 Enter amount to deduct:"
                )
                return
            except ValueError:
                bot.send_message(ADMIN_ID, "❌ Invalid User ID. Enter numeric ID:")
                return
        
        elif state["step"] == "ask_amount":
            try:
                amount = float(msg.text.strip())
                current_balance = state["current_balance"]
                if amount <= 0:
                    bot.send_message(ADMIN_ID, "❌ Amount must be greater than 0:")
                    return
                if amount > current_balance:
                    bot.send_message(
                        ADMIN_ID,
                        f"❌ Amount exceeds balance ({format_currency(current_balance)}):"
                    )
                    return
                
                admin_deduct_state[user_id] = {
                    "step": "ask_reason",
                    "target_user_id": state["target_user_id"],
                    "amount": amount,
                    "current_balance": current_balance
                }
                bot.send_message(ADMIN_ID, "📝 Enter reason for deduction:")
                return
            except ValueError:
                bot.send_message(ADMIN_ID, "❌ Invalid amount. Enter number:")
                return
        
        elif state["step"] == "ask_reason":
            reason = msg.text.strip()
            if not reason:
                bot.send_message(ADMIN_ID, "❌ Reason cannot be empty:")
                return
            
            target_user_id = state["target_user_id"]
            amount = state["amount"]
            old_balance = state["current_balance"]
            
            deduct_balance(target_user_id, amount)
            new_balance = get_balance(target_user_id)
            
            transaction_id = f"DEDUCT{target_user_id}{int(time.time())}"
            if 'deductions' not in db.list_collection_names():
                db.create_collection('deductions')
            db['deductions'].insert_one({
                "transaction_id": transaction_id,
                "user_id": target_user_id,
                "amount": amount,
                "reason": reason,
                "admin_id": user_id,
                "old_balance": old_balance,
                "new_balance": new_balance,
                "timestamp": datetime.utcnow()
            })
            
            bot.send_message(
                ADMIN_ID,
                f"✅ Balance Deducted Successfully\n\n"
                f"👤 User: {target_user_id}\n"
                f"💰 Amount: {format_currency(amount)}\n"
                f"📝 Reason: {reason}\n"
                f"📉 Old Balance: {format_currency(old_balance)}\n"
                f"📈 New Balance: {format_currency(new_balance)}\n"
                f"🆔 Txn ID: {transaction_id}"
            )
            
            try:
                bot.send_message(
                    target_user_id,
                    f"⚠️ Balance Deducted by Admin\n\n"
                    f"💰 Amount: {format_currency(amount)}\n"
                    f"📝 Reason: {reason}\n"
                    f"📈 New Balance: {format_currency(new_balance)}\n"
                    f"🆔 Txn ID: {transaction_id}"
                )
            except:
                bot.send_message(ADMIN_ID, "⚠️ User notification failed (maybe blocked)")
            
            del admin_deduct_state[user_id]
            return
    
    if msg.chat.type == "private":
        bot.send_message(
            user_id,
            "⚠️ Please use /start or buttons from the menu."
        )

# ---------------------------------------------------------------------
# RUN BOT
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(f"🤖 Fixed OTP Bot Starting...")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Global API ID: {GLOBAL_API_ID}")
    logger.info(f"Global API Hash: {GLOBAL_API_HASH[:10]}...")
    logger.info(f"Referral Commission: {REFERRAL_COMMISSION}%")
    logger.info(f"Must Join Channel 1: {MUST_JOIN_CHANNEL_1}")
    logger.info(f"Must Join Channel 2: {MUST_JOIN_CHANNEL_2}")
    logger.info(f"Log Channel ID: {LOG_CHANNEL_ID}")
    
    try:
        coupons_col.create_index([("coupon_code", 1)], unique=True)
        coupons_col.create_index([("status", 1)])
        coupons_col.create_index([("created_at", -1)])
        logger.info("✅ Coupon indexes created")
    except Exception as e:
        logger.error(f"❌ Failed to create coupon indexes: {e}")
    
    try:
        admins_col.create_index([("user_id", 1)], unique=True)
        logger.info("✅ Admin indexes created")
    except Exception as e:
        logger.error(f"❌ Failed to create admin indexes: {e}")
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        time.sleep(30)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)

