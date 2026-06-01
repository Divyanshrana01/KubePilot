import asyncio
from typing import Any

from fastapi import APIRouter
from loguru import logger

from app.config import settings


router = APIRouter(tags=["admin"])

