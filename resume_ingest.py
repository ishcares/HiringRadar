# resume_ingest.py
import io

def extract_resume_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.lower().split('.')[-1]
    text = ""
    
    if ext == 'pdf':
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
        except ImportError:
            # Fallback if fitz is not installed
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                print(f"Fallback PDF extractor failed: {e}")
    elif ext == 'docx':
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            print(f"DOCX extractor failed: {e}")
    else:
        text = file_bytes.decode('utf-8', errors='ignore')
    
    # Collapse excessive whitespace from column-based PDF layouts
    text = "\n".join(line.strip() for line in text.split("\n") if line.strip())
    return text


def extract_resume_text_from_path(file_path: str) -> str:
    """Helper wrapper to extract text directly from a local file path."""
    try:
        with open(file_path, "rb") as f:
            return extract_resume_text(f.read(), file_path)
    except Exception as e:
        print(f"Error reading file path {file_path}: {e}")
        return ""
