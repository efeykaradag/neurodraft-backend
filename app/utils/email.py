import os
import requests
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_NAME = os.getenv("FROM_NAME", "NeuroDrafts")

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    data = {
        "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        print(f"Mail gönderildi: {to_email}")
        return True
    else:
        print(f"Mail gönderilemedi ({to_email}):", response.text)
        return False
