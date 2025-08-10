from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models import Base
from app.database import engine, get_db
from app.routes import folders, notes, file, demo_login, presentation
from app.auth import routes
from .ai import router as ai_router
from fastapi.staticfiles import StaticFiles
from .utils.cleanup_demo import cleanup_expired_demo_sessions
from apscheduler.schedulers.background import BackgroundScheduler

Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_demo_sessions, 'interval', minutes=1)
scheduler.start()

app = FastAPI()
app.include_router(folders.router)

app.include_router(demo_login.router)


app.mount("/uploaded_files", StaticFiles(directory="uploaded_files"), name="uploaded_files")
app.include_router(presentation.router)
app.include_router(file.router)
app.include_router(notes.router)
app.include_router(ai_router)
app.include_router(routes.router)

origins = [
    "https://www.neurodrafts.com",     # Prod domainin
    "http://localhost:3000",           # Lokal geliştirmen için
    "https://neurodrafts.com",
    "https://neurodraft-frontend-git-main-efeykaradags-projects.vercel.app/",
    "neurodraft-frontend.vercel.app",
    "https://neurodraft-frontend-efeykaradags-projects.vercel.app/"

]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
