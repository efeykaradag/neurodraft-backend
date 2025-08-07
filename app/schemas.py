from datetime import datetime
from pydantic import BaseModel,EmailStr

class NoteBase(BaseModel):
    title: str
    content: str

# --- FOLDER SCHEMAS ---
class FolderCreate(BaseModel):
    name: str

class FolderEdit(BaseModel):
    name: str

# --- NOTE SCHEMAS ---
class NoteCreate(BaseModel):
    title: str
    content: str

class NoteEdit(BaseModel):
    content: str

class NoteOut(NoteBase):
    id: int
    created_at: str
    folder_id: int
    class Config:
        orm_mode = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


