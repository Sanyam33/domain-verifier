from schemas import DomainCreate
import hmac
import hashlib
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
import httpx
from urllib.parse import urlparse
from fastapi import APIRouter

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY").encode()
META_TAG_NAME = os.getenv("META_TAG_NAME")
FILE_PREFIX = os.getenv("FILE_PREFIX")

domain_router = APIRouter(prefix="/api/v1", tags=["domain"])


def normalize_domain(domain: str) -> str:
    """Strip scheme and www prefix to get a canonical root domain."""
    # Remove scheme
    for scheme in ("https://", "http://"):
        if domain.startswith(scheme):
            domain = domain[len(scheme):]
    # Strip trailing slash
    domain = domain.rstrip("/")
    # Strip www. prefix so dadsmedia.com and www.dadsmedia.com use the same token
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_path(path: str) -> str:
    return path.rstrip("/")

# def is_valid_redirect(original_url: str, final_url: str) -> bool:
#     orig = urlparse(original_url)
#     final = urlparse(final_url)

#     orig_domain = orig.netloc.replace("www.", "")
#     final_domain = final.netloc.replace("www.", "")

#     if orig_domain != final_domain:
#         return False

#     # Normalize paths before comparing
#     if normalize_path(orig.path) != normalize_path(final.path):
#         return False

#     return True

# def is_canonical_redirect(original_url: str, final_url: str) -> bool:
#     """Return True if the redirect is just a www <-> non-www (or http->https) normalisation."""
#     return normalize_domain(original_url) == normalize_domain(str(final_url))


def generate_hmac_token(domain: str) -> str:
    # Always use the canonical (no-www) domain so the token is identical
    # whether the user submits dadsmedia.com or www.dadsmedia.com
    canonical = normalize_domain(domain)
    return hmac.new(
        SECRET_KEY,
        canonical.encode(),
        hashlib.sha256
    ).hexdigest()


### Meat Tag Based Verification ###

@domain_router.post("/request-token")
def request_token(payload: DomainCreate):
    domain = payload.domain.lower().strip()

    token = generate_hmac_token(domain)

    return {
        "domain": domain,
        "meta_tag":{
            "name":META_TAG_NAME,
            "content":token
        } 
    }


@domain_router.post("/verify-site")
async def verify_site(payload: DomainCreate):
    domain = payload.domain.lower().strip()
    
    expected_token = generate_hmac_token(domain)
    
    target_url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    headers = {"User-Agent": "VerifyBot/1.0"}
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(target_url, headers=headers)

            if response.status_code != 200:
                return {
                    "success": False, 
                    "message": f"Could not reach site. Status code: {response.status_code}"
                }

            soup = BeautifulSoup(response.text, "html.parser")
            
            tag = soup.find("meta", attrs={"name": META_TAG_NAME})

            if not tag:
                return {
                    "success": False, 
                    "message": f"Meta tag '{META_TAG_NAME}' not found."
                }

            found_token = tag.get("content", "")

            if found_token == expected_token:
                return {
                    "success": True,
                    "message": "Domain verified successfully!",
                    "domain": domain
                }
            else:
                return {
                    "success": False,
                    "message": "Token mismatch"
                }

    except httpx.RequestError as e:
        return {"success": False, "message": f"Connection error: {str(e)}"}


### File Based Verification ###

@domain_router.post("/request-file")
def request_verification_file(payload: DomainCreate):
    domain = payload.domain.lower().strip()
    canonical = normalize_domain(domain)

    token = generate_hmac_token(canonical)

    short_hash = token[:10]

    filename = f"{FILE_PREFIX}-{short_hash}.html"

    file_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>Domain Verification</title>
        </head>
        <body>
            {token}
        </body>
        </html>
    """

    return {
        "domain": canonical,
        "filename": filename,
        "file_content": file_content,
        "upload_instruction": "Upload this file to the root of your website.",
        "expected_url": f"https://{canonical}/{filename}"
    }


# @domain_router.post("/verify-file")
# async def verify_verification_file(payload: DomainCreate):
#     domain = payload.domain.lower().strip()
#     canonical = normalize_domain(domain)

#     expected_token = generate_hmac_token(canonical)

#     short_hash = expected_token[:10]
#     filename = f"{FILE_PREFIX}-{short_hash}.html"

#     file_url = f"https://{canonical}/{filename}"

#     headers = {"User-Agent": "VerifyBot/1.0"}

#     try:
#         async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
#             response = await client.get(file_url, headers=headers)

#             if response.status_code != 200:
#                 return {
#                     "success": False,
#                     "message": f"Verification file not found. Status code: {response.status_code}",
#                     "checked_url": file_url
#                 }

#             # Allow canonical redirects (www <-> non-www, http -> https).
#             # These are legitimate same-site redirects — the file is still on
#             # the same domain the user controls.
#             # Block any redirect that goes to a *different* root domain.
#             final_url = str(response.url)

#             if not is_valid_redirect(file_url, final_url):
#                 return {
#                     "success": False,
#                     "message": (
#                         f"Verification file not found at expected location. "
#                         f"Request was redirected to '{final_url}'"
#                     ),
#                     "checked_url": file_url,
#                     "redirected_to": final_url
#                 }

#             file_content = response.text.strip()

#             if expected_token in file_content:
#                 return {
#                     "success": True,
#                     "message": "Domain verified successfully using HTML file.",
#                     "domain": canonical,
#                     "checked_url": file_url
#                 }
#             else:
#                 return {
#                     "success": False,
#                     "message": "Verification file found, but token does not match.",
#                     "checked_url": file_url
#                 }

#     except httpx.RequestError as e:
#         return {
#             "success": False,
#             "message": f"Connection error while accessing site: {str(e)}",
#             "checked_url": file_url
#         }

async def fetch_and_validate(client, url, expected_token):
    try:
        res = await client.get(url)

        if res.status_code != 200:
            return False, f"Status {res.status_code}", url

        final_url = str(res.url)

        parsed_req = urlparse(url)
        parsed_final = urlparse(final_url)

        # Normalize domains
        req_domain = parsed_req.netloc.replace("www.", "")
        final_domain = parsed_final.netloc.replace("www.", "")

        # Normalize paths
        req_path = parsed_req.path.rstrip("/")
        final_path = parsed_final.path.rstrip("/")

        # Reject if path changed (means not actual file)
        if req_path != final_path:
            return False, f"Redirected to different path: {final_url}", url

        # Reject if domain changed
        if req_domain != final_domain:
            return False, f"Redirected to different domain: {final_url}", url

        content = res.text.strip()

        # STRICT CHECK: token must exist
        if expected_token in content:
            return True, "Verified", final_url

        # Detect fake 200 (homepage / fallback)
        if len(content) > 5000:
            return False, "Likely not a verification file (large HTML page)", url

        return False, "Token not found in file", url

    except Exception as e:
        return False, str(e), url


@domain_router.post("/verify-file")
async def verify_verification_file(payload: DomainCreate):
    domain = payload.domain.lower().strip()
    canonical = normalize_domain(domain)

    expected_token = generate_hmac_token(canonical)
    short_hash = expected_token[:10]
    filename = f"{FILE_PREFIX}-{short_hash}.html"

    urls_to_try = [
        f"https://{canonical}/{filename}",
        f"https://www.{canonical}/{filename}"
    ]

    headers = {"User-Agent": "VerifyBot/1.0"}

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0,
            headers=headers
        ) as client:

            for url in urls_to_try:
                success, message, final_url = await fetch_and_validate(
                    client, url, expected_token
                )

                if success:
                    return {
                        "success": True,
                        "message": "Domain verified successfully using HTML file.",
                        "domain": canonical,
                        "checked_url": final_url
                    }

            return {
                "success": False,
                "message": "Verification file not found on both root and www domain.",
                "checked_urls": urls_to_try
            }

    except httpx.RequestError as e:
        return {
            "success": False,
            "message": f"Connection error while accessing site: {str(e)}"
        }







