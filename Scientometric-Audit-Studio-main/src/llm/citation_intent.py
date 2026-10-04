"""
In-Text Citation Intent & Stance Classifier.
Classifies citation sentences into standard scientometric citation functions:
Methodology, Background, Comparison, Critique, and Corroboration.
"""
import logging
from typing import Dict, Any, List, Optional
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

INTENT_CLASSIFICATION_PROMPT = """
You are a scientometric linguist analyzing academic citation function and rhetoric.
Determine the rhetorical stance / intent of the citation within the given in-text sentence.

In-Text Sentence:
\"\"\"{sentence_context}\"\"\"

Cited Marker: \"{marker}\"
Cited Work (if known): \"{cited_title}\"

Classify into one of these 5 standard scientometric categories:
1. METHODOLOGY: The authors directly adopt, apply, or build upon a method, tool, algorithm, dataset, or architecture from the cited work.
2. BACKGROUND: The citation provides foundational context, historical survey, state-of-the-art overview, or general domain introduction.
3. COMPARISON: The authors compare their approach, design, or experimental metrics as a baseline against the cited work.
4. CRITIQUE: The authors highlight limitations, gaps, vulnerabilities, computational bottlenecks, or disagreements with the cited work.
5. CORROBORATION: The authors note that their empirical findings or observations agree with or confirm the cited work.

Return ONLY a valid JSON object matching this schema:
{{
  "intent": "METHODOLOGY | BACKGROUND | COMPARISON | CRITIQUE | CORROBORATION",
  "confidence": 0.90,
  "rationale": "Brief 1-sentence justification of the citation function.",
  "sentiment": "NEUTRAL | POSITIVE | CRITICAL"
}}
"""


class CitationIntentClassifier:
    """
    Classifies the scientometric function and stance of citations in context.
    """

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient.get_default()

    def classify(
        self,
        sentence_context: str,
        marker: str = "",
        cited_title: str = "",
    ) -> Dict[str, Any]:
        """
        Classifies the intent of a single in-text citation snippet.
        """
        if not sentence_context or not sentence_context.strip():
            return {
                "intent": "BACKGROUND",
                "confidence": 0.5,
                "rationale": "Empty sentence context.",
                "sentiment": "NEUTRAL",
            }

        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            sentence_context=sentence_context.strip(),
            marker=marker or "[Ref]",
            cited_title=cited_title or "Unspecified cited work",
        )

        messages = [
            {"role": "system", "content": "You are a scientometric citation stance analyzer. Respond only in JSON."},
            {"role": "user", "content": prompt},
        ]

        resp = self.client.chat_completion(messages, temperature=0.0, max_tokens=250, json_mode=True)
        data = self.client.extract_json(resp)

        if data and isinstance(data, dict):
            intent = str(data.get("intent", "BACKGROUND")).upper().strip()
            if intent not in ("METHODOLOGY", "BACKGROUND", "COMPARISON", "CRITIQUE", "CORROBORATION"):
                intent = "BACKGROUND"
            confidence = float(data.get("confidence", 0.8))
            rationale = str(data.get("rationale", "")).strip()
            sentiment = str(data.get("sentiment", "NEUTRAL")).upper().strip()

            return {
                "intent": intent,
                "confidence": min(1.0, max(0.0, confidence)),
                "rationale": rationale or "Classified by LLM citation stance model.",
                "sentiment": sentiment,
            }

        # Rule-based fallback for high reliability when LLM offline
        lower = sentence_context.lower()
        if any(w in lower for w in ("method", "algorithm", "adopt", "using", "implement", "utilize", "framework")):
            return {"intent": "METHODOLOGY", "confidence": 0.7, "rationale": "Keyword heuristic: methodology", "sentiment": "NEUTRAL"}
        elif any(w in lower for w in ("however", "limitation", "flaw", "fails", "bottleneck", "lack", "suffer")):
            return {"intent": "CRITIQUE", "confidence": 0.7, "rationale": "Keyword heuristic: critical discussion", "sentiment": "CRITICAL"}
        elif any(w in lower for w in ("compare", "baseline", "outperform", "higher than", "versus", "vs.")):
            return {"intent": "COMPARISON", "confidence": 0.7, "rationale": "Keyword heuristic: comparative evaluation", "sentiment": "NEUTRAL"}
        elif any(w in lower for w in ("consistent with", "agrees with", "confirm", "similar observation")):
            return {"intent": "CORROBORATION", "confidence": 0.7, "rationale": "Keyword heuristic: corroboration", "sentiment": "POSITIVE"}

        return {
            "intent": "BACKGROUND",
            "confidence": 0.6,
            "rationale": "Default background literature category.",
            "sentiment": "NEUTRAL",
        }

