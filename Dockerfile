FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Create application user for security and Hugging Face Spaces compatibility (UID 1000)
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=user . .

# Set cache permissions
RUN mkdir -p /home/user/.cache && chown -R user:user /home/user/.cache

# Switch to non-root user
USER user

# Expose port (if web health-check is needed)
EXPOSE 7860

# Launch the bot
CMD ["python", "bot.py"]

