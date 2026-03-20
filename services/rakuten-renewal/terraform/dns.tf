# MX record for sentinel subdomain (inbound email via SendGrid)
resource "aws_route53_record" "sentinel_mx" {
  zone_id = var.route53_zone_id
  name    = var.sentinel_domain
  type    = "MX"
  ttl     = 3600
  records = ["10 mx.sendgrid.net"]
}

# SPF record for outbound email
resource "aws_route53_record" "sentinel_spf" {
  zone_id = var.route53_zone_id
  name    = var.sentinel_domain
  type    = "TXT"
  ttl     = 3600
  records = ["v=spf1 include:sendgrid.net ~all"]
}
