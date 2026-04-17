from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.admin import router as admin_router
from app.student import router as student_router
from app.config_manager import init_data_dirs

app = FastAPI(title="DiplomaSpark", description="AI-powered diploma idea generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
async def startup():
    init_data_dirs()


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def server_error(request: Request, exc):
    return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)


app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(student_router, tags=["student"])
