from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.models import Note, Folder
from app.database import get_db
from app.auth.routes import get_current_user
from app.schemas import NoteCreate
import shutil

router = APIRouter()

# NOT EKLE
@router.post("/folders/{folder_id}/notes")
def add_note(folder_id: int, note: NoteCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder and user.role != "admin":
        raise HTTPException(404, "Klasör bulunamadı veya yetkiniz yok.")
    new_note = Note(title=note.title, content=note.content, folder_id=folder_id)
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note

@router.post("/folders/{folder_id}/files")
def upload_file(folder_id: int, upload_file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_ext = upload_file.filename.split('.')[-1].lower()
    allowed = ['jpg','jpeg','png','pdf','mp3','wav','m4a']
    if file_ext not in allowed:
        raise HTTPException(400, "Dosya tipi desteklenmiyor.")
    save_path = f"uploads/{folder_id}_{upload_file.filename}"
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    # DB’ye File ekle
    file_obj = File(folder_id=folder_id, filename=upload_file.filename, file_type=file_ext, path=save_path)
    db.add(file_obj)
    db.commit()
    return {"msg": "Dosya yüklendi", "file": file_obj.id}

# NOTLARI GETİR
@router.get("/folders/{folder_id}/notes")
def get_notes(folder_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder or (folder.user_id != user.id and user.role != "admin"):
        raise HTTPException(403, "Yetkiniz yok.")
    return db.query(Note).filter(Note.folder_id == folder_id).all()

# NOTU SİL
@router.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    note = (
        db.query(Note)
        .join(Folder)
        .filter(Note.id == note_id, Folder.user_id == user.id)
        .first()
    )
    # Adminler bütün notları silebilir!
    if not note and user.role != "admin":
        raise HTTPException(404, "Not bulunamadı veya yetkiniz yok.")
    db.delete(note)
    db.commit()
    return {"msg": "Not silindi."}

# NOTU DÜZENLE
@router.patch("/notes/{note_id}")
def edit_note(note_id: int, note: NoteCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    db_note = (
        db.query(Note)
        .join(Folder)
        .filter(Note.id == note_id, Folder.user_id == user.id)
        .first()
    )
    # Adminler bütün notları düzenleyebilir!
    if not db_note and user.role != "admin":
        raise HTTPException(404, "Not bulunamadı veya yetkiniz yok.")
    db_note.content = note.content
    db_note.title = note.title   # <-- Bunu ekle!
    db.commit()
    db.refresh(db_note)
    return db_note