import PyPDF2

reader = PyPDF2.PdfReader(r"c:\Users\Ashutosh.thakur\Desktop\Full-Stack-Engineer-Training-and-Project\pddf.pdf")
print(f"Total pages: {len(reader.pages)}")
for i, page in enumerate(reader.pages):
    text = page.extract_text() or "(no text)"
    with open(f"slide_{i+1}.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Page {i+1}: {len(text)} chars")
