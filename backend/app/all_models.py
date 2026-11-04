"""Imports every table so migrations and tests see the full schema."""

from app.ai.models import AiCall
from app.brand.models import (
    Brand, BrandDecision, BrandFile, Conflict, DocLink, Entity, Fact, ImageInfo, Section,
)
from app.campaign.models import Asset, AssetVersion, Campaign
from app.chat.models import Chat, Message
from app.db import Base
from app.memory.models import CampaignRecord, MemoryItem

__all__ = [
    "AiCall", "Asset", "AssetVersion", "CampaignRecord", "MemoryItem", "Base", "Brand", "Campaign", "BrandDecision", "BrandFile", "Chat", "Conflict", "DocLink", "Entity", "Fact",
    "ImageInfo", "Message", "Section",
]
