"""
HTTP client wrapper using only Python stdlib (urllib).
Drop-in replacement for requests.get/post patterns.
"""
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl


# Reusable SSL context (default verification)
_SSL_CTX = ssl.create_default_context()
_DEFAULT_UA = 'Mozilla/5.0 (compatible; FinanceDeepDive/1.0)'


def get(url, params=None, timeout=10, headers=None):
    """HTTP GET returning parsed JSON (or raw bytes on non-JSON)."""
    if params:
        url = url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method='GET')
    req.add_header('User-Agent', _DEFAULT_UA)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        data = resp.read()
        content_type = resp.headers.get('Content-Type', '')
        if 'json' in content_type:
            return json.loads(data)
        # Try JSON anyway
        try:
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return data


def get_text(url, timeout=10, headers=None):
    """HTTP GET returning raw text."""
    req = urllib.request.Request(url, method='GET')
    req.add_header('User-Agent', _DEFAULT_UA)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.read().decode('utf-8', errors='replace')


def post_json(url, payload, headers=None, timeout=10):
    """HTTP POST with JSON body, returns parsed JSON response."""
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', _DEFAULT_UA)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        data = resp.read()
        try:
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return data


def get_json_safe(url, params=None, timeout=10, default=None):
    """GET that returns *default* on any network/parse error."""
    try:
        return get(url, params=params, timeout=timeout)
    except Exception:
        return default
