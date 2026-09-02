FROM python:3.11-slim

WORKDIR /app

# Copy bot files
COPY webhook_bot.py .
COPY generate_lesson.py .
COPY gita-data.json .
COPY gita-progress.json .

# No pip install needed — uses only Python stdlib

# Render sets PORT env var automatically
EXPOSE $PORT

CMD ["python", "webhook_bot.py"]