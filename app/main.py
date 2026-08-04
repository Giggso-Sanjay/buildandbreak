from fastapi import FastAPI

from app.routes.shorten import router as shorten_router

app = FastAPI(title="URL Shortener Service")
app.include_router(shorten_router)
