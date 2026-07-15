import re
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, ConfigDict
from typing import Optional
# Import de ta fonction pour obtenir la session DB
from database import get_db
from models.entity_mapping import DBEntityMapping

router = APIRouter(prefix="/mappings", tags=["Entity Mappings"])

# ==========================================
# 1. SCHÉMAS PYDANTIC
# ==========================================

class MappingCreate(BaseModel):
    # L'utilisateur ne fournit QUE le label GLiNER
    gliner_label: str

class MappingResponse(BaseModel):
    id: int
    gliner_label: str
    presidio_label: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class MappingUpdate(BaseModel):
    gliner_label: Optional[str] = None
    is_active: Optional[bool] = None

# ==========================================
# 2. LOGIQUE DE FORMATAGE & CACHE
# ==========================================

def generate_presidio_label(gliner_label: str) -> str:
    """
    Transforme 'Credit Card' ou 'passport-id' en 'CREDIT_CARD' ou 'PASSPORT_ID'.
    """
    label = gliner_label.strip().upper()
    # Remplace les espaces et les tirets par des underscores
    label = re.sub(r'[\s\-]+', '_', label)
    return label

async def invalidate_redis_cache(request: Request):
    """
    Supprime la clé en cache pour forcer FastAPI à recharger les données depuis Postgres.
    """
    redis_client = request.app.state.redis
    await redis_client.delete("gliner_entity_mapping")

# ==========================================
# 3. ROUTES (CRUD)
# ==========================================

@router.get("/", response_model=list[MappingResponse])
async def list_mappings(db: AsyncSession = Depends(get_db)):
    """Récupère toutes les entités configurées."""
    result = await db.execute(select(DBEntityMapping))
    return result.scalars().all()


@router.post("/", response_model=MappingResponse)
async def create_mapping(
    mapping_in: MappingCreate, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Crée une nouvelle entité. Le label Presidio est généré automatiquement."""
    # On garde la casse d'origine pour GLiNER 2, mais on utilise le lower pour les checks DB
    gliner_label_original = mapping_in.gliner_label.strip()
    gliner_label_lower = gliner_label_original.lower()
    
    # Vérifie si l'entité existe déjà (insensible à la casse)
    result = await db.execute(
        select(DBEntityMapping).where(func.lower(DBEntityMapping.gliner_label) == gliner_label_lower)
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Ce label GLiNER existe déjà.")

    # Génération automatique du label Presidio
    auto_presidio_label = generate_presidio_label(gliner_label_original)

    new_mapping = DBEntityMapping(
        gliner_label=gliner_label_original,  # Sauvegarde avec la casse naturelle
        presidio_label=auto_presidio_label,
        is_active=True
    )
    
    db.add(new_mapping)
    await db.commit()
    await db.refresh(new_mapping)
    
    # Invalide le cache Redis pour prendre en compte le changement
    await invalidate_redis_cache(request)
    
    return new_mapping


@router.delete("/{mapping_id}")
async def delete_mapping(
    mapping_id: int, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Supprime définitivement une entité."""
    result = await db.execute(
        select(DBEntityMapping).where(DBEntityMapping.id == mapping_id)
    )
    mapping = result.scalars().first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping introuvable.")

    await db.delete(mapping)
    await db.commit()

    # Invalide le cache Redis
    await invalidate_redis_cache(request)

    return {"status": "success", "message": f"Entité {mapping.gliner_label} supprimée."}


@router.patch("/{mapping_id}", response_model=MappingResponse)
async def update_mapping(
    mapping_id: int, 
    mapping_in: MappingUpdate, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Met à jour une entité existante (nom ou statut d'activation)."""
    # 1. On cherche l'entité
    result = await db.execute(
        select(DBEntityMapping).where(DBEntityMapping.id == mapping_id)
    )
    mapping = result.scalars().first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping introuvable.")

    # 2. Si l'utilisateur veut modifier le label
    if mapping_in.gliner_label is not None:
        gliner_label_original = mapping_in.gliner_label.strip()
        gliner_label_lower = gliner_label_original.lower()
        
        # Vérifier que le nouveau nom n'existe pas déjà sur une autre entité (insensible à la casse)
        check_exist = await db.execute(
            select(DBEntityMapping).where(
                (func.lower(DBEntityMapping.gliner_label) == gliner_label_lower) & 
                (DBEntityMapping.id != mapping_id)
            )
        )
        if check_exist.scalars().first():
            raise HTTPException(status_code=400, detail="Ce label GLiNER est déjà utilisé ailleurs.")
            
        # Mise à jour des deux labels en conservant la casse naturelle
        mapping.gliner_label = gliner_label_original
        mapping.presidio_label = generate_presidio_label(gliner_label_original)

    # 3. Si l'utilisateur veut activer/désactiver l'entité
    if mapping_in.is_active is not None:
        mapping.is_active = mapping_in.is_active

    # 4. Sauvegarde
    await db.commit()
    await db.refresh(mapping)
    await invalidate_redis_cache(request)

    return mapping