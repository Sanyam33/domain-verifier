from fastapi import FastAPI
import router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router.domain_router)

@app.get("/")
def root():
    return {"message": "Welcome to the Domain Verification API"}

@app.get("/help")
def help():
    return {
        "routes": {
            "request-token": "POST /api/v1/request-token",
            "verify-site": "POST /api/v1/verify-site",
            "request-file": "POST /api/v1/request-file",
            "verify-file": "POST /api/v1/verify-file"
        },
        "example_payload": {
            "domain": "https://example.com"
        }
    }