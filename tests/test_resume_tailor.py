import os
import unittest
from unittest.mock import patch, MagicMock
from resume_tailor import extract_text_from_pdf, query_groq_resume_analysis

# Helper to generate dummy PDF bytes for testing
def create_dummy_pdf_bytes():
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    import io
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()

class TestResumeTailor(unittest.TestCase):

    def test_extract_text_from_pdf_invalid(self):
        with self.assertRaises(ValueError):
            extract_text_from_pdf(b"invalid pdf content")

    def test_extract_text_from_pdf_valid(self):
        pdf_bytes = create_dummy_pdf_bytes()
        # Should parse without exception, even if blank page contains empty string
        text = extract_text_from_pdf(pdf_bytes)
        self.assertEqual(text, "")

    @patch("resume_tailor.requests.post")
    def test_query_groq_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "### 🎯 Role Match: Backend Engineer\n\n### 💡 Top Missing Keywords\n* Python"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        # Temporarily mock API key environment variable
        with patch.dict(os.environ, {"GROQ_API_KEY": "test_api_key"}):
            result = query_groq_resume_analysis("Resume content", "Backend Engineer")
            self.assertIn("Backend Engineer", result)
            self.assertIn("Python", result)

    def test_query_groq_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                query_groq_resume_analysis("Resume content", "Backend Engineer")
