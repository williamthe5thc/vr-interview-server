# VR Interview Practice - Server

This is the server component of the VR Interview Practice application for Oculus Quest. The server handles WebSocket communication, speech processing, and LLM integration to create a realistic interviewer.

## Overview

The server component is responsible for:

- Managing WebSocket connections with VR clients
- Processing audio data from the user (candidate)
- Transcribing speech using Whisper
- Generating interviewer responses using an LLM
- Converting responses to speech using TTS
- Maintaining conversation state and history
- Providing real-time feedback

## Requirements

- Python 3.9+
- PyTorch 2.0+
- CUDA-compatible GPU (recommended for faster LLM processing)
- Microphone and speakers
- Network connectivity between PC and Oculus Quest

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/vr-interview-server.git
cd vr-interview-server
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Download the LLM model:
```
# Example for Phi-2 model
git lfs install
git clone https://huggingface.co/microsoft/phi-2 phi-model
```

4. Create necessary directories:
```
mkdir -p data/audio/uploads data/audio/responses data/conversations
```

5. Configure settings in `config.json` (if needed)

## Usage

1. Start the server:
```
python server.py
```

2. Connect from the VR Interview Application on your Oculus Quest device.
   - Make sure the Quest is on the same network as your PC
   - The default WebSocket address is `ws://YOUR_PC_IP:8080`

## Configuration

Edit `config.json` to customize:

- Server settings (port, host, etc.)
- LLM parameters (temperature, max tokens, etc.)
- Audio settings (TTS engine, Whisper model, etc.)
- Interview settings (interviewer types, difficulty levels, etc.)

## Structure

- `server.py` - Main entry point
- `app/` - Core application code
  - `websocket.py` - WebSocket event handlers
  - `state_manager.py` - Conversation state management
- `services/` - External service integrations
  - `speech_processing.py` - Speech-to-text and text-to-speech
  - `llm_service.py` - LLM integration
- `data/` - Data storage
  - `audio/` - Audio file storage
  - `conversations/` - Saved conversation histories

## Troubleshooting

- Check `server.log` for detailed error messages
- Ensure firewall allows connections on port 8080
- Verify Quest and PC are on the same network
- Check CUDA availability for LLM acceleration

## License

[MIT License](LICENSE)