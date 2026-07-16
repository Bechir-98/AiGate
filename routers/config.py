from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from database import get_db
from utils.config_service import get_active_scanner, set_active_scanner

router = APIRouter(prefix="/config")

class ScannerChoice(BaseModel):
    scanner_name: str 

@router.post("/scanner")
async def update_scanner(
    choice: ScannerChoice, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    
    if choice.scanner_name not in ["spacy", "gliner1", "gliner2"]:
        return {"error": "Invalid scanner name. Choose spacy, gliner1, or gliner2."}
        
    await set_active_scanner(db, redis_client, choice.scanner_name)
    
    return {"message": f"Global scanner updated to {choice.scanner_name}"}

@router.get("/scanner")
async def get_scanner(
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    active_scanner = await get_active_scanner(db, redis_client)
    
    return {"active_scanner": active_scanner}