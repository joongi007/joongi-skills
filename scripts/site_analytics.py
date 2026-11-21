"""Fixed public-site tagging. Never add analytics to local Hub or preview builds."""

import base64
import hashlib

PUBLIC_BASE_URL = "https://joongi007.github.io/joongi-skills"
CONTAINER_ID = "GTM-MCHLMHRF"
BOOTSTRAP = (
    "window.dataLayer = window.dataLayer || [];\n"
    "function gtag(){dataLayer.push(arguments);}\n"
    "gtag('js', new Date());"
)
SCRIPT_HASH = "sha256-" + base64.b64encode(hashlib.sha256(BOOTSTRAP.encode()).digest()).decode()
TAG = (
    '<script async src="https://www.googletagmanager.com/gtm.js?id='
    + CONTAINER_ID
    + '"></script>\n<script>'
    + BOOTSTRAP
    + "</script>"
)
BASE_CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self' https: data:; "
    "font-src 'self'; base-uri 'none'; form-action 'none'"
)


def enabled(base_url):
    return base_url.rstrip("/") == PUBLIC_BASE_URL


def document_csp(analytics=False):
    if not analytics:
        return BASE_CSP
    # No unsafe-inline/eval, arbitrary script hosts, Ads endpoints or preview-mode overrides.
    return (
        BASE_CSP + f"; script-src '{SCRIPT_HASH}' https://www.googletagmanager.com; "
        "script-src-attr 'none'; connect-src https://www.googletagmanager.com "
        "https://*.google-analytics.com https://*.google.com"
    )


def homepage(source, analytics=False):
    if not analytics:
        return source
    if source.count("</head>") != 1:
        raise ValueError("Public homepage must have exactly one head closing tag")
    return source.replace("</head>", TAG + "\n</head>")
