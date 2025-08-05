import os
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
import zipfile
import subprocess
import mimetypes

def compress_image(file_path, out_path, quality=70):
    img = Image.open(file_path)
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    img.save(out_path, "JPEG", quality=quality, optimize=True)

def compress_pdf(file_path, out_path):
    # Ghostscript ile daha iyi sıkıştırma, sistemde gs kurulu olmalı
    try:
        subprocess.run([
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={out_path}",
            file_path
        ], check=True)
    except Exception:
        # fallback: PyPDF2 ile sadece kopyalama, gerçek sıkıştırma yapmaz
        reader = PdfReader(file_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(out_path, "wb") as f:
            writer.write(f)

def compress_audio(input_path, output_path, bitrate="64k"):
    try:
        subprocess.run([
            "ffmpeg", "-i", input_path, "-b:a", bitrate, output_path,
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print("FFmpeg Error:", e)
        raise

def zip_any_file(file_path, out_path):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(file_path, arcname=os.path.basename(file_path))

def get_mime_type(file_path):
    return mimetypes.guess_type(file_path)[0] or "application/octet-stream"
