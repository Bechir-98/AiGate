import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import async_sessionmaker_local
from models.db_models import AppConfig
from models.db_models import DBEntityMapping

DEFAULT_MAPPINGS = [
    {"gliner_label": "PERSON", "presidio_label": "PERSON"},
    {"gliner_label": "EMAIL", "presidio_label": "EMAIL_ADDRESS"},
    {"gliner_label": "PHONE NUMBER", "presidio_label": "PHONE_NUMBER"},
    {"gliner_label": "ADDRESS", "presidio_label": "LOCATION"},
    {"gliner_label": "ORGANIZATION", "presidio_label": "ORGANIZATION"},
    {"gliner_label": "DATE OF BIRTH", "presidio_label": "DATE_TIME"},
    {"gliner_label": "IP ADDRESS", "presidio_label": "IP_ADDRESS"},
]

async def seed_database():
    print("Starting database seeding...")
    
    async with async_sessionmaker_local() as session:
        async with session.begin():
            config_query = await session.execute(
                select(AppConfig).where(AppConfig.key == "active_scanner")
            )
            existing_config = config_query.scalars().first()
            
            if not existing_config:
                session.add(AppConfig(key="active_scanner", value="spacy"))
                print("-> Seeded default active scanner: 'spacy'")
            else:
                print(f"-> Active scanner already set to: '{existing_config.value}'")

            for mapping in DEFAULT_MAPPINGS:
                mapping_query = await session.execute(
                    select(DBEntityMapping).where(
                        DBEntityMapping.gliner_label == mapping["gliner_label"]
                    )
                )
                existing_mapping = mapping_query.scalars().first()
                
                if not existing_mapping:
                    session.add(
                        DBEntityMapping(
                            gliner_label=mapping["gliner_label"],
                            presidio_label=mapping["presidio_label"]
                        )
                    )
                    print(f"-> Seeded mapping: {mapping['gliner_label']} -> {mapping['presidio_label']}")
                else:
                    print(f"-> Mapping already exists for: {mapping['gliner_label']}")

        await session.commit()
    print("Database seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_database())