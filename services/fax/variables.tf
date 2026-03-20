# variables.tf

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

# [변경] 기존 drive_folder_id 제거하고 2개로 분리
variable "drive_folder_id_original" {
  description = "원본 PDF와 결과물이 저장될 폴더 (뷰어 권한 권장)"
  type        = string
}

variable "drive_folder_id_work" {
  description = "업무용 사본이 저장될 폴더 (편집자 권한 권장)"
  type        = string
}

variable "notification_email_sender" {
  type = string
}
variable "notification_email_password" {
  type = string
  sensitive = true # 로그에 노출되지 않게 설정
}
variable "notification_email_receiver" {
  type = string
}

variable "apps_script_url" {
  description = "배포된 Google Apps Script 웹 앱 URL (exec로 끝나는 주소)"
  type        = string
  default     = "" # 배포 전이면 비워두고, 나중에 tfvars에서 채움
}

# tfvars에 추가한 다른 설정이 있다면 여기에도 똑같이 이름을 선언하세요.