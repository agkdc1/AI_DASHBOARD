#!/usr/bin/env python3
"""Update Route53 A and MX records for the mail gateway domain."""

import sys
import urllib.request
import yaml
import boto3


def get_public_ip():
    """Detect public IP address."""
    return urllib.request.urlopen("https://ifconfig.me").read().decode().strip()


def update_dns(config_path):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    domain = config["domain"]
    zone_id = config["aws"]["hosted_zone_id"]
    public_ip = get_public_ip()

    print(f"Public IP: {public_ip}")
    print(f"Updating DNS for: {domain}")

    client = boto3.client("route53")
    client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            "Comment": "mail2fax gateway auto-update",
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": domain,
                        "Type": "A",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": public_ip}],
                    },
                },
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": domain,
                        "Type": "MX",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": f"10 {domain}"}],
                    },
                },
            ],
        },
    )
    print("DNS records updated successfully.")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "/app/config.yaml"
    update_dns(config_path)
