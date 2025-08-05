from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models import Base
from app.database import engine
from app.routes import folders, notes, file
from app.auth import routes as routes
from .ai import router as ai_router
from fastapi.staticfiles import StaticFiles



Base.metadata.create_all(bind=engine)



app = FastAPI()
app.include_router(folders.router)

app.mount("/uploaded_files", StaticFiles(directory="uploaded_files"), name="uploaded_files")

app.include_router(file.router)
app.include_router(notes.router)
app.include_router(ai_router)
app.include_router(routes.router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production’da domainini gir!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
