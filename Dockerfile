FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p bin \
    && g++ -std=c++17 -O2 -Wall -Wextra compiler/main.cpp -o bin/delivery_compiler \
    && chmod +x bin/delivery_compiler

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} web.app:app"]
