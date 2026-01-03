"""
TTS Cache Utility

Provides file-based caching for TTS audio segments.
- tts_cache: EdgeTTS/Azure API 原始音频缓存
- tts_output_cache: RVC 处理后的最终音频缓存

Supports FIFO eviction when cache exceeds size limit.
"""

import os
import hashlib
import time
from pathlib import Path


# API 缓存配置
CACHE_DIR = os.path.join("assets", "tts_cache")
DEFAULT_MAX_SIZE_MB = int(os.environ.get("SRT_TTS_CACHE_SIZE_MB", 512))

# Output 缓存配置
OUTPUT_CACHE_DIR = os.path.join("assets", "tts_output_cache")
OUTPUT_CACHE_MAX_SIZE_MB = int(os.environ.get("TTS_OUTPUT_CACHE_SIZE_MB", 256))


def ensure_cache_dir(cache_dir: str = None):
    """Ensure cache directory exists."""
    dir_path = cache_dir or CACHE_DIR
    os.makedirs(dir_path, exist_ok=True)


def get_cache_key(text: str, voice: str, rate: str, mode: str) -> str:
    """
    Generate a unique cache key based on TTS parameters.
    
    Args:
        text: The text content to synthesize
        voice: Voice name (e.g., "zh-CN-YunxiNeural")
        rate: TTS rate (e.g., "+10%", "-5%", "1.0")
        mode: TTS mode ("azure" or "edge")
        
    Returns:
        MD5 hash string as cache key
    """
    key_string = f"{mode}:{voice}:{rate}:{text}"
    return hashlib.md5(key_string.encode('utf-8')).hexdigest()


def get_cache_path(key: str, format: str = "mp3", cache_dir: str = None) -> str:
    """
    Get the file path for a cached audio segment.
    
    Args:
        key: Cache key (MD5 hash)
        format: Audio format extension ("mp3" or "wav")
        cache_dir: Cache directory (default: CACHE_DIR)
        
    Returns:
        Full path to cache file
    """
    dir_path = cache_dir or CACHE_DIR
    ensure_cache_dir(dir_path)
    return os.path.join(dir_path, f"{key}.{format}")


def get_cached_audio(text: str, voice: str, rate: str, mode: str, format: str = "mp3") -> bytes:
    """
    Retrieve cached audio data if available.
    
    Args:
        text: The text content
        voice: Voice name
        rate: TTS rate
        mode: TTS mode ("azure" or "edge")
        format: Audio format extension
        
    Returns:
        Audio data as bytes, or None if not cached
    """
    key = get_cache_key(text, voice, rate, mode)
    cache_path = get_cache_path(key, format)
    
    if os.path.exists(cache_path):
        try:
            # Update access time for FIFO tracking
            Path(cache_path).touch()
            
            with open(cache_path, 'rb') as f:
                audio_data = f.read()
            
            print(f"[Cache] HIT: {voice} \"{text[:30]}...\"")
            return audio_data
        except Exception as e:
            print(f"[Cache] Error reading cache: {e}")
            return None
    
    return None


def save_to_cache(
    text: str, 
    voice: str, 
    rate: str, 
    mode: str, 
    audio_data: bytes, 
    format: str = "mp3",
    max_size_mb: int = DEFAULT_MAX_SIZE_MB
) -> str:
    """
    Save audio data to cache.
    
    Args:
        text: The text content
        voice: Voice name
        rate: TTS rate
        mode: TTS mode
        audio_data: Audio data as bytes
        format: Audio format extension
        max_size_mb: Maximum cache size in MB
        
    Returns:
        Path to cached file, or None if failed
    """
    if audio_data is None or len(audio_data) == 0:
        return None
    
    key = get_cache_key(text, voice, rate, mode)
    cache_path = get_cache_path(key, format)
    
    try:
        ensure_cache_dir()
        
        with open(cache_path, 'wb') as f:
            f.write(audio_data)
        
        print(f"[Cache] SAVE: {voice} \"{text[:30]}...\" ({len(audio_data)} bytes)")
        
        # Enforce cache limit after saving
        enforce_cache_limit(max_size_mb)
        
        return cache_path
    except Exception as e:
        print(f"[Cache] Error saving to cache: {e}")
        return None


def get_cache_size_mb(cache_dir: str = None) -> float:
    """
    Get current cache size in megabytes.
    
    Returns:
        Cache size in MB
    """
    dir_path = cache_dir or CACHE_DIR
    ensure_cache_dir(dir_path)
    
    total_size = 0
    for file in Path(dir_path).glob("*"):
        if file.is_file():
            total_size += file.stat().st_size
    
    return total_size / (1024 * 1024)


def get_cache_files_sorted(cache_dir: str = None) -> list:
    """
    Get list of cache files sorted by modification time (oldest first).
    
    Returns:
        List of (path, size, mtime) tuples, oldest first
    """
    dir_path = cache_dir or CACHE_DIR
    ensure_cache_dir(dir_path)
    
    files = []
    for file in Path(dir_path).glob("*"):
        if file.is_file():
            stat = file.stat()
            files.append((str(file), stat.st_size, stat.st_mtime))
    
    # Sort by modification time (oldest first for FIFO)
    files.sort(key=lambda x: x[2])
    return files


def enforce_cache_limit(max_size_mb: int = DEFAULT_MAX_SIZE_MB, cache_dir: str = None) -> int:
    """
    Enforce cache size limit using FIFO eviction.
    
    Args:
        max_size_mb: Maximum cache size in MB
        cache_dir: Cache directory
        
    Returns:
        Number of files removed
    """
    dir_path = cache_dir or CACHE_DIR
    current_size = get_cache_size_mb(dir_path)
    
    if current_size <= max_size_mb:
        return 0
    
    files = get_cache_files_sorted(dir_path)
    removed_count = 0
    
    for file_path, file_size, _ in files:
        if current_size <= max_size_mb:
            break
        
        try:
            os.remove(file_path)
            current_size -= file_size / (1024 * 1024)
            removed_count += 1
            print(f"[Cache] EVICT: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"[Cache] Error removing {file_path}: {e}")
    
    return removed_count


def clear_cache(cache_dir: str = None) -> int:
    """
    Clear all cached files.
    
    Returns:
        Number of files removed
    """
    dir_path = cache_dir or CACHE_DIR
    ensure_cache_dir(dir_path)
    
    removed_count = 0
    for file in Path(dir_path).glob("*"):
        if file.is_file():
            try:
                os.remove(file)
                removed_count += 1
            except Exception as e:
                print(f"[Cache] Error removing {file}: {e}")
    
    print(f"[Cache] Cleared {removed_count} files")
    return removed_count


def clear_cache_older_than(hours: int, cache_dir: str = None) -> int:
    """
    Clear cache files older than specified hours.
    
    Args:
        hours: Number of hours (1, 2, 24, etc.)
        cache_dir: Cache directory
        
    Returns:
        Number of files removed
    """
    dir_path = cache_dir or CACHE_DIR
    ensure_cache_dir(dir_path)
    
    cutoff_time = time.time() - (hours * 3600)
    removed_count = 0
    
    for file in Path(dir_path).glob("*"):
        if file.is_file():
            if file.stat().st_mtime < cutoff_time:
                try:
                    os.remove(file)
                    removed_count += 1
                except Exception as e:
                    print(f"[Cache] Error removing {file}: {e}")
    
    print(f"[Cache] Cleared {removed_count} files older than {hours} hours")
    return removed_count


def get_cache_stats(cache_dir: str = None) -> dict:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache stats
    """
    dir_path = cache_dir or CACHE_DIR
    ensure_cache_dir(dir_path)
    
    files = list(Path(dir_path).glob("*"))
    file_count = len([f for f in files if f.is_file()])
    size_mb = get_cache_size_mb(dir_path)
    
    return {
        "file_count": file_count,
        "size_mb": round(size_mb, 2),
        "cache_dir": dir_path
    }


# ============ Output Cache Functions ============

def get_output_cache_key(
    text: str, 
    voice: str, 
    rate: str, 
    model: str,
    pitch: int = 0,
    index_rate: float = 0.75,
    protect: float = 0.5,
    f0_method: str = "rmvpe",
    split_audio: bool = False,
    f0_autotune: bool = False,
    clean_audio: bool = False,
) -> str:
    """
    Generate cache key for TTS output (after RVC).
    Includes all RVC parameters for accurate cache matching.
    
    Args:
        text: Input text
        voice: TTS voice
        rate: TTS rate
        model: RVC model path/name
        pitch: Pitch shift value
        index_rate: Index rate
        protect: Protect value
        f0_method: F0 detection method
        split_audio: Whether audio splitting is enabled
        f0_autotune: Whether autotune is enabled
        clean_audio: Whether audio cleaning is enabled
        
    Returns:
        MD5 hash string
    """
    # Include all RVC params in cache key
    key_string = f"output:{voice}:{rate}:{model}:{pitch}:{index_rate}:{protect}:{f0_method}:{split_audio}:{f0_autotune}:{clean_audio}:{text}"
    return hashlib.md5(key_string.encode('utf-8')).hexdigest()


def get_cached_output(
    text: str, 
    voice: str, 
    rate: str, 
    model: str,
    pitch: int = 0,
    index_rate: float = 0.75,
    protect: float = 0.5,
    f0_method: str = "rmvpe",
    split_audio: bool = False,
    f0_autotune: bool = False,
    clean_audio: bool = False,
    format: str = "wav"
) -> str:
    """
    Get cached output file path if available.
    
    Returns:
        Path to cached file, or None if not cached
    """
    key = get_output_cache_key(
        text, voice, rate, model, pitch,
        index_rate, protect, f0_method,
        split_audio, f0_autotune, clean_audio
    )
    cache_path = os.path.join(OUTPUT_CACHE_DIR, f"{key}.{format}")
    
    if os.path.exists(cache_path):
        # Update access time
        Path(cache_path).touch()
        print(f"[OutputCache] HIT: {os.path.basename(cache_path)}")
        return cache_path
    
    return None


def save_output_to_cache(
    text: str, 
    voice: str, 
    rate: str, 
    model: str,
    pitch: int,
    index_rate: float,
    protect: float,
    f0_method: str,
    split_audio: bool,
    f0_autotune: bool,
    clean_audio: bool,
    source_path: str,
    format: str = "wav"
) -> str:
    """
    Save output file to cache.
    
    Args:
        text: Input text
        voice: TTS voice
        rate: TTS rate
        model: RVC model
        pitch: Pitch value
        index_rate, protect, f0_method, split_audio, f0_autotune, clean_audio: RVC params
        source_path: Path to source file to cache
        format: Audio format
        
    Returns:
        Path to cached file, or None if failed
    """
    import shutil
    
    if not os.path.exists(source_path):
        return None
    
    ensure_cache_dir(OUTPUT_CACHE_DIR)
    
    key = get_output_cache_key(
        text, voice, rate, model, pitch,
        index_rate, protect, f0_method,
        split_audio, f0_autotune, clean_audio
    )
    cache_path = os.path.join(OUTPUT_CACHE_DIR, f"{key}.{format}")
    
    try:
        shutil.copy2(source_path, cache_path)
        print(f"[OutputCache] SAVE: {os.path.basename(cache_path)}")
        
        # Enforce limit
        enforce_cache_limit(OUTPUT_CACHE_MAX_SIZE_MB, OUTPUT_CACHE_DIR)
        
        return cache_path
    except Exception as e:
        print(f"[OutputCache] Error: {e}")
        return None


def clear_all_caches(hours: int = None) -> dict:
    """
    Clear both API cache and output cache.
    
    Args:
        hours: If specified, only clear files older than this many hours
        
    Returns:
        Dict with counts of removed files
    """
    if hours:
        api_count = clear_cache_older_than(hours, CACHE_DIR)
        output_count = clear_cache_older_than(hours, OUTPUT_CACHE_DIR)
    else:
        api_count = clear_cache(CACHE_DIR)
        output_count = clear_cache(OUTPUT_CACHE_DIR)
    
    return {
        "api_cache_cleared": api_count,
        "output_cache_cleared": output_count
    }

