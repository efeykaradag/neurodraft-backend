import os
import pdfplumber
from PIL import Image
import pytesseract
import whisper
import traceback

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

def extract_text_from_pdf(filepath):
    try:
        with pdfplumber.open(filepath) as pdf:
            text = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            text = "\n".join(text) if text else ""
            if text and text.strip():
                return text
    except Exception as e:
        print(f"PDF Extraction Error (plumber): {filepath} - {e}\n{traceback.format_exc()}")

    # fallback: OCR
    if convert_from_path is None:
        print("pdf2image yüklü değil, PDF OCR yapılamıyor.")
        return ""
    try:
        images = convert_from_path(filepath)
        text = ""
        for img in images:
            t = pytesseract.image_to_string(img, lang="tur+eng")
            text += t + "\n"
        return text.strip() if text.strip() else ""
    except Exception as e:
        print(f"PDF OCR Extraction Error: {filepath} - {e}\n{traceback.format_exc()}")
        return ""

def extract_text_from_image(filepath, lang="tur+eng"):
    try:
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img, lang=lang)
        return text if text.strip() else ""
    except Exception as e:
        print(f"Image OCR Error: {filepath} - {e}\n{traceback.format_exc()}")
        return ""

def extract_text_from_audio(filepath, model_size="base"):
    try:
        model = whisper.load_model(model_size)
        result = model.transcribe(filepath)
        return result["text"].strip() if result["text"] else ""
    except Exception as e:
        print(f"Audio Extraction Error: {filepath} - {e}\n{traceback.format_exc()}")
        return ""

def extract_text_from_txt(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"TXT Extraction Error: {filepath} - {e}\n{traceback.format_exc()}")
        return ""

def extract_text_auto(filepath, mime=None):
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if mime:
            if "pdf" in mime:
                return extract_text_from_pdf(filepath)
            elif "image" in mime:
                return extract_text_from_image(filepath)
            elif "audio" in mime:
                return extract_text_from_audio(filepath)
            elif "text" in mime or ext in [".txt", ".csv", ".md"]:
                return extract_text_from_txt(filepath)
        if ext == ".pdf":
            return extract_text_from_pdf(filepath)
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"]:
            return extract_text_from_image(filepath)
        elif ext in [".mp3", ".wav", ".m4a", ".ogg"]:
            return extract_text_from_audio(filepath)
        elif ext in [".txt", ".csv", ".md"]:
            return extract_text_from_txt(filepath)
        else:
            return ""
    except Exception as e:
        print(f"Universal Extraction Error: {filepath} - {e}\n{traceback.format_exc()}")
        return ""

__all__ = [
    "extract_text_from_pdf",
    "extract_text_from_image",
    "extract_text_from_audio",
    "extract_text_from_txt",
    "extract_text_auto",
]
