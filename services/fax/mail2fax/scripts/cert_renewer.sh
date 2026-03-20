#!/bin/bash
# Monthly certificate renewal (called by cron)
certbot renew --quiet
postfix reload
