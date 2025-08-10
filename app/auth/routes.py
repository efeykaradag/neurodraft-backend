from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.models import User, EmailCode, DemoSession
from app.database import get_db
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import os, random, string
from dotenv import load_dotenv
from app.utils.email import send_email
from app.schemas import LoginRequest
from typing import Optional

load_dotenv()

# ----------------- Ortam Ayarları -----------------
def is_prod():
    return os.getenv("ENV") == "prod"

COOKIE_DOMAIN = ".neurodrafts.com" if is_prod() else None
COOKIE_SECURE = True if is_prod() else False
COOKIE_SAMESITE = "None" if is_prod() else "Lax"
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 30))

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Giriş yapmalısınız!")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(401, "Token geçersiz.")
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(401, "Kullanıcı bulunamadı.")
        return user
    except JWTError:
        raise HTTPException(401, "Token geçersiz veya süresi dolmuş.")


def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    """
    Kullanıcı giriş yapmamışsa None döner, giriş yapmışsa user objesini döner.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None  # Girişli user yoksa None dön
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None
        user = db.query(User).filter(User.email == email).first()
        return user
    except JWTError:
        return None


# ----------------- Cookie Helper -----------------
def set_auth_cookie(response: Response, key: str, value: str, max_age: int):
    cookie_kwargs = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "max_age": max_age,
        "path": "/",
    }
    if COOKIE_DOMAIN:
        cookie_kwargs["domain"] = COOKIE_DOMAIN
    response.set_cookie(key=key, value=value, **cookie_kwargs)


# ----------------- Pydantic Modeller -----------------
class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    termsAccepted: bool
    termsAcceptedAt: Optional[datetime]

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


# ----------------- Kayıt -----------------
@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(400, "Bu mail adresiyle kayıt zaten var!")

    hashed_pw = pwd_context.hash(data.password)
    user = User(
        email=data.email,
        hashed_password=hashed_pw,
        full_name=data.full_name,
        is_active=False,
        role="user",
        terms_accepted=data.termsAccepted,
        terms_accepted_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    code = ''.join(random.choices(string.digits, k=6))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    email_code = EmailCode(code=code, code_type="register", expiry=expiry, user_id=user.id)
    db.add(email_code)
    db.commit()

    subject = "NeuroDrafts Kaydını Onayla 🚀"
    html = f"""<div style="max-width:440px;margin:auto;padding:24px;background:#fff;
                border-radius:12px;font-family:sans-serif;color:#222;
                border:1px solid #e4e8f0;box-shadow:0 4px 32px #0001;">
        <div style="text-align:center;margin-bottom:18px;">
            <img src="https://neurodrafts.com/logo.png" alt="NeuroDrafts" width="54" style="margin-bottom:12px;"/>
            <h2 style="margin:0;font-size:1.5rem;color:#4b40c5;">Hoşgeldin!</h2>
        </div>
        <div style="font-size:1.12rem;margin-bottom:18px;">
            NeuroDrafts hesabını oluşturmak üzeresin.<br>
            Kaydını tamamlamak için aşağıdaki <b>onay kodunu</b> kullanabilirsin:
        </div>
        <div style="font-size:2rem;font-weight:700;background:#f5f8ff;border-radius:8px;padding:14px 0;text-align:center;letter-spacing:6px;color:#4b40c5;">
            {code}
        </div>
        <div style="font-size:0.95rem;color:#555;margin:24px 0 8px;">
            Kodun <b>10 dakika</b> boyunca geçerlidir. Kodun süresi dolarsa yeni bir kod alabilirsin.<br>
            Eğer bu işlemi <b>sen başlatmadıysan</b> bu maili görmezden gel.
        </div>
        <hr style="margin:24px 0 8px;">
        <div style="font-size:0.87rem;color:#777;text-align:center;">
            NeuroDrafts ekibi <br>
            <a href="https://neurodrafts.com" style="color:#06B6D4;text-decoration:none;">neurodrafts.com</a>
        </div>
    </div>"""
    send_email(data.email, subject, html)

    return {"msg": "Onay kodu e-mail adresine gönderildi!"}


# ----------------- Kullanıcı (me) -----------------
@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            if email:
                user = db.query(User).filter(User.email == email).first()
                if user:
                    return {
                        "mode": "user",
                        "email": user.email,
                        "role": user.role,
                        "name": user.full_name,
                    }
        except Exception:
            pass

    ip = request.headers.get("x-forwarded-for", request.client.host)
    session = db.query(DemoSession).filter(
        DemoSession.ip_address == ip,
        DemoSession.expires_at > datetime.now(timezone.utc)
    ).first()
    if session:
        return {
            "mode": "demo",
            "ip": ip,
            "expires_at": session.expires_at,
        }

    raise HTTPException(401, "Giriş yapmadınız veya demo süreniz bitti.")


# ----------------- Auth Helper Fonksiyonlar -----------------
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def authenticate_user(db: Session, email: str, password: str):
    user = get_user(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {**data, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict, expires_delta: timedelta = None):
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode = {**data, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ----------------- Login -----------------
@router.post("/login")
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(401, "Kullanıcı veya şifre hatalı.")
    if not user.is_active:
        raise HTTPException(401, "Email onayı yapılmamış.")
    if user.is_waitlist:
        raise HTTPException(403, "Henüz sıradasınız! Tam sürüm açıldığında ilk sizinle iletişime geçeceğiz.")

    access_token = create_access_token({"sub": user.email, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.email})

    set_auth_cookie(response, "access_token", access_token, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    set_auth_cookie(response, "refresh_token", refresh_token, REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)

    return {"msg": "Giriş başarılı"}


# ----------------- Refresh Token -----------------
@router.post("/refresh-token")
def refresh_token(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "Refresh token yok!")
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        new_access_token = create_access_token({"sub": user_email})
        set_auth_cookie(response, "access_token", new_access_token, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        return {"msg": "Token yenilendi"}
    except Exception:
        raise HTTPException(401, "Refresh token geçersiz veya süresi dolmuş!")


# ----------------- Logout -----------------
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"msg": "Çıkış yapıldı"}


# ----------------- Resend Verify Code -----------------
@router.post("/resend-verify-code")
def resend_verify_code(data: dict, db: Session = Depends(get_db)):
    email = data.get("email")
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(404, "Kullanıcı bulunamadı!")

    if user.is_active:
        raise HTTPException(400, "Kullanıcı zaten aktif!")

    code = ''.join(random.choices(string.digits, k=6))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    db.query(EmailCode).filter_by(user_id=user.id, code_type="register").delete()

    email_code = EmailCode(code=code, code_type="register", expiry=expiry, user_id=user.id)
    db.add(email_code)
    db.commit()

    subject = "NeuroDrafts Kaydını Onayla 🚀"
    html = f"""..."""  # HTML içeriği buraya
    send_email(email, subject, html)

    return {"msg": "Yeni doğrulama kodu e-posta adresine gönderildi."}


# ----------------- Verify Email -----------------
@router.post("/verify-email")
def verify_email(data: dict, db: Session = Depends(get_db)):
    email = data.get("email")
    code = data.get("code")
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(404, "Kullanıcı bulunamadı!")

    code_obj = db.query(EmailCode).filter_by(
        user_id=user.id, code_type="register", code=code
    ).first()
    if not code_obj or code_obj.expiry < datetime.utcnow():
        raise HTTPException(400, "Kod hatalı veya süresi geçti!")

    user.is_active = True
    db.commit()
    db.delete(code_obj)
    db.commit()

    return {"msg": "Hesap başarıyla doğrulandı."}
