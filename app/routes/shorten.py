from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.link import Link
from app.services.code_gen import generate_unique_code

router = APIRouter()


class ShortenRequest(BaseModel):
    long_url: str


class ShortenResponse(BaseModel):
    code: str
    long_url: str


@router.post("/shorten", response_model=ShortenResponse)
def shorten(payload: ShortenRequest, response: Response, db: Session = Depends(get_db)):
    response.status_code = status.HTTP_200_OK

    existing = db.execute(select(Link).where(Link.long_url == payload.long_url)).scalar_one_or_none()
    if existing is not None:
        return ShortenResponse(code=existing.code, long_url=existing.long_url)

    code = generate_unique_code(db)
    link = Link(code=code, long_url=payload.long_url)
    db.add(link)
    db.commit()

    return ShortenResponse(code=code, long_url=link.long_url)
