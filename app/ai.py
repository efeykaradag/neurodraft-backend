# app/routes/ai.py
import os
import re
import json
import requests
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Note, File

# --- OpenAI SDK ---
from openai import OpenAI
_openai_client: Optional[OpenAI] = None

# --- Opsiyonel bağımlılıklar ---
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

# ===================== Config =====================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY env değişkeni set edilmeli.")

client = OpenAI(api_key=OPENAI_API_KEY)
TEXT_MODEL = "gpt-4o-mini"
TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "verse"

# Canva API
CANVA_API_BASE = "https://api.canva.com/v1"
CANVA_ACCESS_TOKEN = os.getenv("CANVA_ACCESS_TOKEN")

router = APIRouter()

# ===================== Schemas =====================
class NoteSummaryRequest(BaseModel):
    note_id: int
    text: str

class FolderRequest(BaseModel):
    folder_id: int

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None

# ===================== Dosya/Not Yardımcıları =====================
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

def get_folder_all_contents(db: Session, folder_id: int) -> str:
    result = []
    notes = db.query(Note).filter(Note.folder_id == folder_id).all()
    files = db.query(File).filter(File.folder_id == folder_id).all()

    for note in notes:
        result.append(f"[Not: {note.title}]\n{note.content}")

    for f in files:
        if f.filetype == "pdf":
            result.append(f"[PDF: {f.filename}]\n{extract_pdf_text(f.path)}")
        elif f.filetype in ("mp3", "wav", "m4a", "audio"):
            result.append(f"[Ses: {f.filename}]\n{transcribe_audio(f.path)}")
        elif f.filetype in ("png", "jpg", "jpeg", "image"):
            result.append(f"[Görsel: {f.filename}]\n{extract_image_text(f.path)}")
        else:
            result.append(f"[Dosya: {f.filename}] (Tip: {f.filetype})")

    return "\n\n".join(result)

def get_note_content(db: Session, note_id: int) -> str:
    note = db.query(Note).filter(Note.id == note_id).first()
    return note.content if note else ""

# ===================== OpenAI Yardımcıları =====================
def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY ortam değişkeni tanımlı değil!")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

def ai_chat_openai(prompt: str, max_tokens: int = 512, temperature: float = 0.6) -> str:
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": "Sadece Türkçe, kısa ve doğrudan cevap ver."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        n=1,
    )
    return clean_ai_response(resp.choices[0].message.content or "")

def clean_ai_response(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*", "", text, flags=re.IGNORECASE)
    return text.strip()

# ===================== Canva Yardımcıları =====================
def _post_to_canva(canva_payload: dict) -> dict:
    if not CANVA_ACCESS_TOKEN:
        return {"ok": False, "error": "CANVA_ACCESS_TOKEN not set"}
    headers = {"Authorization": f"Bearer {CANVA_ACCESS_TOKEN}", "Content-Type": "application/json"}
    resp = requests.post(f"{CANVA_API_BASE}/presentations", headers=headers, json=canva_payload, timeout=60)
    try:
        data = resp.json()
    except Exception:
        data = {"raw_text": resp.text}
    return {"ok": resp.status_code in (200, 201), "status": resp.status_code, "data": data}

# ===================== FOLDER AI ENDPOINTS =====================
@router.post("/ai/folder_summary")
def folder_summary(folder_id: int = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    if not content.strip():
        return {"summary": "Bu klasörde özetlenecek içerik yok."}
    prompt = f"Sen çok iyi bir özetleme asistanısın. Türkçe, 2-3 madde halinde, net yaz.\n\n{content}"
    return {"summary": ai_chat_openai(prompt, max_tokens=350, temperature=0.3)}

@router.post("/ai/folder_tags")
def folder_tags(folder_id: int = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    prompt = f"Etiketleme uzmanısın. Türkçe kısa etiketler üret; virgülle ayır.\n\n{content}"
    return {"tags": ai_chat_openai(prompt, max_tokens=80, temperature=0.4)}

@router.post("/ai/folder_presentation")
def folder_presentation(folder_id: int = Body(...), style: Optional[str] = Body(None), push_to_canva: bool = Body(False), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    if not content.strip():
        return {"presentation": {"title": "Boş Sunum", "slides": []}, "canva_payload": None, "ppt_markdown": ""}

    style_hint = f"\nStil: {style}." if style else ""
    system_msg = (
        "Sadece GEÇERLİ JSON üret.\n"
        '{ "title": "string", "slides": [ { "title": "string", "bullets": ["string",...], "notes": "string" } ] }\n'
        "Bullets ≤5 madde, ≤15 kelime, notes kısa."
    )
    user_msg = f"Klasör içeriğinden 6-10 slayt arası Türkçe sunum üret.{style_hint}\n\n{content}"

    raw = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
        max_tokens=1200,
        temperature=0.7,
        n=1,
    )
    try:
        data = json.loads((raw.choices[0].message.content or "").strip())
    except Exception:
        data = {"title": "Otomatik Sunum", "slides": [{"title": "Özet", "bullets": ["İçerik analiz edildi."], "notes": ""}]}

    slides = []
    for s in data.get("slides", []):
        title = s.get("title", "").strip()[:90]
        bullets = [b.strip() for b in (s.get("bullets") or []) if b.strip()][:5]
        notes = s.get("notes", "").strip()
        if title and bullets:
            slides.append({"title": title, "bullets": bullets, "notes": notes})
    if len(slides) < 6:
        while len(slides) < 6:
            slides.append({"title": f"Ek {len(slides)+1}", "bullets": ["Önemli nokta"], "notes": ""})
    elif len(slides) > 10:
        slides = slides[:10]

    presentation = {"title": data.get("title", "Sunum"), "slides": slides}
    canva_payload = {"title": presentation["title"], "pages": [{"elements": [{"type": "heading", "text": s["title"]}, {"type": "bulleted_list", "items": s["bullets"]}], "notes": s.get("notes", "")} for s in slides]}
    ppt_md = "\n".join([f"# {presentation['title']}"] + [f"## Slide {i+1}: {s['title']}\n" + "\n".join(f"- {b}" for b in s["bullets"]) for i, s in enumerate(slides)])

    canva_result = _post_to_canva(canva_payload) if push_to_canva else None
    return {"presentation": presentation, "canva_payload": canva_payload, "ppt_markdown": ppt_md, "canva_result": canva_result}

@router.post("/ai/folder_chat")
def folder_chat(folder_id: int = Body(...), question: str = Body(...), db: Session = Depends(get_db)):
    content = get_folder_all_contents(db, folder_id)
    prompt = f"Klasör notlarının asistanısın. Türkçe, kısa ve net cevap ver.\n\n{content}\n---\nSoru: {question}"
    return {"answer": ai_chat_openai(prompt, max_tokens=350, temperature=0.5)}

# ===================== NOTE AI ENDPOINTS =====================
@router.post("/ai/note_summary")
def note_summary(note_id: int = Body(...), text: str = Body(...)):
    return {"summary": ai_chat_openai(f"Türkçe, madde madde kısa özetle:\n\n{text}", max_tokens=250, temperature=0.3)}

@router.post("/ai/note_title")
def note_title(note_id: int = Body(...), text: str = Body(...)):
    return {"title": ai_chat_openai(f"Kısa ve etkileyici Türkçe başlık üret:\n\n{text}", max_tokens=20, temperature=0.7)}

@router.post("/ai/note_markdown")
def note_markdown(note_id: int = Body(...), text: str = Body(...)):
    return {"markdown": ai_chat_openai(f"Markdown düzelt:\n\n{text}", max_tokens=400, temperature=0.2)}

@router.post("/ai/note_chat")
def note_chat(note_id: int = Body(...), question: str = Body(...), db: Session = Depends(get_db)):
    content = get_note_content(db, note_id)
    return {"answer": ai_chat_openai(f"Not asistanısın. Türkçe, kısa cevap ver:\n\n{content}\n---\nSoru: {question}", max_tokens=350, temperature=0.5)}

@router.post("/ai/note_references")
def note_references(note_id: int = Body(...), text: str = Body(...)):
    return {"references": ai_chat_openai(f"Not içindeki kaynak/atfı listele:\n\n{text}", max_tokens=250, temperature=0.2)}

# ===================== OpenAI TTS =====================
@router.post("/ai/note_audio_summary")
def note_audio_summary(body: TTSRequest):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Metin boş olamaz.")
    voice = (body.voice or DEFAULT_TTS_VOICE).strip()

    def audio_stream():
        with client.audio.speech.with_streaming_response.create(model=TTS_MODEL, voice=voice, input=text) as resp:
            for chunk in resp.iter_bytes():
                yield chunk
    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@router.post("/ai/folder_presentation_gamma")
def folder_presentation_gamma(
    folder_id: int = Body(...),
    style: Optional[str] = Body(None),
    db: Session = Depends(get_db),
):
    """
    Gamma.app paste akışı için optimize edilmiş Markdown döndürür.
    """
    content = get_folder_all_contents(db, folder_id)
    if not content.strip():
        return {
            "presentation": {"title": "Boş Sunum", "slides": []},
            "gamma_markdown": "# Boş Sunum\n\n> İçerik bulunamadı.",
            "gamma_tip_url": "https://gamma.app/create",
        }

    style_hint = ""
    if style:
        style_hint = f"\nStil: {style}. Ton: net ve Türkçe. Başlıklar kısa, maddeler tek satır."

    system_msg = (
        "Sadece GEÇERLİ JSON üret. Markdown veya açıklama verme.\n"
        "Şema:\n{\n"
        '  "title": "string",\n'
        '  "slides": [ {"title": "string", "bullets": ["string", ...], "notes": "string"} ]\n'
        "}\n"
        "Kurallar: bullets max 5 madde, her madde 15 kelimeyi aşmasın. 'notes' kısa olsun."
    )
    user_msg = (
        f"Aşağıdaki içerikten 6-10 slayt arası sunum üret.{style_hint}\n\n"
        f"İçerik:\n{content}"
    )

    raw = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1200,
        temperature=0.7,
        n=1,
    )
    txt = (raw.choices[0].message.content or "").strip()
    try:
        data = json.loads(txt)
    except Exception:
        data = {
            "title": "Otomatik Sunum",
            "slides": [
                {"title": "Özet", "bullets": ["İçerik analiz edildi.", "JSON formatı alınamadı."], "notes": ""}
            ],
        }

    title = (data.get("title") or "Sunum").strip()
    slides_in = data.get("slides") or []
    cleaned = []
    for s in slides_in:
        st = (s.get("title") or "").strip()[:90]
        bullets = [b.strip() for b in (s.get("bullets") or []) if isinstance(b, str)]
        bullets = [b for b in bullets if b][:5]
        notes = (s.get("notes") or "").strip()
        if st and bullets:
            cleaned.append({"title": st, "bullets": bullets, "notes": notes})

    if len(cleaned) < 6:
        while len(cleaned) < 6:
            cleaned.append({"title": f"Ek {len(cleaned)+1}", "bullets": ["Önemli nokta", "Örnek/çıkarım"], "notes": ""})
    elif len(cleaned) > 10:
        cleaned = cleaned[:10]

    # --- Gamma paste-friendly Markdown ---
    md_lines = [f"# {title}", ""]
    for idx, s in enumerate(cleaned, start=1):
        md_lines.append(f"## {s['title']}")
        for b in s["bullets"]:
            md_lines.append(f"- {b}")
        if s.get("notes"):
            md_lines.append(f"> Konuşmacı Notu: {s['notes']}")
        md_lines.append("")
    gamma_md = "\n".join(md_lines)

    return {
        "presentation": {"title": title, "slides": cleaned},
        "gamma_markdown": gamma_md,
        "gamma_tip_url": "https://gamma.app/create",  # yeni sunum oluşturma
    }