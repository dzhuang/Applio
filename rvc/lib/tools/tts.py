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
    
    # Ensure text is not empty
    if not text or not text.strip():
        print("Error: No text to synthesize")
        return
    
    # EdgeTTS outputs MP3 format, save to temp file first
    base_path = os.path.splitext(output_file)[0]
    temp_mp3 = f"{base_path}_temp.mp3"
    
    try:
        await edge_tts.Communicate(text, voice, rate=rates).save(temp_mp3)
    except Exception as e:
        print(f"Error during EdgeTTS synthesis: {e}")
        return
    
    # Verify temp file exists and has content
    if not os.path.exists(temp_mp3):
        print(f"Error: EdgeTTS failed to create file {temp_mp3}")
        return
    
    file_size = os.path.getsize(temp_mp3)
    if file_size < 1000:  # Less than 1KB is likely an error
        print(f"Error: EdgeTTS created invalid file (size: {file_size} bytes)")
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)
        return
    
    # Convert MP3 to WAV for RVC compatibility
    try:
        audio = AudioSegment.from_mp3(temp_mp3)
        audio.export(output_file, format="wav")
        print(f"TTS completed. Output: {output_file}")
    except Exception as e:
        print(f"Error converting MP3 to WAV: {e}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)


if __name__ == "__main__":
    asyncio.run(main())
