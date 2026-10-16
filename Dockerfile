FROM python:3.12-slim
WORKDIR /srv/bot
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
VOLUME ["/srv/bot/data"]
CMD ["python", "-m", "app.main"]
