FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Create user with UID 1000 (Hugging Face expectation)
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its system dependencies
RUN playwright install-deps chromium && playwright install chromium

# Copy the rest of the application code
COPY --chown=user . .

# Set permissions for Hugging Face cache directories
RUN mkdir -p /home/user/.cache && chown -R user:user /home/user/.cache

# Switch to the non-root user
USER user

# Expose port 7860
EXPOSE 7860

# Run the FastAPI app
CMD ["python", "app.py"]
