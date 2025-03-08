#!/usr/bin/env python
"""
Create a test speech file for the VR Interview Server.
"""

import os
from gtts import gTTS

def create_speech_file(text, filename="test_audio/test_speech.wav"):
    """Create a speech audio file using gTTS."""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # Create a temporary MP3 file
    mp3_file = filename.replace('.wav', '.mp3')
    
    # Generate speech
    tts = gTTS(text=text, lang='en', slow=False)
    tts.save(mp3_file)
    
    # Convert to WAV if needed
    if filename.endswith('.wav'):
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(mp3_file)
            audio.export(filename, format="wav")
            # Clean up MP3 file
            os.remove(mp3_file)
            print(f"Speech sample created: {filename}")
        except ImportError:
            print("pydub not installed. Keeping MP3 format.")
            print(f"Speech sample created: {mp3_file}")
            return mp3_file
    
    return filename

if __name__ == "__main__":
    # Create a few different speech samples
    speeches = [
        "Hello, I'm interested in the software engineering position. Could you tell me more about the role?",
        "I have experience with Python and JavaScript. I've worked on several web applications using React and Node.js.",
        "In my previous job, I led a team of four developers. We built a customer relationship management system from scratch.",
        "I'm particularly interested in machine learning and have completed several courses on the topic.",
        "I'm looking for a role where I can continue to grow technically while also developing my leadership skills."
    ]
    
    for i, speech in enumerate(speeches):
        filename = f"test_audio/speech_sample_{i+1}.wav"
        create_speech_file(speech, filename)
    
    print("Created 5 speech samples in test_audio/ directory")