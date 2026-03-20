FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    fonts-noto-cjk \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY daemon/ ./daemon/

# PDF download directory (also volume-mounted)
RUN mkdir -p /app/pdfs/yamato /app/pdfs/sagawa /app/cookies

# Symlink so config.yaml's global.repo_root (/home/pi/SHINBEE) resolves
# correctly inside the container: repo_root/services/selenium-daemon → /app
RUN mkdir -p /home/pi/SHINBEE/services && ln -s /app /home/pi/SHINBEE/services/selenium-daemon

ENV DISPLAY=:99

# Chromium runs as root inside the container → --no-sandbox is required
# (added in browser_args by daemon/browser/session.py)

COPY entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
