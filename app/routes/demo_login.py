import shutil
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile
from sqlalchemy.orm import Session
from fastapi import File as FastAPIFile

from datetime import datetime, timedelta, timezone
from app.database import get_db  # kendi db dependency'n!
from app.models import DemoSession, DemoBan, File  # az önce eklediğin modeller
router = APIRouter()

def get_client_ip(request):
    # X-Forwarded-For varsa öncelikli onu kullan (proxy arkasında ise)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0]
    else:
        ip = request.client.host
    return ip


@router.post("/demo-login")
def demo_login(request: Request, db: Session = Depends(get_db)):
    ip = request.client.host  # proxy arkasında ise x-forwarded-for bakabilirsin

    # 1. Ban kontrolü
    ban = db.query(DemoBan).filter_by(ip_address=ip).first()
    if ban and ban.banned_until > datetime.utcnow():
        wait_min = int((ban.banned_until - datetime.utcnow()).total_seconds() // 60)
        raise HTTPException(403, f"Demo süren doldu. {wait_min} dakika sonra tekrar deneyebilirsin.")

    now = datetime.utcnow()
    # 2. Var olan session kontrolü (aktif mi?)
    session = db.query(DemoSession).filter_by(ip_address=ip).first()
    if session and session.expires_at > now:
        remaining = int((session.expires_at - now).total_seconds() // 60)
        return {
            "msg": f"Demo zaten aktif, {remaining} dakika kaldı.",
            "expires_at": session.expires_at.isoformat()
        }

    # 3. Eski session (ve varsa ilişkili verileri) temizle
    if session:
        db.delete(session)
        # Burada session ile ilişkili not/dosya vs. varsa onları da silebilirsin!

    # 4. Yeni session aç
    expires = now + timedelta(minutes=15)
    new_session = DemoSession(ip_address=ip, started_at=now, expires_at=expires)
    db.add(new_session)
    db.commit()
    return {
        "msg": "Demo başlatıldı!",
        "expires_at": expires.isoformat()
    }

@router.get("/demo-status")
def demo_status(request: Request, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    session = db.query(DemoSession).filter_by(ip_address=ip).first()
    if not session:
        raise HTTPException(404, "No demo session.")
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    remaining = (expires_at - now).total_seconds()
    return {
        "active": remaining > 0,
        "remaining_seconds": max(0, int(remaining)),
        "expires_at": expires_at.isoformat(),
    }