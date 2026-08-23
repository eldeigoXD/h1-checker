# ── Stage 1: Python app ──────────────────────────────────────────────────────
FROM python:3.11-slim

# Install Chrome + ChromeDriver for Selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip curl \
    fonts-liberation libgbm1 libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libdrm2 libgdk-pixbuf2.0-0 \
    libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libxshmfence1 \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Default port Flask listens on
EXPOSE 5000

# Run Flask with auto-reload disabled in production
CMD ["python", "app.py"]
