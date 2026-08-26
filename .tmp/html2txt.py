#!/usr/bin/env python3
"""Fetch a URL and print readable text."""
import sys, re, html, urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research)'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode('utf-8', 'replace')

def strip(h):
    h = re.sub(r'<script[\s\S]*?</script>', ' ', h, flags=re.I)
    h = re.sub(r'<style[\s\S]*?</style>', ' ', h, flags=re.I)
    h = re.sub(r'<noscript[\s\S]*?</noscript>', ' ', h, flags=re.I)
    h = re.sub(r'<!--[\s\S]*?-->', ' ', h)
    h = re.sub(r'<(br|/p|/div|/li|/h[1-6]|/tr|/section|/pre)[^>]*>', '\n', h, flags=re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    h = html.unescape(h)
    h = re.sub(r'[ \t]+', ' ', h)
    h = re.sub(r'\n\s*\n+', '\n', h)
    return h.strip()

url = sys.argv[1]
try:
    txt = strip(fetch(url))
    print(txt)
except Exception as e:
    print(f'ERROR: {e}')
