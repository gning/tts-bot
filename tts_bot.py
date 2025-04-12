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
MAX_TEXT_LENGTH = 2500

# TTS Services
TTS_SERVICE_ELEVENLABS = "elevenlabs"
TTS_SERVICE_AZURE = "azure"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    # Initialize user settings if not present
    if 'tts_service' not in context.user_data:
        context.user_data['tts_service'] = TTS_SERVICE_ELEVENLABS  # Default to Eleven Labs
    
    await update.message.reply_text(
        "👋 Welcome to the TTS Bot!\n\n"
        "Send me text, a PDF, or a TXT file, and I'll convert it to speech.\n\n"
        "Use /help to see available commands.\n"
        "Use /settings to configure the bot."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "🔊 TTS Bot Help 🔊\n\n"
        "Simply send me:\n"
        "- Text message to convert to speech\n"
        "- PDF file to extract text and convert\n"
        "- TXT file to convert to speech\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/settings - Configure bot settings\n"
        "/voices - List available voices\n"
        "/service - Select TTS service"
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display settings menu."""
    keyboard = [
        [InlineKeyboardButton("🔊 TTS Service", callback_data="settings_tts_service")],
        [InlineKeyboardButton("🎙 Voice Selection", callback_data="settings_voice")],
        [InlineKeyboardButton("ℹ️ Current Settings", callback_data="settings_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ Settings Menu:", reply_markup=reply_markup)

async def service_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Let user select TTS service."""
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
        
        # After setting the service, show the back button
        keyboard = [[InlineKeyboardButton("« Back to Settings", callback_data="back_to_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"TTS service set to: {service.title()}", reply_markup=reply_markup)
    
    elif data.startswith("voice_"):  # Eleven Labs voice
        voice_id = data.split('_')[1]
        context.user_data['voice_id'] = voice_id
        
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
    text = update.message.text
    
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(
            f"⚠️ Your text is too long ({len(text)} characters). "
            f"Maximum length is {MAX_TEXT_LENGTH} characters."
        )
        return
    
    await process_text_to_speech(update, context, text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF and TXT documents."""
    # Get file info and download
    file = await context.bot.get_file(update.message.document.file_id)
    file_bytes = BytesIO()
    await file.download_to_memory(file_bytes)
    file_bytes.seek(0)
    
    # Check document type
    file_name = update.message.document.file_name
    if file_name.lower().endswith('.pdf'):
        await update.message.reply_text("📄 Processing PDF file...")
        try:
            text = extract_text_from_pdf(file_bytes)
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            await update.message.reply_text("❌ Error processing PDF file.")
            return
    elif file_name.lower().endswith('.txt'):
        await update.message.reply_text("📝 Processing TXT file...")
        try:
            text = extract_text_from_txt(file_bytes)
        except Exception as e:
            logger.error(f"Error extracting text from TXT: {e}")
            await update.message.reply_text("❌ Error processing TXT file.")
            return
    else:
        await update.message.reply_text("❌ Unsupported file type. Please send a PDF or TXT file.")
        return
    
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(
            f"⚠️ Extracted text is too long ({len(text)} characters). "
            f"Maximum length is {MAX_TEXT_LENGTH} characters."
        )
        return
    
    await process_text_to_speech(update, context, text)

async def process_text_to_speech(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process text to speech and send voice message."""
    # Get selected TTS service
    tts_service = context.user_data.get('tts_service', TTS_SERVICE_ELEVENLABS)
    
    service_name = "Eleven Labs" if tts_service == TTS_SERVICE_ELEVENLABS else "Azure"
    await update.message.reply_text(f"🔊 Converting text to speech using {service_name}...")
    
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
        
        # Try to send as voice message first
        try:
            with open(temp_audio_path, 'rb') as audio:
                await update.message.reply_voice(audio)
        except Exception as voice_error:
            # If voice messages are forbidden, send as regular audio file
            if "Voice_messages_forbidden" in str(voice_error):
                logger.info("Voice messages forbidden, sending as audio file instead")
                with open(temp_audio_path, 'rb') as audio:
                    await update.message.reply_audio(audio, filename="speech.mp3")
            else:
                # Re-raise if it's a different error
                raise
        
        # Clean up temporary file
        os.unlink(temp_audio_path)
        
    except Exception as e:
        logger.error(f"Error in text to speech conversion: {e}")
        await update.message.reply_text(f"❌ Error converting text to speech: {str(e)}")

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
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

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
    application.add_handler(MessageHandler(filters.Document.PDF | filters.Document.TXT, handle_document))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == '__main__':
    main() 