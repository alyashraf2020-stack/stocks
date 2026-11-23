from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.services.seeder import seed_security_master
from app.api.v1.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema and seed full EGX Security Master
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_security_master(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="منصة التحليل الفني ودعم القرار اللحظي لأسهم البورصة المصرية (EGX حصراً)",
    lifespan=lifespan
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

@app.middleware("http")
async def validate_browser_write_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in settings.CORS_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
    return await call_next(request)


app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "message": "مرحباً بكم في منصة تداول وتحليل أسهم البورصة المصرية (EGX)",
        "disclaimer": "هذه المنصة أداة دعم قرار وليست ضماناً للربح أو بديلاً عن الاستشارة المالية المتخصصة.",
        "api_docs": "/docs",
        "scope": "Egyptian Exchange Equities Only"
    }