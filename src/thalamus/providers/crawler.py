import trafilatura
from typing import Optional
import logging
from ..core.config import settings

logger = logging.getLogger(__name__)

class CrawlerProvider:
    """
    High-fidelity web documentation extractor.
    Uses trafilatura to strip boilerplates (navbars, ads, footers).
    """
    
    @staticmethod
    def _is_raw_code(content_type: str, url: str) -> bool:
        """Helper to identify if content is likely raw source code."""
        raw_types = ["text/plain", "text/javascript", "application/x-javascript", "text/x-python", "text/x-typescript"]
        if any(t in content_type for t in raw_types):
            return True
        ext = url.split("?")[0].lower().split(".")[-1]
        return ext in ["js", "py", "ts", "txt", "go", "rs", "cpp", "h", "c"]

    @staticmethod
    def fetch_and_clean(url: str) -> Optional[str]:
        content_type = ""
        content = None
        is_pdf = False
        is_code = False
        try:
            import httpx
            import io
            import urllib.parse
            import socket
            import ipaddress

            parsed = urllib.parse.urlparse(url)
            if parsed.hostname:
                try:
                    ip = socket.gethostbyname(parsed.hostname)
                    if ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback:
                        logger.error(f"[Thalamus] SSRF Prevention: Blocked internal network address {url}")
                        return None
                except socket.gaierror:
                    logger.error(f"[Thalamus] SSRF Prevention: Could not resolve hostname {parsed.hostname}")
                    return None

            logger.info(f"[Thalamus] Crawling: {url}")
            
            headers = {
                "User-Agent": settings.crawler_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/pdf",
                "Accept-Language": "en-US,en;q=0.9"
            }
            
            with httpx.Client(follow_redirects=True, timeout=settings.crawler_timeout) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                
                content_type = response.headers.get("Content-Type", "").lower()
                is_pdf = "application/pdf" in content_type or url.lower().endswith(".pdf")
                is_code = CrawlerProvider._is_raw_code(content_type, url)

                # 1. Handle PDFs
                if is_pdf:
                    logger.info(f"[Thalamus] Detected PDF for {url}. Extracting text...")
                    return CrawlerProvider._extract_pdf(response.content)

                # 2. Handle Raw Code / Plain Text
                if is_code:
                    logger.info(f"[Thalamus] Detected Raw Code/Text for {url}")
                    content = response.text
                else:
                    # 3. Handle HTML (Default)
                    downloaded = response.text
                    content = trafilatura.extract(
                        downloaded, 
                        include_comments=False,
                        include_tables=True,
                        no_fallback=False
                    )

            if not content:
                logger.warning(f"[Thalamus] No content extracted from: {url}")
                return None

            # BRAIN ROT PROTECTION: Heuristics to detect bot-blocking/CAPTCHA pages
            # Skip length check for Code (which can be very short but dense)
            if not is_code:
                if len(content) < 200:
                    logger.warning(f"[Thalamus] Content from {url} is too short ({len(content)} chars). Likely garbage.")
                    return None

                rot_signatures = ["captcha", "human verification", "access denied", "blocked", "cloudflare", "ddos guard"]
                content_lower = content.lower()
                if any(sig in content_lower for sig in rot_signatures):
                    logger.error(f"[Thalamus] Detected 'Brain Rot' signature on {url}. Rejecting.")
                    return None
                
            return content
        except Exception as e:
            logger.error(f"[Thalamus] Crawler error on {url}: {e}")
            return None

    @staticmethod
    def _extract_pdf(pdf_bytes: bytes) -> Optional[str]:
        """Extracts text from PDF bytes using pypdf."""
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            return "\n\n".join(text) if text else None
        except Exception as e:
            logger.error(f"[Thalamus] PDF extraction error: {e}")
            return None
