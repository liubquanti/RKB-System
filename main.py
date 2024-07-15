import logging
import re
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
import requests
from datetime import datetime
from config import TOKEN, CHANNEL_ID
from tags import tags  # Імпорт тегів з файлу tags.py
from banned import banned_tags
import random
import time

# Встановити логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Функція для перевірки доступності зображення
def is_image_accessible(url):
    try:
        response = requests.head(url)
        return response.status_code == 200
    except requests.RequestException:
        return False

# Функція для отримання випадкового зображення з Danbooru з врахуванням всіх тегів
def get_random_image():
    all_tags = ' '.join(tags)  # Об'єднати всі теги в один рядок
    url = f"https://danbooru.donmai.us/posts.json?tags={all_tags}&random=true"
    
    for _ in range(10):  # Максимум 10 спроб знайти зображення без забанених тегів
        response = requests.get(url)
        data = response.json()
        
        if isinstance(data, list) and data:
            random.shuffle(data)  # Перемішати результати для додаткової випадковості
            
            for image_data in data:
                image_url = image_data.get('file_url')
                tag_string = image_data.get('tag_string', '')

                # Перевірити, чи містить тег забанені теги
                if any(banned_tag in tag_string for banned_tag in banned_tags):
                    continue

                if is_image_accessible(image_url):
                    published_at = image_data.get('created_at')
                    tag_string_character = image_data.get('tag_string_character', '')
                    characters = tag_string_character.replace(' ', ', ')
                    copyright_info = image_data.get('tag_string_copyright', '')
                    return image_url, published_at, characters, copyright_info

    return None, None, None, None

# Функція для очищення імен персонажів
def clean_character_name(name):
    return re.sub(r'_?\([^)]*\)', '', name)

# Оновлення файлу tags.py
def update_tags_file():
    with open("tags.py", "w") as file:
        file.write("tags = [\n")
        for tag in tags:
            file.write(f'    "{tag}",\n')
        file.write("]\n")

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Вітаю! Надішліть команду /get_image для отримання випадкового зображення.\n'
                                    'Для додавання тегу використайте команду /add_tag <tag>.\n'
                                    'Для видалення тегу використайте команду /remove_tag <tag>.\n'
                                    'Для перегляду всіх тегів використайте команду /list_tags.')

# Команда /get_image
async def get_image(update: Update, context: CallbackContext) -> None:
    image_url, published_at, characters, copyright_info = get_random_image()
    if image_url:
        keyboard = [
            [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
            [InlineKeyboardButton("Відхилити", callback_data='reject')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
        character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
        
        cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
        copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)
        
        hashtags = character_hashtags + ' ' + copyright_hashtags
        
        caption = (
            f"Час публікації: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Теги: {hashtags if hashtags else 'Немає тегів'}"
        )
        channel_caption = (
            f"Теги: {hashtags if hashtags else 'Немає тегів'}"
        )
        
        context.user_data['current_image'] = image_url
        context.user_data['current_caption'] = caption
        context.user_data['current_channel_caption'] = channel_caption
        await update.message.reply_photo(photo=image_url, caption=caption, reply_markup=reply_markup)
    else:
        await update.message.reply_text('Не вдалося отримати зображення. Спробуйте ще раз.')

# Обробка натискання кнопок
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm':
        image_url = context.user_data.get('current_image')
        caption = context.user_data.get('current_caption')
        channel_caption = context.user_data.get('current_channel_caption')
        if image_url:
            try:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption)
                try:
                    await query.edit_message_text(text="Зображення підтверджено та опубліковано.")
                except Exception as e:
                    logger.error(f"Failed to edit message text: {e}")
            except Exception as e:
                logger.error(f"Failed to send photo: {e}")
                try:
                    await query.edit_message_text(text="Не вдалося опублікувати зображення.")
                except Exception as e:
                    logger.error(f"Failed to edit message text: {e}")
    elif query.data == 'reject':
        max_retries = 5
        for attempt in range(max_retries):
            image_url, published_at, characters, copyright_info = get_random_image()
            if image_url:
                keyboard = [
                    [InlineKeyboardButton("Підтвердити", callback_data='confirm')],
                    [InlineKeyboardButton("Відхилити", callback_data='reject')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
                character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
                
                cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
                copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)
                
                hashtags = character_hashtags + ' ' + copyright_hashtags
                
                caption = (
                    f"Час публікації: {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Теги: {hashtags if hashtags else 'Немає тегів'}"
                )
                channel_caption = (
                    f"Теги: {hashtags if hashtags else 'Немає тегів'}"
                )
                
                context.user_data['current_image'] = image_url
                context.user_data['current_caption'] = caption
                context.user_data['current_channel_caption'] = channel_caption
                try:
                    await query.edit_message_media(media=InputMediaPhoto(image_url, caption=caption), reply_markup=reply_markup)
                    break
                except Exception as e:
                    logger.error(f"Failed to edit message media (attempt {attempt+1}/{max_retries}): {e}")
                    time.sleep(1)  # Затримка перед повторною спробою
            else:
                logger.error(f"Failed to get image (attempt {attempt+1}/{max_retries})")
                time.sleep(1)  # Затримка перед повторною спробою
        else:
            try:
                await query.edit_message_text(text='Не вдалося отримати зображення. Спробуйте ще раз.')
            except Exception as e:
                logger.error(f"Failed to edit message text: {e}")

# Команда /add_tag
async def add_tag(update: Update, context: CallbackContext) -> None:
    tag = ' '.join(context.args)
    if tag:
        if tag not in tags:
            tags.append(tag)
            update_tags_file()
            await update.message.reply_text(f'Tег "{tag}" успішно додано.')
        else:
            await update.message.reply_text(f'Tег "{tag}" вже існує.')
    else:
        await update.message.reply_text('Будь ласка, вкажіть тег для додавання.')

# Команда /remove_tag
async def remove_tag(update: Update, context: CallbackContext) -> None:
    tag = ' '.join(context.args)
    if tag:
        if tag in tags:
            tags.remove(tag)
            update_tags_file()
            await update.message.reply_text(f'Tег "{tag}" успішно видалено.')
        else:
            await update.message.reply_text(f'Tег "{tag}" не знайдено.')
    else:
        await update.message.reply_text('Будь ласка, вкажіть тег для видалення.')

# Команда /list_tags
async def list_tags(update: Update, context: CallbackContext) -> None:
    if tags:
        await update.message.reply_text('Список тегів:\n' + '\n'.join(tags))
    else:
        await update.message.reply_text('Список тегів порожній.')

# Основна функція
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start",start))
    application.add_handler(CommandHandler("get_image", get_image))
    application.add_handler(CommandHandler("add_tag", add_tag))
    application.add_handler(CommandHandler("remove_tag", remove_tag))
    application.add_handler(CommandHandler("list_tags", list_tags))
    application.add_handler(CallbackQueryHandler(button))

    # Реєстрація обробника помилок
    application.add_error_handler(error_handler)

    application.run_polling()

# Обробник помилок
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

if __name__ == '__main__':
    main()
