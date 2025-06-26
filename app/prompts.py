import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

SUMMARY_PROMPT = """
Summarize the following conversation and extract key points, especially from user.
Respond in maximum 5 sentences mentioning the most important information.
"""


def get_google_doc_content(document_id=None):
    SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
    credentials_info = {
        "type": os.getenv("GOOGLE_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL"),
        "universe_domain": os.getenv("GOOGLE_UNIVERSE_DOMAIN"),
    }
    if document_id is None:
        document_id = os.getenv("GOOGLE_DOC_ID")
    creds = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    service = build('docs', 'v1', credentials=creds)
    doc = service.documents().get(documentId=document_id).execute()
    content = []
    for element in doc.get('body').get('content'):
        if 'paragraph' in element:
            for run in element['paragraph'].get('elements', []):
                text = run.get('textRun', {}).get('content')
                if text:
                    content.append(text)
    return ''.join(content)
