# backend/routes_contact.py

from fastapi import APIRouter, Request, status
from pydantic import BaseModel
from fastapi.responses import JSONResponse

router = APIRouter()

class ContactForm(BaseModel):
    name: str
    email: str
    message: str

@router.post("/contact")
async def submit_contact(form: ContactForm, request: Request):
    # Burada veritabanına kaydedebilirsin, e-posta gönderebilirsin vs.
    print(f"Yeni iletişim mesajı: {form.dict()}")
    return JSONResponse(content={"success": True}, status_code=status.HTTP_201_CREATED)
