# Amazon SP-API — WIF + STS (no long-lived AWS keys).
#
# Flow: GCP SA OIDC token → AWS STS AssumeRoleWithWebIdentity → temp creds → SigV4
# Register the role ARN in Seller Central SP-API app registration.

# OIDC identity provider for Google — allows GCP SAs to assume AWS roles
resource "aws_iam_openid_connect_provider" "google" {
  url             = "https://accounts.google.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["08745487e891c19e3078c1f2a07e452950ef36f6"]

  tags = {
    Purpose   = "GCP WIF for SP-API"
    ManagedBy = "terraform"
  }
}

# SP-API execution role — trusted by GCP SA via OIDC federation
resource "aws_iam_role" "sp_api" {
  name = "shinbee-sp-api-role"
  path = "/service/"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.google.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "accounts.google.com:aud" = "sts.amazonaws.com"
            "accounts.google.com:sub" = "109937379808293600770"
          }
        }
      }
    ]
  })

  tags = {
    Purpose   = "Amazon SP-API execution role via WIF+STS"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role_policy" "sp_api_execute" {
  name = "sp-api-execute"
  role = aws_iam_role.sp_api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SPAPIExecute"
        Effect   = "Allow"
        Action   = "execute-api:Invoke"
        Resource = "arn:aws:execute-api:*:*:*"
      }
    ]
  })
}

output "sp_api_role_arn" {
  description = "Role ARN for Seller Central SP-API app registration"
  value       = aws_iam_role.sp_api.arn
}
