import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from sqlalchemy.orm import Session
import random
import json

from database import get_db, User, Account, Report, ReportTarget, engine
from config import BOT_TOKEN, ADMIN_IDS, OWNER_ID, REPORT_INTERVAL, MAX_REPORTS_PER_ACCOUNT

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
PHONE, CODE, PASSWORD = range(3)

# Active reporting tasks
reporting_tasks = {}

class ReportBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        
    def setup_handlers(self):
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("addaccount", self.add_account_start))
        self.application.add_handler(CommandHandler("myaccounts", self.my_accounts))
        self.application.add_handler(CommandHandler("addtarget", self.add_target))
        self.application.add_handler(CommandHandler("targets", self.list_targets))
        self.application.add_handler(CommandHandler("startreport", self.start_reporting))
        self.application.add_handler(CommandHandler("stopreport", self.stop_reporting))
        self.application.add_handler(CommandHandler("coins", self.check_coins))
        self.application.add_handler(CommandHandler("broadcast", self.broadcast_message))
        
        # Admin commands
        self.application.add_handler(CommandHandler("addcoins", self.add_coins))
        self.application.add_handler(CommandHandler("addadmin", self.add_admin))
        
        # Conversation handler for adding account
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("addaccount", self.add_account_start)],
            states={
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_phone)],
                CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_code)],
                PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_password)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(conv_handler)
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        db = next(get_db())
        
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
        
        await update.message.reply_text(
            f"Welcome {user.first_name}!\n\n"
            f"Your Coins: {db_user.coins}\n"
            f"Status: {'Owner' if db_user.is_owner else 'Admin' if db_user.is_admin else 'User'}\n\n"
            "Commands:\n"
            "/addaccount - Add Telegram account\n"
            "/myaccounts - List your accounts\n"
            "/addtarget - Add target to report\n"
            "/targets - List report targets\n"
            "/startreport - Start reporting\n"
            "/stopreport - Stop reporting\n"
            "/coins - Check your coins\n"
            "/help - Get help"
        )
        db.close()
    
    async def add_account_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the account addition process"""
        await update.message.reply_text(
            "Please enter your phone number (with country code):\n"
            "Example: +1234567890\n\n"
            "Send /cancel to cancel."
        )
        return PHONE
    
    async def add_account_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle phone number input"""
        phone = update.message.text
        context.user_data['phone'] = phone
        
        # Create temporary client
        client = TelegramClient(f'session_{phone}', api_id, api_hash)
        await client.connect()
        
        try:
            await client.send_code_request(phone)
            context.user_data['client'] = client
            await update.message.reply_text(
                "Verification code sent to your Telegram app.\n"
                "Please enter the code:"
            )
            return CODE
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")
            return ConversationHandler.END
    
    async def add_account_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle verification code input"""
        code = update.message.text
        client = context.user_data.get('client')
        phone = context.user_data.get('phone')
        
        try:
            await client.sign_in(phone=phone, code=code)
            # Save session
            session_string = client.session.save()
            
            # Encrypt session (implement proper encryption)
            encrypted_session = self.encrypt_session(session_string)
            
            # Save to database
            db = next(get_db())
            account = Account(
                user_id=update.effective_user.id,
                phone_number=phone,
                session_string=encrypted_session
            )
            db.add(account)
            db.commit()
            db.close()
            
            await update.message.reply_text("Account added successfully!")
            return ConversationHandler.END
            
        except SessionPasswordNeededError:
            await update.message.reply_text(
                "Two-step verification enabled.\n"
                "Please enter your password:"
            )
            return PASSWORD
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")
            return ConversationHandler.END
    
    async def add_account_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password input for 2FA"""
        password = update.message.text
        client = context.user_data.get('client')
        
        try:
            await client.sign_in(password=password)
            # Save session (similar to above)
            # ... (save session code)
            await update.message.reply_text("Account added successfully!")
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")
        
        return ConversationHandler.END
    
    async def my_accounts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List user's accounts"""
        db = next(get_db())
        accounts = db.query(Account).filter_by(user_id=update.effective_user.id).all()
        
        if not accounts:
            await update.message.reply_text("You haven't added any accounts yet.")
        else:
            text = "Your accounts:\n\n"
            for acc in accounts:
                text += f"📱 {acc.phone_number}\n"
                text += f"Status: {'✅ Active' if acc.is_active else '❌ Inactive'}\n"
                text += f"Reports: {acc.reports_count}\n"
                text += f"Last report: {acc.last_report_time or 'Never'}\n\n"
            
            await update.message.reply_text(text)
        db.close()
    
    async def add_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add target to report"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /addtarget <type> <username/id>\n"
                "Types: group, channel, user\n"
                "Example: /addtarget channel @spam_channel"
            )
            return
        
        target_type = context.args[0].lower()
        target_id = context.args[1]
        
        db = next(get_db())
        
        # Check if user has enough coins (1 coin per target)
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if user.coins < 1:
            await update.message.reply_text("You don't have enough coins!")
            db.close()
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
        
        await update.message.reply_text(f"Target {target_id} added successfully!")
        db.close()
    
    async def list_targets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all report targets"""
        db = next(get_db())
        targets = db.query(ReportTarget).filter_by(is_active=True).all()
        
        if not targets:
            await update.message.reply_text("No active targets.")
        else:
            text = "Active targets:\n\n"
            for t in targets:
                text += f"🔴 {t.target_type}: {t.target_id}\n"
            await update.message.reply_text(text)
        db.close()
    
    async def start_reporting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the reporting process"""
        if update.effective_user.id in reporting_tasks:
            await update.message.reply_text("Reporting is already running!")
            return
        
        db = next(get_db())
        
        # Check if user has accounts
        accounts = db.query(Account).filter_by(
            user_id=update.effective_user.id,
            is_active=True
        ).all()
        
        targets = db.query(ReportTarget).filter_by(is_active=True).all()
        
        if not accounts:
            await update.message.reply_text("You need to add accounts first!")
            db.close()
            return
        
        if not targets:
            await update.message.reply_text("You need to add targets first!")
            db.close()
            return
        
        # Start reporting task
        task = asyncio.create_task(
            self.report_loop(update.effective_user.id, accounts, targets, db)
        )
        reporting_tasks[update.effective_user.id] = task
        
        await update.message.reply_text(
            f"Reporting started!\n"
            f"Accounts: {len(accounts)}\n"
            f"Targets: {len(targets)}\n"
            f"Interval: {REPORT_INTERVAL} seconds"
        )
        db.close()
    
    async def report_loop(self, user_id, accounts, targets, db):
        """Main reporting loop"""
        account_index = 0
        target_index = 0
        
        while user_id in reporting_tasks:
            try:
                # Get current account and target
                account = accounts[account_index]
                target = targets[target_index]
                
                # Check account cooldown
                if account.last_report_time:
                    time_diff = datetime.utcnow() - account.last_report_time
                    if time_diff.total_seconds() < 3600:  # 1 hour cooldown
                        account_index = (account_index + 1) % len(accounts)
                        continue
                
                # Perform report using Telethon
                client = TelegramClient(
                    StringSession(self.decrypt_session(account.session_string)),
                    api_id,
                    api_hash
                )
                await client.connect()
                
                try:
                    # Report logic here
                    # This is where you'd implement the actual reporting
                    # Note: Implementing actual reporting might violate Telegram ToS
                    
                    # Update account stats
                    account.reports_count += 1
                    account.last_report_time = datetime.utcnow()
                    
                    # Save report record
                    report = Report(
                        account_id=account.id,
                        target_type=target.target_type,
                        target_id=target.target_id
                    )
                    db.add(report)
                    db.commit()
                    
                finally:
                    await client.disconnect()
                
                # Move to next account and target
                account_index = (account_index + 1) % len(accounts)
                target_index = (target_index + 1) % len(targets)
                
                # Wait for next report
                await asyncio.sleep(REPORT_INTERVAL)
                
            except Exception as e:
                logger.error(f"Reporting error: {e}")
                await asyncio.sleep(10)
    
    async def stop_reporting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop the reporting process"""
        if update.effective_user.id in reporting_tasks:
            reporting_tasks[update.effective_user.id].cancel()
            del reporting_tasks[update.effective_user.id]
            await update.message.reply_text("Reporting stopped!")
        else:
            await update.message.reply_text("No active reporting!")
    
    async def check_coins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check user's coins"""
        db = next(get_db())
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        await update.message.reply_text(f"You have {user.coins} coins.")
        db.close()
    
    async def add_coins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command to add coins to user"""
        if update.effective_user.id not in ADMIN_IDS and update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Unauthorized!")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /addcoins <user_id> <amount>")
            return
        
        try:
            user_id = int(context.args[0])
            amount = int(context.args[1])
            
            db = next(get_db())
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user:
                user.coins += amount
                db.commit()
                await update.message.reply_text(f"Added {amount} coins to user {user_id}")
            else:
                await update.message.reply_text("User not found!")
            db.close()
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    
    async def add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Owner command to add admin"""
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Only owner can use this command!")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /addadmin <user_id>")
            return
        
        try:
            user_id = int(context.args[0])
            db = next(get_db())
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user:
                user.is_admin = True
                db.commit()
                await update.message.reply_text(f"User {user_id} is now admin!")
            else:
                await update.message.reply_text("User not found!")
            db.close()
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    
    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users"""
        if update.effective_user.id not in ADMIN_IDS and update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Unauthorized!")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /broadcast <message>")
            return
        
        message = ' '.join(context.args)
        
        db = next(get_db())
        users = db.query(User).all()
        
        success = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 Broadcast:\n\n{message}"
                )
                success += 1
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                logger.error(f"Failed to send to {user.telegram_id}: {e}")
        
        await update.message.reply_text(f"Broadcast sent to {success}/{len(users)} users!")
        db.close()
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        # Handle different callbacks
        data = query.data
        # Implement button logic here
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        help_text = """
🤖 Bot Commands:

User Commands:
/start - Start the bot
/help - Show this help
/addaccount - Add Telegram account
/myaccounts - List your accounts
/addtarget - Add target to report
/targets - List targets
/startreport - Start reporting
/stopreport - Stop reporting
/coins - Check your coins

Admin Commands:
/addcoins - Add coins to user
/broadcast - Broadcast message

Owner Commands:
/addadmin - Add new admin
        """
        await update.message.reply_text(help_text)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation"""
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END
    
    def encrypt_session(self, session_string):
        """Encrypt session string (implement proper encryption)"""
        # TODO: Implement proper encryption
        return session_string
    
    def decrypt_session(self, encrypted_session):
        """Decrypt session string (implement proper decryption)"""
        # TODO: Implement proper decryption
        return encrypted_session
    
    def run(self):
        """Run the bot"""
        self.application.run_polling()

if __name__ == "__main__":
    # Your API credentials from https://my.telegram.org
    api_id = 123456  # Replace with your API ID
    api_hash = "your_api_hash"  # Replace with your API hash
    
    bot = ReportBot()
    bot.run()
