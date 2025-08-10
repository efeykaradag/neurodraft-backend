import os
import json
import requests
from typing import Optional, List, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.ai import get_openai_client, get_folder_all_contents
from app.routes.canva import _get_valid_token, _owner_key

router = APIRouter()

# NOT: Canva’nın tasarım oluşturma REST endpoint’i partner planına göre değişebilir.
# Aşağıdaki URL’yi env’den yönetelim.
CANVA_CREATE_URL = os.getenv("CANVA_CREATE_URL", "https://api.canva.com/v1/designs")


def _slides_to_canva_pages(presentation: Dict) -> List[Dict]:
    """
    OpenAI’dan dönen {title, slides[{title, bullets, notes}]} yapısını
    Canva tarafında basit bir sayfa/eleman şemasına çeviriyoruz.
    Gerçek Canva API şeman için sağlayıcı dokümantasyonunu izleyip
    burayı ufak oynamalarla güncelle.
    """
    pages = []

    # Kapak
    pages.append({
        "elements": [
            {"type": "heading", "text": presentation["title"]},
            {"type": "subheading", "text": "AI tarafından oluşturulan sunum"}
        ],
        "notes": ""
    })

    # İçerik
    for s in presentation["slides"]:
        pages.append({
            "elements": [
                {"type": "heading", "text": s["title"]},
                {"type": "bulleted_list", "items": s["bullets"]},
            ],
            "notes": s.get("notes") or ""
        })

    return pages


@router.post("/ai/folder_presentation_full")
def folder_presentation_full(
    request: Request,
    folder_id: int = Body(...),
    style: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """
    1) Klasör içeriğini topla
    2) OpenAI ile {title, slides[]} JSON üret
    3) Canva’ya tasarım oluşturma isteği at
    4) link/ids frontend’e dön
    """
    # 1) İçerik
    content = get_folder_all_contents(db, folder_id)
    if not content.strip():
        raise HTTPException(400, "Klasör boş.")

    style_hint = f" Stil: {style}." if style else ""
    system_msg = (
        "Sadece GEÇERLİ JSON üret. Markdown ya da açıklama ekleme.\n"
        "Şema:\n{\n"
        '  "title": "string",\n'
        '  "slides": [\n'
        '    {"title": "string", "bullets": ["string", ...], "notes": "string"}\n'
        "  ]\n"
        "}\n"
        "Kurallar: 6-10 slayt, bullets en fazla 5 madde; her madde 15 kelimeyi aşmasın. Türkçe yaz."
    )
    user_msg = (
        f"Aşağıdaki içeriği {style_hint} sunuma çevir.\n\n"
        f"İçerik:\n{content}"
    )

    # 2) OpenAI
    client = get_openai_client()
    raw = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1200,
        temperature=0.7,
        n=1,
    )
    text = (raw.choices[0].message.content or "").strip()
    try:
        presentation = json.loads(text)
    except Exception:
        presentation = {
            "title": "Otomatik Sunum",
            "slides": [
                {"title": "Özet", "bullets": ["JSON üretimi başarısız.", "Manuel düzenleme gerekli olabilir."], "notes": ""}
            ]
        }

    # Temizle / sınırla
    pres_title = (presentation.get("title") or "Sunum").strip()[:90]
    slides = presentation.get("slides") or []
    cleaned = []
    for s in slides:
        t = (s.get("title") or "").strip()[:90]
        bullets = [b.strip() for b in (s.get("bullets") or []) if isinstance(b, str)]
        bullets = [b for b in bullets if b][:5]
        notes = (s.get("notes") or "").strip()
        if t and bullets:
            cleaned.append({"title": t, "bullets": bullets, "notes": notes})
    if len(cleaned) < 6:
        while len(cleaned) < 6:
            cleaned.append({"title": f"Ek {len(cleaned)+1}", "bullets": ["Önemli nokta", "Örnek/çıkarım"], "notes": ""})
    elif len(cleaned) > 10:
        cleaned = cleaned[:10]

    presentation = {"title": pres_title, "slides": cleaned}

    # 3) Canva’ya gönder
    owner = _owner_key(request)
    access_token = _get_valid_token(owner)
    if not access_token:
        # FE: önce /canva/auth → izin ver → /canva/callback sonrası tekrar dener
        return {
            "presentation": presentation,
            "canva_needed": True,
            "message": "Canva bağlantısı yok. Lütfen Canva bağlantısını verin (Ayarlar > Canva bağla)."
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "title": presentation["title"],
        "documentType": "presentation",
        "pages": _slides_to_canva_pages(presentation),
    }

    try:
        resp = requests.post(CANVA_CREATE_URL, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        # Canva API erişilemezse: en azından taslağı döndür
        return {
            "presentation": presentation,
            "canva_error": f"Canva isteği başarısız: {e}",
            "canva_response": None
        }

    if resp.status_code >= 300:
        return {
            "presentation": presentation,
            "canva_error": f"Canva API {resp.status_code}",
            "canva_response": resp.text
        }

    data = resp.json() if resp.text else {}
    # Sağlayıcıya göre anahtarlar değişebilir:
    design_id = data.get("id") or data.get("design_id")
    share_url = data.get("share_url") or data.get("url")

    return {
        "presentation": presentation,
        "canva": {
            "design_id": design_id,
            "share_url": share_url,
            "raw": data
        }
    }
