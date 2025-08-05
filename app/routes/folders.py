from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import Folder, Note, File
from app.database import get_db
from app.auth.routes import get_current_user
from app.schemas import FolderCreate

router = APIRouter()

@router.post("/folders")
def create_folder(folder: FolderCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    new_folder = Folder(name=folder.name, user_id=user.id)
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)
    return new_folder

@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder and user.role != "admin":
        raise HTTPException(404, "Klasör bulunamadı veya yetkiniz yok.")
    db.delete(folder)
    db.commit()
    return {"msg": "Klasör silindi."}

@router.patch("/folders/{folder_id}")
def edit_folder(folder_id: int, folder: FolderCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    db_folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not db_folder and user.role != "admin":
        raise HTTPException(404, "Klasör bulunamadı veya yetkiniz yok.")
    db_folder.name = folder.name
    db.commit()
    return db_folder

@router.get("/folders")
def get_folders(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role == "admin":
        return db.query(Folder).all()
    return db.query(Folder).filter(Folder.user_id == user.id).all()

@router.get("/folders/{folder_id}/contents")
def get_folder_contents(folder_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Klasörün kullanıcıya ait veya admin olup olmadığı kontrolü
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Klasör bulunamadı")
    if user.role != "admin" and folder.user_id != user.id:
        raise HTTPException(status_code=403, detail="Erişim reddedildi")

    notes = db.query(Note).filter(Note.folder_id == folder_id).all()
    files = db.query(File).filter(File.folder_id == folder_id).all()

    return {
        "folder_id": folder.id,
        "folder_name": folder.name,
        "notes": [
            {"id": n.id, "title": n.title, "content": n.content, "created_at": n.created_at}
            for n in notes
        ],
        "files": [
            {"id": f.id, "filename": f.filename, "type": f.filetype, "uploaded_at": f.uploaded_at}
            for f in files
        ]
    }