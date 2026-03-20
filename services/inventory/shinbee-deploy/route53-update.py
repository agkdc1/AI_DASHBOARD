#!/usr/bin/env python3
"""Update Route53 A and AAAA records with the host's current IP.

Usage: python route53-update.py [--mode production|test] <domain>

  production (default): A = external IPv4, AAAA = external IPv6 (if available)
  test:                 A = internal/private IPv4, no AAAA

Auto-detects the Route53 hosted zone ID from the domain name.
Requires AWS credentials (via ~/.aws, env vars, or IAM role).
"""
import argparse
import os
import socket
import sys
import urllib.request

import boto3


def get_public_ipv4():
    """Get public IPv4 from AWS checkip service."""
    resp = urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10)
    return resp.read().decode().strip()


def get_public_ipv6():
    """Get public IPv6 address. Returns None if unavailable."""
    try:
        resp = urllib.request.urlopen("https://api6.ipify.org", timeout=10)
        addr = resp.read().decode().strip()
        # Sanity-check: must contain a colon (IPv6)
        if ":" in addr:
            return addr
        return None
    except Exception:
        return None


def get_internal_ipv4():
    """Get the host's internal/private IPv4 address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def find_hosted_zone(client, domain):
    """Find the Route53 hosted zone ID for the given domain.

    Walks up the domain hierarchy to find the matching zone.
    e.g. for 'api.your-domain.com', tries:
      - api.your-domain.com.
      - your-domain.com.

    Uses list_hosted_zones (paginated) instead of list_hosted_zones_by_name
    to avoid needing the route53:ListHostedZonesByName permission.
    """
    # Build all candidate zone names (most specific first)
    parts = domain.split(".")
    candidates = set()
    for i in range(len(parts) - 1):
        candidates.add(".".join(parts[i:]) + ".")

    # Paginate through all hosted zones
    paginator = client.get_paginator("list_hosted_zones")
    for page in paginator.paginate():
        for zone in page["HostedZones"]:
            if zone["Name"] in candidates:
                zone_id = zone["Id"].split("/")[-1]
                print(f"Found hosted zone: {zone['Name']} -> {zone_id}")
                return zone_id
    return None


def resolve_cname(domain):
    """Resolve CNAME target for a domain via DNS query. Returns target or None."""
    import re
    import subprocess
    # nslookup is available on Alpine (busybox)
    try:
        result = subprocess.run(
            ["nslookup", "-type=cname", domain],
            capture_output=True, text=True, timeout=10
        )
        # Parse "api.your-domain.com  canonical name = target.example.com."
        for line in result.stdout.splitlines():
            m = re.search(r"canonical name\s*=\s*(\S+?)\.?$", line, re.IGNORECASE)
            if m:
                target = m.group(1)
                if not target.endswith("."):
                    target += "."
                return target
    except Exception:
        pass
    return None


def delete_and_create_record(client, zone_id, domain, cname_target, record_type, value, ttl=300):
    """Delete a conflicting CNAME and create the desired record in one batch."""
    print(f"Attempting to delete CNAME ({cname_target}) and create {record_type} record...")
    # Try common TTL values since we can't query the exact TTL
    for try_ttl in [300, 60, 3600, 86400, 900, 600, 120, 1800, 7200, 43200]:
        try:
            client.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Comment": f"Replace CNAME with {record_type} for dynamic DNS",
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "CNAME",
                                "TTL": try_ttl,
                                "ResourceRecords": [{"Value": cname_target}],
                            },
                        },
                        {
                            "Action": "CREATE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": record_type,
                                "TTL": ttl,
                                "ResourceRecords": [{"Value": value}],
                            },
                        },
                    ],
                },
            )
            print(f"CNAME deleted (TTL was {try_ttl}), {record_type} record created.")
            return
        except client.exceptions.InvalidChangeBatch:
            continue
    raise RuntimeError(
        f"Could not delete CNAME for {domain}. "
        f"Please delete it manually in the AWS Route53 console."
    )


def upsert_record(client, zone_id, domain, record_type, value, ttl=300):
    """UPSERT a single DNS record. Handles CNAME conflicts automatically."""
    try:
        client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Comment": f"Auto-update {record_type} from certbot container",
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": domain,
                            "Type": record_type,
                            "TTL": ttl,
                            "ResourceRecords": [{"Value": value}],
                        },
                    }
                ],
            },
        )
    except client.exceptions.InvalidChangeBatch as e:
        if "CNAME" in str(e):
            cname_target = resolve_cname(domain)
            if cname_target:
                print(f"CNAME conflict detected (target: {cname_target}). Replacing...")
                delete_and_create_record(
                    client, zone_id, domain, cname_target,
                    record_type, value, ttl
                )
            else:
                print(f"CNAME conflict but could not resolve target. "
                      f"Delete the CNAME manually in Route53.", file=sys.stderr)
                raise
        else:
            raise


def main():
    parser = argparse.ArgumentParser(description="Update Route53 DNS records")
    parser.add_argument("domain", help="Domain name to update")
    parser.add_argument(
        "--mode",
        choices=["production", "test"],
        default="production",
        help="production: external IPs; test: internal IPv4 only",
    )
    parser.add_argument(
        "--zone-id",
        default=os.environ.get("ROUTE53_ZONE_ID", ""),
        help="Route53 hosted zone ID (skips auto-detection)",
    )
    args = parser.parse_args()

    # ── Resolve IPs based on mode ──
    if args.mode == "test":
        ipv4 = get_internal_ipv4()
        ipv6 = None
        print(f"Mode: test (internal IPv4)")
    else:
        ipv4 = get_public_ipv4()
        ipv6 = get_public_ipv6()
        print(f"Mode: production (external IPs)")

    if not ipv4:
        print("ERROR: Could not determine IPv4 address", file=sys.stderr)
        sys.exit(1)
    print(f"IPv4: {ipv4}")

    if ipv6:
        print(f"IPv6: {ipv6}")
    else:
        print("IPv6: not available — skipping AAAA record")

    # ── Find hosted zone ──
    client = boto3.client("route53")
    if args.zone_id:
        zone_id = args.zone_id
        print(f"Using provided zone ID: {zone_id}")
    else:
        zone_id = find_hosted_zone(client, args.domain)
        if not zone_id:
            print(f"ERROR: No hosted zone found for {args.domain}", file=sys.stderr)
            sys.exit(1)

    # ── UPSERT A record ──
    print(f"Upserting A record: {args.domain} -> {ipv4}")
    upsert_record(client, zone_id, args.domain, "A", ipv4)
    print(f"A record updated: {args.domain} -> {ipv4} (TTL 300)")

    # ── UPSERT AAAA record (production only, if IPv6 available) ──
    if ipv6:
        print(f"Upserting AAAA record: {args.domain} -> {ipv6}")
        upsert_record(client, zone_id, args.domain, "AAAA", ipv6)
        print(f"AAAA record updated: {args.domain} -> {ipv6} (TTL 300)")


if __name__ == "__main__":
    main()
