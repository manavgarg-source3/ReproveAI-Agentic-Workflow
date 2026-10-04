"""
LLM-Powered Bibliometric Intelligence Package.
Provides citation extraction, semantic discrepancy auditing, citation intent classification,
and executive scientometric synthesis.
"""
from src.llm.client import LLMClient
from src.llm.citation_extractor import LLMCitationExtractor
from src.llm.discrepancy_auditor import LLMDiscrepancyAuditor
from src.llm.citation_intent import CitationIntentClassifier
from src.llm.scientometric_synthesizer import ScientometricSynthesizer

__all__ = [
    "LLMClient",
    "LLMCitationExtractor",
    "LLMDiscrepancyAuditor",
    "CitationIntentClassifier",
    "ScientometricSynthesizer",
]

