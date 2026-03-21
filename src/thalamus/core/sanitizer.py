import re
import base64
import io
import logging
from typing import List
from .config import settings
from ..providers.crawler import CrawlerProvider

logger = logging.getLogger(__name__)

class BinarySanitizer:
    """
    Detects and sanitizes binary data (base64, data URLs) in message content.
    - Replaces images with placeholder [IMAGE].
    - Extracts text from base64-encoded PDFs.
    - Enforces size limits to prevent 'brain rot' and DDoS.
    """

    # Matches dataURL: data:image/png;base64,iVBOR... or data:application/pdf;base64,...
    DATA_URL_PATTERN = re.compile(r"data:([a-zA-Z0-9/.-]+);base64,([a-zA-Z0-9+/=]+)")
    
    # Matches generic large base64-looking blocks (heuristically)
    # A long alphanumeric string without spaces that is likely binary
    BASE64_BLOCK_PATTERN = re.compile(r"(?:[a-zA-Z0-9+/]{64,})={0,2}")

    @staticmethod
    def _process_binary_block(b64_data: str, mime_suggestion: str = None) -> str:
        """Identifies binary type and extracts content (text) or summary (metadata)."""
        try:
            # Decode head for magic byte detection
            raw_head = base64.b64decode(b64_data[:128])
            
            # 1. PDF Detection & DEEP EXTRACTION
            if raw_head.startswith(b"%PDF-") or (mime_suggestion and "pdf" in mime_suggestion):
                print("[Thalamus Sanitizer] Detected PDF block. Attempting deep extraction...", flush=True)
                try:
                    pdf_bytes = base64.b64decode(b64_data)
                    text = CrawlerProvider._extract_pdf(pdf_bytes)
                    return f"\n[EXTRACTED FROM PDF]:\n{text}\n" if text else " [EMPTY PDF] "
                except Exception as e:
                    logger.error(f"[Thalamus] Raw PDF extraction failed: {e}")
                    return " [FAILED PDF EXTRACTION] "

            # 2. PNG Detection & Metadata
            if raw_head.startswith(b"\x89PNG\r\n\x1a\n") or (mime_suggestion and "png" in mime_suggestion):
                import struct
                # PNG dimensions are at 16-24
                w, h = struct.unpack(">II", raw_head[16:24]) if len(raw_head) >= 24 else (0, 0)
                return f" [IMAGE: PNG, {w}x{h}] " if w > 0 else " [IMAGE: PNG] "
            
            # 3. JPEG Detection
            if raw_head.startswith(b"\xff\xd8\xff") or (mime_suggestion and "jpeg" in mime_suggestion):
                return " [IMAGE: JPEG] "
            
            # 4. GIF Detection
            if raw_head.startswith(b"GIF87a") or raw_head.startswith(b"GIF89a") or (mime_suggestion and "gif" in mime_suggestion):
                return " [IMAGE: GIF] "

            # 5. Audio/Video Signaries
            if raw_head.startswith(b"ID3") or raw_head.startswith(b"\xff\xfb"):
                return " [AUDIO: MP3] "
            if b"ftyp" in raw_head:
                return " [VIDEO/AUDIO: MP4/MOV] "
            
            if mime_suggestion:
                return f" [BINARY: {mime_suggestion}] "
            return " [UNIDENTIFIED BINARY BLOCK] "
        except Exception as e:
            logger.debug(f"[Thalamus] Binary processing error: {e}")
            return " [INVALID BINARY DATA] "

    @staticmethod
    def sanitize_message(content: str) -> str:
        if len(content) > settings.max_message_size:
            logger.warning(f"[Thalamus] Message too large ({len(content)} chars). Truncating.")
            content = content[:settings.max_message_size] + "\n... [TRUNCATED DUE TO SIZE] ..."

        # 1. Handle Data URLs (Explicit MIME)
        def handle_data_url(match):
            mime_type = match.group(1).lower()
            b64_data = match.group(2)
            summary = BinarySanitizer._process_binary_block(b64_data, mime_suggestion=mime_type)
            print(f"[Thalamus Sanitizer] Sanitized Data URL ({mime_type})", flush=True)
            return summary

        content = BinarySanitizer.DATA_URL_PATTERN.sub(handle_data_url, content)

        # 2. Handle raw base64 blocks (Heuristic detection)
        def handle_raw_b64(match):
            block = match.group(0)
            if len(block) > 300: # Final threshold for "brain rot"
                summary = BinarySanitizer._process_binary_block(block)
                print(f"[Thalamus Sanitizer] Stripping raw base64 block: {summary.strip()[:50]}...", flush=True)
                return summary
            return block

        content = BinarySanitizer.BASE64_BLOCK_PATTERN.sub(handle_raw_b64, content)

        return content
