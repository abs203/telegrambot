from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler
from datetime import datetime, timedelta
from telegram.error import BadRequest, Unauthorized
import logging
import sqlite3
import qrcode
from io import BytesIO
import os
# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Admin user ID
admin_id = 869258827

# Initialize SQLite database


def create_connection():
    # Get the directory path of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Join the directory path with the database file name
    db_path = os.path.join(script_dir, 'bot_database.db')
    return sqlite3.connect(db_path)


# Create table if not exists
def create_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    ''')
    conn.commit()

# Load groups from the database into memory
def load_groups():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM groups')
    return {group[0]: group[1] for group in cursor.fetchall()}

groups = load_groups()

# Command handler for /start command
def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id == admin_id:
        valid_groups = {}
        for group_id, group_name in groups.items():
            try:
                member_status = context.bot.get_chat_member(group_id, context.bot.id).status
                if member_status != 'left':
                    valid_groups[group_id] = group_name
            except (BadRequest, Unauthorized) as e:
                # Ignore BadRequest (Chat not found) and Unauthorized (bot kicked) exceptions
                pass
        
        buttons = [
            [KeyboardButton(group_name)]
            for group_id, group_name in valid_groups.items()
        ]
        
        # Create ReplyKeyboardMarkup with the buttons
        reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
        # Send the keyboard directly as a reply to the user
        update.message.reply_text("Here are the groups:", reply_markup=reply_markup)

# Custom callback function for button clicks
def button_click(update: Update, context: CallbackContext) -> None:
    selected_group_name = update.message.text
    selected_group_id = None
    for group_id, group_name in groups.items():
        if group_name == selected_group_name:
            selected_group_id = group_id
            break
    
    if selected_group_id:
        # Call the join_group function with the selected group ID
        join_group(update, context, selected_group_id)
    else:
        update.message.reply_text("Invalid group selection.")

# Join group function triggered by button click
def join_group(update: Update, context: CallbackContext, group_id: int) -> None:
    group_name = groups[group_id]
    try:
        # Generate a temporary invite link
        invite_link = context.bot.export_chat_invite_link(group_id)
        expiry_date = datetime.now() + timedelta(days=1)  # Link valid for one day
        invite_text = f"Join {group_name} with this temporary invite link, valid until {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}:\n{invite_link}"
        
        # Generate QR code for the invite link
        qr = qrcode.make(invite_link)
        qr_bytes = BytesIO()
        qr.save(qr_bytes, format='PNG')
        qr_bytes.seek(0)
        
        # Send the invite link and QR code to the admin who clicked the button
        context.bot.send_message(chat_id=admin_id, text=invite_text)
        context.bot.send_photo(chat_id=admin_id, photo=qr_bytes, caption="Scan this QR code to join the group")

        # Wait for one user to join the group
        context.job_queue.run_once(lambda c: revoke_invite_link(update, context, group_id, invite_link), 60)
    except Exception as e:
        logging.error(f"Error generating invite link: {e}")

# Function to revoke invite link after one user joins
def revoke_invite_link(update: Update, context: CallbackContext, group_id: int, invite_link: str) -> None:
    # Revoke the invite link
    context.bot.revoke_chat_invite_link(group_id, invite_link)

# Handler to capture group information when added as admin
def capture_group(update: Update, context: CallbackContext) -> None:
    if update.message.chat.type == "group" or update.message.chat.type == "supergroup":
        group_id = update.message.chat.id
        group_name = update.message.chat.title
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (group_id, group_name))
        conn.commit()
        groups[group_id] = group_name

def main() -> None:
    updater = Updater("7141687496:AAF9SvsZ9311rSPkXV9TVXIyo899xHk0Ll4")
    dispatcher = updater.dispatcher

    # Handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, button_click))
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, capture_group))

    logging.info("Bot started polling.")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
