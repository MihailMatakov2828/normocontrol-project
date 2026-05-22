from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_service")

app = FastAPI(title=os.getenv("SERVICE_NAME", "Normocontrol-Judge"))

LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = "http://localhost:11434"

SYSTEM_PROMPT = """
оцени текст от 0 до 100. верни только число.

правила:
- есть слово "введение" → 40 баллов
- есть слово "заключение" → 40 баллов
- длина текста больше 500 символов → 20 баллов

максимум 100.

пример:
- текст: "введение ... заключение ..." (длина >500) → 100
- текст: "введение ... заключение ..." (длина <500) → 80
- текст: "введение ..." (длина >500) → 60
- текст: "заключение ..." (длина >500) → 60
- текст: "просто текст" → 0

верни только число. ничего кроме числа.
"""

class CheckRequest(BaseModel):
    prompt: str

def extract_score(raw_response: str) -> int:
    """Извлекает число из ответа модели"""
    # Ищем число в ответе
    match = re.search(r'\b([0-9]{1,3})\b', raw_response)
    if match:
        score = int(match.group(1))
        return min(100, max(0, score))  # Ограничиваем от 0 до 100
    return 0

@app.post("/check")
async def check(request: CheckRequest):
    logger.info(f"[{os.getenv('SERVICE_NAME')}] Проверка...")
    
    full_prompt = f"{SYSTEM_PROMPT}\n\nтекст:\n{request.prompt[:3000]}\n\nоценка:"
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 20}
            }
        )
        result = response.json()
        raw_response = result.get("response", "").strip()
        
        logger.info(f"[{os.getenv('SERVICE_NAME')}] Ответ модели: {raw_response}")
        
        # Извлекаем оценку
        score = extract_score(raw_response)
        
        # Превращаем в good/bad (порог 70)
        verdict = "good" if score >= 70 else "bad"
        
        logger.info(f"[{os.getenv('SERVICE_NAME')}] Оценка: {score}, Вердикт: {verdict}")
        return {"verdict": verdict, "score": score}

@app.get("/health")
async def health():
    return {"status": "ok", "model": LLM_MODEL}
