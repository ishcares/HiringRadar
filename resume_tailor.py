"""
resume_tailor.py — Core utility for analyzing PDF resumes against target roles using Groq LLM.

Uses pypdf to extract raw text and queries Groq's API via requests.
No heavy LLM framework dependencies.
"""

import io
import os
import requests
from pypdf import PdfReader

# The Groq endpoint for chat completions
GROQ_API_URL = "https://api.groq.com/openapi/v1/chat/completions"


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text content from raw PDF bytes."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def query_groq_resume_analysis(resume_text: str, target_role: str) -> str:
    """
    Sends the resume text and target role to Groq for comparative analysis.
    Returns recommendations: missing keywords, summary rewrite, and outreach hook.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not configured.")

    system_prompt = (
        "You are an expert technical recruiter matching candidate resumes to job descriptions. "
        "Analyze the candidate's resume text against the target role title. "
        "Be constructive, direct, and concise. Do not use generic filler words."
    )

    user_prompt = f"""
Target Role: {target_role}

Candidate Resume Text:
---
{resume_text[:4000]}
---

Please perform a comparative analysis and respond using this exact markdown template:

### 🎯 Role Match: [Target Role]

### 💡 Top Missing Keywords
* Identify 4-6 specific technical skills, tools, or frameworks commonly required for the target role that are missing or weak in the resume text.

### ✍️ Tailored Summary Suggestion
* Provide a strong, 3-sentence summary (profile header) optimized for this target role.

### 📬 Cold Outreach Hook
* Provide a concise 2-sentence cold message/email pitch the candidate can send to recruiters for this role.
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1000
    }

    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
        if response.status_code != 200:
            raise RuntimeError(f"Groq API returned error status {response.status_code}: {response.text}")
        
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Failed to communicate with Groq LLM API: {str(e)}")
