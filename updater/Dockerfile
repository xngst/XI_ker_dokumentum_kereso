FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y cron && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
    
COPY crontab_def /etc/cron.d/crontab_def
COPY . .

RUN chmod 0644 /etc/cron.d/crontab_def && \
    crontab /etc/cron.d/crontab_def

CMD ["cron", "-f"]
