#!/usr/bin/env bash
# Send Phase 11 presentations and documents via email.
# Usage: ./send-emails.sh [--dry-run]
#
# Requires: sendmail (postfix) and base64.
# Presentations are Marp markdown files that can be converted to PPTX/PDF first:
#   npx @marp-team/marp-cli --pptx 01-stakeholder-jp-kr.md
#   npx @marp-team/marp-cli --pdf  02-family-kr.md
#   npx @marp-team/marp-cli --pptx 03-employee-kr-jp.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TO="admin@your-domain.com"
FROM="system@your-domain.com"
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

send_email() {
    local subject="$1"
    local body="$2"
    local attachment="$3"
    local attachment_name="$4"
    local boundary="SHINBEE_BOUNDARY_$(date +%s)"

    if [[ -z "$attachment" ]]; then
        # Plain text email
        local msg="From: $FROM
To: $TO
Subject: $subject
Content-Type: text/plain; charset=UTF-8
MIME-Version: 1.0

$body"
    else
        # MIME multipart email with attachment
        local encoded
        encoded=$(base64 "$attachment")
        local content_type="application/octet-stream"
        [[ "$attachment" == *.md ]] && content_type="text/markdown; charset=UTF-8"
        [[ "$attachment" == *.pdf ]] && content_type="application/pdf"
        [[ "$attachment" == *.pptx ]] && content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"

        local msg="From: $FROM
To: $TO
Subject: $subject
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=\"$boundary\"

--$boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 8bit

$body

--$boundary
Content-Type: $content_type
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename=\"$attachment_name\"

$encoded
--$boundary--"
    fi

    if $DRY_RUN; then
        echo "[DRY RUN] Would send: $subject"
        echo "  To: $TO"
        echo "  Attachment: ${attachment_name:-none}"
        echo ""
    else
        echo "$msg" | /usr/sbin/sendmail -t
        echo "Sent: $subject"
    fi
}

echo "=== Sending Phase 11 emails ==="
echo ""

# Email 1: Stakeholder presentation
send_email \
    "【SHINBEE】ステークホルダー向けプレゼンテーション / 이해관계자 프레젠테이션" \
    "シンビジャパン 統合業務システムの紹介資料です。

신비재팬 통합 업무 시스템 소개 자료입니다.

添付ファイルをご確認ください。
첨부 파일을 확인해 주세요." \
    "$SCRIPT_DIR/01-stakeholder-jp-kr.md" \
    "01-stakeholder-jp-kr.md"

# Email 2: Family presentation
send_email \
    "【SHINBEE】가족 프레젠테이션" \
    "신비재팬 IT 프로젝트 소개 자료입니다.

첨부 파일을 확인해 주세요." \
    "$SCRIPT_DIR/02-family-kr.md" \
    "02-family-kr.md"

# Email 3: Employee presentation
send_email \
    "【SHINBEE】社内プレゼンテーション（従業員向け）/ 사내 프레젠테이션 (직원용)" \
    "新しい業務システムの社内説明資料です。
새로운 업무 시스템 사내 설명 자료입니다.

添付ファイルをご確認ください。
첨부 파일을 확인해 주세요." \
    "$SCRIPT_DIR/03-employee-kr-jp.md" \
    "03-employee-kr-jp.md"

# Email 4: Implementation plan
send_email \
    "【SHINBEE】Phase 8-11 Implementation Plan" \
    "Infrastructure migration plan (Phases 8-11) is attached.

Phases 1-10 are COMPLETE.
Phase 11 (documentation and presentations) is in progress." \
    "$REPO_ROOT/PLAN.md" \
    "PLAN.md"

# Email 5: Architecture summary
send_email \
    "【SHINBEE】Infrastructure Migration Summary" \
    "K8s cluster architecture document is attached.

Current state:
- K3s cluster: 2 workers (WiFi+Tailscale) + GCP control plane
- Namespaces: shinbee, intranet, shinbee-test
- Domains: portal, api, fax, tasks, wiki, app (.your-domain.com)
- All phases 1-10 complete
- DNS on Cloud DNS, TLS via cert-manager
- Flutter dashboard at app.your-domain.com
- AI assistant with PII masking, Gemini guidance, meeting mode" \
    "$REPO_ROOT/infrastructure/kubernetes/docs/ARCHITECTURE.md" \
    "ARCHITECTURE.md"

echo ""
echo "=== Done ==="
