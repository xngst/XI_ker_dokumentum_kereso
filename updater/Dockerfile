FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y cron && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
    
COPY example-crontab /etc/cron.d/example-crontab
COPY . .

RUN chmod 0644 /etc/cron.d/example-crontab && \
    crontab /etc/cron.d/example-crontab
 
#RUN useradd -u 1000 shareduser   
#USER shareduser

CMD ["cron", "-f"]
