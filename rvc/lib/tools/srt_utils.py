"""
SRT to Speech Utilities

Provides functions for parsing SRT files and generating synchronized audio
using either Azure TTS (with timing sync) or EdgeTTS (sequential only).
"""

import io
import os
import time
from collections import Counter
from datetime import timedelta

import srt
from langdetect import detect
from pydub import AudioSegment

# Azure TTS support (optional)
try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False


def parse_srt(srt_file: str) -> list:
    """
    Parse an SRT file and return a list of (start, end, content) tuples.
    
    Args:
        srt_file: Path to the SRT file
        
    Returns:
        List of tuples: [(start_timedelta, end_timedelta, text_content), ...]
    """
    with open(srt_file, 'r', encoding='utf-8') as file:
        subtitles = srt.parse(file.read())
        segments = [(sub.start, sub.end, sub.content) for sub in subtitles]
    return segments


def detect_majority_language(segments: list) -> str:
    """
    Detect the majority language in SRT segments.
    
    Args:
        segments: List of (start, end, content) tuples
        
    Returns:
        Language code (e.g., 'en', 'zh-cn', 'ja')
    """
    languages = []
    for _, _, content in segments:
        try:
            detected_lang = detect(content)
            languages.append(detected_lang)
        except Exception as e:
            print(f"Error detecting language for content: {content}. Error: {e}")
    
    if languages:
        most_common_language = Counter(languages).most_common(1)[0][0]
        return most_common_language
    return 'en'


def get_azure_voice_for_language(language: str) -> str:
    """
    Get the default Azure voice name for a language.
    
    Args:
        language: Language code (e.g., 'en', 'zh-cn')
        
    Returns:
        Azure voice name
    """
    voice_map = {
        "en": "en-US-AriaNeural",
        "es": "es-ES-ArnauNeural",
        "zh-cn": "zh-CN-YunjieNeural",
        "zh-tw": "zh-TW-HsiaoChenNeural",
        "fr": "fr-FR-DeniseNeural",
        "de": "de-DE-KatjaNeural",
        "it": "it-IT-ElsaNeural",
        "ja": "ja-JP-NanamiNeural",
        "ko": "ko-KR-SunHiNeural",
        "pt": "pt-BR-FranciscaNeural",
        "ru": "ru-RU-DariyaNeural",
        "hi": "hi-IN-MadhurNeural",
    }
    return voice_map.get(language, "en-US-AriaNeural")


def text_to_speech_azure(
    text: str,
    speech_key: str,
    service_region: str,
    prosody_rate: str,
    voice_name: str,
    use_cache: bool = True,
    max_cache_size_mb: int = 512
) -> bytes:
    """
    Generate speech audio using Azure TTS with prosody rate adjustment.
    
    Args:
        text: Text to synthesize
        speech_key: Azure Speech API key
        service_region: Azure service region
        prosody_rate: Speed factor (e.g., "1.0", "1.5")
        voice_name: Azure voice name
        use_cache: Whether to use caching
        max_cache_size_mb: Maximum cache size in MB
        
    Returns:
        Audio data as bytes, or None if failed
    """
    # Check cache first
    if use_cache:
        from rvc.lib.tools.tts_cache import get_cached_audio, save_to_cache
        cached = get_cached_audio(text, voice_name, prosody_rate, "azure", "wav")
        if cached:
            return cached
    
    if not AZURE_AVAILABLE:
        print("Azure Speech SDK not available")
        return None
    
    # 移除 [API] 标记（如果存在）
    actual_voice_name = voice_name.replace(" [API]", "")
        
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    speech_config.speech_synthesis_voice_name = actual_voice_name
    
    # Set output format to WAV (16kHz, 16-bit, mono)
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
    )
    
    # Build SSML with prosody rate
    lang_code = actual_voice_name.split('-')[0] + '-' + actual_voice_name.split('-')[1]
    ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' 
           xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='{lang_code}'>
        <voice name='{actual_voice_name}'>
            <prosody rate='{prosody_rate}'>
                {text}
            </prosody>
        </voice>
    </speak>
    """
    
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_ssml_async(ssml_string).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        audio_data = result.audio_data
        # Save to cache
        if use_cache and audio_data:
            save_to_cache(text, voice_name, prosody_rate, "azure", audio_data, "wav", max_cache_size_mb)
        return audio_data
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print(f"Speech synthesis canceled: {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                print(f"Error details: {cancellation_details.error_details}")
        return None
    return None


def get_audio_duration(audio_data: bytes) -> float:
    """
    Get the duration of audio data in seconds.
    
    Args:
        audio_data: Audio data as bytes
        
    Returns:
        Duration in seconds, or 0 if audio is invalid
    """
    if not is_valid_wav_data(audio_data):
        print("[Azure] Invalid WAV data, returning duration 0")
        return 0
    
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        return len(audio) / 1000.0
    except Exception as e:
        print(f"[Azure] Error getting audio duration: {e}")
        return 0


def is_valid_wav_data(audio_data: bytes) -> bool:
    """
    Check if audio data is valid WAV format.
    
    Args:
        audio_data: Audio data as bytes
        
    Returns:
        True if valid WAV, False otherwise
    """
    if audio_data is None:
        return False
    if len(audio_data) < 44:  # WAV header is at least 44 bytes
        return False
    # Check for RIFF header
    if audio_data[:4] != b'RIFF':
        return False
    # Check for WAVE format
    if audio_data[8:12] != b'WAVE':
        return False
    return True


def combine_audio_segments_azure(
    segments: list,
    speech_key: str,
    service_region: str,
    voice_name: str,
    progress_callback=None
) -> AudioSegment:
    """
    Combine audio segments using Azure TTS with timing synchronization.
    
    This generates audio for each subtitle segment and adjusts the prosody rate
    to match the target duration from the SRT file.
    
    Args:
        segments: List of (start, end, content) tuples
        speech_key: Azure Speech API key
        service_region: Azure service region
        voice_name: Azure voice name
        progress_callback: Optional callback(current, total) for progress updates
        
    Returns:
        Combined AudioSegment
    """
    combined = AudioSegment.silent(duration=0)
    total = len(segments)
    success_count = 0
    
    for i, (start, end, content) in enumerate(segments):
        if progress_callback:
            progress_callback(i + 1, total)
        
        print(f"[Azure] Processing segment {i}: '{content[:30]}...'")
        target_duration = (end - start).total_seconds()
        
        # Generate audio with default prosody rate to measure duration
        audio_data = text_to_speech_azure(content, speech_key, service_region, "1.0", voice_name)
        
        # Retry logic
        retries = 3
        while (audio_data is None or not is_valid_wav_data(audio_data)) and retries > 0:
            print(f"[Azure] Retrying for segment {i}... (attempt {4-retries}/3)")
            time.sleep(2)
            audio_data = text_to_speech_azure(content, speech_key, service_region, "1.0", voice_name)
            retries -= 1
        
        if audio_data is None or not is_valid_wav_data(audio_data):
            # Use silent segment if TTS fails
            print(f"[Azure] Segment {i} failed, using silence")
            audio_segment = AudioSegment.silent(duration=int(target_duration * 1000))
        else:
            default_duration = get_audio_duration(audio_data)
            
            if default_duration <= 0:
                print(f"[Azure] Segment {i} has invalid duration, using silence")
                audio_segment = AudioSegment.silent(duration=int(target_duration * 1000))
            else:
                speed_factor = default_duration / target_duration
                
                # Clamp speed factor to reasonable range (0.5 to 3.0)
                speed_factor = max(0.5, min(3.0, speed_factor))
                prosody_rate = f"{speed_factor:.2f}"
                
                # Generate final audio with adjusted prosody rate
                audio_data = text_to_speech_azure(content, speech_key, service_region, prosody_rate, voice_name)
                
                # Retry if needed
                retries = 3
                while (audio_data is None or not is_valid_wav_data(audio_data)) and retries > 0:
                    print(f"[Azure] Retrying for segment {i} with prosody rate {prosody_rate}...")
                    time.sleep(2)
                    audio_data = text_to_speech_azure(content, speech_key, service_region, prosody_rate, voice_name)
                    retries -= 1
                
                if audio_data is None or not is_valid_wav_data(audio_data):
                    print(f"[Azure] Segment {i} final attempt failed, using silence")
                    audio_segment = AudioSegment.silent(duration=int(target_duration * 1000))
                else:
                    audio_segment = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
                    success_count += 1
                    print(f"[Azure] Segment {i} generated: {len(audio_segment)}ms")
        
        # Add silence to align with start time
        start_ms = int(start.total_seconds() * 1000)
        current_length = len(combined)
        if start_ms > current_length:
            silence = AudioSegment.silent(duration=start_ms - current_length)
            combined += silence
        
        combined += audio_segment
    
    print(f"[Azure] Generated {success_count}/{total} segments successfully")
    return combined


def combine_audio_segments_edge(
    audio_files: list,
    segments: list
) -> AudioSegment:
    """
    Combine audio files sequentially (EdgeTTS mode, no timing sync).
    
    Note: Unlike Azure mode, EdgeTTS mode concatenates audio segments
    sequentially without attempting to sync with SRT timestamps.
    
    Args:
        audio_files: List of audio file paths
        segments: List of (start, end, content) tuples (not used for timing)
        
    Returns:
        Combined AudioSegment
    """
    combined = None
    total_loaded = 0
    
    print(f"[SRT] Starting to combine {len(audio_files)} audio files")
    
    for i, audio_file in enumerate(audio_files):
        audio_segment = None
        
        if os.path.exists(audio_file):
            file_size = os.path.getsize(audio_file)
            print(f"[SRT] Segment {i}: file size = {file_size} bytes")
            
            if file_size > 500:  # At least 500 bytes for valid audio
                try:
                    audio_segment = AudioSegment.from_file(audio_file, format="mp3")
                    duration_ms = len(audio_segment)
                    print(f"[SRT] Segment {i}: loaded successfully, duration = {duration_ms}ms")
                    total_loaded += 1
                except Exception as e:
                    print(f"[SRT] Segment {i}: Error loading - {e}")
                    audio_segment = None
            else:
                print(f"[SRT] Segment {i}: file too small, skipping")
        else:
            print(f"[SRT] Segment {i}: file not found")
        
        # Skip invalid segments
        if audio_segment is None or len(audio_segment) == 0:
            continue
        
        # Combine
        if combined is None:
            combined = audio_segment
        else:
            # Add a small gap between segments
            gap = AudioSegment.silent(duration=300)
            combined = combined + gap + audio_segment
    
    # Handle case where no segments were loaded
    if combined is None:
        print("[SRT] WARNING: No segments loaded, returning 1 second of silence")
        combined = AudioSegment.silent(duration=1000)
    
    print(f"[SRT] Final combined duration: {len(combined)}ms ({len(combined)/1000:.1f} seconds)")
    print(f"[SRT] Successfully loaded {total_loaded}/{len(audio_files)} segments")
    
    return combined


def check_azure_api_available() -> tuple:
    """
    Check if Azure API credentials are available in environment variables.
    
    Returns:
        Tuple of (is_available: bool, speech_key: str, service_region: str)
    """
    speech_key = os.environ.get("AZURE_SPEECH_KEY", "")
    service_region = os.environ.get("AZURE_SERVICE_REGION", "")
    
    is_available = bool(speech_key and service_region and AZURE_AVAILABLE)
    return is_available, speech_key, service_region
