from datetime import datetime
from app.database import Base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)  # İsteğe bağlı ekledim
    is_active = Column(Boolean, default=False)
    role = Column(String, default="user")

    folders = relationship("Folder", back_populates="user")
    email_codes = relationship("EmailCode", back_populates="user")  # Onay/sıfırlama kodları için

class EmailCode(Base):
    __tablename__ = "email_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False)
    code_type = Column(String, nullable=False)  # "register" veya "reset"
    expiry = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="email_codes")

class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="folders")
    notes = relationship("Note", back_populates="folder")
    files = relationship("File", back_populates="folder")


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)  # YENİ ALAN
    content = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    folder_id = Column(Integer, ForeignKey("folders.id"))
    folder = relationship("Folder", back_populates="notes")


class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    filetype = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    extracted_text = Column(String, nullable=False)
    folder = relationship("Folder", back_populates="files")
    user = relationship("User")