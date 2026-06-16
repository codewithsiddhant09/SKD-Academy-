#!/usr/bin/env python
"""Test startup to debug initialization issues"""
import sys
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("1. Loading config...")
from app.core.config import get_settings
settings = get_settings()
print(f"   - OpenAI API Key set: {'***' if settings.openai_api_key else 'NO'}")

print("2. Loading category service...")
from app.services.category_service import CategoryService
cs = CategoryService()
cs.warmup()
categories = cs.get_category_names()
print(f"   - Categories: {categories}")

print("3. Creating agents...")
from app.agents.intent_agent import IntentAgent
print("   - IntentAgent...")
ia = IntentAgent()
print("   - OK")

from app.agents.category_agent import CategoryAgent
print("   - CategoryAgent...")
cag = CategoryAgent()
print("   - OK")

from app.agents.location_agent import LocationAgent
print("   - LocationAgent...")
la = LocationAgent()
print("   - OK")

from app.agents.salon_discovery_agent import SalonDiscoveryAgent
print("   - SalonDiscoveryAgent...")
sda = SalonDiscoveryAgent()
print("   - OK")

from app.agents.salon_ranking_agent import SalonRankingAgent
print("   - SalonRankingAgent...")
sra = SalonRankingAgent()
print("   - OK")

from app.agents.faq_agent import FaqAgent
print("   - FaqAgent...")
fa = FaqAgent()
print("   - OK")

from app.agents.booking_agent import BookingAgent
print("   - BookingAgent...")
ba = BookingAgent()
print("   - OK")

print("4. Creating services...")
from app.services.booking_service import BookingService
print("   - BookingService...")
bs = BookingService()
print("   - OK")

print("5. Creating memory...")
from app.memory.conversation_store import ConversationStore
print("   - ConversationStore...")
memory = ConversationStore()
print("   - OK")

print("6. Creating workflow...")
from app.graph.workflow import OrchestratorWorkflow
print("   - OrchestratorWorkflow...")
workflow = OrchestratorWorkflow(
    memory=memory,
    categories=categories,
    intent_agent=ia,
    category_agent=cag,
    location_agent=la,
    discovery_agent=sda,
    ranking_agent=sra,
    faq_agent=fa,
    booking_agent=ba,
    booking_service=bs,
)
print("   - OK")

print("7. Creating OrchestratorService...")
from app.services.orchestrator_service import OrchestratorService
os = OrchestratorService(categories=categories)
print("   - OK")

print("✅ All initialization complete!")
