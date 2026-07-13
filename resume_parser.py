import pypdf

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts all text from a local PDF file."""
    text = ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
    return text.strip()
