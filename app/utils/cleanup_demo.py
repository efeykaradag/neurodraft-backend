from datetime import datetime, timedelta
from app.models import DemoSession, DemoBan, Note, File, Folder
from app.database import SessionLocal  # DİKKAT: get_db değil, SessionLocal!
from sqlalchemy.orm import Session

def cleanup_expired_demo_sessions():
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        expired_sessions = db.query(DemoSession).filter(DemoSession.expires_at < now).all()
        for session in expired_sessions:
            # 1. Tüm notları sil
            db.query(Note).filter(Note.demo_session_id == session.id).delete()
            # 2. Tüm dosyaları sil
            db.query(File).filter(File.demo_session_id == session.id).delete()
            # 3. Tüm klasörleri sil
            db.query(Folder).filter(Folder.demo_session_id == session.id).delete()
            # 4. DemoSession kaydını sil
            db.delete(session)
            # 5. IP’yi 2 saat banla (DemoBan tablosuna ekle)
            ban = db.query(DemoBan).filter_by(ip_address=session.ip_address).first()
            banned_until = now + timedelta(hours=2)
            if ban:
                ban.banned_until = banned_until
            else:
                db.add(DemoBan(ip_address=session.ip_address, banned_until=banned_until))
        db.commit()
        return len(expired_sessions)  # Kaç tane session silindiğini döndür
    finally:
        db.close()
