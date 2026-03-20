provider "google" {
  project = var.project_id
  region  = var.region
}

terraform {
  backend "gcs" {
    bucket  = "your-project-tfstate" # 위에서 만든 버킷 이름
    prefix  = "terraform/state"
  }
}

# 프로젝트 번호를 가져오기 위한 데이터 소스
data "google_project" "project" {
}

# [추가됨] 소스 코드를 저장할 별도 버킷 (팩스 수신 버킷과 분리!)
resource "google_storage_bucket" "function_source_bucket" {
  name          = "${var.project_id}-function-source"
  location      = var.region
  force_destroy = true
  uniform_bucket_level_access = true
}

# [추가됨] 로컬의 src 폴더를 zip 파일로 압축
data "archive_file" "source_zip" {
  type        = "zip"
  source_dir  = "${path.module}/src"  # main.py가 들어있는 폴더 경로
  output_path = "${path.module}/source.zip"
}

# [추가됨] 압축된 zip 파일을 버킷에 업로드
resource "google_storage_bucket_object" "source_archive" {# 파일 이름에 MD5 해시를 추가하여 내용 변경 시 이름이 바뀌게 함
  name   = "source-${data.archive_file.source_zip.output_md5}.zip" 
  bucket = google_storage_bucket.function_source_bucket.name
  source = data.archive_file.source_zip.output_path
}

# 수신 버킷
resource "google_storage_bucket" "fax_incoming" {
  name          = "${var.project_id}-fax-incoming"
  location      = var.region
  force_destroy = true
}

# 아카이브 버킷 (1년 수명 주기)
resource "google_storage_bucket" "fax_archive" {
  name     = "${var.project_id}-fax-archive"
  location = var.region
  lifecycle_rule {
    condition { age = 365 }
    action {
      type = "SetStorageClass"
      storage_class = "ARCHIVE"
      }
  }
}

# 1. Cloud Function 전용 서비스 계정 생성
resource "google_service_account" "function_sa" {
  account_id   = "fax-ocr-sa"
  display_name = "Fax OCR Function Service Account"
}

# 2. 서비스 계정에 필요한 권한 부여
# (버킷 읽기/쓰기, Document AI 사용, 로그 기록, Cloud Run 실행 권한)
resource "google_project_iam_member" "function_sa_roles" {
  for_each = toset([
    "roles/storage.objectAdmin",     # 버킷 파일 읽고 쓰기
    "roles/aiplatform.user",        # Vertex AI (Gemini Flash) 호출
    "roles/logging.logWriter",       # 로그 남기기
    "roles/run.invoker",             # 2세대 함수(Cloud Run) 실행 권한
    "roles/eventarc.eventReceiver"   # 이벤트 트리거 수신
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

# 1. Eventarc 서비스 에이전트에게 필요한 권한 부여 (지금 발생한 에러 해결용)
resource "google_project_iam_member" "eventarc_agent_roles" {
  project = data.google_project.project.id
  role    = "roles/eventarc.serviceAgent"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# 2. Cloud Storage 서비스 에이전트에게 Pub/Sub 게시 권한 부여 (다음 단계 에러 방지용)
# GCS 트리거가 Eventarc로 신호를 보내려면 이 권한이 꼭 필요합니다.
data "google_storage_project_service_account" "gcs_account" {
}

resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = data.google_project.project.id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

# Cloud Functions (2세대) 수정
resource "google_cloudfunctions2_function" "fax_processor_function" {
  name        = "fax-ocr-processor"
  location    = var.region
  description = "Process incoming faxes using Gemini Flash"

  build_config {
    runtime     = "python310"
    entry_point = "process_fax" # main.py 안의 함수 이름과 일치해야 함
    source {
      storage_source {
        # [수정됨] 소스 전용 버킷을 바라보도록 변경
        bucket = google_storage_bucket.function_source_bucket.name
        object = google_storage_bucket_object.source_archive.name
      }
    }
  }

  service_config {
    available_memory   = "512Mi"
    timeout_seconds    = 120
    service_account_email = google_service_account.function_sa.email
    environment_variables = {
      GCP_PROJECT     = var.project_id
      GCP_REGION      = var.region
      ARCHIVE_BUCKET  = google_storage_bucket.fax_archive.name
      DRIVE_FOLDER_ID_ORIGINAL = var.drive_folder_id_original
      DRIVE_FOLDER_ID_WORK     = var.drive_folder_id_work
      EMAIL_SENDER             = var.notification_email_sender
      EMAIL_PASSWORD           = nonsensitive(var.notification_email_password)
      EMAIL_RECEIVER           = var.notification_email_receiver
      APPS_SCRIPT_URL = var.apps_script_url
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.storage.object.v1.finalized"
    retry_policy   = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.function_sa.email # (권장) 별도 SA가 있다면 추가

    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.fax_incoming.name # 감지는 여전히 수신 버킷에서 함
    }
  }

  depends_on = [
    google_project_iam_member.eventarc_agent_roles,
    google_project_iam_member.gcs_pubsub_publisher
  ]
}

output "service_account_email" {
  value = google_service_account.function_sa.email
}

# 1. 업로드 전용 서비스 계정 생성
resource "google_service_account" "uploader_sa" {
  account_id   = "fax-storage-uploader"
  display_name = "Fax Storage Uploader Service Account"
}

# 2. 최소 권한(Object Creator) 부여
# roles/storage.objectCreator는 파일을 생성(업로드)만 할 수 있으며, 삭제나 목록 조회가 불가능한 최소 권한입니다.
resource "google_storage_bucket_iam_member" "uploader_iam" {
  bucket = google_storage_bucket.fax_incoming.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.uploader_sa.email}"
}

# 3. 서비스 계정 키 생성
resource "google_service_account_key" "uploader_key" {
  service_account_id = google_service_account.uploader_sa.name
}

# 4. 키 JSON을 설치 (root:root 600)
resource "terraform_data" "install_sa_key" {
  input = google_service_account_key.uploader_key.id

  provisioner "local-exec" {
    command = <<-EOT
      sudo mkdir -p /etc/shinbee/fax
      printf '%s' "$SA_KEY_B64" | base64 -d | sudo install -m 600 -o root -g root /dev/stdin /etc/shinbee/fax/gcp-sa.json
    EOT
    environment = {
      SA_KEY_B64 = google_service_account_key.uploader_key.private_key
    }
  }
}

output "uploader_key_json" {
  value     = google_service_account_key.uploader_key.private_key
  sensitive = true
}