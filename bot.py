import os
import re
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)
from redis_utils import (
    is_bot_busy,
    set_bot_busy,
    get_user_state,
    set_user_state,
    clear_user_state,
)
from dotenv import load_dotenv

load_dotenv()

# Define conversation states
TXT_FILE, START_LINE, END_LINE, BATCH_NAME, OWNER_NAME = range(5)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')

def start(update: Update, context: CallbackContext) -> int:
    """Start command handler"""
    if is_bot_busy():
        update.message.reply_text("⚠️ Bot is currently processing another request. Please try again later.")
        return ConversationHandler.END
    
    set_bot_busy(True)
    user_id = update.effective_user.id
    clear_user_state(user_id)  # Clear any previous state
    
    update.message.reply_text(
        "📁 Send me your TXT file in the format 'name:url'"
    )
    return TXT_FILE

def stop(update: Update, context: CallbackContext) -> int:
    """Stop command handler"""
    user_id = update.effective_user.id
    clear_user_state(user_id)
    set_bot_busy(False)
    update.message.reply_text("🛑 Current operation stopped.")
    return ConversationHandler.END

def handle_txt_file(update: Update, context: CallbackContext) -> int:
    """Handle TXT file upload"""
    if not update.message.document:
        update.message.reply_text("Please send a TXT file.")
        return TXT_FILE
    
    user_id = update.effective_user.id
    file = update.message.document.get_file()
    
    # Download the file
    file_path = f"user_{user_id}.txt"
    file.download(file_path)
    
    # Count total lines
    with open(file_path, 'r') as f:
        total_lines = sum(1 for _ in f)
    
    # Save state
    set_user_state(user_id, {
        'file_path': file_path,
        'total_lines': total_lines,
        'current_state': TXT_FILE
    })
    
    update.message.reply_text(
        f"📊 Total Lines: {total_lines}\n\n🔢 Now send from where you want to start (line number)"
    )
    return START_LINE

def handle_start_line(update: Update, context: CallbackContext) -> int:
    """Handle start line input"""
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    try:
        start_line = int(update.message.text)
        total_lines = user_state['total_lines']
        
        if start_line < 1 or start_line > total_lines:
            update.message.reply_text(f"Please enter a number between 1 and {total_lines}")
            return START_LINE
            
        # Update state
        user_state['start_line'] = start_line
        user_state['current_state'] = START_LINE
        set_user_state(user_id, user_state)
        
        update.message.reply_text(
            f"🔢 Now send up to where you want (line number, max {total_lines})"
        )
        return END_LINE
    except ValueError:
        update.message.reply_text("Please enter a valid number")
        return START_LINE

def handle_end_line(update: Update, context: CallbackContext) -> int:
    """Handle end line input"""
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    try:
        end_line = int(update.message.text)
        start_line = user_state['start_line']
        total_lines = user_state['total_lines']
        
        if end_line < start_line or end_line > total_lines:
            update.message.reply_text(f"Please enter a number between {start_line} and {total_lines}")
            return END_LINE
            
        # Update state
        user_state['end_line'] = end_line
        user_state['current_state'] = END_LINE
        set_user_state(user_id, user_state)
        
        update.message.reply_text("📛 Now send me batch name")
        return BATCH_NAME
    except ValueError:
        update.message.reply_text("Please enter a valid number")
        return END_LINE

def handle_batch_name(update: Update, context: CallbackContext) -> int:
    """Handle batch name input"""
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    batch_name = update.message.text
    
    # Update state
    user_state['batch_name'] = batch_name
    user_state['current_state'] = BATCH_NAME
    set_user_state(user_id, user_state)
    
    update.message.reply_text("👤 Now send me owner name")
    return OWNER_NAME

def handle_owner_name(update: Update, context: CallbackContext) -> int:
    """Handle owner name input and process the file"""
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    owner_name = update.message.text
    file_path = user_state['file_path']
    start_line = user_state['start_line']
    end_line = user_state['end_line']
    batch_name = user_state['batch_name']
    
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        selected_lines = lines[start_line-1:end_line]
        
        for index, line in enumerate(selected_lines, start=1):
            if ':' in line:
                name, url = line.strip().split(':', 1)
                url = url.strip()
                
                if 'playlist.m3u8' in url:
                    formatted_url = f'https://master-api-v3.vercel.app/nomis-player?url={url}'
                else:
                    formatted_url = url
                
                message = (
                    f"➭ Index » {index}\n"
                    f"➭ Title » {name}\n"
                    f"➭ Batch » {batch_name}\n"
                    f"➭ Link » {formatted_url}\n"
                    f"➭ Downloaded By » {owner_name}\n"
                    "━━━━━━━✦✗✦━━━━━━━"
                )
                
                update.message.reply_text(message)
        
        update.message.reply_text(f"✅ Successfully processed {len(selected_lines)} items!")
    
    except Exception as e:
        update.message.reply_text(f"❌ Error processing file: {str(e)}")
    
    finally:
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        clear_user_state(user_id)
        set_bot_busy(False)
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current operation"""
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    if user_state and 'file_path' in user_state:
        file_path = user_state['file_path']
        if os.path.exists(file_path):
            os.remove(file_path)
    
    clear_user_state(user_id)
    set_bot_busy(False)
    update.message.reply_text('🛑 Operation cancelled.')
    return ConversationHandler.END

def error_handler(update: Update, context: CallbackContext):
    """Handle errors"""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id:
        clear_user_state(user_id)
    set_bot_busy(False)
    
    if update.message:
        update.message.reply_text('⚠️ An error occurred. Please try again.')

def main():
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('txt', start),
        ],
        states={
            TXT_FILE: [MessageHandler(Filters.document.category("text/plain"), handle_txt_file)],
            START_LINE: [MessageHandler(Filters.text & ~Filters.command, handle_start_line)],
            END_LINE: [MessageHandler(Filters.text & ~Filters.command, handle_end_line)],
            BATCH_NAME: [MessageHandler(Filters.text & ~Filters.command, handle_batch_name)],
            OWNER_NAME: [MessageHandler(Filters.text & ~Filters.command, handle_owner_name)],
        },
        fallbacks=[
            CommandHandler('stop', stop),
            CommandHandler('cancel', cancel),
        ],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
