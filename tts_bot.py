import os
import logging
import tempfile
from dotenv import load_dotenv
import requests
import PyPDF2
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import azure.cognitiveservices.speech as speechsdk
import json
import uuid
import wave
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Eleven Labs Settings
ELEVEN_LABS_API_KEY = os.getenv('ELEVEN_LABS_API_KEY')
ELEVEN_LABS_VOICE_ID = os.getenv('ELEVEN_LABS_VOICE_ID', 'EXAVITQu4vr4xnSDxMaL')  # Default voice
ELEVEN_LABS_MODEL_ID = os.getenv('ELEVEN_LABS_MODEL_ID', 'eleven_monolingual_v1')  # Default model

# Azure Speech Settings
AZURE_SPEECH_KEY = os.getenv('AZURE_SPEECH_KEY')
AZURE_SPEECH_REGION = os.getenv('AZURE_SPEECH_REGION')
AZURE_SPEECH_VOICE_NAME = os.getenv('AZURE_SPEECH_VOICE_NAME', 'en-US-JennyNeural')  # Default voice
AZURE_SPEECH_URL = os.getenv('AZURE_SPEECH_URL')  # Custom endpoint URL

# API URLs
ELEVEN_LABS_TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_LABS_VOICE_ID}/stream"

# Maximum text length (Eleven Labs free tier limitation)
MAX_TEXT_LENGTH = 204800

# TTS Services
TTS_SERVICE_ELEVENLABS = "elevenlabs"
TTS_SERVICE_AZURE = "azure"

# Settings file path
SETTINGS_FILE = "user_settings.json"

# Default settings
DEFAULT_SETTINGS = {
    'tts_service': TTS_SERVICE_ELEVENLABS,
    'voice_id': ELEVEN_LABS_VOICE_ID,
    'azure_voice_name': AZURE_SPEECH_VOICE_NAME
}

def load_user_settings():
    """Load user settings from JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            logger.info(f"Loaded settings for {len(settings)} users from {SETTINGS_FILE}")
            return settings
        except Exception as e:
            logger.error(f"Error loading settings file: {e}")
            return {}
    else:
        logger.info(f"Settings file {SETTINGS_FILE} not found, creating new settings")
        return {}

def save_user_settings(user_settings):
    """Save user settings to JSON file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(user_settings, f, indent=2)
        logger.info(f"Saved settings for {len(user_settings)} users to {SETTINGS_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving settings file: {e}")
        return False

def ensure_user_settings(context, user_id):
    """Ensure user settings are loaded from persistent storage."""
    user_id = str(user_id)  # Convert to string to ensure consistency
    
    # Make sure user_settings exists in bot_data
    if 'user_settings' not in context.bot_data:
        context.bot_data['user_settings'] = load_user_settings()
        logger.info(f"Loaded settings for {len(context.bot_data['user_settings'])} users from file")
    
    # If this user has stored settings but they're not in user_data, load them
    if user_id in context.bot_data['user_settings'] and not context.user_data:
        # Load settings into user_data
        context.user_data.update(context.bot_data['user_settings'][user_id])
        logger.info(f"Loaded saved settings for user {user_id}")
    # If user doesn't have settings yet, create with defaults
    elif user_id not in context.bot_data['user_settings']:
        context.bot_data['user_settings'][user_id] = DEFAULT_SETTINGS.copy()
        # Also update user_data with defaults
        context.user_data.update(DEFAULT_SETTINGS)
        save_user_settings(context.bot_data['user_settings'])
        logger.info(f"Created new settings for user {user_id}")
    
    return context.user_data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user_id = str(update.effective_user.id)
    
    # Ensure user settings are loaded
    ensure_user_settings(context, user_id)
    
    await update.message.reply_text(
        "👋 Welcome to the TTS Bot!\n\n"
        "Send me text, a PDF, TXT, or EPUB file, and I'll convert it to speech.\n\n"
        "Use /help to see available commands.\n"
        "Use /settings to configure the bot."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    # Ensure user settings are loaded
    ensure_user_settings(context, update.effective_user.id)
    
    await update.message.reply_text(
        "🔊 TTS Bot Help 🔊\n\n"
        "Simply send me:\n"
        "- Text message to convert to speech\n"
        "- PDF file to extract text and convert\n"
        "- TXT file to convert to speech\n"
        "- EPUB file to extract text and convert\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/settings - Configure bot settings\n"
        "/voices - List available voices\n"
        "/service - Select TTS service"
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display settings menu."""
    # Ensure user settings are loaded
    ensure_user_settings(context, update.effective_user.id)
    
    keyboard = [
        [InlineKeyboardButton("🔊 TTS Service", callback_data="settings_tts_service")],
        [InlineKeyboardButton("🎙 Voice Selection", callback_data="settings_voice")],
        [InlineKeyboardButton("ℹ️ Current Settings", callback_data="settings_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ Settings Menu:", reply_markup=reply_markup)

async def service_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Let user select TTS service."""
    # Ensure user settings are loaded
    ensure_user_settings(context, update.effective_user.id)
    
    keyboard = [
        [
            InlineKeyboardButton("Eleven Labs", callback_data=f"service_{TTS_SERVICE_ELEVENLABS}"),
            InlineKeyboardButton("Azure", callback_data=f"service_{TTS_SERVICE_AZURE}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a TTS service:", reply_markup=reply_markup)

async def voices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List available voices and let user select one."""
    # Ensure user settings are loaded
    ensure_user_settings(context, update.effective_user.id)
    
    tts_service = context.user_data.get('tts_service', TTS_SERVICE_ELEVENLABS)
    
    if tts_service == TTS_SERVICE_ELEVENLABS:
        # Eleven Labs voices
        keyboard = [
            [
                InlineKeyboardButton("Rachel (Default)", callback_data="voice_EXAVITQu4vr4xnSDxMaL"),
                InlineKeyboardButton("Domi", callback_data="voice_AZnzlk1XvdvUeBnXmlld"),
            ],
            [
                InlineKeyboardButton("Bella", callback_data="voice_EXAVITQu4vr4xnSDxMaL"),
                InlineKeyboardButton("Antoni", callback_data="voice_ErXwobaYiN019PkySvjV"),
            ],
        ]
    else:  # Azure voices
        keyboard = [
            [
                InlineKeyboardButton("Jenny (US)", callback_data="azure_voice_en-US-JennyNeural"),
                InlineKeyboardButton("Guy (US)", callback_data="azure_voice_en-US-GuyNeural"),
            ],
            [
                InlineKeyboardButton("Clara (UK)", callback_data="azure_voice_en-GB-ClaraNeu"),
                InlineKeyboardButton("Thomas (UK)", callback_data="azure_voice_en-GB-ThomasNeural"),
            ],
            [
                InlineKeyboardButton("Xiaoxiao (CN)", callback_data="azure_voice_zh-CN-XiaoxiaoNeural"),
                InlineKeyboardButton("Yunxi (CN)", callback_data="azure_voice_zh-CN-YunxiNeural"),
            ],
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Select a {tts_service} voice:", reply_markup=reply_markup)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = str(update.effective_user.id)
    
    # Ensure user settings are loaded
    ensure_user_settings(context, user_id)
    
    settings_updated = False
    
    # EPUB chapter selection handler
    if data.startswith("epub_"):
        # Get the full chapter key by removing only the "epub_" prefix
        chapter_key = data[5:]  # Remove "epub_" prefix
        logger.info(f"Selected chapter key: {chapter_key}")
        chapters = context.user_data.get('epub_chapters', {})
        
        if chapter_key in chapters:
            chapter_info = chapters[chapter_key]
            chapter_text = chapter_info["text"]
            
            # Check if chapter is too long
            if len(chapter_text) > MAX_TEXT_LENGTH:
                await query.edit_message_text(
                    f"⚠️ Chapter text is too long ({len(chapter_text)} characters). "
                    f"Maximum length is {MAX_TEXT_LENGTH} characters."
                )
                return
            
            # Create a sanitized file name from the chapter title and book info
            chapter_title = chapter_info["title"]
            book_title = chapter_info.get("book_title", context.user_data.get('current_book_title', ''))
            
            # Create the file name with book title and chapter
            sanitized_chapter_title = ''.join(c for c in chapter_title if c.isalnum() or c in ' _-.')
            sanitized_book_title = ''.join(c for c in book_title if c.isalnum() or c in ' _-.')
            
            # Get original file name base if available
            original_base_name = context.user_data.get('current_base_name', '')
            
            # Decide which name to use for the base (prioritize book title)
            if sanitized_book_title:
                base_file_name = f"{sanitized_book_title} - {sanitized_chapter_title}"
            elif original_base_name:
                base_file_name = f"{original_base_name} - {sanitized_chapter_title}"
            else:
                base_file_name = sanitized_chapter_title
            
            if len(base_file_name) > 36:
                base_file_name = base_file_name[:35] + "..."
            
            # Process the selected chapter
            await query.edit_message_text(f"🔊 Converting chapter \"{chapter_info['title']}\" to speech...")
            
            # Get selected TTS service
            tts_service = context.user_data.get('tts_service', TTS_SERVICE_ELEVENLABS)
            
            service_name = "Eleven Labs" if tts_service == TTS_SERVICE_ELEVENLABS else "Azure"
            logger.info(f"Converting chapter '{chapter_info['title']}' using {service_name}")
            
            # Split text into manageable chunks if necessary (max ~4000 chars per chunk for safer audio file sizes)
            max_chunk_size = 4000
            text_chunks = split_text_into_chunks(chapter_text, max_chunk_size)
            total_chunks = len(text_chunks)
            
            logger.info(f"Split chapter into {total_chunks} chunks for processing")
            
            # If there's only one chunk, process normally
            if total_chunks == 1:
                await process_text_chunk(query, context, chapter_info["title"], text_chunks[0], tts_service, base_file_name)
            else:
                # For multiple chunks, send a message indicating multiple parts
                await query.edit_message_text(
                    f"🔊 Chapter will be processed in {total_chunks} parts due to length. "
                    f"Converting part 1/{total_chunks}..."
                )
                
                # Process each chunk with numbered parts
                for i, chunk in enumerate(text_chunks, 1):
                    # Update progress for subsequent chunks
                    if i > 1:
                        await query.edit_message_text(
                            f"🔊 Converting part {i}/{total_chunks}..."
                        )
                    
                    # Process this chunk with part number
                    part_title = f"{chapter_info['title']} (Part {i}/{total_chunks})"
                    part_file_name = f"{base_file_name}-{i}"
                    logger.info(f"Processing part {i} of {total_chunks} for chapter {chapter_info['title']} with file name {part_file_name}")
                    await process_text_chunk(query, context, part_title, chunk, tts_service, part_file_name)
                
                # Final status update after all chunks processed
                await query.edit_message_text(
                    f"✅ Chapter \"{chapter_info['title']}\" converted to speech in {total_chunks} parts."
                )
        else:
            logger.error(f"Chapter not found: {chapter_key}. Available keys: {list(chapters.keys())}")
            await query.edit_message_text("❌ Chapter not found. Please try again.")
        return
    
    # Settings menu handlers
    if data == "settings_tts_service":
        # Show TTS service selection
        keyboard = [
            [
                InlineKeyboardButton("Eleven Labs", callback_data=f"service_{TTS_SERVICE_ELEVENLABS}"),
                InlineKeyboardButton("Azure", callback_data=f"service_{TTS_SERVICE_AZURE}"),
            ],
            [InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Select TTS Service:", reply_markup=reply_markup)
    
    elif data == "settings_voice":
        # Redirect to voice selection based on current service
        tts_service = context.user_data.get('tts_service', TTS_SERVICE_ELEVENLABS)
        
        if tts_service == TTS_SERVICE_ELEVENLABS:
            # Eleven Labs voices
            keyboard = [
                [
                    InlineKeyboardButton("Rachel (Default)", callback_data="voice_EXAVITQu4vr4xnSDxMaL"),
                    InlineKeyboardButton("Domi", callback_data="voice_AZnzlk1XvdvUeBnXmlld"),
                ],
                [
                    InlineKeyboardButton("Bella", callback_data="voice_EXAVITQu4vr4xnSDxMaL"),
                    InlineKeyboardButton("Antoni", callback_data="voice_ErXwobaYiN019PkySvjV"),
                ],
                [InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]
            ]
        else:  # Azure voices
            keyboard = [
                [
                    InlineKeyboardButton("Jenny (US)", callback_data="azure_voice_en-US-JennyNeural"),
                    InlineKeyboardButton("Guy (US)", callback_data="azure_voice_en-US-GuyNeural"),
                ],
                [
                    InlineKeyboardButton("Clara (UK)", callback_data="azure_voice_en-GB-ClaraNeu"),
                    InlineKeyboardButton("Thomas (UK)", callback_data="azure_voice_en-GB-ThomasNeural"),
                ],
                [
                    InlineKeyboardButton("Xiaoxiao (CN)", callback_data="azure_voice_zh-CN-XiaoxiaoNeural"),
                    InlineKeyboardButton("Yunxi (CN)", callback_data="azure_voice_zh-CN-YunxiNeural"),
                ],
                [InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Select {tts_service.title()} Voice:", reply_markup=reply_markup)
    
    elif data == "settings_info":
        # Show current settings
        tts_service = context.user_data.get('tts_service', TTS_SERVICE_ELEVENLABS)
        service_name = "Eleven Labs" if tts_service == TTS_SERVICE_ELEVENLABS else "Azure"
        
        if tts_service == TTS_SERVICE_ELEVENLABS:
            voice_id = context.user_data.get('voice_id', ELEVEN_LABS_VOICE_ID)
            voice_names = {
                "EXAVITQu4vr4xnSDxMaL": "Rachel",
                "AZnzlk1XvdvUeBnXmlld": "Domi",
                "ErXwobaYiN019PkySvjV": "Antoni"
            }
            voice_name = voice_names.get(voice_id, "Unknown")
        else:  # Azure
            voice_name_full = context.user_data.get('azure_voice_name', AZURE_SPEECH_VOICE_NAME)
            friendly_names = {
                "en-US-JennyNeural": "Jenny (US)",
                "en-US-GuyNeural": "Guy (US)",
                "en-GB-ClaraNeu": "Clara (UK)",
                "en-GB-ThomasNeural": "Thomas (UK)",
                "zh-CN-XiaoxiaoNeural": "Xiaoxiao (CN)",
                "zh-CN-YunxiNeural": "Yunxi (CN)"
            }
            voice_name = friendly_names.get(voice_name_full, voice_name_full)
        
        settings_info = (
            f"⚙️ Current Settings:\n\n"
            f"TTS Service: {service_name}\n"
            f"Voice: {voice_name}\n"
        )
        
        keyboard = [[InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(settings_info, reply_markup=reply_markup)
    
    elif data == "back_to_settings":
        # Go back to main settings menu
        keyboard = [
            [InlineKeyboardButton("🔊 TTS Service", callback_data="settings_tts_service")],
            [InlineKeyboardButton("🎙 Voice Selection", callback_data="settings_voice")],
            [InlineKeyboardButton("ℹ️ Current Settings", callback_data="settings_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚙️ Settings Menu:", reply_markup=reply_markup)
    
    # Service and voice selection handlers
    elif data.startswith("service_"):
        service = data.split("_")[1]
        context.user_data['tts_service'] = service
        
        # Save the updated settings
        if 'user_settings' in context.bot_data:
            context.bot_data['user_settings'][user_id] = context.user_data.copy()
            save_user_settings(context.bot_data['user_settings'])
        
        # After setting the service, show the back button
        keyboard = [[InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"TTS service set to: {service.title()}", reply_markup=reply_markup)
    
    elif data.startswith("voice_"):  # Eleven Labs voice
        voice_id = data.split('_')[1]
        context.user_data['voice_id'] = voice_id
        
        # Save the updated settings
        if 'user_settings' in context.bot_data:
            context.bot_data['user_settings'][user_id] = context.user_data.copy()
            save_user_settings(context.bot_data['user_settings'])
        
        # Get voice name (this would be better with a proper mapping)
        voice_names = {
            "EXAVITQu4vr4xnSDxMaL": "Rachel",
            "AZnzlk1XvdvUeBnXmlld": "Domi",
            "ErXwobaYiN019PkySvjV": "Antoni"
        }
        voice_name = voice_names.get(voice_id, "Selected voice")
        
        # After setting the voice, show the back button
        keyboard = [[InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"Voice set to: {voice_name}", reply_markup=reply_markup)
    
    elif data.startswith("azure_voice_"):  # Azure voice
        voice_name = data.split('_')[2]
        context.user_data['azure_voice_name'] = voice_name
        
        # Save the updated settings
        if 'user_settings' in context.bot_data:
            context.bot_data['user_settings'][user_id] = context.user_data.copy()
            save_user_settings(context.bot_data['user_settings'])
        
        # Display a friendly name
        friendly_names = {
            "en-US-JennyNeural": "Jenny (US)",
            "en-US-GuyNeural": "Guy (US)",
            "en-GB-ClaraNeu": "Clara (UK)",
            "en-GB-ThomasNeural": "Thomas (UK)",
            "zh-CN-XiaoxiaoNeural": "Xiaoxiao (CN)",
            "zh-CN-YunxiNeural": "Yunxi (CN)"
        }
        friendly_name = friendly_names.get(voice_name, voice_name)
        
        # After setting the voice, show the back button
        keyboard = [[InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"Azure voice set to: {friendly_name}", reply_markup=reply_markup)

def extract_text_from_pdf(pdf_file):
    """Extract text from a PDF file"""
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_text_from_txt(txt_file):
    """Extract text from a TXT file"""
    return txt_file.read().decode('utf-8')

def extract_text_from_epub(epub_file):
    """Extract text from an EPUB file and return chapters dictionary"""
    # Create a temporary file to save the EPUB content
    with tempfile.NamedTemporaryFile(suffix='.epub', delete=False) as temp_epub:
        temp_epub_path = temp_epub.name
        # Write BytesIO content to the temporary file
        temp_epub.write(epub_file.read())
    
    try:
        # Read from the temporary file path
        logger.info(f"Reading EPUB from temporary file: {temp_epub_path}")
        book = epub.read_epub(temp_epub_path)
        chapters = {}
        chapter_index = 1
        
        # Get book title if available
        book_title = book.get_metadata('DC', 'title')
        book_title_string = book_title[0][0] if book_title else "Unknown"
        logger.info(f"EPUB book title: {book_title_string}")
        
        # Log the number of items found
        items = list(book.get_items())
        document_items = [item for item in items if item.get_type() == ebooklib.ITEM_DOCUMENT]
        logger.info(f"Found {len(items)} total items, {len(document_items)} document items in EPUB")
        
        for item in document_items:
            # Try to get chapter title from item
            item_title = ""
            try:
                # Get item ID and file name for debugging
                item_id = item.get_id()
                item_name = item.get_name()
                logger.info(f"Processing EPUB item: ID={item_id}, Name={item_name}")
                
                # Parse HTML content
                html_content = item.get_content().decode('utf-8')
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Try to find chapter title from headings
                for heading in soup.find_all(['h1', 'h2', 'h3']):
                    if heading.text.strip():
                        item_title = heading.text.strip()
                        break
                
                # Extract text (remove HTML tags)
                chapter_text = soup.get_text()
                chapter_length = len(chapter_text.strip())
                logger.info(f"Extracted text from item {item_id}: {chapter_length} characters, Title: {item_title or 'Not found'}")
                
                # Only add non-empty chapters
                if chapter_text.strip():
                    # Generate chapter key and title
                    chapter_key = f"ch_{chapter_index}"
                    if not item_title:
                        item_title = f"Chapter {chapter_index}"
                    
                    # Store chapter information with separate book title and chapter title
                    chapters[chapter_key] = {
                        "title": item_title,  # Just the chapter title
                        "book_title": book_title_string,  # Book title separately
                        "full_title": f"{book_title_string} - {item_title}",  # Full title for filenames
                        "text": chapter_text
                    }
                    logger.info(f"Added chapter {chapter_key}: '{item_title}', {len(chapter_text)} characters")
                    chapter_index += 1
                else:
                    logger.info(f"Skipping empty item {item_id}")
                    
            except Exception as e:
                logger.error(f"Error extracting chapter from item {getattr(item, 'id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Successfully extracted {len(chapters)} chapters from EPUB")
        # Log all chapter keys for debugging
        logger.info(f"Chapter keys: {list(chapters.keys())}")
        return chapters
    except Exception as e:
        logger.error(f"Error processing EPUB file: {e}")
        raise
    finally:
        # Always clean up the temporary file
        if os.path.exists(temp_epub_path):
            os.unlink(temp_epub_path)
            logger.info(f"Temporary EPUB file {temp_epub_path} removed")

def elevenlabs_text_to_speech(text, voice_id=None):
    """Convert text to speech using Eleven Labs API"""
    if not voice_id:
        voice_id = ELEVEN_LABS_VOICE_ID
        
    headers = {
        "Accept": "audio/mpeg",
        "xi-api-key": ELEVEN_LABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "model_id": ELEVEN_LABS_MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    
    response = requests.post(url, json=data, headers=headers, stream=True)
    
    if response.status_code != 200:
        logger.error(f"Eleven Labs API error: {response.text}")
        return None
        
    return response.content

def azure_text_to_speech(text, voice_name=None):
    """Convert text to speech using Azure Speech Service"""
    if not voice_name:
        voice_name = AZURE_SPEECH_VOICE_NAME
    
    # Check if Azure credentials are properly set
    if not AZURE_SPEECH_KEY or AZURE_SPEECH_KEY == "your_azure_speech_key_here":
        error_msg = "Azure Speech key not properly configured"
        logger.error(error_msg)
        return None, error_msg
    
    # First try using the SDK approach
    try:
        audio_data, error = azure_sdk_synthesis(text, voice_name)
        if audio_data:
            return audio_data, None
        
        # If SDK approach failed, try the REST API approach
        logger.warning(f"SDK synthesis failed: {error}. Trying REST API approach...")
        audio_data, error = azure_rest_synthesis(text, voice_name)
        return audio_data, error
            
    except Exception as e:
        error_msg = f"Azure TTS error: {str(e)}"
        logger.error(error_msg)
        return None, error_msg

def azure_sdk_synthesis(text, voice_name):
    """Use the Azure SDK to synthesize speech"""
    try:
        # Configure the speech configuration
        speech_config = None
        
        if AZURE_SPEECH_URL:
            # Use custom endpoint if provided (without trailing slash)
            endpoint = AZURE_SPEECH_URL.rstrip('/')
            speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, endpoint=endpoint)
            logger.info(f"Using custom Azure Speech endpoint")
        elif AZURE_SPEECH_REGION:
            # Use region-based configuration
            speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
            logger.info(f"Using Azure Speech region: {AZURE_SPEECH_REGION}")
        else:
            error_msg = "Either Azure Speech URL or region must be provided"
            logger.error(error_msg)
            return None, error_msg
        
        # Set the voice name and adjust properties
        speech_config.speech_synthesis_voice_name = voice_name
        
        # Set timeout
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "5000")
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "5000")
        
        # Create a temporary file for output
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        file_path = temp_file.name
        temp_file.close()
        
        # Configure audio output to file
        audio_config = speechsdk.audio.AudioOutputConfig(filename=file_path)
        
        # Create speech synthesizer with file output
        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        
        # Determine language based on voice name
        language = "en-US"  # Default
        if voice_name.startswith("zh-"):
            language = "zh-CN"
        elif voice_name.startswith("en-GB"):
            language = "en-GB"
        
        # Use SSML for more control over synthesis
        ssml = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">
            <voice name="{voice_name}">
                {text}
            </voice>
        </speak>
        """
        
        # Synthesize using SSML
        result = speech_synthesizer.speak_ssml_async(ssml).get()
        
        # Check result
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            # Read the audio file
            with open(file_path, "rb") as audio_file:
                audio_data = audio_file.read()
            
            # Clean up the temp file
            os.unlink(file_path)
            
            return audio_data, None
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            error_msg = f"Azure TTS cancelled: {cancellation_details.reason}. Error details: {cancellation_details.error_details}"
            logger.error(f"Azure TTS cancelled: {cancellation_details.reason}")
            logger.error(f"Azure TTS error details: {cancellation_details.error_details}")
            
            # Clean up the temp file
            if os.path.exists(file_path):
                os.unlink(file_path)
                
            return None, error_msg
        else:
            error_msg = f"Azure TTS failed with reason: {result.reason}"
            logger.error(error_msg)
            
            # Clean up the temp file
            if os.path.exists(file_path):
                os.unlink(file_path)
                
            return None, error_msg
    
    except Exception as e:
        error_msg = f"Azure SDK synthesis error: {str(e)}"
        logger.error(error_msg)
        return None, error_msg

def azure_rest_synthesis(text, voice_name):
    """Use the Azure REST API to synthesize speech (as fallback)"""
    try:
        # Remove any trailing slash from the endpoint
        base_url = AZURE_SPEECH_URL.rstrip('/')
        
        # Construct the full URL
        tts_url = f"{base_url}/cognitiveservices/v1"
        
        # Determine language based on voice name
        language = "en-US"  # Default
        if voice_name.startswith("zh-"):
            language = "zh-CN"
        elif voice_name.startswith("en-GB"):
            language = "en-GB"
        
        # Prepare the SSML payload
        ssml_payload = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">
            <voice name="{voice_name}">
                {text}
            </voice>
        </speak>
        """
        
        # Set up headers
        headers = {
            "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "TelegramTTSBot"
        }
        
        # Make the request with a timeout
        response = requests.post(
            tts_url, 
            headers=headers, 
            data=ssml_payload.encode('utf-8'),
            timeout=30  # 30 seconds timeout
        )
        
        # Check response
        if response.status_code == 200:
            return response.content, None
        else:
            error_msg = f"Azure REST API error: Status {response.status_code}, {response.text}"
            logger.error(error_msg)
            return None, error_msg
            
    except requests.exceptions.Timeout:
        error_msg = "Azure REST API timeout: Request took too long to complete"
        logger.error(error_msg)
        return None, error_msg
        
    except Exception as e:
        error_msg = f"Azure REST API error: {str(e)}"
        logger.error(error_msg)
        return None, error_msg

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    # Ensure user settings are loaded
    ensure_user_settings(context, update.effective_user.id)
    
    text = update.message.text
    
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(
            f"⚠️ Your text is too long ({len(text)} characters). "
            f"Maximum length is {MAX_TEXT_LENGTH} characters."
        )
        return
    
    await process_text_to_speech(update, context, text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF, TXT and EPUB documents."""
    # Ensure user settings are loaded
    ensure_user_settings(context, update.effective_user.id)
    
    # Get file info and download
    file = await context.bot.get_file(update.message.document.file_id)
    file_bytes = BytesIO()
    await file.download_to_memory(file_bytes)
    file_bytes.seek(0)
    
    # Store original filename in user data for reference
    file_name = update.message.document.file_name
    context.user_data['current_file_name'] = file_name
    base_name = os.path.splitext(file_name)[0]
    context.user_data['current_base_name'] = base_name
    
    # Check document type
    if file_name.lower().endswith('.pdf'):
        await update.message.reply_text("📄 Processing PDF file...")
        try:
            text = extract_text_from_pdf(file_bytes)
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            await update.message.reply_text("❌ Error processing PDF file.")
            return
            
        if len(text) > MAX_TEXT_LENGTH:
            await update.message.reply_text(
                f"⚠️ Extracted text is too long ({len(text)} characters). "
                f"Maximum length is {MAX_TEXT_LENGTH} characters."
            )
            return
            
        await process_text_to_speech(update, context, text, base_name)
        
    elif file_name.lower().endswith('.txt'):
        await update.message.reply_text("📝 Processing TXT file...")
        try:
            text = extract_text_from_txt(file_bytes)
        except Exception as e:
            logger.error(f"Error extracting text from TXT: {e}")
            await update.message.reply_text("❌ Error processing TXT file.")
            return
            
        if len(text) > MAX_TEXT_LENGTH:
            await update.message.reply_text(
                f"⚠️ Extracted text is too long ({len(text)} characters). "
                f"Maximum length is {MAX_TEXT_LENGTH} characters."
            )
            return
            
        await process_text_to_speech(update, context, text, base_name)
        
    elif file_name.lower().endswith('.epub'):
        await update.message.reply_text("📚 Processing EPUB file...")
        try:
            chapters = extract_text_from_epub(file_bytes)
            
            if not chapters:
                await update.message.reply_text("❌ No readable content found in EPUB file.")
                return
                
            # Store chapters in user data for later access
            context.user_data['epub_chapters'] = chapters
            # Also store book title for reference
            first_chapter = next(iter(chapters.values()))
            context.user_data['current_book_title'] = first_chapter.get('book_title', '')
            
            # Create chapter selection keyboard
            keyboard = []
            row = []
            
            for i, (chapter_key, chapter_info) in enumerate(chapters.items()):
                # Create a new row every 2 buttons
                if i % 2 == 0 and i > 0:
                    keyboard.append(row)
                    row = []
                
                # Use only the chapter title (not the full title with book name)
                title = chapter_info["title"]
                if len(title) > 30:
                    title = title[:27] + "..."
                
                row.append(InlineKeyboardButton(title, callback_data=f"epub_{chapter_key}"))
            
            # Add the last row if not empty
            if row:
                keyboard.append(row)
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send chapter selection message with book title
            book_title = context.user_data['current_book_title']
            await update.message.reply_text(
                f"📖 EPUB: \"{book_title}\" loaded with {len(chapters)} chapters.\n"
                f"Please select a chapter to convert to speech:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error extracting text from EPUB: {e}")
            await update.message.reply_text("❌ Error processing EPUB file.")
            return
    else:
        await update.message.reply_text("❌ Unsupported file type. Please send a PDF, TXT, or EPUB file.")
        return

async def process_text_to_speech(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, file_name_base=None) -> None:
    """Process text to speech and send voice message."""
    # Get selected TTS service
    tts_service = context.user_data.get('tts_service', TTS_SERVICE_ELEVENLABS)
    
    service_name = "Eleven Labs" if tts_service == TTS_SERVICE_ELEVENLABS else "Azure"
    
    # Split text into manageable chunks if necessary (max ~4000 chars per chunk for safer audio file sizes)
    max_chunk_size = 4000
    text_chunks = split_text_into_chunks(text, max_chunk_size)
    total_chunks = len(text_chunks)
    
    logger.info(f"Split text into {total_chunks} chunks for processing")
    
    # For single chunk, process normally
    if total_chunks == 1:
        await update.message.reply_text(f"🔊 Converting text to speech using {service_name}...")
        
        try:
            audio_content = None
            error_message = None
            
            # Use the selected service
            if tts_service == TTS_SERVICE_ELEVENLABS:
                # Get user-selected voice if available
                voice_id = context.user_data.get('voice_id', ELEVEN_LABS_VOICE_ID)
                audio_content = elevenlabs_text_to_speech(text_chunks[0], voice_id)
            else:  # Azure
                # Get user-selected voice if available
                voice_name = context.user_data.get('azure_voice_name', AZURE_SPEECH_VOICE_NAME)
                audio_content, error_message = azure_text_to_speech(text_chunks[0], voice_name)
                
                # If Azure failed, return the error message instead of falling back
                if not audio_content:
                    await update.message.reply_text(f"❌ Azure TTS Error: {error_message}")
                    return
            
            if not audio_content:
                await update.message.reply_text(f"❌ Failed to convert text to speech.")
                return
            
            # Create temporary file for the audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
                temp_audio.write(audio_content)
                temp_audio_path = temp_audio.name
            
            # File name for the audio (use original file name if available)
            if not file_name_base:
                output_file_name = "speech"
            else:
                # Clean filename to ensure it's valid
                output_file_name = ''.join(c for c in file_name_base if c.isalnum() or c in ' _-.')
                # Truncate if too long
                if len(output_file_name) > 64:
                    output_file_name = output_file_name[:61] + "..."
            
            # Try to send as voice message first
            try:
                with open(temp_audio_path, 'rb') as audio:
                    await update.message.reply_voice(audio, caption=f"{output_file_name}")
            except Exception as voice_error:
                # If voice messages are forbidden, send as regular audio file
                if "Voice_messages_forbidden" in str(voice_error):
                    logger.info("Voice messages forbidden, sending as audio file instead")
                    with open(temp_audio_path, 'rb') as audio:
                        await update.message.reply_audio(audio, filename=f"{output_file_name}.mp3")
                else:
                    # Re-raise if it's a different error
                    raise
            
            # Clean up temporary file
            os.unlink(temp_audio_path)
            
        except Exception as e:
            logger.error(f"Error in text to speech conversion: {e}")
            await update.message.reply_text(f"❌ Error converting text to speech: {str(e)}")
    
    # For multiple chunks, process each separately with part numbers
    else:
        await update.message.reply_text(
            f"🔊 Text will be processed in {total_chunks} parts due to length. Converting..."
        )
        
        for i, chunk in enumerate(text_chunks, 1):
            # Create part-specific filename
            if not file_name_base:
                part_file_name = f"speech_part_{i}_of_{total_chunks}"
            else:
                # Clean filename to ensure it's valid
                clean_base = ''.join(c for c in file_name_base if c.isalnum() or c in ' _-.')
                # Truncate if too long
                if len(clean_base) > 50:
                    clean_base = clean_base[:47] + "..."
                part_file_name = f"{clean_base}_part_{i}_of_{total_chunks}"
            
            # Status update for each part
            await update.message.reply_text(f"🔊 Converting part {i}/{total_chunks} using {service_name}...")
            
            try:
                audio_content = None
                error_message = None
                
                # Use the selected service
                if tts_service == TTS_SERVICE_ELEVENLABS:
                    # Get user-selected voice if available
                    voice_id = context.user_data.get('voice_id', ELEVEN_LABS_VOICE_ID)
                    audio_content = elevenlabs_text_to_speech(chunk, voice_id)
                else:  # Azure
                    # Get user-selected voice if available
                    voice_name = context.user_data.get('azure_voice_name', AZURE_SPEECH_VOICE_NAME)
                    audio_content, error_message = azure_text_to_speech(chunk, voice_name)
                    
                    # If Azure failed, return the error message instead of falling back
                    if not audio_content:
                        await update.message.reply_text(f"❌ Azure TTS Error: {error_message}")
                        continue
                
                if not audio_content:
                    await update.message.reply_text(f"❌ Failed to convert part {i}/{total_chunks} to speech.")
                    continue
                
                # Create temporary file for the audio
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
                    temp_audio.write(audio_content)
                    temp_audio_path = temp_audio.name
                
                # Try to send as voice message first
                try:
                    with open(temp_audio_path, 'rb') as audio:
                        await update.message.reply_voice(audio, caption=f"{part_file_name}")
                except Exception as voice_error:
                    # If voice messages are forbidden, send as regular audio file
                    if "Voice_messages_forbidden" in str(voice_error):
                        logger.info("Voice messages forbidden, sending as audio file instead")
                        with open(temp_audio_path, 'rb') as audio:
                            await update.message.reply_audio(audio, filename=f"{part_file_name}.mp3")
                    else:
                        # Re-raise if it's a different error
                        raise
                
                # Clean up temporary file
                os.unlink(temp_audio_path)
                
            except Exception as e:
                logger.error(f"Error in text to speech conversion for part {i}: {e}")
                await update.message.reply_text(f"❌ Error converting part {i}/{total_chunks} to speech: {str(e)}")
        
        # Final status message after all parts processed
        await update.message.reply_text(f"✅ Completed converting text to speech in {total_chunks} parts.")

def split_text_into_chunks(text, max_chunk_size):
    """Split text into chunks of approximately max_chunk_size characters.
    Tries to split at sentence or paragraph boundaries to maintain natural speech flow."""
    
    # If text is shorter than max size, return it as is
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    remaining_text = text
    
    while remaining_text:
        # If remaining text fits in one chunk
        if len(remaining_text) <= max_chunk_size:
            chunks.append(remaining_text)
            break
        
        # Try to find paragraph break near the max size
        paragraph_break = remaining_text.rfind('\n\n', 0, max_chunk_size)
        
        # If no paragraph break, try to find sentence break
        if paragraph_break == -1 or paragraph_break < max_chunk_size // 2:
            sentence_end = -1
            # Look for sentence endings (.?!) followed by space or newline
            for punct in ['. ', '? ', '! ', '.\n', '?\n', '!\n']:
                pos = remaining_text.rfind(punct, 0, max_chunk_size - 1)
                if pos > sentence_end:
                    sentence_end = pos + 1  # Include the punctuation
            
            # If no good sentence break found, just cut at word boundary
            if sentence_end < max_chunk_size // 2:
                # Find last space before max size
                space_pos = remaining_text.rfind(' ', max_chunk_size // 2, max_chunk_size)
                if space_pos != -1:
                    chunk_end = space_pos
                else:
                    # If no good break found, just cut at max size
                    chunk_end = max_chunk_size
            else:
                chunk_end = sentence_end + 1  # +1 to include the space after punctuation
        else:
            # Use paragraph break (include the newlines)
            chunk_end = paragraph_break + 2
        
        # Add chunk and update remaining text
        chunks.append(remaining_text[:chunk_end].strip())
        remaining_text = remaining_text[chunk_end:].strip()
    
    return chunks

async def process_text_chunk(query, context, title, text, tts_service, file_name=None):
    """Process a single chunk of text and send the audio message."""
    try:
        audio_content = None
        error_message = None
        
        # Use the selected service
        if tts_service == TTS_SERVICE_ELEVENLABS:
            # Get user-selected voice if available
            voice_id = context.user_data.get('voice_id', ELEVEN_LABS_VOICE_ID)
            audio_content = elevenlabs_text_to_speech(text, voice_id)
        else:  # Azure
            # Get user-selected voice if available
            voice_name = context.user_data.get('azure_voice_name', AZURE_SPEECH_VOICE_NAME)
            audio_content, error_message = azure_text_to_speech(text, voice_name)
            
            # If Azure failed, return the error message
            if not audio_content:
                await query.edit_message_text(f"❌ Azure TTS Error: {error_message}")
                return False
        
        if not audio_content:
            await query.edit_message_text(f"❌ Failed to convert text to speech.")
            return False
        
        # Create temporary file for the audio
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
            temp_audio.write(audio_content)
            temp_audio_path = temp_audio.name
        
        # Get file size for logging
        file_size = os.path.getsize(temp_audio_path)
        logger.info(f"Generated audio file size: {file_size / (1024*1024):.2f} MB")
        
        # Use provided file name or default to title if not provided
        if not file_name:
            sanitized_title = ''.join(c for c in title if c.isalnum() or c in ' _-.')
            if len(sanitized_title) > 64:
                sanitized_title = sanitized_title[:61] + "..."
            output_file_name = sanitized_title
        else:
            output_file_name = file_name
        
        # Try to send as voice message first
        try:
            with open(temp_audio_path, 'rb') as audio:
                # Use proper caption with title and output filename
                await query.message.reply_voice(audio, caption=f"{output_file_name}")
        except Exception as voice_error:
            # If voice messages are forbidden or too large, try audio file
            if "Voice_messages_forbidden" in str(voice_error) or "Request Entity Too Large" in str(voice_error):
                logger.info(f"Voice message failed: {str(voice_error)}, trying audio file")
                
                # If file is too large, also try to split into smaller chunks for next time
                if "Request Entity Too Large" in str(voice_error):
                    logger.warning(f"Audio file too large ({file_size / (1024*1024):.2f} MB). Consider using smaller chunks.")
                
                try:
                    with open(temp_audio_path, 'rb') as audio:
                        # For audio files, automatically add file extension
                        filename = f"{output_file_name}.mp3"
                        logger.info(f"Sending audio file: {filename}")
                        await query.message.reply_audio(audio, filename=filename)
                except Exception as audio_error:
                    logger.error(f"Audio file send error: {str(audio_error)}")
                    await query.edit_message_text(f"❌ Failed to send audio: {str(audio_error)}")
                    os.unlink(temp_audio_path)
                    return False
            else:
                # Re-raise if it's a different error
                raise
        
        # Clean up temporary file
        os.unlink(temp_audio_path)
        return True
        
    except Exception as e:
        logger.error(f"Error in text to speech conversion: {e}")
        await query.edit_message_text(f"❌ Error converting text to speech: {str(e)}")
        return False

def main() -> None:
    """Start the bot."""
    # Check Azure dependencies
    if AZURE_SPEECH_KEY and AZURE_SPEECH_KEY != "your_azure_speech_key_here" and (AZURE_SPEECH_REGION or AZURE_SPEECH_URL):
        try:
            # Test the Azure SDK initialization
            if AZURE_SPEECH_URL:
                speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, endpoint=AZURE_SPEECH_URL)
                logger.info(f"Azure Speech SDK initialized successfully with custom endpoint")
            else:
                speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
                logger.info("Azure Speech SDK initialized successfully")
                
            logger.info("Azure Speech Service is properly configured")
        except Exception as e:
            logger.warning(f"Azure Speech SDK initialization failed: {str(e)}")
            logger.warning("Azure TTS may not work. Make sure you have the required system dependencies.")
            logger.warning("For Linux, try installing: libssl-dev, libasound2, and build-essential")
    else:
        logger.warning("Azure Speech Service is not configured properly. Eleven Labs will be used as fallback.")
    
    # Create the Application and store persistence data in bot_data
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Initialize user settings
    application.bot_data['user_settings'] = load_user_settings()
    logger.info(f"Loaded settings for {len(application.bot_data['user_settings'])} users")

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("voices", voices_command))
    application.add_handler(CommandHandler("service", service_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Add message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.Document.PDF | filters.Document.TXT | filters.Document.MimeType("application/epub+zip"), handle_document))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == '__main__':
    main() 