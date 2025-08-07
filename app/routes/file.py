import os
from datetime import datetime

from fastapi import APIRouter, UploadFile, File as FastAPIFile, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import File as FileModel, Folder, File, Note, DemoSession
from app.auth.routes import get_current_user, get_current_user_optional
from app.utils.compression import compress_image, zip_any_file, get_mime_type
from uuid import uuid4
from app.utils.extractors import extract_text_auto

router = APIRouter()
UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_SIZE_MB = 30  # Gerekirse değiştir

@router.post("/folders/{folder_id}/files")
async def upload_file(
    folder_id: int,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Klasör bulunamadı!")

    content = await file.read()
    if len(content) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dosya çok büyük!")

    # Geçici olarak kaydet
    temp_id = str(uuid4())
    filename = f"{temp_id}_{file.filename}"
    temp_path = os.path.join(UPLOAD_DIR, filename)
    with open(temp_path, "wb") as f:
        f.write(content)

    # MIME türünü bul
    mime = get_mime_type(temp_path)

    # --- 1. ADIM: Extract text from ORIGINAL FILE! ---
    try:
        extracted_text = extract_text_auto(temp_path, mime=mime)
    except Exception as e:
        print(f"Extract error: {e}")
        extracted_text = None

    # --- 2. ADIM: Sıkıştırma/optimizasyon (optional, prod için faydalı) ---
    final_path = temp_path
    if "image" in mime:
        compressed_path = temp_path.rsplit('.', 1)[0] + "_compressed.jpg"
        compress_image(temp_path, compressed_path)
        os.remove(temp_path)
        final_path = compressed_path
    elif not ("image" in mime):
        zipped_path = temp_path + ".zip"
        zip_any_file(temp_path, zipped_path)
        os.remove(temp_path)
        final_path = zipped_path

    # --- 3. ADIM: File kaydı ---
    new_file = FileModel(
        folder_id=folder_id,
        user_id=user.id,
        filename=os.path.basename(final_path),
        filepath=final_path,
        filetype=mime,
        extracted_text=extracted_text or ""  # NULL constraint hatasını engelle
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    # --- 4. ADIM: Note olarak da kaydet (AI notu) ---
    new_note = None
    if extracted_text and extracted_text.strip():
        new_note = Note(
            folder_id=folder_id,
            title=file.filename,
            content=extracted_text,
        )
        db.add(new_note)
        db.commit()
        db.refresh(new_note)

    return {
        "message": "Dosya başarıyla yüklendi, işlendi ve not olarak kaydedildi!",
        "file_id": new_file.id,
        "note_id": new_note.id if new_note else None,
        "filename": new_file.filename,
        "type": new_file.filetype,
        "extracted_text_preview": extracted_text[:300] if extracted_text else None
    }


from fastapi import Request

@router.get("/folders/{folder_id}/files")
async def list_files(
    folder_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        # DEMO kullanıcı
        ip = request.client.host
        demo_session = db.query(DemoSession).filter_by(ip_address=ip).first()
        if not demo_session or demo_session.expires_at < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Demo süresi dolmuş veya aktif demo yok.")
        files = db.query(FileModel).filter(
            FileModel.folder_id == folder_id,
            FileModel.demo_session_id == demo_session.id
        ).all()
    else:
        # Normal user
        files = db.query(FileModel).filter(
            FileModel.folder_id == folder_id,
            FileModel.user_id == user.id
        ).all()

    return [
        {"id": f.id, "filename": f.filename, "type": f.filetype, "uploaded_at": f.uploaded_at}
        for f in files
    ]

@router.delete("/files/{file_id}")
def delete_file(
        file_id: int,
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    file = db.query(File).filter(File.id == file_id, File.user_id == user.id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file.filepath  # <--- DİKKAT! Senin modelinde yol/fiziksel isim neyse onu kullan

    # Önce DB'den sil
    db.delete(file)
    db.commit()

    # Sonra dosyayı diskten sil (yoksa hata vermez)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            # Opsiyonel: Logla ama kullanıcıya hata döndürme!
            print(f"Dosya silinirken hata: {e}")

    return {"detail": "File and physical file deleted"}

@router.get("/files/{file_id}/preview")
def preview_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        # DEMO kullanıcısı ise:
        ip = request.client.host
        demo_session = db.query(DemoSession).filter_by(ip_address=ip).first()
        if not demo_session or demo_session.expires_at < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Demo süresi dolmuş veya aktif demo yok.")
        file = db.query(FileModel).filter(
            FileModel.id == file_id,
            FileModel.demo_session_id == demo_session.id
        ).first()
    else:
        # Normal user ise:
        file = db.query(FileModel).filter(
            FileModel.id == file_id,
            FileModel.user_id == user.id
        ).first()

    if not file:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı!")

    # Eğer .zip dosyasıysa aç
    if file.filepath.endswith(".zip"):
        import zipfile, tempfile, os
        with zipfile.ZipFile(file.filepath, "r") as zipf:
            namelist = zipf.namelist()
            if not namelist:
                raise HTTPException(status_code=404, detail="Zip dosyası boş!")
            tmp_dir = tempfile.mkdtemp()
            member = namelist[0]
            out_path = os.path.join(tmp_dir, member)
            zipf.extract(member, tmp_dir)
            from fastapi.responses import FileResponse
            return FileResponse(out_path, filename=member)
    # Zipsiz ise direkt dosyayı göster
    from fastapi.responses import FileResponse
    return FileResponse(file.filepath, filename=file.filename)
