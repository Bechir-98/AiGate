from fastapi import FastAPI
from routers.scanner import router as scan_router
from routers.anonymizer import router as anonymizer_router
from routers.deanonymizer import router as deanonymizer_router
app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


app.include_router(scan_router)
app.include_router(anonymizer_router)
app.include_router(deanonymizer_router)
    