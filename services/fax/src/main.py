import os
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import functions_framework
from google.cloud import storage
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import google.auth
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# [헬퍼] 하위 폴더 찾기 또는 생성
def get_or_create_subfolder(service, parent_id, folder_name):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and '{parent_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        print(f"Created subfolder: {folder_name} ({folder['id']})")
        return folder['id']

# [헬퍼] 이메일 발송
def send_email_notification(file_name, doc_url):
    sender_email = os.environ.get('EMAIL_SENDER')
    sender_password = os.environ.get('EMAIL_PASSWORD')
    receiver_email = os.environ.get('EMAIL_RECEIVER')
    apps_script_url = os.environ.get('APPS_SCRIPT_URL')

    if not all([sender_email, sender_password, receiver_email]):
        print("Email configuration missing. Skipping notification.")
        return

    subject = f"[FAX受信] {file_name}"
    body_html = f"""
    <h2>新規FAXを受信しました。</h2>
    <p>Googleドライブ(Under Review)に新しいFAXドキュメントが保存されました。</p>
    <br>
    <p><b>ファイル名:</b> {file_name}</p>
    <p><b>📄 文書確認(Google Doc):</b> <a href="{doc_url}">ドキュメントを開く</a></p>
    """

    # Apps Script リビューリンクがあればボタン追加
    if apps_script_url:
        body_html += f"""
        <br>
        <div style="background-color: #f1f3f4; padding: 15px; border-radius: 5px; text-align: center;">
            <p style="margin: 0 0 10px 0; font-weight: bold; color: #333;">▼ 内容確認と承認はこちら ▼</p>
            <a href="{apps_script_url}" style="background-color: #4285f4; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; font-size: 16px;">
                レビュー画面を開く
            </a>
            <p style="margin: 10px 0 0 0; font-size: 12px; color: #666;">(原本PDFと変換結果を比較・編集できます)</p>
        </div>
        """

    body_html += """
    <hr>
    <p style="font-size: small; color: gray;">※本メールはシステムによる自動送信です。</p>
    """

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Notification email sent to {receiver_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

@functions_framework.cloud_event
def process_fax(cloud_event):
    data = cloud_event.data
    source_bucket_name, file_name = data['bucket'], data['name']

    print(f"Processing file: {file_name} from {source_bucket_name}")

    folder_id_original = os.environ.get('DRIVE_FOLDER_ID_ORIGINAL')
    folder_id_work = os.environ.get('DRIVE_FOLDER_ID_WORK')
    archive_bucket_name = os.environ.get('ARCHIVE_BUCKET')
    gcp_project = os.environ.get('GCP_PROJECT')
    gcp_region = os.environ.get('GCP_REGION', 'asia-northeast1')

    storage_client = storage.Client()

    source_blob = storage_client.bucket(source_bucket_name).blob(file_name)
    content = source_blob.download_as_bytes()

    # 1. Drive 서비스 연결
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive'])
    docs_service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    # 2. [Original 폴더] 원본 PDF 업로드
    pdf_metadata = {'name': file_name, 'parents': [folder_id_original]}
    pdf_media = MediaIoBaseUpload(io.BytesIO(content), mimetype='application/pdf')
    original_pdf = drive_service.files().create(
        body=pdf_metadata, media_body=pdf_media, fields='id', supportsAllDrives=True
    ).execute()
    print("Original PDF uploaded.")

    # 3. Gemini Flash로 OCR 실행
    vertexai.init(project=gcp_project, location='us-central1')
    model = GenerativeModel("gemini-3.0-flash")

    response = model.generate_content([
        Part.from_data(content, mime_type="application/pdf"),
        "このFAXドキュメントからすべてのテキストを正確に抽出してください。"
        "レイアウトと書式をできるだけ保持してください。"
        "テキストのみを出力し、説明や前置きは不要です。"
    ])
    extracted_text = response.text
    print(f"Gemini Flash extracted {len(extracted_text)} characters.")

    # 4. [Original 폴더] Google Doc 생성
    doc_title = f"[OCR] {file_name}"
    doc_metadata = {
        'name': doc_title,
        'mimeType': 'application/vnd.google-apps.document',
        'parents': [folder_id_original]
    }
    original_doc = drive_service.files().create(
        body=doc_metadata, supportsAllDrives=True, fields='id'
    ).execute()
    doc_id = original_doc['id']
    print(f"Original Doc created: {doc_id}")

    # 5. 문서 내용 채우기
    requests = []
    if extracted_text:
         requests.append({'insertText': {'location': {'index': 1}, 'text': extracted_text + "\n\n"}})

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()

    # ---------------------------------------------------------
    # 6. [Work 폴더 처리] under review 폴더 확보 및 파일 복사
    # ---------------------------------------------------------

    # (1) working 폴더 아래에 'under review' 폴더가 있는지 확인하고 없으면 생성
    folder_id_under_review = get_or_create_subfolder(drive_service, folder_id_work, 'under review')

    # (2) 나중에 리뷰 완료 시 이동할 'reviewed' 폴더도 미리 생성해둠 (Apps Script 오류 방지)
    get_or_create_subfolder(drive_service, folder_id_work, 'reviewed')

    # (3) PDF 복사본을 under review에 저장 (리뷰할 때 원본 대조용)
    drive_service.files().copy(
        fileId=original_pdf['id'],
        body={'name': file_name, 'parents': [folder_id_under_review]},
        supportsAllDrives=True
    ).execute()

    # (4) Google Doc 복사본을 under review에 저장 (편집용)
    work_doc = drive_service.files().copy(
        fileId=doc_id,
        body={'name': file_name, 'parents': [folder_id_under_review]},
        supportsAllDrives=True
    ).execute()

    work_doc_url = f"https://docs.google.com/document/d/{work_doc['id']}/edit"
    print("Files copied to 'under review' folder.")

    # 7. GCS 정리
    storage_client.bucket(source_bucket_name).copy_blob(
        source_blob, storage_client.bucket(archive_bucket_name), file_name
    )
    source_blob.delete()

    # 이메일 발송 (Work Doc 링크 전송)
    send_email_notification(file_name, work_doc_url)
