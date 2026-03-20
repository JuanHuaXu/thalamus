from pypdf import PdfWriter, PageObject
import io

writer = PdfWriter()
page = PageObject.create_blank_page(width=72*8.5, height=72*11)
# Simply adding some text to the page if possible, or just a known string in metadata
writer.add_page(page)
writer.add_metadata({"/Title": "Thalamus PDF Test", "/Author": "Clawdius"})

with open("/Users/clawdius/Projects/thalamus/tmp/test.pdf", "wb") as f:
    writer.write(f)

# Note: pypdf.create_blank_page is empty. 
# To add text, we'd need reportlab, but it might not be installed.
# I'll just use a small existing PDF if I can find one, or assume the crawler logic is enough.
print("Tiny PDF created at /Users/clawdius/Projects/thalamus/tmp/test.pdf")
