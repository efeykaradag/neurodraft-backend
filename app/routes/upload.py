import os
from fastapi import APIRouter, UploadFile, File as FastAPIFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import File as FileModel, Note  # <-- Note modelini import et!
from app.auth.routes import get_current_user
from app.utils.compression import (
    compress_image, compress_pdf, compress_audio, zip_any_file, get_mime_type
)
from app.utils.extractors import (
    extract_text_from_pdf, extract_text_from_image, extract_text_from_audio
)
from uuid import uuid4

router = APIRouter()
UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_SIZE_MB = int(os.getenv("MAX_SIZE_MB") or 32)

@router.post("/files/upload")
async def upload_file(
    folder_id: int = Form(...),
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # --- Dosya Boyut Limiti ---
    content = await file.read()
    if len(content) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dosya çok büyük.")

    temp_id = str(uuid4())
    original_path = os.path.join(UPLOAD_DIR, f"{temp_id}_{file.filename}")
    with open(original_path, "wb") as f:
        f.write(content)

    mime = get_mime_type(original_path)
    compressed_path = original_path

    # --- METİN ÇIKAR ---
    try:
        if "pdf" in mime:
            extracted_text = extract_text_from_pdf(original_path)
        elif "image" in mime:
            extracted_text = extract_text_from_image(original_path)
        elif "audio" in mime:
            extracted_text = extract_text_from_audio(original_path)
        else:
            extracted_text = ""
    except Exception as e:
        extracted_text = ""
        print(f"Extract Error: {file.filename} - {e}")

    # --- SIKIŞTIR ---
    try:
        if "image" in mime:
            compressed_path = original_path.rsplit('.', 1)[0] + "_compressed.jpg"
            compress_image(original_path, compressed_path)
            os.remove(original_path)
        elif "pdf" in mime:
            compressed_path = original_path.rsplit('.', 1)[0] + "_compressed.pdf"
            compress_pdf(original_path, compressed_path)
            os.remove(original_path)
        elif "audio" in mime:
            compressed_path = original_path.rsplit('.', 1)[0] + "_compressed.mp3"
            compress_audio(original_path, compressed_path)
            os.remove(original_path)
        else:
            compressed_path = original_path + ".zip"
            zip_any_file(original_path, compressed_path)
            os.remove(original_path)
    except Exception as e:
        if os.path.exists(original_path):
            os.remove(original_path)
        print(f"Compression Error: {file.filename} - {e}")
        raise HTTPException(status_code=500, detail="Sıkıştırma işlemi başarısız.")

    # --- DOSYA VERİTABANI KAYDI ---
    new_file = FileModel(
        folder_id=folder_id,
        user_id=current_user["id"],
        filename=os.path.basename(compressed_path),
        filetype=mime,
        filepath=compressed_path,
        extracted_text=extracted_text or ""
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    # --- ÇIKAN TEXT'TEN OTOMATİK NOT EKLEME ---
    created_note_id = None
    if extracted_text and extracted_text.strip():
        note = Note(
            folder_id=folder_id,
            created_at=current_user["id"],
            title=f"AI ile çıkarılan: {file.filename}",
            content=extracted_text[:10000]  # Çok büyükse kırp (ör: 10k karakter)
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        created_note_id = note.id

    return {
        "message": "Dosya başarıyla yüklendi ve sıkıştırıldı",
        "file_id": new_file.id,
        "filename": new_file.filename,
        "compressed_size": os.path.getsize(compressed_path),
        "original_size": len(content),
        "type": mime,
        "extracted_text": extracted_text[:400] if extracted_text else None,
        "note_id": created_note_id,
        "note_created": bool(created_note_id),
    }
