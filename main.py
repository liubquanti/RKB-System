import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
import requests
from datetime import datetime
from config import TOKEN, CHANNEL_ID
from tags import tags  # Імпорт тегів з файлу tags.py
import random

# Встановити логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Функція для отримання випадкового зображення з Danbooru з врахуванням тегів
def get_random_image():
    selected_tag = random.choice(tags)
    url = f"https://danbooru.donmai.us/posts.json?tags={selected_tag}&random=true"
    response = requests.get(url)
    data = response.json()
    if data:
        image_data = data[0]
        image_url = image_data.get('file_url')
        published_at = image_data.get('created_at')
        tag_string_character = image_data.get('tag_string_character', '')
        characters = tag_string_character.replace(' ', ', ')
        return image_url, published_at, characters
    return None, None, None

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Вітаю! Надішліть команду /get_image для отримання випадкового зображення.')

# Команда /get_image
async def get_image(update: Update, context: CallbackContext) -> None:
    image_url, published_at, characters = get_random_image()
    if image_url:
        keyboard = [
            [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
            [InlineKeyboardButton("Відхилити", callback_data='reject')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формуємо текст опису зображення з додаванням часу публікації та персонажів
        caption = f"Час публікації: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\nПерсонажі: {characters if characters else 'Немає персонажів'}"
        
        context.user_data['current_image'] = image_url
        await update.message.reply_photo(photo=image_url, caption=caption, reply_markup=reply_markup)
    else:
        await update.message.reply_text('Не вдалося отримати зображення. Спробуйте ще раз.')

# Обробка натискання кнопок
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm':
        image_url = context.user_data.get('current_image')
        if image_url:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url)
            await query.edit_message_text(text="Зображення підтверджено та опубліковано.")
    elif query.data == 'reject':
        image_url, published_at, characters = get_random_image()
        if image_url:
            keyboard = [
                [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                [InlineKeyboardButton("Відхилити", callback_data='reject')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Формуємо текст опису зображення з додаванням часу публікації та персонажів
            caption = f"Час публікації: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\nПерсонажі: {characters if characters else 'Немає персонажів'}"
            
            context.user_data['current_image'] = image_url
            await query.edit_message_media(media=InputMediaPhoto(image_url, caption=caption), reply_markup=reply_markup)
        else:
            await query.edit_message_text(text='Не вдалося отримати зображення. Спробуйте ще раз.')

# Основна функція
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_image", get_image))
    application.add_handler(CallbackQueryHandler(button))

    application.run_polling()

if __name__ == '__main__':
    main()
