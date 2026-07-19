from fastapi import APIRouter, Request, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.models import Input, GatewayResponse
from services.gateway_service import process_gateway_chat

router = APIRouter(prefix="/gateway")

@router.post("/chat", response_model=GatewayResponse)
async def chat_with_llm(
    request: Request, 
    input_data: Input, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    return await process_gateway_chat(request, input_data, background_tasks, db)