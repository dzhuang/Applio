"""
TTS Cache Utility

Provides file-based caching for TTS audio segments to avoid redundant API calls.
Supports FIFO eviction when cache exceeds size limit.
"""

import os
import hashlib
import time
from pathlib import Path


# Default configuration (can be overridden by environment variable)
CACHE_DIR = os.path.join("assets", "tts_cache")
DEFAULT_MAX_SIZE_MB = int(os.environ.get("SRT_TTS_CACHE_SIZE_MB", 512))


def ensure_cache_dir():
    """Ensure cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)


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


def get_cache_path(key: str, format: str = "mp3") -> str:
    """
    Get the file path for a cached audio segment.
    
    Args:
        key: Cache key (MD5 hash)
        format: Audio format extension ("mp3" or "wav")
        
    Returns:
        Full path to cache file
    """
    ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{key}.{format}")


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


def get_cache_size_mb() -> float:
    """
    Get current cache size in megabytes.
    
    Returns:
        Cache size in MB
    """
    ensure_cache_dir()
    
    total_size = 0
    for file in Path(CACHE_DIR).glob("*"):
        if file.is_file():
            total_size += file.stat().st_size
    
    return total_size / (1024 * 1024)


def get_cache_files_sorted() -> list:
    """
    Get list of cache files sorted by modification time (oldest first).
    
    Returns:
        List of (path, size, mtime) tuples, oldest first
    """
    ensure_cache_dir()
    
    files = []
    for file in Path(CACHE_DIR).glob("*"):
        if file.is_file():
            stat = file.stat()
            files.append((str(file), stat.st_size, stat.st_mtime))
    
    # Sort by modification time (oldest first for FIFO)
    files.sort(key=lambda x: x[2])
    return files


def enforce_cache_limit(max_size_mb: int = DEFAULT_MAX_SIZE_MB) -> int:
    """
    Enforce cache size limit using FIFO eviction.
    
    Args:
        max_size_mb: Maximum cache size in MB
        
    Returns:
        Number of files removed
    """
    current_size = get_cache_size_mb()
    
    if current_size <= max_size_mb:
        return 0
    
    files = get_cache_files_sorted()
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


def clear_cache() -> int:
    """
    Clear all cached files.
    
    Returns:
        Number of files removed
    """
    ensure_cache_dir()
    
    removed_count = 0
    for file in Path(CACHE_DIR).glob("*"):
        if file.is_file():
            try:
                os.remove(file)
                removed_count += 1
            except Exception as e:
                print(f"[Cache] Error removing {file}: {e}")
    
    print(f"[Cache] Cleared {removed_count} files")
    return removed_count


def get_cache_stats() -> dict:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache stats
    """
    ensure_cache_dir()
    
    files = list(Path(CACHE_DIR).glob("*"))
    file_count = len([f for f in files if f.is_file()])
    size_mb = get_cache_size_mb()
    
    return {
        "file_count": file_count,
        "size_mb": round(size_mb, 2),
        "cache_dir": CACHE_DIR
    }
