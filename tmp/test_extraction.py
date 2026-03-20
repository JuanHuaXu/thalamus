import asyncio
import sys
import os

# Add src to path
sys.path.append(os.path.abspath("src"))

from thalamus.providers.crawler import CrawlerProvider

async def test_real_extraction():
    url = "https://docs.openclaw.ai/start/getting-started"
    print(f"Testing extraction for: {url}")
    content = CrawlerProvider.fetch_and_clean(url)
    
    if content:
        print("\n--- EXTRACTION SUCCESSFUL ---")
        print(f"Length: {len(content)} chars")
        print("Sample (first 500 chars):")
        print(content[:500])
        print("--- END SAMPLE ---")
    else:
        print("\n--- EXTRACTION FAILED (Likely blocked or too short) ---")

if __name__ == "__main__":
    asyncio.run(test_real_extraction())
