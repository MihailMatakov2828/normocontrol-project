from fastapi import FastAPI
from pydantic import BaseModel
import logging
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("normocontrol-service")

app = FastAPI()

class ProcessRequest(BaseModel):
    check_id: str
    filename: str
    content: str

@app.post("/process")
async def process(request: ProcessRequest):
    text = request.content
    errors = []
    
    if "Введение" not in text and "ВВЕДЕНИЕ" not in text:
        errors.append("Нет раздела 'Введение'")
    if "Заключение" not in text and "ЗАКЛЮЧЕНИЕ" not in text:
        errors.append("Нет раздела 'Заключение'")
    if "список литературы" not in text.lower():
        errors.append("Нет списка литературы")
    
    result = {
        "check_id": request.check_id,
        "filename": request.filename,
        "status": "approved" if len(errors) == 0 else "rejected",
        "errors": errors
    }
    
    os.makedirs("/app/reports", exist_ok=True)
    with open(f"/app/reports/{request.check_id}.json", "w") as f:
        json.dump(result, f)
    
    logger.info(f"[{request.check_id}] Результат: {result['status']}")
    return result

@app.get("/health")
async def health():
    return {"status": "ok"}
