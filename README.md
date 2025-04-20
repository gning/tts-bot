# Telegram TTS Bot

A Telegram bot that converts text to speech using either Eleven Labs API or Azure Speech Service. The bot can process plain text messages, PDF files, TXT files, EPUB files, and images.

## Features

- Convert text messages to speech
- Extract text from PDF files and convert to speech
- Process TXT files and convert to speech
- Extract text from EPUB files and convert to speech by chapter
- Extract text from images using Google's Gemini multimodal LLM
- Multiple TTS service options (Eleven Labs and Azure)
- Voice selection from available voices for each service
- Comprehensive settings menu with service and voice selection
- Configurable via environment variables

## Requirements

- Python 3.8+
- Telegram Bot Token (from [BotFather](https://t.me/botfather))
- Eleven Labs API Key (from [Eleven Labs](https://elevenlabs.io))
- (Optional) Azure Speech Service Key (from [Azure Portal](https://portal.azure.com))
- (Optional) Google Gemini API Key (from [Google AI Studio](https://ai.google.dev/))

### Azure TTS Dependencies
If you plan to use Azure TTS, you may need to install additional system dependencies:

**Linux:**
```
sudo apt-get update
sudo apt-get install libssl-dev libasound2 build-essential
```

**macOS:**
```
brew install openssl
```

**Windows:**
Windows typically has all required dependencies pre-installed.

## Setup

1. Clone the repository
   ```
   git clone https://github.com/yourusername/telegram-tts-bot.git
   cd telegram-tts-bot
   ```

2. Create a virtual environment
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install requirements
   ```
   pip install -r requirements.txt
   ```

4. Create `.env` file from the template
   ```
   cp .env.example .env
   ```

5. Edit the `.env` file with your Telegram Bot Token, Eleven Labs API Key, and optionally Azure Speech Service and Google Gemini API credentials
   ```
   nano .env  # Or use any text editor
   ```

## Configuration

The bot supports the following configuration options in the `.env` file:

### Telegram Settings
- `TELEGRAM_TOKEN`: Your Telegram bot token from BotFather
- `USE_LOCAL_API`: (Optional) Set to 'true' to use a local Telegram API server (default: 'false')
- `LOCAL_API_URL`: (Optional) URL of the local Telegram API server (e.g. 'http://localhost:8081')

### Eleven Labs Settings
- `ELEVEN_LABS_API_KEY`: Your Eleven Labs API key
- `ELEVEN_LABS_VOICE_ID`: (Optional) Default voice ID to use
- `ELEVEN_LABS_MODEL_ID`: (Optional) Model ID to use for text-to-speech conversion

Available Eleven Labs models include:
- `eleven_monolingual_v1`: Standard monolingual model (default)
- `eleven_multilingual_v2`: Multilingual model with improved quality
- `eleven_turbo_v2`: Faster response with slightly lower quality
- `eleven_enhanced`: Enhanced quality model

### Azure Speech Service Settings
- `AZURE_SPEECH_KEY`: Your Azure Speech Service subscription key
- `AZURE_SPEECH_REGION`: Azure region for your Speech Service (e.g., eastus, westeurope)
- `AZURE_SPEECH_VOICE_NAME`: Default Azure voice name (e.g., en-US-JennyNeural)

### Gemini AI Settings
- `GEMINI_API_KEY`: Your Google AI (Gemini) API key
- `GEMINI_MODEL_NAME`: (Optional) Gemini model to use for image-to-text conversion (default: gemini-pro-vision)

Available Gemini models include:
- `gemini-pro-vision`: Standard vision model
- `gemini-2.5-pro-preview-03-25`: Latest preview model with improved capabilities

## Local Telegram API Server

By default, Telegram's Bot API limits file downloads to 20MB, which can be restrictive when working with larger audio files or PDFs. To bypass this limitation, you can configure the bot to use a local Telegram API server:

1. Set `USE_LOCAL_API=true` in your `.env` file
2. Specify the URL of your local API server with `LOCAL_API_URL=http://your-server-url`

### Local API Server Configuration

To properly handle files larger than 20MB, you need to configure your local Telegram API server correctly:

1. Download the official [Telegram Bot API server](https://github.com/tdlib/telegram-bot-api)
2. Run the server with the `--local` flag and appropriate storage options:

```bash
./telegram-bot-api --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local
```

3. Make sure your local server is properly configured for file storage and has enough disk space
4. You may need additional parameters depending on your setup:
   - `--dir`: Directory for persistent data storage
   - `--temp-dir`: Directory for storing temporary files

The local API server will typically run on port 8081 by default, so your `LOCAL_API_URL` should be `http://localhost:8081` in most cases.

For more information on running and configuring a local Telegram API server, refer to the [official Telegram documentation](https://core.telegram.org/bots/api#using-a-local-bot-api-server).

## Usage

1. Start the bot
   ```
   python tts_bot.py
   ```

2. Open Telegram and start a conversation with your bot

3. Send a text message, PDF, TXT, EPUB file, or an image to convert to speech

4. Use `/settings` command to configure TTS service and voice preferences

## Commands

- `/start` - Start the bot
- `/help` - Show help message
- `/settings` - Access the settings menu to configure TTS service and voice
- `/voices` - List and select available voices
- `/service` - Quickly change TTS service

## Limitations

- Free tier of Eleven Labs limits text length to 2,500 characters
- PDF extraction might not work perfectly for all PDF layouts
- Azure Speech Service requires system dependencies for proper operation
- Image text extraction quality depends on the clarity of the image and the text formatting

## Troubleshooting

### Azure TTS Issues
If you encounter errors with Azure TTS:
1. Ensure your Azure subscription key and region are correct
2. Install the required system dependencies (see Requirements section)
3. Check that your network allows connections to Azure services

If Azure TTS fails, the bot will automatically fall back to using Eleven Labs.

### File Size Errors
If you're using a local Telegram API server but still encounter "File is too big" errors:
1. Make sure the local API server is started with the `--local` flag
2. Check that the server has sufficient storage space and permissions
3. Use appropriate file storage parameters for your server setup

## License

MIT
