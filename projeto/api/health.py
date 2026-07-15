from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "online", "version": "1.0.0"}
