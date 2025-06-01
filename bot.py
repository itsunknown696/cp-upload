import os
import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from redis_utils import (
    is_bot_busy,
    set_bot_busy,
    get_user_state,
    set_user_state,
    clear_user_state,
)
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

# Define conversation states
TXT_FILE, START_LINE, END_LINE, BATCH_NAME, OWNER_NAME, IMAGE_URL = range(6)

BOT_TOKEN = os.getenv('BOT_TOKEN')

def download_image(image_url: str, filename: str) -> bool:
    """Download image from URL"""
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception as e:
        print(f"Error downloading image: {e}")
    return False

def format_message(index: int, name: str, batch_name: str, url: str, owner_name: str) -> str:
    """Format the message with proper spacing and bold formatting"""
    message = (
        f"<b>➭ Index »</b> {index}\n\n"
        f"<b>➭ Title »</b> {name}\n\n"
        f"<b>➭ Batch »</b> {batch_name}\n\n"
        f"<b>➭ Link »</b> {url}\n\n"
        f"<b>➭ Downloaded By »</b> {owner_name}\n\n"
        "━━━━━━━✦✗✦━━━━━━━"
    )
    return message

def process_url(url: str) -> str:
    """Process URL based on file type"""
    if '.m3u8' in url:
        encoded_url = urllib.parse.quote(url, safe='')
        return f'https://master-api-v3.vercel.app/nomis-player?url={encoded_url}'
    return url

def start(update: Update, context: CallbackContext) -> int:
    if is_bot_busy():
        update.message.reply_text("⚠️ Bot is currently processing another request. Please try again later.")
        return ConversationHandler.END
    
    set_bot_busy(True)
    user_id = update.effective_user.id
    clear_user_state(user_id)
    
    update.message.reply_text(
        "📁 Send me your TXT file in the format 'name:url'"
    )
    return TXT_FILE

def handle_txt_file(update: Update, context: CallbackContext) -> int:
    if not update.message.document:
        update.message.reply_text("Please send a TXT file.")
        return TXT_FILE
    
    user_id = update.effective_user.id
    file = update.message.document.get_file()
    
    file_path = f"user_{user_id}.txt"
    file.download(file_path)
    
    with open(file_path, 'r') as f:
        total_lines = sum(1 for _ in f)
    
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
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    try:
        start_line = int(update.message.text)
        total_lines = user_state['total_lines']
        
        if start_line < 1 or start_line > total_lines:
            update.message.reply_text(f"Please enter a number between 1 and {total_lines}")
            return START_LINE
            
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
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    try:
        end_line = int(update.message.text)
        start_line = user_state['start_line']
        total_lines = user_state['total_lines']
        
        if end_line < start_line or end_line > total_lines:
            update.message.reply_text(f"Please enter a number between {start_line} and {total_lines}")
            return END_LINE
            
        user_state['end_line'] = end_line
        user_state['current_state'] = END_LINE
        set_user_state(user_id, user_state)
        
        update.message.reply_text("📛 Now send me batch name")
        return BATCH_NAME
    except ValueError:
        update.message.reply_text("Please enter a valid number")
        return END_LINE

def handle_batch_name(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    batch_name = update.message.text
    
    user_state['batch_name'] = batch_name
    user_state['current_state'] = BATCH_NAME
    set_user_state(user_id, user_state)
    
    update.message.reply_text("👤 Now send me owner name")
    return OWNER_NAME

def handle_owner_name(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    owner_name = update.message.text
    user_state['owner_name'] = owner_name
    user_state['current_state'] = OWNER_NAME
    set_user_state(user_id, user_state)
    
    update.message.reply_text("🖼️ Now send me image URL (or /skip to continue without image)")
    return IMAGE_URL

def handle_image_url(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    if update.message.text.lower() == '/skip':
        user_state['image_path'] = None
        set_user_state(user_id, user_state)
        return process_and_send(update, context)
    
    image_url = update.message.text
    image_path = f"user_{user_id}_image.jpg"
    
    if download_image(image_url, image_path):
        user_state['image_path'] = image_path
        set_user_state(user_id, user_state)
    else:
        update.message.reply_text("❌ Failed to download image. Please try another URL or /skip")
        return IMAGE_URL
    
    return process_and_send(update, context)

def process_and_send(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    file_path = user_state['file_path']
    start_line = user_state['start_line']
    end_line = user_state['end_line']
    batch_name = user_state['batch_name']
    owner_name = user_state['owner_name']
    image_path = user_state.get('image_path')
    
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        selected_lines = lines[start_line-1:end_line]
        
        for index, line in enumerate(selected_lines, start=1):
            if ':' in line:
                name, url = line.strip().split(':', 1)
                url = url.strip()
                processed_url = process_url(url)
                
                message = format_message(index, name, batch_name, processed_url, owner_name)
                
                if image_path and os.path.exists(image_path):
                    with open(image_path, 'rb') as img:
                        update.message.reply_photo(
                            photo=img,
                            caption=message,
                            parse_mode='HTML'
                        )
                else:
                    update.message.reply_text(
                        message,
                        parse_mode='HTML'
                    )
        
        update.message.reply_text(f"✅ Successfully processed {len(selected_lines)} items!")
    
    except Exception as e:
        update.message.reply_text(f"❌ Error processing file: {str(e)}")
    
    finally:
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        clear_user_state(user_id)
        set_bot_busy(False)
    
    return ConversationHandler.END

def stop(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    
    if user_state:
        if 'file_path' in user_state and os.path.exists(user_state['file_path']):
            os.remove(user_state['file_path'])
        if 'image_path' in user_state and os.path.exists(user_state['image_path']):
            os.remove(user_state['image_path'])
    
    clear_user_state(user_id)
    set_bot_busy(False)
    update.message.reply_text('🛑 Operation stopped.')
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    return stop(update, context)

def error_handler(update: Update, context: CallbackContext):
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
            IMAGE_URL: [
                MessageHandler(Filters.text & ~Filters.command, handle_image_url),
                CommandHandler('skip', handle_image_url),
            ],
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
