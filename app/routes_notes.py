from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import Folder, Note
from app.database import get_db
from app.auth.routes import get_current_user  # az önce yazdığın fonksiyon

router = APIRouter()

# Kendi klasörlerini getir
@router.get("/folders")
def get_folders(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role == "admin":
        return db.query(Folder).all()
    return db.query(Folder).filter(Folder.user_id == user.id).all()

# Klasör oluştur
@router.post("/folders")
def create_folder(name: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    folder = Folder(name=name, user_id=user.id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder

# Klasöre not ekle
@router.post("/folders/{folder_id}/notes")
def add_note(folder_id: int, content: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder and user.role != "admin":
        raise HTTPException(404, "Klasör bulunamadı veya yetkiniz yok.")
    note = Note(content=content, folder_id=folder_id)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note

# Klasördeki notları getir
@router.get("/folders/{folder_id}/notes")
def get_notes(folder_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder or (folder.user_id != user.id and user.role != "admin"):
        raise HTTPException(403, "Yetkiniz yok.")
    return db.query(Note).filter(Note.folder_id == folder_id).all()
