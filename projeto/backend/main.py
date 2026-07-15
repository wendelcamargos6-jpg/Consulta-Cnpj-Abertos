from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.logger import logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.export import router as export_router
from api.health import router as health_router
from api.root import router as root_router
from api.search import router as search_router
from api.test import router as test_router
from services.database_service import DatabaseService

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

def create_app() -> FastAPI:
    app = FastAPI(title="CNPJ Hunter Pro")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(root_router)
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(export_router)
    app.include_router(test_router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            serialized_error = dict(error)
            ctx = serialized_error.get("ctx")
            if isinstance(ctx, dict):
                serialized_error["ctx"] = {
                    key: str(value) if isinstance(value, Exception) else value
                    for key, value in ctx.items()
                }
            errors.append(serialized_error)

        logger.warning("Validação falhou para %s: %s", request.url, errors)
        detail_message = "Dados de entrada inválidos. Verifique os campos e tente novamente."
        if errors:
            first_error = errors[0]
            msg = first_error.get("msg", "")
            if "Data deve estar no formato" in msg:
                detail_message = "Data deve estar no formato YYYY-MM-DD."
            elif "Intervalo máximo" in msg:
                detail_message = "O intervalo entre datas não pode ultrapassar 10 dias."
            elif "não pode ser maior" in msg:
                detail_message = "O valor mínimo não pode ser maior que o valor máximo."

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": detail_message,
                "errors": errors,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.error("HTTP exception em %s: %s", request.url, exc.detail)
        content = {"success": False, "message": exc.detail}
        if isinstance(exc.detail, dict):
            content.update(exc.detail)
        else:
            content["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.on_event("startup")
    def startup_event():
        logger.info("Inicializando aplicação CNPJ Hunter Pro")
        DatabaseService.initialize_database()

    return app

app = create_app()
