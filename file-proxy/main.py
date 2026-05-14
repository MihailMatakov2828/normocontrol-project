import asyncio
import httpx
from fastapi import FastAPI, UploadFile, File
import logging
import uuid
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("file-proxy")

app = FastAPI(title="File Proxy for Normocontrol")


LLM_SERVICES = [
    "http://llm-1:8000/check",
    "http://llm-2:8000/check",
    "http://llm-3:8000/check",
]
SERVICE_URL = "http://normocontrol-service:8000/process"
QUORUM_THRESHOLD = 2  # 2 голоса из 3

async def query_llm(client: httpx.AsyncClient, url: str, text: str) -> tuple:
    try:
        response = await client.post(
            url,
            json={"prompt": text[:2000]},
            timeout=300.0,
        )
        if response.status_code == 200:
            result = response.json()
            verdict = result.get("verdict", "bad")
            logger.info(f"LLM {url}: {verdict}")
            return ("ok", verdict)
        else:
            logger.warning(f"LLM {url} вернул статус {response.status_code}")
            return ("error", "bad")
    except Exception as e:
        logger.error(f"Ошибка при запросе к {url}: {e}")
        return ("error", "bad")

async def get_consensus(text: str) -> tuple:
    good_votes = 0
    total_ok = 0
    votes = {}

    async with httpx.AsyncClient() as client:
        tasks = [query_llm(client, url, text) for url in LLM_SERVICES]
        results = await asyncio.gather(*tasks)

        for i, (status, verdict) in enumerate(results):
            service_name = f"llm_{i+1}"
            votes[service_name] = verdict if status == "ok" else "error"
            
            if status == "ok":
                total_ok += 1
                if verdict == "good":
                    good_votes += 1
                    logger.info(f"{service_name}: GOOD")
                else:
                    logger.info(f"{service_name}: BAD")
            else:
                logger.warning(f"{service_name}: {status}")

    quorum_reached = good_votes >= QUORUM_THRESHOLD
    
    logger.info(f"Голосование: GOOD={good_votes}, BAD={total_ok-good_votes}, Всего ответов={total_ok}")
    logger.info(f"Кворум ({QUORUM_THRESHOLD} из {len(LLM_SERVICES)}): {' ДОСТИГНУТ' if quorum_reached else ' НЕ ДОСТИГНУТ'}")
    
    return quorum_reached, {"good_votes": good_votes, "total_ok": total_ok, "votes": votes}

@app.post("/check")
async def check_file(file: UploadFile = File(...)):
    check_id = str(uuid.uuid4())[:8]
    
    logger.info(f"\n{'='*50}")
    logger.info(f"[{check_id}] НОВЫЙ ФАЙЛ: {file.filename}")
    
    content = await file.read()
    text = content.decode('utf-8', errors='ignore')
    
    os.makedirs("/app/uploads", exist_ok=True)
    with open(f"/app/uploads/{check_id}_{file.filename}", "wb") as f:
        f.write(content)
    
    logger.info(f"[{check_id}] Размер текста: {len(text)} символов")
    
    is_good, consensus = await get_consensus(text[:3000])
    
    if is_good:
        logger.info(f"[{check_id}]  РЕШЕНИЕ: ОДОБРЕНО, отправляем на нормоконтроль")
        
        async with httpx.AsyncClient() as client:
            service_response = await client.post(
                SERVICE_URL,
                json={
                    "check_id": check_id,
                    "filename": file.filename,
                    "content": text
                },
                timeout=120.0
            )
            result = service_response.json()
        
        return {
            "status": "approved",
            "check_id": check_id,
            "consensus": consensus,
            "normocontrol_result": result
        }
    else:
        logger.warning(f"[{check_id}]  РЕШЕНИЕ: ОТКЛОНЕНО")
        return {
            "status": "rejected",
            "check_id": check_id,
            "consensus": consensus,
            "reason": "Файл не прошёл предварительную проверку"
        }

@app.get("/health")
async def health():
    return {"status": "file_proxy_ok", "active_judges": len(LLM_SERVICES)}