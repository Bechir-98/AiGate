import logging
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.models import Input, GatewayResponse
from services.gateway_service import process_gateway_chat

logger = logging.getLogger("gateway_router")
router = APIRouter(prefix="/gateway", tags=["Gateway Orchestration"])

@router.post("/chat", response_model=GatewayResponse)
async def chat_with_llm(
    request: Request, 
    input_data: Input, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Entrypoint for the master LLM proxy pipeline.
    Delegates payload to the internal gateway service for scanning, 
    anonymization, and upstream LLM execution.
    """
    return await process_gateway_chat(request, input_data, background_tasks, db)