from schemas import DomainCreate
import hmac
import hashlib
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
import httpx
from fastapi import APIRouter

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY").encode()
META_TAG_NAME = os.getenv("META_TAG_NAME")
FILE_PREFIX = os.getenv("FILE_PREFIX")

domain_router = APIRouter(prefix="/api/v1", tags=["domain"])


def generate_hmac_token(domain: str) -> str:
    return hmac.new(
        SECRET_KEY,
        domain.encode(),
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

    token = generate_hmac_token(domain)

    short_hash = token[:10]

    filename = f"{FILE_PREFIX}-{short_hash}.html"

    file_content =f"""<!DOCTYPE html>
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
        "domain": domain,
        "filename": filename,
        "file_content": file_content,
        "upload_instruction": "Upload this file to the root of your website.",
        "expected_url": f"{domain}/{filename}"
    }


@domain_router.post("/verify-file")
async def verify_verification_file(payload: DomainCreate):
    domain = payload.domain.lower().strip()

    expected_token = generate_hmac_token(domain)

    short_hash = expected_token[:10]
    filename = f"{FILE_PREFIX}-{short_hash}.html"

    target_url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    file_url = f"{target_url}/{filename}"
    
    headers = {"User-Agent": "VerifyBot/1.0"}

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(file_url, headers=headers)

            if response.status_code != 200:
                return {
                    "success": False,
                    "message": f"Verification file not found. Status code: {response.status_code}",
                    "checked_url": file_url
                }

            file_content = response.text.strip()

            if expected_token in file_content:
                return {
                    "success": True,
                    "message": "Domain verified successfully using HTML file.",
                    "checked_url": file_url
                }
            else:
                return {
                    "success": False,
                    "message": "Verification file found, but token does not match.",
                    "checked_url": file_url
                }

    except httpx.RequestError as e:
        return {
            "success": False,
            "message": f"Connection error while accessing site: {str(e)}",
            "checked_url": file_url
        }