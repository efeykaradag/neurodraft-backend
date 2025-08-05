from passlib.context import CryptContext
from app.auth.routes import VerifyEmailRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.database import SessionLocal
from fastapi import Depends, HTTPException
from app.models import User, EmailCode
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import os, random, string
from fastapi import APIRouter

SECRET_KEY = os.getenv("SECRET_KEY", "demo")
ALGORITHM = "HS256"
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()





@router.post("/verify-email")
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email).first()
    if not user:
        raise HTTPException(404, "Kullanıcı bulunamadı!")
    email_code = db.query(EmailCode).filter_by(user_id=user.id, code=data.code, code_type="register").first()
    if not email_code or email_code.expiry < datetime.utcnow():
        raise HTTPException(400, "Kod hatalı veya süresi doldu!")
    user.is_active = True
    db.delete(email_code)
    db.commit()
    return {"msg": "E-posta doğrulandı!"}

# Şifremi unuttum
@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email).first()
    if not user:
        raise HTTPException(404, "Kullanıcı bulunamadı!")
    code = ''.join(random.choices(string.digits, k=6))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    email_code = EmailCode(code=code, code_type="reset", expiry=expiry, user_id=user.id)
    db.add(email_code)
    db.commit()
    print(f"MAIL: {data.email} için şifre sıfırlama kodu: {code}")
    return {"msg": "Şifre sıfırlama kodu gönderildi."}

# Şifre sıfırlama
@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email).first()
    if not user:
        raise HTTPException(404, "Kullanıcı bulunamadı!")
    email_code = db.query(EmailCode).filter_by(user_id=user.id, code=data.code, code_type="reset").first()
    if not email_code or email_code.expiry < datetime.utcnow():
        raise HTTPException(400, "Kod hatalı veya süresi geçti.")
    user.hashed_password = pwd_context.hash(data.new_password)
    db.delete(email_code)
    db.commit()
    return {"msg": "Şifre başarıyla değiştirildi."}


