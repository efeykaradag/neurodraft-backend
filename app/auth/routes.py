from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.models import User, EmailCode
from app.database import get_db
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import os, random, string
from dotenv import load_dotenv

from app.schemas import LoginRequest

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"))

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

### --------- Pydantic Modeller ---------
class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


### --------- Endpointler ---------

# Kayıt
@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(400, "Bu mail adresiyle kayıt zaten var!")
    hashed_pw = pwd_context.hash(data.password)
    user = User(email=data.email, hashed_password=hashed_pw, full_name=data.full_name, is_active=False, role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    code = ''.join(random.choices(string.digits, k=6))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    email_code = EmailCode(code=code, code_type="register", expiry=expiry, user_id=user.id)
    db.add(email_code)
    db.commit()
    print(f"MAIL: {data.email} için kayıt kodu: {code}")
    return {"msg": "Onay kodu e-mail adresine gönderildi!"}


### --------- Kullanıcı (me) ---------
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

@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"email": user.email, "role": user.role, "name": user.full_name}

### --------- Ekstra Auth Fonksiyonları ---------
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def authenticate_user(db: Session, email: str, password: str):
    user = get_user(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/login")
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # Kullanıcıyı email + şifre ile bul...
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(401, "Kullanıcı veya şifre hatalı.")
    access_token = create_access_token({"sub": user.email, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.email})
    response.set_cookie(
        key="access_token", value=access_token, httponly=True, secure=False, samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60, path="/"
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS*24*60*60, path="/"
    )
    return {"msg": "Giriş başarılı"}


@router.post("/refresh-token")
def refresh_token(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "Refresh token yok!")
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        new_access_token = create_access_token({"sub": user_email})
        response.set_cookie(
            key="access_token", value=new_access_token, httponly=True, secure=False, samesite="strict", max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60, path="/"
        )
        return {"msg": "Token yenilendi"}
    except Exception:
        raise HTTPException(401, "Refresh token geçersiz veya süresi dolmuş!")

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"msg": "Çıkış yapıldı"}