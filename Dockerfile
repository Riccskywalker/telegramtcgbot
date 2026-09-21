FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 bot \
    && chown bot:bot /app
COPY --chown=bot:bot tcgbot/ ./tcgbot/
USER bot
CMD ["python", "-m", "tcgbot"]
