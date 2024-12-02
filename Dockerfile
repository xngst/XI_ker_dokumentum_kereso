FROM python:3.9-slim

WORKDIR /app

COPY app/ /app/

RUN pip install -r requirements.txt

EXPOSE 8510

CMD ["streamlit", "run", "app.py", "--server.port=8510", "--server.address=0.0.0.0"]

