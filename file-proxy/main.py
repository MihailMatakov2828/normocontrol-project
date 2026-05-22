import asyncio
import httpx
from fastapi import FastAPI, UploadFile, File
import logging
import uuid
import os
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("file-proxy")

app = FastAPI(title="File Proxy for Normocontrol")


LLM_SERVICES = [
    "http://llm-1:8000/check",
    # "http://llm-2:8000/check",   
    # "http://llm-3:8000/check",   
]
SERVICE_URL = "http://normocontrol-service:8000/process"
QUORUM_THRESHOLD = 1  # 1 голос из 1

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
            score = result.get("score", 0)
            logger.info(f"LLM {url}: {verdict} (score={score})")
            return ("ok", verdict, score)
        else:
            logger.warning(f"LLM {url} вернул статус {response.status_code}")
            return ("error", "bad", 0)
    except Exception as e:
        logger.error(f"Ошибка при запросе к {url}: {e}")
        return ("error", "bad", 0)

async def get_consensus(text: str) -> tuple:
    good_votes = 0
    total_ok = 0
    votes = {}

    async with httpx.AsyncClient() as client:
        tasks = [query_llm(client, url, text) for url in LLM_SERVICES]
        results = await asyncio.gather(*tasks)

        for i, (status, verdict, score) in enumerate(results):  # ← исправлено
            service_name = f"llm_{i+1}"
            votes[service_name] = {"verdict": verdict, "score": score}
            
            if status == "ok":
                total_ok += 1
                if verdict == "good":
                    good_votes += 1
                    logger.info(f"{service_name}: GOOD (score={score})")
                else:
                    logger.info(f"{service_name}: BAD (score={score})")
            else:
                logger.warning(f"{service_name}: {status}")

    quorum_reached = good_votes >= QUORUM_THRESHOLD
    
    logger.info(f"Голосование: GOOD={good_votes}, BAD={total_ok-good_votes}, Всего ответов={total_ok}")
    logger.info(f"Кворум ({QUORUM_THRESHOLD} из {len(LLM_SERVICES)}): {'✅ ДОСТИГНУТ' if quorum_reached else '❌ НЕ ДОСТИГНУТ'}")
    
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
        logger.info(f"[{check_id}] ✅ РЕШЕНИЕ: ОДОБРЕНО, отправляем на нормоконтроль")
        
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
        logger.warning(f"[{check_id}] ❌ РЕШЕНИЕ: ОТКЛОНЕНО")
        return {
            "status": "rejected",
            "check_id": check_id,
            "consensus": consensus,
            "reason": "Файл не прошёл предварительную проверку"
        }

@app.get("/health")
async def health():
    return {"status": "file_proxy_ok", "active_judges": len(LLM_SERVICES)}


@app.post("/batch_test")
async def batch_test():
    """Проверяет все сгенерированные файлы и считает точность"""
    
    folder = "/app/test_files"
    results = []
    correct = 0
    total = 0
    
    info_path = os.path.join(folder, "files_info.json")
    if not os.path.exists(info_path):
        return {"error": "files_info.json not found. Run generate_tests.py first."}
    
    with open(info_path, "r", encoding="utf-8") as f:
        files_info = json.load(f)
    
    for file_info in files_info:
        filename = file_info["filename"]
        expected = file_info["expected"]
        
        filepath = os.path.join(folder, filename)
        if not os.path.exists(filepath):
            continue
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        is_good, consensus = await get_consensus(content[:3000])
        llm_verdict = "good" if is_good else "bad"
        
        total += 1
        if llm_verdict == expected:
            correct += 1
        
        results.append({
            "filename": filename,
            "corruption": file_info.get("corruption", 0),
            "expected": expected,
            "llm_verdict": llm_verdict,
            "correct": llm_verdict == expected,
            "scores": consensus.get("votes", {})
        })
    
    accuracy = correct / total if total > 0 else 0
    
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "results": results
    }
