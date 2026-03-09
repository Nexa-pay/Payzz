import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import random
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set!")
    sys.exit(1)

try:
    ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
    OWNER_ID = int(os.getenv('OWNER_ID', '0'))
    API_ID = int(os.getenv('API_ID', '0'))
except ValueError as e:
    logger.error(f"Invalid ID in environment variables: {e}")
    sys.exit(1)

API_HASH = os.getenv('API_HASH')
if not API_HASH:
    logger.error("API_HASH not set!")
    sys.exit(1)

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///reports.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Report Configuration
REPORT_INTERVAL = int(os.getenv('REPORT_INTERVAL', '10'))
MAX_REPORTS_PER_ACCOUNT = int(os.getenv('MAX_REPORTS_PER_ACCOUNT', '50'))

# Conversation states
PHONE, CODE, PASSWORD = range(3)

# Database setup
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String, nullable=True)
    coins = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    phone_number = Column(String, unique=True)
    session_string = Column(Text)  # Changed to Text for longer sessions
    is_active = Column(Boolean, default=True)
    reports_count = Column(Integer, default=0)
    last_report_time = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer)
    target_type = Column(String)
    target_id = Column(String)
    reported_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    
class ReportTarget(Base):
    __tablename__ = 'report_targets'
    
    id = Column(Integer, primary_key=True)
    target_type = Column(String)
    target_id = Column(String)
    target_username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    added_by = Column(Integer)
    added_at = Column(DateTime, default=datetime.utcnow)

# Create tables
try:
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {e}")
    sys.exit(1)

# Active reporting tasks
reporting_tasks = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    db = SessionLocal()
    
    try:
        # Check if user exists in database
        db_user = db.query(User).filter_by(telegram_id=user.id).first()
        if not db_user:
            is_owner = user.id == OWNER_ID
            db_user = User(
                telegram_id=user.id,
                username=user.username,
                coins=100 if is_owner else 0,
                is_owner=is_owner,
                is_admin=user.id in ADMIN_IDS or is_owner
            )
            db.add(db_user)
            db.commit()
            logger.info(f"New user added: {user.id} - {user.username}")
        
        await update.message.reply_text(
            f"Welcome {user.first_name}!\n\n"
            f"💰 Your Coins: {db_user.coins}\n"
            f"👤 Status: {'👑 Owner' if db_user.is_owner else '🔧 Admin' if db_user.is_admin else '👤 User'}\n\n"
            "📋 **Commands:**\n"
            "/addaccount - Add Telegram account\n"
            "/myaccounts - List your accounts\n"
            "/addtarget - Add target to report\n"
            "/targets - List report targets\n"
            "/startreport - Start reporting\n"
            "/stopreport - Stop reporting\n"
            "/coins - Check your coins\n"
            "/help - Get help",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("An error occurred. Please try again later.")
    finally:
        db.close()

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the account addition process"""
    await update.message.reply_text(
        "📱 Please enter your phone number (with country code):\n"
        "Example: `+1234567890`\n\n"
        "Send /cancel to cancel.",
        parse_mode='Markdown'
    )
    return PHONE

async def add_account_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input"""
    phone = update.message.text
    context.user_data['phone'] = phone
    
    try:
        # Create temporary client
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        # Send code request
        await client.send_code_request(phone)
        context.user_data['client'] = client
        
        await update.message.reply_text(
            "✅ Verification code sent!\n"
            "Please enter the code you received:"
        )
        return CODE
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
        return ConversationHandler.END

async def add_account_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification code input"""
    code = update.message.text
    client = context.user_data.get('client')
    phone = context.user_data.get('phone')
    
    try:
        await client.sign_in(phone=phone, code=code)
        
        # Save session
        session_string = client.session.save()
        
        # Save to database
        db = SessionLocal()
        account = Account(
            user_id=update.effective_user.id,
            phone_number=phone,
            session_string=session_string
        )
        db.add(account)
        db.commit()
        db.close()
        
        await client.disconnect()
        await update.message.reply_text("✅ Account added successfully!")
        logger.info(f"Account added for user {update.effective_user.id}: {phone}")
        return ConversationHandler.END
        
    except SessionPasswordNeededError:
        await update.message.reply_text(
            "🔐 Two-step verification enabled.\n"
            "Please enter your password:"
        )
        return PASSWORD
    except Exception as e:
        logger.error(f"Error signing in: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
        return ConversationHandler.END

async def add_account_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle password input for 2FA"""
    password = update.message.text
    client = context.user_data.get('client')
    phone = context.user_data.get('phone')
    
    try:
        await client.sign_in(password=password)
        
        # Save session
        session_string = client.session.save()
        
        # Save to database
        db = SessionLocal()
        account = Account(
            user_id=update.effective_user.id,
            phone_number=phone,
            session_string=session_string
        )
        db.add(account)
        db.commit()
        db.close()
        
        await client.disconnect()
        await update.message.reply_text("✅ Account added successfully!")
        logger.info(f"Account added for user {update.effective_user.id}: {phone}")
        
    except Exception as e:
        logger.error(f"Error with password: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    return ConversationHandler.END

async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List user's accounts"""
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter_by(user_id=update.effective_user.id).all()
        
        if not accounts:
            await update.message.reply_text("❌ You haven't added any accounts yet.")
        else:
            text = "📱 **Your accounts:**\n\n"
            for i, acc in enumerate(accounts, 1):
                status = "✅ Active" if acc.is_active else "❌ Inactive"
                last_report = acc.last_report_time.strftime("%Y-%m-%d %H:%M") if acc.last_report_time else "Never"
                text += f"{i}. `{acc.phone_number}`\n"
                text += f"   Status: {status}\n"
                text += f"   Reports: {acc.reports_count}\n"
                text += f"   Last report: {last_report}\n\n"
            
            await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
    finally:
        db.close()

async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add target to report"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/addtarget <type> <username/id>`\n"
            "Types: `group`, `channel`, `user`\n"
            "Example: `/addtarget channel @spam_channel`",
            parse_mode='Markdown'
        )
        return
    
    target_type = context.args[0].lower()
    target_id = context.args[1]
    
    if target_type not in ['group', 'channel', 'user']:
        await update.message.reply_text("❌ Invalid type! Use: group, channel, or user")
        return
    
    db = SessionLocal()
    try:
        # Check if user has enough coins (1 coin per target)
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if user.coins < 1:
            await update.message.reply_text("❌ You don't have enough coins!")
            return
        
        # Add target
        target = ReportTarget(
            target_type=target_type,
            target_id=target_id,
            added_by=update.effective_user.id
        )
        db.add(target)
        
        # Deduct coin
        user.coins -= 1
        db.commit()
        
        await update.message.reply_text(f"✅ Target {target_id} added successfully!")
        logger.info(f"Target added by {update.effective_user.id}: {target_type} - {target_id}")
    except Exception as e:
        logger.error(f"Error adding target: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
    finally:
        db.close()

async def list_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all report targets"""
    db = SessionLocal()
    try:
        targets = db.query(ReportTarget).filter_by(is_active=True).all()
        
        if not targets:
            await update.message.reply_text("❌ No active targets.")
        else:
            text = "🎯 **Active targets:**\n\n"
            for i, t in enumerate(targets, 1):
                text += f"{i}. {t.target_type}: `{t.target_id}`\n"
            await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error listing targets: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
    finally:
        db.close()

async def report_loop(user_id, accounts, targets):
    """Main reporting loop"""
    account_index = 0
    target_index = 0
    
    logger.info(f"Starting report loop for user {user_id} with {len(accounts)} accounts and {len(targets)} targets")
    
    while user_id in reporting_tasks:
        try:
            # Get current account and target
            account = accounts[account_index]
            target = targets[target_index]
            
            db = SessionLocal()
            
            # Check account cooldown
            if account.last_report_time:
                time_diff = datetime.utcnow() - account.last_report_time
                if time_diff.total_seconds() < 3600:  # 1 hour cooldown
                    account_index = (account_index + 1) % len(accounts)
                    db.close()
                    await asyncio.sleep(1)
                    continue
            
            # Perform report using Telethon
            try:
                client = TelegramClient(StringSession(account.session_string), API_ID, API_HASH)
                await client.connect()
                
                if await client.is_user_authorized():
                    # Here you would implement the actual reporting
                    logger.info(f"Reporting {target.target_id} with account {account.phone_number}")
                    
                    # Update account stats
                    account.reports_count += 1
                    account.last_report_time = datetime.utcnow()
                    
                    # Save report record
                    report = Report(
                        account_id=account.id,
                        target_type=target.target_type,
                        target_id=target.target_id,
                        success=True
                    )
                    db.add(report)
                    db.commit()
                
                await client.disconnect()
                
            except Exception as e:
                logger.error(f"Reporting error with account {account.phone_number}: {e}")
            
            # Move to next account and target
            account_index = (account_index + 1) % len(accounts)
            target_index = (target_index + 1) % len(targets)
            
            db.close()
            
            # Wait for next report
            await asyncio.sleep(REPORT_INTERVAL)
            
        except Exception as e:
            logger.error(f"Report loop error: {e}")
            await asyncio.sleep(10)
    
    logger.info(f"Report loop ended for user {user_id}")

async def start_reporting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the reporting process"""
    user_id = update.effective_user.id
    
    if user_id in reporting_tasks:
        await update.message.reply_text("⚠️ Reporting is already running!")
        return
    
    db = SessionLocal()
    try:
        # Check if user has accounts
        accounts = db.query(Account).filter_by(
            user_id=user_id,
            is_active=True
        ).all()
        
        targets = db.query(ReportTarget).filter_by(is_active=True).all()
        
        if not accounts:
            await update.message.reply_text("❌ You need to add accounts first!\nUse /addaccount")
            return
        
        if not targets:
            await update.message.reply_text("❌ You need to add targets first!\nUse /addtarget")
            return
        
        # Start reporting task
        task = asyncio.create_task(
            report_loop(user_id, accounts, targets)
        )
        reporting_tasks[user_id] = task
        
        await update.message.reply_text(
            f"✅ **Reporting started!**\n\n"
            f"📱 Accounts: {len(accounts)}\n"
            f"🎯 Targets: {len(targets)}\n"
            f"⏱️ Interval: {REPORT_INTERVAL} seconds\n\n"
            f"Use /stopreport to stop.",
            parse_mode='Markdown'
        )
        logger.info(f"Reporting started for user {user_id}")
    except Exception as e:
        logger.error(f"Error starting reporting: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
    finally:
        db.close()

async def stop_reporting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the reporting process"""
    user_id = update.effective_user.id
    
    if user_id in reporting_tasks:
        reporting_tasks[user_id].cancel()
        del reporting_tasks[user_id]
        await update.message.reply_text("✅ Reporting stopped!")
        logger.info(f"Reporting stopped for user {user_id}")
    else:
        await update.message.reply_text("❌ No active reporting!")

async def check_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user's coins"""
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        await update.message.reply_text(f"💰 You have **{user.coins} coins**.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error checking coins: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
    finally:
        db.close()

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add coins to user"""
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: `/addcoins <user_id> <amount>`", parse_mode='Markdown')
        return
    
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=user_id).first()
        if user:
            user.coins += amount
            db.commit()
            await update.message.reply_text(f"✅ Added {amount} coins to user {user_id}")
            logger.info(f"Added {amount} coins to user {user_id} by admin {update.effective_user.id}")
        else:
            await update.message.reply_text("❌ User not found!")
        db.close()
    except Exception as e:
        logger.error(f"Error adding coins: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner command to add admin"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/addadmin <user_id>`", parse_mode='Markdown')
        return
    
    try:
        user_id = int(context.args[0])
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=user_id).first()
        if user:
            user.is_admin = True
            db.commit()
            await update.message.reply_text(f"✅ User {user_id} is now admin!")
            logger.info(f"User {user_id} made admin by owner {update.effective_user.id}")
        else:
            await update.message.reply_text("❌ User not found!")
        db.close()
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/broadcast <message>`", parse_mode='Markdown')
        return
    
    message = ' '.join(context.args)
    
    db = SessionLocal()
    users = db.query(User).all()
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"📢 **Broadcast Message**\n\n{message}",
                parse_mode='Markdown'
            )
            success += 1
            await asyncio.sleep(0.05)  # Rate limiting
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send to {user.telegram_id}: {e}")
    
    await update.message.reply_text(f"✅ Broadcast sent to {success}/{len(users)} users! Failed: {failed}")
    logger.info(f"Broadcast sent by {update.effective_user.id}: Success {success}, Failed {failed}")
    db.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = """
🤖 **Bot Commands:**

**👤 User Commands:**
/start - Start the bot
/help - Show this help
/addaccount - Add Telegram account
/myaccounts - List your accounts
/addtarget - Add target to report
/targets - List targets
/startreport - Start reporting
/stopreport - Stop reporting
/coins - Check your coins

**🔧 Admin Commands:**
/addcoins - Add coins to user
/broadcast - Broadcast message

**👑 Owner Commands:**
/addadmin - Add new admin

**📝 Note:** Each target costs 1 coin to add.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

def main():
    """Main function to run the bot"""
    logger.info("Starting bot...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addaccount", add_account_start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myaccounts", my_accounts))
    application.add_handler(CommandHandler("addtarget", add_target))
    application.add_handler(CommandHandler("targets", list_targets))
    application.add_handler(CommandHandler("startreport", start_reporting))
    application.add_handler(CommandHandler("stopreport", stop_reporting))
    application.add_handler(CommandHandler("coins", check_coins))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("addcoins", add_coins))
    application.add_handler(CommandHandler("addadmin", add_admin))
    
    # Start the bot
    logger.info("Bot is running! Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)