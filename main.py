import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
import requests
import random
from config import TOKEN
from config import CHANNEL_ID

# Встановити логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Функція для отримання випадкового зображення з Danbooru
def get_random_image():
    url = "https://danbooru.donmai.us/posts.json?random=true"
    response = requests.get(url)
    data = response.json()
    if data:
        image_url = data[0]['file_url']
        return image_url
    return None

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Вітаю! Надішліть команду /get_image для отримання випадкового зображення.')

# Команда /get_image
async def get_image(update: Update, context: CallbackContext) -> None:
    image_url = get_random_image()
    if image_url:
        keyboard = [
            [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
            [InlineKeyboardButton("Відхилити", callback_data='reject')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data['current_image'] = image_url
        await update.message.reply_photo(photo=image_url, reply_markup=reply_markup)
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
        image_url = get_random_image()
        if image_url:
            keyboard = [
                [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                [InlineKeyboardButton("Відхилити", callback_data='reject')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.user_data['current_image'] = image_url
            await query.edit_message_media(media=InputMediaPhoto(image_url), reply_markup=reply_markup)
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
