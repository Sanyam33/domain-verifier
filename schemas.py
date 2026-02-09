from pydantic import BaseModel, Field

class DomainCreate(BaseModel):
    domain: str = Field(..., example="example.com")
