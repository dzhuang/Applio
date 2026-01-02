import sys
import asyncio
import edge_tts
import os
from pydub import AudioSegment


async def main():
    # Parse command line arguments
    tts_file = str(sys.argv[1])
    text = str(sys.argv[2])
    voice = str(sys.argv[3])
    rate = int(sys.argv[4])
    output_file = str(sys.argv[5])

    rates = f"+{rate}%" if rate >= 0 else f"{rate}%"
    if tts_file and os.path.exists(tts_file):
        text = ""
        try:
            with open(tts_file, "r", encoding="utf-8") as file:
                text = file.read()
        except UnicodeDecodeError:
            with open(tts_file, "r") as file:
                text = file.read()
    
    # EdgeTTS outputs MP3 format, save to temp file first
    temp_mp3 = output_file.replace(".wav", "_temp.mp3")
    await edge_tts.Communicate(text, voice, rate=rates).save(temp_mp3)
    
    # Convert MP3 to WAV for RVC compatibility
    audio = AudioSegment.from_mp3(temp_mp3)
    audio.export(output_file, format="wav")
    
    # Clean up temp file
    if os.path.exists(temp_mp3):
        os.remove(temp_mp3)


if __name__ == "__main__":
    asyncio.run(main())
