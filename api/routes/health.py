import httpx
from fastapi import APIRouter
from config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/test-groq-keys")
async def test_groq_keys():
    keys = settings.get_groq_api_keys()
    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for idx, key in enumerate(keys, 1):
            masked = key[:7] + "..." + key[-4:] if len(key) > 11 else "invalid"
            try:
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if resp.status_code == 200:
                    status = "VÁLIDA (200 OK)"
                elif resp.status_code == 429:
                    status = f"AGOTADA (429 Rate Limit) - {resp.text}"
                else:
                    status = f"INVÁLIDA ({resp.status_code}) - {resp.text}"
            except Exception as e:
                status = f"ERROR: {str(e)}"
            results.append({"key_num": idx, "key_masked": masked, "status": status})
    return {"total_keys": len(keys), "results": results}

