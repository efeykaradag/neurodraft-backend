import os
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Note, File
from together import Together
import re
import requests
from fastapi.responses import StreamingResponse
import json

# --- 3rd-party paketler için import (veya comment) ---
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

try:
    import whisper
except ImportError:
    whisper = None

class TTSRequest(BaseModel):
    text: str

# ========== API & Router ==========
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "Xb7hH8MSUJpSbSDYk0k2"
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
client = Together(api_key=TOGETHER_API_KEY)

router = APIRouter()

# ========== BODY SCHEMAS ==========
class NoteSummaryRequest(BaseModel):
    note_id: int
    text: str

class FolderRequest(BaseModel):
    folder_id: int

# ========== DOSYA İŞLEME ==========

def extract_pdf_text(pdf_path: str) -> str:
    if pdfplumber is None:
        return "[pdfplumber yüklü değil]"
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])
    except Exception as e:
        return f"[PDF okunamadı: {e}]"

def extract_image_text(image_path: str) -> str:
    if pytesseract is None or Image is None:
        return "[pytesseract/Pillow yüklü değil]"
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang="tur")
    except Exception as e:
        return f"[Resimden metin okunamadı: {e}]"

def transcribe_audio(audio_path: str) -> str:
    if whisper is None:
        return "[whisper yüklü değil]"
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language="tr")
        return result["text"]
    except Exception as e:
        return f"[Ses dosyası çözümlenemedi: {e}]"

# ========== KLASÖRÜN BÜTÜN İÇERİĞİNİ ÇEK ==========
def get_folder_all_contents(db: Session, folder_id: int) -> str:
    result = []
    notes = db.query(Note).filter(Note.folder_id == folder_id).all()
    files = db.query(File).filter(File.folder_id == folder_id).all()

    for note in notes:
        result.append(f"[Not: {note.title}]\n{note.content}")

    for file in files:
        if file.filetype == "pdf":
            pdf_text = extract_pdf_text(file.path)
            result.append(f"[PDF: {file.filename}]\n{pdf_text}")
        elif file.filetype == "audio":
            transcript = transcribe_audio(file.path)
            result.append(f"[Ses Dosyası: {file.filename}]\n{transcript}")
        elif file.filetype == "image":
            ocr_text = extract_image_text(file.path)
            result.append(f"[Görsel: {file.filename}]\n{ocr_text}")
        else:
            # Diğer dosya tipleri için dosya adını ekle
            result.append(f"[Dosya: {file.filename}] (Tip: {file.filetype})")
    return "\n\n".join(result)



def get_note_content(db: Session, note_id: int) -> str:
    note = db.query(Note).filter(Note.id == note_id).first()
    return note.content if note else ""

# ========== Together Chat Fonksiyonu ==========
def ai_chat_together(prompt, model="moonshotai/Kimi-K2-Instruct", max_tokens=512, temperature=0.6):
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        n=1,
    )
    return response.choices[0].message.content.strip()

def clean_ai_response(text: str) -> str:
    # <think> bloklarını temizle, sonradan gelen reasoning'i sil
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*", "", text, flags=re.IGNORECASE)
    return text.strip()

# ========== FOLDER AI ENDPOINTS ==========

@router.post("/ai/folder_summary")
def folder_summary(folder_id: int = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    if not content.strip():
        return {"summary": "Bu klasörde özetlenecek içerik bulunamadı."}
    prompt = (
        "Sen çok iyi bir özetleme asistanısın. "
        "Cevabını sadece Türkçe ve 2 cümle olarak döndür. sadece cevabı döndür.\n\n"
        f"Aşağıdaki klasörün tüm içeriğini (notlar, dosyalar) kısa ve madde madde özetle:\n\n{content}"
    )
    summary = ai_chat_together(prompt, max_tokens=400)
    summary = clean_ai_response(summary)
    return {"summary": summary}

@router.post("/ai/folder_tags")
def folder_tags(folder_id: int = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    prompt = (
        "Etiketleme uzmanısın. Sadece Türkçe ve kısa etiketler üret, virgülle ayır. "
        "Sadece cevabı döndür.\n\n"
        f"Aşağıdaki notların anahtar kelimelerini etiketle:\n\n{content}"
    )
    tags = ai_chat_together(prompt, max_tokens=80)
    tags = clean_ai_response(tags)
    return {"tags": tags}

@router.post("/ai/folder_presentation")
def folder_presentation(folder_id: int = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    prompt = (
        "Sunum hazırlama botusun. Türkçe, yaratıcı ve kısa yaz. "
        "Slide başlıklarını ve içeriklerini 'Slide 1:', 'Slide 2:' şeklinde sırala. "
        "Sadece cevabı döndür.\n\n"
        f"Şu klasördeki notlardan slayt sunumu için başlık ve madde madde slide önerileri üret:\n\n{content}"
    )
    slides = ai_chat_together(prompt, max_tokens=800)
    slides = clean_ai_response(slides)
    return {"presentation": slides}

@router.post("/ai/folder_chat")
def folder_chat(folder_id: int = Body(...), question: str = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    prompt = (
        "Klasördeki notların asistanısın. Cevabını sadece kısa, öz ve Türkçe ver. "
        "Sadece cevabı döndür.\n\n"
        f"Context (notlar):\n{content}\n---\nKullanıcı sorusu: {question}"
    )
    answer = ai_chat_together(prompt, max_tokens=350)
    answer = clean_ai_response(answer)
    return {"answer": answer}

# ========== NOTE AI ENDPOINTS ==========

@router.post("/ai/note_summary")
def note_summary(note_id: int = Body(...), text: str = Body(...), db: Session = Depends(get_db)):
    prompt = (
        "Sen çok iyi bir özetleme asistanısın. Cevabını sadece Türkçe ve madde madde, kısa olarak ver. "
        "Sadece cevabı döndür.\n\n"
        f"Şu notu kısa ve madde madde özetle:\n\n{text}"
    )
    summary = ai_chat_together(prompt, max_tokens=250)
    summary = clean_ai_response(summary)
    return {"summary": summary}

@router.post("/ai/note_title")
def note_title(note_id: int = Body(...), text: str = Body(...), db: Session = Depends(get_db)):
    prompt = (
        "Sen başlık bulma uzmanısın. dikkatlice algıla ve konun tamamı ile ilgili genel ve kısa bir başlık üret. Sadece başlığı döndür. "
        f"Şu nota başlık öner:\n\n{text}"
    )
    title = ai_chat_together(prompt, max_tokens=20)
    title = clean_ai_response(title)
    return {"title": title}

@router.post("/ai/note_markdown")
def note_markdown(note_id: int = Body(...), text: str = Body(...), db: Session = Depends(get_db)):
    prompt = (
        "Markdown düzeltme botusun. Sadece düzeltilmiş markdown'ı döndür. Sadece cevabı döndür.\n\n"
        f"Şu markdown metnini düzelt:\n\n{text}"
    )
    markdown = ai_chat_together(prompt, max_tokens=400)
    markdown = clean_ai_response(markdown)
    return {"markdown": markdown}

@router.post("/ai/note_chat")
def note_chat(note_id: int = Body(...), question: str = Body(...), db: Session = Depends(get_db)):
    content = get_note_content(db, note_id)
    prompt = (
        "Not asistanısın. Cevabını sadece kısa, net ve Türkçe ver. "
        "Sadece cevabı döndür.\n\n"
        f"Context (not):\n{content}\n---\nKullanıcı sorusu: {question}"
    )
    answer = ai_chat_together(prompt, max_tokens=350)
    answer = clean_ai_response(answer)
    return {"answer": answer}

@router.post("/ai/note_references")
def note_references(note_id: int = Body(...), text: str = Body(...), db: Session = Depends(get_db)):
    prompt = (
        "Akademik referans bulma botusun. Not içindeki kaynakları ve referansları (yazar, makale, link vs) çıkar, madde madde yaz. "
        "Sadece cevabı döndür.\n\n"
        f"Şu not içindeki kaynakları ve referansları bul:\n\n{text}"
    )
    references = ai_chat_together(prompt, max_tokens=200)
    references = clean_ai_response(references)
    return {"references": references}




@router.post("/ai/note_audio_summary")
async def note_audio_summary(body: TTSRequest):
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json; charset=utf-8"
    }
    data = {
        "text": body.text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.8
        }
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    json_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
    resp = requests.post(url, headers=headers, data=json_data, stream=True)
    if resp.status_code != 200:
        print("TTS ERROR:", resp.text)
        raise HTTPException(status_code=500, detail="ElevenLabs TTS servis hatası")
    return StreamingResponse(resp.raw, media_type="audio/mpeg")