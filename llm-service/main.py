from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_service")

app = FastAPI(title=os.getenv("SERVICE_NAME", "Normocontrol-Judge"))

LLM_MODEL = os.getenv("LLM_MODEL", "gemma2:2b")
OLLAMA_BASE_URL = "http://localhost:11434"

SYSTEM_PROMPT = """
Ты — интеллектуальный фильтр для системы нормоконтроля. Проверь, имеет ли смысл отправлять файл на полную проверку.

Проверь наличие этих элементов:
1. Введение (или раздел, который его заменяет по смыслу)
2. Заключение (или выводы)
3. Список литературы (минимум 3 источника)
4. Текст не слишком короткий (больше 500 символов)

Правило: если присутствуют хотя бы 3 элемента из 4 → ответь "good", иначе "bad".

Ответь только одним словом: good или bad.
"""

class CheckRequest(BaseModel):
    prompt: str

@app.post("/check")
async def check(request: CheckRequest):
    logger.info(f"[{os.getenv('SERVICE_NAME')}] Проверка...")
    
    full_prompt = f"{SYSTEM_PROMPT}\n\nТекст:\n{request.prompt[:2000]}\n\nОтвет:"
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 50}
            }
        )
        result = response.json()
        raw_response = result.get("response", "").strip().lower()
        
        verdict = "good" if "good" in raw_response else "bad"
        
        logger.info(f"[{os.getenv('SERVICE_NAME')}] Вердикт: {verdict}")
        return {"verdict": verdict}

@app.get("/health")
async def health():
    return {"status": "ok", "model": LLM_MODEL}