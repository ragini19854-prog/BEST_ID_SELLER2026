import logging
import re
import threading
import time
import random
from datetime import datetime, timedelta
from bson import ObjectId
import asyncio
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from pymongo import MongoClient
import os
import requests
from pyrogram import Client
from pyrogram.errors import (
    ApiIdInvalid, PhoneNumberInvalid, PhoneCodeInvalid,
    PhoneCodeExpired, SessionPasswordNeeded, PasswordHashInvalid,
    FloodWait, PhoneCodeEmpty
)

# -----------------------
# CONFIG
# -----------------------
BOT_TOKEN = os.getenv('BOT_TOKEN', 'pest')
ADMIN_ID = int(os.getenv('ADMIN_ID', '7582601826'))
MONGO_URL = os.getenv('MONGO_URL', 'mongodb+srv://teamdaxx123:teamdaxx123@cluster0.ysbpgcp.mongodb.net/?retryWrites=true&w=majority')
API_ID = int(os.getenv('API_ID', '30038466'))
API_HASH = os.getenv('API_HASH', '5a492a0dfb22b1a0b7caacbf90cbf96e')


# Referral commission percentage
REFERRAL_COMMISSION = 1.5  # 1.5% per recharge

# Global API Credentials for Pyrogram Login
GLOBAL_API_ID = 6435225
GLOBAL_API_HASH = "4e984ea35f854762dcde906dce426c2d"

# -----------------------
# INIT
# -----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB Setup
try:
    client = MongoClient(MONGO_URL)
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
broadcast_data = {}  # For broadcast state

# Pyrogram login states
login_states = {}  # Format: {user_id: {"step": "phone", "client": client_obj, ...}}

# Import account management
try:
    from account import AccountManager
    account_manager = AccountManager(GLOBAL_API_ID, GLOBAL_API_HASH)
    logger.info("✅ Account manager loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load account module: {e}")
    account_manager = None

# Async manager for background tasks
async_manager = None
if account_manager:
    async_manager = account_manager.async_manager

# -----------------------
# UTILITY FUNCTIONS
# -----------------------
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
        
        # If referred by someone, record the referral
        if referred_by:
            referral_record = {
                "referrer_id": referred_by,
                "referred_id": user_id,
                "referral_code": user_data['referral_code'],
                "status": "pending",
                "created_at": datetime.utcnow()
            }
            referrals_col.insert_one(referral_record)
            # Update referrer's total referrals count
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

def is_admin(user_id):
    """Check if user is admin"""
    try:
        return str(user_id) == str(ADMIN_ID)
    except:
        return False

def is_user_banned(user_id):
    """Check if user is banned"""
    banned = banned_users_col.find_one({"user_id": user_id, "status": "active"})
    return banned is not None

def get_all_countries():
    """Get all active countries"""
    return list(countries_col.find({"status": "active"}))

def get_country_by_name(country_name):
    return countries_col.find_one({
        "name": {"$regex": f"^{country_name}$", "$options": "i"},
        "status": "active"
    })

def add_referral_commission(referrer_id, recharge_amount, recharge_id):
    """Add commission to referrer when referred user recharges"""
    try:
        commission = (recharge_amount * REFERRAL_COMMISSION) / 100
        
        # Add commission to referrer's balance
        add_balance(referrer_id, commission)
        
        # Record transaction
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
        
        # Update user's total commission
        users_col.update_one(
            {"user_id": referrer_id},
            {"$inc": {"total_commission_earned": commission}}
        )
        
        # Update referral status
        referrals_col.update_one(
            {"referred_id": recharge_id.get("user_id"), "referrer_id": referrer_id},
            {"$set": {"status": "completed", "commission": commission, "completed_at": datetime.utcnow()}}
        )
        
        # Notify referrer
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

# -----------------------
# BOT HANDLERS
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    logger.info(f"Start command from user {user_id}")
    
    # Check if user is banned
    if is_user_banned(user_id):
        try:
            bot.delete_message(msg.chat.id, msg.message_id)
        except:
            pass
        return
    
    # Check for referral parameter
    referred_by = None
    if len(msg.text.split()) > 1:
        referral_code = msg.text.split()[1]
        if referral_code.startswith('REF'):
            try:
                referrer_id = int(referral_code[3:])
                # Verify referrer exists
                referrer = users_col.find_one({"user_id": referrer_id})
                if referrer:
                    referred_by = referrer_id
                    logger.info(f"Referral detected: {referrer_id} -> {user_id}")
            except:
                pass
    
    ensure_user_exists(user_id, msg.from_user.first_name, msg.from_user.username, referred_by)
    
    # Send single photo message with buttons and quoted caption
    caption = """<blockquote>🥂 <b>Welcome To OTP Bot By Xqueen</b> 🥂</blockquote>

<blockquote><b>Features:</b>
• Automatic OTPs 📍
• Easy to Use 🥂🥂
• 24/7 Support 👨‍🔧
• Instant Payment Approvals 🧾

<b>How to use:</b>
1️⃣ Recharge
2️⃣ Select Country
3️⃣ Buy Account
4️⃣ Get Number & Login through Telegram X
5️⃣ Receive OTP & You're Done ✅

🚀 <b>Enjoy Fast Account Buying Experience!</b></blockquote>"""
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account"),
        InlineKeyboardButton("💰 Balance", callback_data="balance")
    )
    markup.add(
        InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton("👥 Refer Friends", callback_data="refer_friends")
    )
    markup.add(
        InlineKeyboardButton("🛠️ Support", callback_data="support")
    )
    
    if is_admin(user_id):
        markup.add(InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel"))
    
    try:
        bot.send_photo(
            user_id,
            "https://files.catbox.moe/7s0nqh.jpg",
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error sending start message: {e}")
        bot.send_message(
            user_id,
            caption,
            parse_mode="HTML",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    # Check if user is banned
    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 Your account is banned", show_alert=True)
        return
    
    logger.info(f"Callback received: {data} from user {user_id}")
    
    try:
        if data == "buy_account":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            show_countries(call.message.chat.id)
        
        elif data == "balance":
            balance = get_balance(user_id)
            user_data = users_col.find_one({"user_id": user_id}) or {}
            commission_earned = user_data.get("total_commission_earned", 0)
            
            message = f"💰 **Your Balance:** {format_currency(balance)}\n\n"
            message += f"📊 **Referral Stats:**\n"
            message += f"• Total Commission Earned: {format_currency(commission_earned)}\n"
            message += f"• Total Referrals: {user_data.get('total_referrals', 0)}\n"
            message += f"• Commission Rate: {REFERRAL_COMMISSION}%\n\n"
            message += f"Your Referral Code: `{user_data.get('referral_code', 'REF' + str(user_id))}`"
            
            try:
                bot.edit_message_text(
                    message,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")
                    )
                )
            except:
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                bot.send_message(
                    call.message.chat.id,
                    message,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")
                    )
                )
        
        elif data == "recharge":
            show_recharge_options(call.message.chat.id, call.message.message_id)
        
        elif data == "refer_friends":
            show_referral_info(user_id, call.message.chat.id)
        
        elif data == "support":
            try:
                bot.edit_message_text(
                    "🛠️ Support: @NOBITA_USA_903",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")
                    )
                )
            except:
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                bot.send_message(
                    call.message.chat.id,
                    "🛠️ Support: @NOBITA_USA_903",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")
                    )
                )
        
        elif data == "admin_panel":
            if is_admin(user_id):
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                show_admin_panel(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data.startswith("country_raw_"):
            country_name = data.replace("country_raw_", "")
            show_country_details(user_id, country_name, call.message.chat.id, call.message.message_id, call.id)
        
        elif data.startswith("buy_"):
            account_id = data.split("_", 1)[1]
            process_purchase(user_id, account_id, call.message.chat.id, call.message.message_id, call.id)
        
        elif data.startswith("logout_session_"):
            session_id = data.split("_", 2)[2]
            handle_logout_session(user_id, session_id, call.message.chat.id, call.id)
        
        elif data.startswith("get_otp_"):
            session_id = data.split("_", 2)[2]
            get_latest_otp(user_id, session_id, call.message.chat.id, call.id)
        
        elif data == "back_to_countries":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            show_countries(call.message.chat.id)
        
        elif data == "back_to_menu":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            show_main_menu(call.message.chat.id)
        
        elif data == "recharge_manual":
            try:
                bot.edit_message_text(
                    "💳 Enter recharge amount (minimum ₹1):",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
                    )
                )
                bot.register_next_step_handler(call.message, process_recharge_amount_manual)
            except:
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                bot.send_message(
                    call.message.chat.id,
                    "💳 Enter recharge amount (minimum ₹1):",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
                    )
                )
                bot.register_next_step_handler(call.message, process_recharge_amount_manual)
        
        elif data.startswith("approve_rech|") or data.startswith("cancel_rech|"):
            # Manual recharge approval
            if is_admin(user_id):
                parts = data.split("|")
                action = parts[0]
                req_id = parts[1] if len(parts) > 1 else None
                req = recharges_col.find_one({"req_id": req_id}) if req_id else None
                
                if not req:
                    bot.answer_callback_query(call.id, "❌ Request not found", show_alert=True)
                    return
                
                user_target = req.get("user_id")
                amount = float(req.get("amount", 0))
                
                if action == "approve_rech":
                    add_balance(user_target, amount)
                    recharges_col.update_one(
                        {"req_id": req_id},
                        {"$set": {"status": "approved", "processed_at": datetime.utcnow(), "processed_by": ADMIN_ID}}
                    )
                    bot.answer_callback_query(call.id, "✅ Recharge approved", show_alert=True)
                    
                    # Check for referral commission
                    user_data = users_col.find_one({"user_id": user_target})
                    if user_data and user_data.get("referred_by"):
                        add_referral_commission(user_data["referred_by"], amount, req)
                    
                    kb = InlineKeyboardMarkup()
                    kb.add(InlineKeyboardButton("🛒 Buy Account Now", callback_data="buy_account"))
                    
                    # Delete admin message
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                    except:
                        pass
                    
                    bot.send_message(
                        user_target,
                        f"✅ Your recharge of {format_currency(amount)} has been approved and added to your wallet.\n\n"
                        f"💰 <b>New Balance: {format_currency(get_balance(user_target))}</b>\n\n"
                        f"Click below to buy accounts:",
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                
                else:
                    recharges_col.update_one(
                        {"req_id": req_id},
                        {"$set": {"status": "cancelled", "processed_at": datetime.utcnow(), "processed_by": ADMIN_ID}}
                    )
                    bot.answer_callback_query(call.id, "❌ Recharge cancelled", show_alert=True)
                    
                    # Delete admin message
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                    except:
                        pass
                    
                    bot.send_message(user_target, f"❌ Your recharge of {format_currency(amount)} was not received.")
            else:
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        
        elif data == "add_account":
            logger.info(f"Add account button clicked by user {user_id}")
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
                return
            
            # Start new Pyrogram login flow
            login_states[user_id] = {
                "step": "select_country",
                "message_id": call.message.message_id,
                "chat_id": call.message.chat.id
            }
            
            # Show country selection
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
            
            try:
                bot.edit_message_text(
                    "🌍 **Select Country for Account**\n\nChoose country:",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            except:
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                bot.send_message(
                    call.message.chat.id,
                    "🌍 **Select Country for Account**\n\nChoose country:",
                    reply_markup=markup
                )
        
        elif data.startswith("login_country_"):
            handle_login_country_selection(call)
        
        elif data == "cancel_login":
            handle_cancel_login(call)
        
        elif data == "out_of_stock":
            bot.answer_callback_query(call.id, "❌ Out of Stock! No accounts available.", show_alert=True)
        
        # ADMIN FEATURES - BROADCAST FIXED
        elif data == "broadcast_menu":
            if is_admin(user_id):
                bot.answer_callback_query(call.id, "📢 Reply any photo / document / video / text with /sendbroadcast")
                bot.send_message(call.message.chat.id, "📢 **Broadcast Instructions**\n\nReply to any message (photo / document / video / text) with /sendbroadcast")
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
                # Clear any previous broadcast state
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
                # Actually remove the country
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

def show_main_menu(chat_id):
    user_id = chat_id
    
    # Check if user is banned
    if is_user_banned(user_id):
        bot.send_message(
            user_id,
            "🚫 **Account Banned**\n\n"
            "Your account has been banned from using this bot.\n"
            "Contact admin @NOBITA_USA_903 for assistance."
        )
        return
    
    # Send fresh start message with image
    caption = """<blockquote>🥂 <b>Welcome To OTP Bot By Xqueen</b> 🥂</blockquote>

<blockquote><b>Features:</b>
• Automatic OTPs 📍
• Easy to Use 🥂🥂
• 24/7 Support 👨‍🔧
• Instant Payment Approvals 🧾

<b>How to use:</b>
1️⃣ Recharge
2️⃣ Select Country
3️⃣ Buy Account
4️⃣ Get Number & Login through Telegram X
5️⃣ Receive OTP & You're Done ✅

🚀 <b>Enjoy Fast Account Buying Experience!</b></blockquote>"""
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account"),
        InlineKeyboardButton("💰 Balance", callback_data="balance")
    )
    markup.add(
        InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton("👥 Refer Friends", callback_data="refer_friends")
    )
    markup.add(
        InlineKeyboardButton("🛠️ Support", callback_data="support")
    )
    
    if is_admin(user_id):
        markup.add(InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel"))
    
    try:
        bot.send_photo(
            chat_id,
            "https://files.catbox.moe/7s0nqh.jpg",
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error sending main menu: {e}")
        bot.send_message(
            chat_id,
            caption,
            parse_mode="HTML",
            reply_markup=markup
        )

def show_country_details(user_id, country_name, chat_id, message_id, callback_id):
    """Show country details page"""
    try:
        # Get country details
        country = get_country_by_name(country_name)
        if not country:
            bot.answer_callback_query(callback_id, "❌ Country not found", show_alert=True)
            return
        
        # Get available accounts
        accounts_count = get_available_accounts_count(country_name)
        
        # Format message with quote
        text = f"""⚡ <b>Telegram Account Info</b>

<blockquote>🌍 Country : {country_name}
💸 Price : {format_currency(country['price'])}
📦 Available : {accounts_count}

🔍 Reliable | Affordable | Good Quality

⚠️ Use Telegram X only to login.
🚫 Not responsible for freeze / ban.</blockquote>"""
        
        markup = InlineKeyboardMarkup(row_width=2)
        
        if accounts_count > 0:
            # Get all available accounts
            accounts = list(accounts_col.find({
                "country": country_name,
                "status": "active",
                "used": False
            }))
            
            # Show Buy Account button
            markup.add(InlineKeyboardButton(
                "🛒 Buy Account",
                callback_data=f"buy_{accounts[0]['_id']}" if accounts else "out_of_stock"
            ))
        else:
            # No accounts available - still show buy button with out of stock alert
            markup.add(InlineKeyboardButton(
                "🛒 Buy Account",
                callback_data="out_of_stock"
            ))
        
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_countries"))
        
        try:
            bot.edit_message_text(
                text,
                chat_id,
                message_id,
                parse_mode="HTML",
                reply_markup=markup
            )
        except:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                reply_markup=markup
            )
    
    except Exception as e:
        logger.error(f"Country details error: {e}")
        bot.answer_callback_query(callback_id, "❌ Error loading country details", show_alert=True)

def handle_login_country_selection(call):
    user_id = call.from_user.id
    
    if user_id not in login_states:
        bot.answer_callback_query(call.id, "❌ Session expired", show_alert=True)
        return
    
    country_name = call.data.replace("login_country_", "")
    login_states[user_id]["country"] = country_name
    login_states[user_id]["step"] = "phone"
    
    try:
        bot.edit_message_text(
            f"🌍 Country: {country_name}\n\n"
            "📱 Enter phone number with country code:\n"
            "Example: +919876543210",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")
            )
        )
    except:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(
            call.message.chat.id,
            f"🌍 Country: {country_name}\n\n"
            "📱 Enter phone number with country code:\n"
            "Example: +919876543210",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")
            )
        )

def handle_cancel_login(call):
    user_id = call.from_user.id
    
    # Cleanup any active client
    if user_id in login_states:
        state = login_states[user_id]
        if "client" in state:
            try:
                # Cleanup client if account_manager and account_manager.pyrogram_manager:
                import asyncio
                asyncio.run(account_manager.pyrogram_manager.safe_disconnect(state["client"]))
            except:
                pass
        login_states.pop(user_id, None)
    
    try:
        bot.edit_message_text(
            "❌ Login cancelled.",
            call.message.chat.id,
            call.message.message_id
        )
    except:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(call.message.chat.id, "❌ Login cancelled.")
    
    show_admin_panel(call.message.chat.id)

def handle_logout_session(user_id, session_id, chat_id, callback_id):
    """Handle user logout from session"""
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
            
            bot.send_message(
                chat_id,
                "✅ **Logged Out Successfully!**\n\n"
                "You have been logged out from this session.\n"
                "Order marked as completed.\n\n"
                "Thank you for using our service! 👋\n\n"
                "GOING MANE PAGE /start"
            )
        else:
            bot.answer_callback_query(callback_id, f"❌ {message}", show_alert=True)
    
    except Exception as e:
        logger.error(f"Logout handler error: {e}")
        bot.answer_callback_query(callback_id, "❌ Error logging out", show_alert=True)

def get_latest_otp(user_id, session_id, chat_id, callback_id):
    """Get the latest OTP for a session - SHOWS ONLY WHEN CLICKED"""
    try:
        # Find the session
        session_data = otp_sessions_col.find_one({"session_id": session_id})
        if not session_data:
            bot.answer_callback_query(callback_id, "❌ Session not found", show_alert=True)
            return
        
        # Check if OTP already exists in database
        existing_otp = session_data.get("last_otp")
        if existing_otp:
            # OTP already in database, show it
            otp_code = existing_otp
            logger.info(f"Using existing OTP from database: {otp_code}")
        else:
            # Try to get latest OTP from session
            bot.answer_callback_query(callback_id, "🔍 Searching for OTP...", show_alert=False)
            session_string = session_data.get("session_string")
            if not session_string:
                bot.answer_callback_query(callback_id, "❌ No session string found", show_alert=True)
                return
            
            otp_code = account_manager.get_latest_otp_sync(session_string)
            if not otp_code:
                bot.answer_callback_query(callback_id, "❌ No OTP received yet", show_alert=True)
                return
            
            # Save to database
            otp_sessions_col.update_one(
                {"session_id": session_id},
                {"$set": {
                    "has_otp": True,
                    "last_otp": otp_code,
                    "last_otp_time": datetime.utcnow(),
                    "status": "otp_received"
                }}
            )
        
        # Get account details for 2FA password
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
        
        # Create message
        message = f"✅ **Latest OTP**\n\n"
        message += f"📱 Phone: `{session_data.get('phone', 'N/A')}`\n"
        message += f"🔢 OTP Code: `{otp_code}`\n"
        if two_step_password:
            message += f"🔐 2FA Password: `{two_step_password}`\n"
        elif account and account.get("two_step_password"):
            message += f"🔐 2FA Password: `{account.get('two_step_password')}`\n"
        message += f"\n⏰ Time: {datetime.utcnow().strftime('%H:%M:%S')}"
        message += f"\n\nEnter this code in Telegram X app."
        
        # Create inline keyboard with BOTH buttons
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🔄 Get OTP Again", callback_data=f"get_otp_{session_id}"),
            InlineKeyboardButton("🚪 Logout", callback_data=f"logout_session_{session_id}")
        )
        
        # Try to edit existing message
        try:
            bot.edit_message_text(
                message,
                chat_id,
                callback_id.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
        except:
            # If editing fails, send new message
            bot.send_message(
                chat_id,
                message,
                parse_mode="Markdown",
                reply_markup=markup
            )
        
        bot.answer_callback_query(callback_id, "✅ OTP sent!", show_alert=False)
    
    except Exception as e:
        logger.error(f"Get OTP error: {e}")
        bot.answer_callback_query(callback_id, "❌ Error getting OTP", show_alert=True)

# -----------------------
# MESSAGE HANDLER FOR LOGIN FLOW
# -----------------------
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
        # Process phone number
        phone = msg.text.strip()
        if not re.match(r'^\+\d{10,15}$', phone):
            bot.send_message(chat_id, "❌ Invalid phone number format. Please enter with country code:\nExample: +919876543210")
            return
        
        # Check if account manager is loaded
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
        
        # Start Pyrogram login flow using account manager
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
        # Process OTP
        otp = msg.text.strip()
        if not otp.isdigit() or len(otp) != 5:
            bot.send_message(chat_id, "❌ Invalid OTP format. Please enter 5-digit OTP:")
            return
        
        # Check if account manager is loaded
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
                # Account added successfully
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
                # Cleanup
                login_states.pop(user_id, None)
            
            elif message == "password_required":
                # 2FA required
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
        # Process 2FA password
        password = msg.text.strip()
        if not password:
            bot.send_message(chat_id, "❌ Password cannot be empty. Enter 2FA password:")
            return
        
        # Check if account manager is loaded
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
                # Account added successfully with 2FA
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
                # Cleanup
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

# -----------------------
# REFERRAL SYSTEM FUNCTIONS
# -----------------------
def show_referral_info(user_id, chat_id):
    """Show referral information and stats"""
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
    markup.add(InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={referral_link}&text=Join%20this%20awesome%20OTP%20bot%20to%20buy%20Telegram%20accounts!"))
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
    
    bot.send_message(chat_id, message, parse_mode="Markdown", reply_markup=markup)

# -----------------------
# ADMIN MANAGEMENT FUNCTIONS
# -----------------------
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
    
    text = (
        f"👑 **Admin Panel**\n\n"
        f"📊 **Statistics:**\n"
        f"• Total Accounts: {total_accounts}\n"
        f"• Active Accounts: {active_accounts}\n"
        f"• Total Users: {total_users}\n"
        f"• Total Orders: {total_orders}\n"
        f"• Banned Users: {banned_users}\n"
        f"• Active Countries: {active_countries}\n\n"
        f"🛠️ **Management Tools:**"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Add Account", callback_data="add_account"),
        InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu")
    )
    markup.add(
        InlineKeyboardButton("💸 Refund", callback_data="refund_start"),
        InlineKeyboardButton("📊 Ranking", callback_data="ranking")
    )
    markup.add(
        InlineKeyboardButton("💬 Message User", callback_data="message_user"),
        InlineKeyboardButton("💳 Deduct Balance", callback_data="admin_deduct_start")
    )
    markup.add(
        InlineKeyboardButton("🚫 Ban User", callback_data="ban_user"),
        InlineKeyboardButton("✅ Unban User", callback_data="unban_user")
    )
    markup.add(
        InlineKeyboardButton("🌍 Manage Countries", callback_data="manage_countries")
    )
    
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def show_country_management(chat_id):
    """Show country management options"""
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
        InlineKeyboardButton("➕ Add Country", callback_data="add_country"),
        InlineKeyboardButton("➖ Remove Country", callback_data="remove_country")
    )
    markup.add(InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def ask_country_name(message):
    """Ask for country name to add"""
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
    """Ask for country price"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    try:
        price = float(message.text.strip())
        user_data = user_states.get(message.chat.id)
        country_name = user_data.get("country_name")
        
        # Add country to database
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
    """Show countries for removal"""
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
    
    bot.send_message(
        chat_id,
        "🗑️ **Remove Country**\n\nSelect a country to remove:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

def remove_country(country_name, chat_id, message_id=None):
    """Remove a country from the system"""
    if not is_admin(chat_id):
        return "❌ Unauthorized access"
    
    try:
        # Mark country as inactive
        result = countries_col.update_one(
            {"name": country_name, "status": "active"},
            {"$set": {"status": "inactive", "removed_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            # Delete all accounts for this country
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
    """Ask for user ID to ban"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    try:
        user_id_to_ban = int(message.text.strip())
        
        # Check if user exists
        user = users_col.find_one({"user_id": user_id_to_ban})
        if not user:
            bot.send_message(message.chat.id, "❌ User not found in database.")
            return
        
        # Check if already banned
        already_banned = banned_users_col.find_one({"user_id": user_id_to_ban, "status": "active"})
        if already_banned:
            bot.send_message(message.chat.id, "⚠️ User is already banned.")
            return
        
        # Ban the user
        ban_record = {
            "user_id": user_id_to_ban,
            "banned_by": message.from_user.id,
            "reason": "Admin banned",
            "status": "active",
            "banned_at": datetime.utcnow()
        }
        banned_users_col.insert_one(ban_record)
        
        bot.send_message(message.chat.id, f"✅ User {user_id_to_ban} has been banned.")
        
        # Notify user
        try:
            bot.send_message(
                user_id_to_ban,
                "🚫 **Your Account Has Been Banned**\n\n"
                "You have been banned from using this bot.\n"
                "Contact admin @NOBITA_USA_903 if you believe this is a mistake."
            )
        except:
            pass
    
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Please enter numeric ID only.")

def ask_unban_user(message):
    """Ask for user ID to unban"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unauthorized access")
        return
    
    try:
        user_id_to_unban = int(message.text.strip())
        
        # Check if user is banned
        ban_record = banned_users_col.find_one({"user_id": user_id_to_unban, "status": "active"})
        if not ban_record:
            bot.send_message(message.chat.id, "⚠️ User is not banned.")
            return
        
        # Unban the user
        banned_users_col.update_one(
            {"user_id": user_id_to_unban, "status": "active"},
            {"$set": {"status": "unbanned", "unbanned_at": datetime.utcnow(), "unbanned_by": message.from_user.id}}
        )
        
        bot.send_message(message.chat.id, f"✅ User {user_id_to_unban} has been unbanned.")
        
        # Notify user
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
    """Show user ranking by balance"""
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Unauthorized access")
        return
    
    try:
        # Get all wallet records and join with users
        users_ranking = []
        all_wallets = wallets_col.find()
        
        for wallet in all_wallets:
            user_id_rank = wallet.get("user_id")
            balance = float(wallet.get("balance", 0))
            
            # Only include users with balance > 0
            if balance > 0:
                # Get user details
                user = users_col.find_one({"user_id": user_id_rank}) or {}
                name = user.get("name", "Unknown")
                username_db = user.get("username")
                users_ranking.append({
                    "user_id": user_id_rank,
                    "balance": balance,
                    "name": name,
                    "username": username_db
                })
        
        # Sort by balance (highest first)
        users_ranking.sort(key=lambda x: x["balance"], reverse=True)
        
        # Create ranking message
        ranking_text = "📊 **User Ranking by Wallet Balance**\n\n"
        
        if not users_ranking:
            ranking_text = "📊 No users found with balance greater than zero."
        else:
            for index, user_data in enumerate(users_ranking[:20], 1):  # Show top 20
                user_link = f"<a href='tg://user?id={user_data['user_id']}'>{user_data['user_id']}</a>"
                username_display = f"@{user_data['username']}" if user_data['username'] else "No Username"
                ranking_text += f"{index}. {user_link} - {username_display}\n"
                ranking_text += f"   💰 Balance: {format_currency(user_data['balance'])}\n\n"
        
        # Send ranking message
        bot.send_message(chat_id, ranking_text, parse_mode="HTML")
    
    except Exception as e:
        logger.exception("Error in ranking:")
        bot.send_message(chat_id, f"❌ Error generating ranking: {str(e)}")

# -----------------------
# BROADCAST FUNCTION - FIXED
# -----------------------
@bot.message_handler(commands=['sendbroadcast'])
def handle_sendbroadcast_command(msg):
    """Handle /sendbroadcast command"""
    if not is_admin(msg.from_user.id):
        bot.send_message(msg.chat.id, "❌ Unauthorized access")
        return
    
    if not msg.reply_to_message:
        bot.send_message(msg.chat.id, "❌ Please reply to a message (text/photo/video/document) with /sendbroadcast")
        return
    
    source = msg.reply_to_message
    text = getattr(source, "text", None) or getattr(source, "caption", "") or ""
    is_photo = bool(getattr(source, "photo", None))
    is_video = getattr(source, "video", None) is not None
    is_document = getattr(source, "document", None) is not None
    
    bot.send_message(msg.chat.id, "📡 Broadcasting started... Please wait.")
    threading.Thread(target=broadcast_thread, args=(source, text, is_photo, is_video, is_document)).start()

def broadcast_thread(source_msg, text, is_photo, is_video, is_document):
    users = list(users_col.find())
    total = len(users)
    sent = 0
    failed = 0
    progress_interval = 25
    
    for user in users:
        uid = user.get("user_id")
        if not uid or uid == ADMIN_ID:
            continue
        
        try:
            if is_photo and getattr(source_msg, "photo", None):
                bot.send_photo(uid, photo=source_msg.photo[-1].file_id, caption=text or "")
            elif is_video and getattr(source_msg, "video", None):
                bot.send_video(uid, video=source_msg.video.file_id, caption=text or "")
            elif is_document and getattr(source_msg, "document", None):
                bot.send_document(uid, document=source_msg.document.file_id, caption=text or "")
            else:
                bot.send_message(uid, f"📢 **Broadcast from Admin**\n\n{text}")
            
            sent += 1
            if sent % progress_interval == 0:
                try:
                    bot.send_message(ADMIN_ID, f"✅ Sent {sent}/{total} users...")
                except Exception:
                    pass
            time.sleep(0.1)
        
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {uid}: {e}")
    
    try:
        bot.send_message(
            ADMIN_ID,
            f"🎯 **Broadcast Completed!**\n\n✅ Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {total}"
        )
    except Exception:
        pass

# -----------------------
# OTHER FUNCTIONS FROM FIRST CODE
# -----------------------
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
        # Check if user exists
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
        # Get message content
        text = getattr(msg, "text", None) or getattr(msg, "caption", "") or ""
        is_photo = bool(getattr(msg, "photo", None))
        is_video = getattr(msg, "video", None) is not None
        is_document = getattr(msg, "document", None) is not None
        
        # Send message to target user
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

# -----------------------
# COUNTRY SELECTION FUNCTIONS
# -----------------------
def show_countries(chat_id):
    countries = get_all_countries()
    
    if not countries:
        text = "🌍 **Select Country**\n\n❌ No countries available right now. Please check back later."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
        
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        return
    
    text = "🌍 **Select Country**\n\nChoose your country:"
    markup = InlineKeyboardMarkup(row_width=2)
    
    # Create buttons in 2x2 grid (2 countries per row)
    row = []
    for i, country in enumerate(countries):
        row.append(InlineKeyboardButton(
            country['name'],
            callback_data=f"country_raw_{country['name']}"
        ))
        
        # Add 2 buttons per row
        if len(row) == 2:
            markup.add(*row)
            row = []
    
    # Add any remaining buttons
    if row:
        markup.add(*row)
    
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
    
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

# -----------------------
# RECHARGE FUNCTIONS
# -----------------------
def show_recharge_options(chat_id, message_id):
    text = "💳 Recharge Options\n\nChoose payment method:"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👨‍💻 Manual", callback_data="recharge_manual")
    )
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu"))
    
    if message_id:
        try:
            bot.edit_message_text(
                text,
                chat_id,
                message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def process_recharge_amount_manual(msg):
    """Process manual recharge amount"""
    try:
        amount = float(msg.text)
        if amount < 1:
            bot.send_message(msg.chat.id, "❌ Minimum recharge is ₹1. Enter amount again:")
            bot.register_next_step_handler(msg, process_recharge_amount_manual)
            return
        
        user_id = msg.from_user.id
        
        # Show QR code and payment details
        caption = f"""<blockquote>💳 <b>Payment Details</b>

💰 Amount: {format_currency(amount)}
📱 UPI ID: <code>YOUR UPI ID</code>
👤 Name: YOUR UPI NAME</blockquote>

<blockquote>📋 <b>Instructions:</b>
1. Scan QR code OR send {format_currency(amount)} to above UPI
2. Send screenshot OR 12-digit UTR here
3. Payment will be verified manually</blockquote>"""
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ Cancel", callback_data="back_to_menu"))
        
        # Send QR code image
        bot.send_photo(
            msg.chat.id,
            "https://files.catbox.moe/8rpxez.jpg",
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
        
        # Store recharge data
        recharge_data = {
            "user_id": user_id,
            "amount": amount,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "method": "manual"
        }
        recharge_id = recharges_col.insert_one(recharge_data).inserted_id
        
        # Set user state to wait for proof
        user_stage[user_id] = "waiting_recharge_proof"
        pending_messages[user_id] = {
            "recharge_amount": amount,
            "recharge_id": str(recharge_id)
        }
    
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Invalid amount. Enter numbers only:")
        bot.register_next_step_handler(msg, process_recharge_amount_manual)

@bot.message_handler(
    func=lambda m: user_stage.get(m.from_user.id) == "waiting_recharge_proof",
    content_types=['photo', 'text']
)
def handle_payment_proof(msg):
    user_id = msg.from_user.id
    
    if user_stage.get(user_id) == "waiting_recharge_proof":
        amount = pending_messages[user_id].get("recharge_amount", 0)
        recharge_id = pending_messages[user_id].get("recharge_id")
        
        if msg.content_type == 'photo':
            # Screenshot provided
            proof_type = "screenshot"
            proof_value = msg.photo[-1].file_id
            admin_caption = f"📸 Payment Screenshot\n\nUser: {user_id}\nAmount: {format_currency(amount)}\nRecharge ID: {recharge_id}"
            
            # Update recharge with screenshot
            recharges_col.update_one(
                {"_id": ObjectId(recharge_id)},
                {"$set": {
                    "screenshot": proof_value,
                    "submitted_at": datetime.utcnow(),
                    "proof_type": "screenshot"
                }}
            )
        
        elif msg.content_type == 'text' and msg.text.strip().isdigit() and len(msg.text.strip()) == 12:
            # UTR provided
            proof_type = "utr"
            proof_value = msg.text.strip()
            admin_caption = f"💳 UTR Provided\n\nUser: {user_id}\nAmount: {format_currency(amount)}\nUTR: {proof_value}\nRecharge ID: {recharge_id}"
            
            # Update recharge with UTR
            recharges_col.update_one(
                {"_id": ObjectId(recharge_id)},
                {"$set": {
                    "utr": proof_value,
                    "submitted_at": datetime.utcnow(),
                    "proof_type": "utr"
                }}
            )
        
        else:
            bot.send_message(user_id, "❌ Please send a screenshot OR 12-digit UTR only.")
            return
        
        # Create unique request ID
        req_id = f"R{int(time.time())}{user_id}"
        recharges_col.update_one(
            {"_id": ObjectId(recharge_id)},
            {"$set": {"req_id": req_id}}
        )
        
        # Send to admin with buttons
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_rech|{req_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"cancel_rech|{req_id}")
        )
        
        if proof_type == "screenshot":
            bot.send_photo(
                ADMIN_ID,
                proof_value,
                caption=admin_caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            bot.send_message(
                ADMIN_ID,
                admin_caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        
        # Confirm to user
        bot.send_message(
            user_id,
            "✅ Payment proof received! Admin will verify and approve soon."
        )
        
        # Cleanup
        user_stage[user_id] = "done"
        pending_messages.pop(user_id, None)

# -----------------------
# PROCESS PURCHASE FUNCTION (UPDATED)
# -----------------------
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
            # Go back to country selection
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            show_countries(chat_id)
            return
        
        # Get country price
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
        
        # Create OTP session for this purchase
        session_id = f"otp_{user_id}_{int(time.time())}"
        otp_session = {
            "session_id": session_id,
            "user_id": user_id,
            "phone": account['phone'],
            "session_string": account.get('session_string', ''),
            "status": "active",
            "created_at": datetime.utcnow(),
            "account_id": str(account['_id']),
            "has_otp": False,  # Start with False, becomes True when OTP received
            "last_otp": None,
            "last_otp_time": None
        }
        otp_sessions_col.insert_one(otp_session)
        
        # Create order
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
        
        # Mark account as used
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
        
        # Start simple background monitoring (session keep-alive only, no auto OTP search)
        def start_simple_monitoring():
            try:
                account_manager.start_simple_monitoring_sync(
                    account.get('session_string', ''),
                    session_id,
                    1800
                )
            except Exception as e:
                logger.error(f"Simple monitoring error: {e}")
        
        # Start monitoring thread
        thread = threading.Thread(target=start_simple_monitoring, daemon=True)
        thread.start()
        
        # USER KO SIRF PHONE NUMBER DIKHAO - NO API ID/HASH
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
        
        # Add ONLY Get OTP button
        get_otp_markup = InlineKeyboardMarkup()
        get_otp_markup.add(InlineKeyboardButton("🔢 Get OTP", callback_data=f"get_otp_{session_id}"))
        
        account_details += f"\n💰 Remaining Balance: {format_currency(get_balance(user_id))}"
        
        try:
            bot.edit_message_text(
                account_details,
                chat_id,
                message_id,
                parse_mode="Markdown",
                reply_markup=get_otp_markup
            )
        except:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            bot.send_message(
                chat_id,
                account_details,
                parse_mode="Markdown",
                reply_markup=get_otp_markup
            )
        
        bot.answer_callback_query(callback_id, "✅ Purchase successful! Click Get OTP when needed.", show_alert=True)
    
    except Exception as e:
        logger.error(f"Purchase error: {e}")
        try:
            bot.answer_callback_query(callback_id, "❌ Purchase failed", show_alert=True)
        except:
            pass

# MESSAGE HANDLER FOR ADMIN DEDUCT AND BROADCAST - COMPLETELY FIXED
# -----------------------
@bot.message_handler(func=lambda m: True, content_types=['text','photo','video','document'])
def chat_handler(msg):
    user_id = msg.from_user.id
    
    # ADMIN DEDUCT MUST HAVE PRIORITY
    if user_id == ADMIN_ID and user_id in admin_deduct_state:
        pass

    # Check if user is banned
    if is_user_banned(user_id):
        return

    ensure_user_exists(
        user_id,
        msg.from_user.first_name or "Unknown",
        msg.from_user.username
    )

    # Skip commands ONLY if admin is NOT in deduct flow
    if (
        msg.text
        and msg.text.startswith('/')
        and not (user_id == ADMIN_ID and user_id in admin_deduct_state)
    ):
        return

    # ===============================
    # ADMIN DEDUCT FLOW (PRIORITY)
    # ===============================
    if user_id == ADMIN_ID and user_id in admin_deduct_state:
        state = admin_deduct_state[user_id]

        # STEP 1: Ask User ID
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

        # STEP 2: Ask Amount
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

        # STEP 3: Ask Reason + Deduct
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

    # Default reply
    if msg.chat.type == "private":
        bot.send_message(
            user_id,
            "⚠️ Please use /start or buttons from the menu."
        )
# -----------------------
# RUN BOT
# -----------------------
if __name__ == "__main__":
    logger.info(f"🤖 Fixed OTP Bot Starting...")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Global API ID: {GLOBAL_API_ID}")
    logger.info(f"Global API Hash: {GLOBAL_API_HASH[:10]}...")
    logger.info(f"Referral Commission: {REFERRAL_COMMISSION}%")
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        time.sleep(30)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
