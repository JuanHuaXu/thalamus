import httpx
import pypdf
import io
import trafilatura

url = "https://arxiv.org/pdf/1706.03762.pdf"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf"
}

try:
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        response = client.get(url, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"Content Length: {len(response.content)}")
        
        if response.status_code == 200:
            reader = pypdf.PdfReader(io.BytesIO(response.content))
            text = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
                if i > 2: break # Only first 3 pages
            
            print(f"Extracted Text Length: {len(' '.join(text))}")
            print("Snippet:", (" ".join(text))[:200])
except Exception as e:
    print(f"Error: {e}")
