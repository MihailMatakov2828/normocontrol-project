FROM ollama/ollama

WORKDIR /app

# Устанавливаем Python и зависимости
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python-пакеты (флаг --break-system-packages решает ошибку)
RUN pip3 install --break-system-packages --no-cache-dir fastapi uvicorn httpx

COPY main.py .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000 11434

ENTRYPOINT ["/entrypoint.sh"]