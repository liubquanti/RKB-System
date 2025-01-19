import re
import os
import random
import time
import asyncio
import schedule
from colorama import Fore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, filters
import requests
from datetime import datetime, timedelta
from config import TOKEN, CHANNEL_ID, ALLOWED_USER_ID, MODE
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('firebase.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

async def is_post_published(post_id):
    doc_ref = db.collection('published').document('arts')
    doc = doc_ref.get()
    if doc.exists:
        published_ids = doc.to_dict().get('ids', [])
        return str(post_id) in published_ids
    return False

async def save_published_post(post_id):
    doc_ref = db.collection('published').document('arts')
    doc = doc_ref.get()
    if doc.exists:
        published_ids = doc.to_dict().get('ids', [])
    else:
        published_ids = []
    
    if str(post_id) not in published_ids:
        published_ids.append(str(post_id))
        doc_ref.set({'ids': published_ids})

def is_image_accessible(url):
    try:
        response = requests.head(url)
        return response.status_code == 200
    except requests.RequestException:
        return False

async def get_random_image():
    random_tag = random.choice(tags)
    url = f"https://danbooru.donmai.us/posts.json?tags={random_tag}&random=true"

    for _ in range(10):
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"{Fore.RED}[WRN] Не вдалося отримати дані фото: {e}{Fore.RESET}")
            continue

        if not isinstance(data, list) or not data:
            continue

        random.shuffle(data)

        for image_data in data:
            image_url = image_data.get('file_url')
            tag_string = image_data.get('tag_string', '')
            rating = image_data.get('rating', '')
            post_id = image_data.get('id')

            if await check_published_post(post_id):
                continue

            if any(banned_tag in tag_string for banned_tag in banned_tags):
                continue

            if any(rating_tag in rating for rating_tag in rating_tags):
                continue

            if not any(necessary_tag in tag_string for necessary_tag in necessary_tags):
                continue

            if is_image_accessible(image_url):
                return (
                    image_url,
                    image_data.get('created_at'),
                    image_data.get('tag_string_character', '').replace(' ', ', '),
                    image_data.get('tag_string_copyright', ''),
                    rating,
                    image_data.get('tag_string_general', ''),
                    post_id,
                    image_data.get('tag_string_artist', '')
                )

    return None, None, None, None, None, None, None, None

async def check_published_post(post_id):
    doc_ref = db.collection('published').document('arts')
    doc = doc_ref.get()
    if doc.exists:
        published_ids = doc.to_dict().get('ids', [])
        return str(post_id) in published_ids
    return False

async def save_published_post(post_id):
    doc_ref = db.collection('published').document('arts')
    doc = doc_ref.get()
    if doc.exists:
        published_ids = doc.to_dict().get('ids', [])
    else:
        published_ids = []
    
    if str(post_id) not in published_ids:
        published_ids.append(str(post_id))
        doc_ref.set({'ids': published_ids})

def clean_character_name(name):
    return (name)

def clean_character_name_publish(name):
    cleaned_name = re.sub(r'\([^)]*\)', '', name)
    cleaned_name = cleaned_name.replace('/', '_')
    cleaned_name = re.sub(r'[^a-zA-Z0-9_]', '', cleaned_name)
    cleaned_name = '_'.join(word.capitalize() if word.islower() else word for word in cleaned_name.split('_'))
    return cleaned_name.rstrip('_')

async def get_tags_from_firestore(collection_name):
    doc_ref = db.collection(collection_name).document('tags')
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get('tags', [])
    return []

async def update_tags_in_firestore(collection_name, tags_list):
    doc_ref = db.collection(collection_name).document('tags')
    doc_ref.set({'tags': tags_list})

async def update_tags_file():
    await update_tags_in_firestore('tags', tags)

async def update_banned_tags_file():
    await update_tags_in_firestore('banned', banned_tags)

async def initialize_tags():
    global tags, banned_tags, necessary_tags, rating_tags
    tags = await get_tags_from_firestore('tags')
    banned_tags = await get_tags_from_firestore('banned')
    necessary_tags = await get_tags_from_firestore('necessary')
    rating_tags = await get_rating_tags_from_firestore()

async def get_rating_tags_from_firestore():
    doc_ref = db.collection('rating').document('tags')
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        return [tag for tag in ['e', 'g', 'q', 's'] if data.get(tag, False)]
    return []

async def update_rating_tags_in_firestore(rating_tags):
    doc_ref = db.collection('rating').document('tags')
    data = {
        'e': 'e' in rating_tags,
        'g': 'g' in rating_tags,
        'q': 'q' in rating_tags,
        's': 's' in rating_tags
    }
    doc_ref.set(data)

async def delete_message_later(context: CallbackContext, message_id: int, chat_id: int, delay: int = 1):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"{Fore.RED}[WRN] Не вдалося видалити повідомлення: {e}{Fore.RESET}")

def is_user_allowed(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID

async def start(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        args = context.args
        if args:
            post_id = args[0]
            url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                image_url = data.get('file_url')
                if image_url and is_image_accessible(image_url):
                    await update.message.reply_text('🤗  •  Надсилаємо вам арт!')
                    await update.message.reply_document(document=image_url)
                    user_name = update.effective_user.full_name
                    await context.bot.send_message(chat_id=ALLOWED_USER_ID, text=f"👀  •  Користувач {user_name} (<a href='tg://user?id={update.effective_user.id}'>{update.effective_user.id}</a>) отримав <a href='https://t.me/rkbsystem_bot?start={post_id}'>фото</a>.", parse_mode='HTML')
                    return
            except (requests.RequestException, ValueError) as e:
                print(f"{Fore.RED}[WRN] Не вдалося отримати дані фото: {e}{Fore.RESET}")
        await update.message.reply_text('🍓  •  Вітаю в системі RKB!\n\n😨  •  Схоже, що Ви прийшли не з нашого каналу. Цей бот призначений, щоб швидко отримувати арти без стиснення, які публікуються в потоці @rkbsystem.\n\n👀  •  Якщо Ви прийшли за артами, то радимо підписатися на канал @rkbsystem. І пізніше зможете тут отримати роботи, які Вам сподобаються.')
    if not is_user_allowed(update):
        return
    args = context.args
    if args:
        post_id = args[0]
        url = f"https://danbooru.donmai.us/posts/{post_id}.json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            image_url = data.get('file_url')
            if image_url and is_image_accessible(image_url):
                await update.message.reply_document(document=image_url)
                return
        except (requests.RequestException, ValueError) as e:
            print(f"{Fore.RED}[WRN] Не вдалося отримати дані фото: {e}{Fore.RESET}")
    await update.message.reply_text('🍓  •  Вітаю в системі RKB!\n'
                                    '\n'
                                    '🔎  •  Знайти арт: /get_image.\n'
                                    '\n'
                                    '➕  •  Додати тег: /add_tag <tag>.\n'
                                    '➖  •  Видалити тег: /remove_tag <tag>.\n'
                                    '🚫  •  Заблокувати тег: /block_tag <tag>.\n'
                                    '✅  •  Розблокувати тег: /unblock_tag <tag>.\n'
                                    '📃  •  Всі теги: /list_tags.')
    
async def publish_image(application: Application) -> None:
    max_retries = 5
    
    for attempt in range(max_retries):
        image_data = await get_random_image()
        if not image_data[0]:
            print(f"{Fore.RED}[WRN] Не вдалося отримати фото (спроба {attempt+1}/{max_retries}){Fore.RESET}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            schedule_next_job(application)
            return

        image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = image_data

        cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
        character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)

        cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
        copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)

        cleaned_characters_publish = {clean_character_name_publish(char) for char in characters.split(', ')}
        character_hashtags_publish = ' '.join(f"#{char}" for char in cleaned_characters_publish)

        cleaned_copyrights_publish = {clean_character_name_publish(copyright) for copyright in copyright_info.split(' ')}
        copyright_hashtags_publish = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights_publish)

        rating = {
            'g': '🟢  •  #general',
            's': '🟡  •  #sensetive', 
            'q': '🟠  •  #questionable',
            'e': '🔴  •  #explicit'
        }.get(rating, rating)

        channel_hashtags = '\n'.join(f"🎭  •  #{char}" for char in cleaned_characters_publish) + '\n' + \
                        '\n'.join(f"🌐  •  #{copyright}" for copyright in cleaned_copyrights_publish) + \
                        f"\n\n✒️  •  <a href='https://t.me/rkbsystem_bot?start={post_id}'>Арт без стиснення</a>\n\n🍓  •  <a href='https://t.me/rkbsystem'>Підписатися на RKBS</a>"
        
        channel_caption = channel_hashtags if channel_hashtags else 'Немає тегів'

        try:
            await application.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption, parse_mode='HTML')
            await save_published_post(post_id)
            print(f"{Fore.YELLOW}[LOG] Фото успішно опубліковано.{Fore.RESET}")
            break
        except Exception as e:
            print(f"{Fore.RED}[WRN] Не вдалося відправити фото (спроба {attempt+1}/{max_retries}): {e}{Fore.RESET}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue

    schedule_next_job(application)

def schedule_next_job(application: Application) -> None:
    scheduler = application.job_queue.scheduler
    random_minute = random.randint(0, 59)
    now = datetime.now()
    next_run_time = (now + timedelta(hours=random.randint(4, 8))).replace(minute=random_minute, second=0, microsecond=0)
    print(f"{Fore.YELLOW}[LOG] Наступне фото буде відправлено: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}{Fore.RESET}")
    scheduler.add_job(publish_image, 'date', run_date=next_run_time, args=(application,), misfire_grace_time=5)

def start_scheduler(application: Application) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    scheduler = AsyncIOScheduler(event_loop=loop)
    application.job_queue.scheduler = scheduler
    scheduler.start()
    schedule_next_job(application)

async def format_captions(image_data):
    image_url, published_at, characters, copyright_info, rating, tag_string_general, post_id, artist = image_data
    
    cleaned_characters = {clean_character_name(char) for char in characters.split(', ')}
    character_hashtags = ' '.join(f"#{char}" for char in cleaned_characters)
    
    cleaned_characters_publish = {clean_character_name_publish(char) for char in characters.split(', ')}
    character_hashtags_publish = ' '.join(f"#{char}" for char in cleaned_characters_publish)

    cleaned_copyrights = {clean_character_name(copyright) for copyright in copyright_info.split(' ')}
    copyright_hashtags = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights)
    
    cleaned_copyrights_publish = {clean_character_name_publish(copyright) for copyright in copyright_info.split(' ')}
    copyright_hashtags_publish = ' '.join(f"#{copyright}" for copyright in cleaned_copyrights_publish)

    tag_string_general = '\n'.join(f'<code>{tag}</code>' for tag in tag_string_general.split())
    rating = {
        'g': '🟢  •  #general',
        's': '🟡  •  #sensetive',
        'q': '🟠  •  #questionable',
        'e': '🔴  •  #explicit'
    }.get(rating, rating)

    hashtags = f"{character_hashtags}\n🌐  •  {copyright_hashtags}"
    channel_hashtags = (
        '\n'.join(f"🎭  •  #{char}" for char in cleaned_characters_publish) + '\n' +
        '\n'.join(f"🌐  •  #{copyright}" for copyright in cleaned_copyrights_publish) +
        f"\n\n✒️  •  <a href='https://t.me/rkbsystem_bot?start={post_id}'>Арт без стиснення</a>\n\n" +
        f"🍓  •  <a href='https://t.me/rkbsystem'>Підписатися на RKBS</a>"
    )

    post_url = f"https://danbooru.donmai.us/posts/{post_id}"
    main_caption = (
        f"🕒  •  {datetime.fromisoformat(published_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🪶  •  #{artist}\n"
        f"🎭  •  {hashtags if hashtags else 'Немає тегів'}\n"
        f"{rating}\n"
        f"🔗  •  <a href='{post_url}'>Посилання</a>\n"
        f"<blockquote expandable>{tag_string_general}\n</blockquote>"
    )
    channel_caption = channel_hashtags if channel_hashtags else 'Немає тегів'

    return image_url, main_caption, channel_caption

async def get_image(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return

    image_data = await get_random_image()
    if not image_data[0]:
        await update.message.reply_text('Не вдалося отримати зображення. Спробуйте ще раз.')
        return

    image_url, caption, channel_caption = await format_captions(image_data)
    
    context.user_data['current_image'] = image_url
    context.user_data['current_caption'] = caption
    context.user_data['current_channel_caption'] = channel_caption

    keyboard = create_keyboard()
    await update.message.reply_photo(
        photo=image_url,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        show_caption_above_media=True
    )

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    keyboard = create_keyboard()

    async def edit_message_with_retry(attempt, max_retries, image_url, caption, reply_markup, parse_mode, show_caption_above_media):
        try:
            await query.edit_message_media(media=InputMediaPhoto(image_url, caption=caption, parse_mode=parse_mode, show_caption_above_media=show_caption_above_media), reply_markup=reply_markup)
            return True
        except Exception as e:
            print(f"{Fore.RED}[WRN] Не вдалося отримати фото: (спроба {attempt+1}/{max_retries}) {e}{Fore.RESET}")
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"Невдача!\nПочекайте! ({attempt+1}/{max_retries})", callback_data='wait')]]
            ))
            time.sleep(1)
            return False

    if query.data == 'confirm':
        image_url = context.user_data.get('current_image')
        channel_caption = context.user_data.get('current_channel_caption')
        caption = context.user_data.get('current_caption')
        post_id_match = re.search(r'danbooru\.donmai\.us/posts/(\d+)', caption)
        if post_id_match:
            post_id = post_id_match.group(1)
            try:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=channel_caption, parse_mode='HTML')
                await save_published_post(post_id)
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(f"Опубліковано!", callback_data='reject')]]
                ))
                print(f"{Fore.YELLOW}[LOG] Фото опубліковано!{Fore.RESET}")
                time.sleep(1)
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
            except Exception as e:
                print(f"{Fore.RED}[WRN] Не вдалося відправити фото: {e}{Fore.RESET}")
                await query.edit_message_text(text="Не вдалося опублікувати зображення.")
    elif query.data == 'reject':
        max_retries = 5
        for attempt in range(max_retries):
            image_data = await get_random_image()
            if image_data[0]:
                image_url, caption, channel_caption = await format_captions(image_data)
                
                context.user_data['current_image'] = image_url
                context.user_data['current_caption'] = caption
                context.user_data['current_channel_caption'] = channel_caption

                if await edit_message_with_retry(attempt, max_retries, image_url, caption, InlineKeyboardMarkup(create_keyboard()), parse_mode='HTML', show_caption_above_media=True):
                    break
        else:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
    elif query.data == 'block_character':
        characters = context.user_data.get('current_caption').split('\n')[2].replace('🎭  •  ', '').split(' ')
        characters = [char.replace('#', '') for char in characters if char]

        if characters:
            character_buttons = [[InlineKeyboardButton(char, callback_data=f'ban_{char}')] for char in characters]
            character_buttons.append([InlineKeyboardButton("Відмінити", callback_data='cancel')])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(character_buttons))
        else:
            await query.message.reply_text('Немає персонажів для блокування.')
    elif query.data.startswith('ban_'):
        char_to_ban = query.data.split('_', 1)[1]
        if char_to_ban and char_to_ban not in banned_tags:
            banned_tags.append(char_to_ban)
            await update_banned_tags_file()
            response = await query.message.reply_text(f'Персонаж "{char_to_ban}" успішно заблоковано.')
            await delete_message_later(context, response.message_id, response.chat_id, delay=1)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
    elif query.data == 'cancel':
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
    elif query.data.startswith('modify_'):
        tag_to_modify = query.data.split('_')[1][0]
        if tag_to_modify in rating_tags:
            rating_tags.remove(tag_to_modify)
        else:
            rating_tags.append(tag_to_modify)
        await update_rating_tags_in_firestore(rating_tags)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))
        with open("rating.py", "w") as file:
            file.write("rating_tags = [\n")
            for g in rating_tags:
                file.write(f'    "{g}",\n')
            file.write("]\n")
    elif query.data == 'block_author':
        author = context.user_data.get('current_caption').split('\n')[1].replace('🪶  •  #', '')
        if author:
            banned_tags.append(author)
            await update_banned_tags_file()
            response = await query.message.reply_text(f'Автор "{author}" успішно заблоковано.')
            await delete_message_later(context, response.message_id, response.chat_id, delay=1)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(create_keyboard()))

def create_keyboard():
    rating_states = get_rating_states()
    return [
        [InlineKeyboardButton("✅ Підтвердити", callback_data='confirm'),
         InlineKeyboardButton("❌ Відхилити", callback_data='reject')],
        [InlineKeyboardButton("🎭", callback_data='block_character'),
         InlineKeyboardButton("🪶", callback_data='block_author')],
        [InlineKeyboardButton(rating_states["g"], callback_data='modify_general'), 
         InlineKeyboardButton(rating_states["s"], callback_data='modify_sensetive'), 
         InlineKeyboardButton(rating_states["q"], callback_data='modify_questionable'), 
         InlineKeyboardButton(rating_states["e"], callback_data='modify_explicit')]
    ]

def get_rating_states():
    states = {
        "g": "🟢",
        "q": "🟠",
        "s": "🟡",
        "e": "🔴"
    }
    return {tag: "🔘" if tag in rating_tags else states[tag] for tag in states}

async def add_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag not in tags:
            tags.append(tag)
            await update_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно додано.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" вже існує.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для додавання.')

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

async def remove_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag in tags:
            tags.remove(tag)
            await update_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно видалено.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" не знайдено.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для видалення.')

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

async def list_tags(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    if tags:
        await update.message.reply_text('Список тегів:\n' + '\n'.join(tags))
    else:
        await update.message.reply_text('Список тегів порожній.')

async def block_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag not in banned_tags:
            banned_tags.append(tag)
            await update_banned_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно заблоковано.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" вже заблоковано.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для блокування.')

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)

async def unblock_tag(update: Update, context: CallbackContext) -> None:
    if not is_user_allowed(update):
        return
    tag = ' '.join(context.args)
    if tag:
        if tag in banned_tags:
            banned_tags.remove(tag)
            await update_banned_tags_file()
            response = await update.message.reply_text(f'Tег "{tag}" успішно розблоковано.')
        else:
            response = await update.message.reply_text(f'Tег "{tag}" не знайдено серед заблокованих.')
    else:
        response = await update.message.reply_text('Будь ласка, вкажіть тег для розблокування.')

    await delete_message_later(context, update.message.message_id, update.message.chat_id)
    await delete_message_later(context, response.message_id, response.chat_id)



def main() -> None:
    application = Application.builder().token(TOKEN).build()

    asyncio.run(initialize_tags())

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_image", get_image))
    application.add_handler(CommandHandler("add_tag", add_tag))
    application.add_handler(CommandHandler("remove_tag", remove_tag))
    application.add_handler(CommandHandler("block_tag", block_tag))
    application.add_handler(CommandHandler("unblock_tag", unblock_tag))
    application.add_handler(CommandHandler("list_tags", list_tags))
    application.add_handler(CallbackQueryHandler(button))
    application.add_error_handler(error_handler)
    if MODE == 'self':
        start_scheduler(application)
    application.run_polling()

async def error_handler(update: Update, context: CallbackContext) -> None:
    print(f"{Fore.RED}[WRN] Виняток під час обробки оновлення: {context.error}{Fore.RESET}")

if __name__ == '__main__':
    print(f"{Fore.YELLOW}[LOG] Систему RKB запущено!{Fore.RESET}")
    main()