import re

POLICIES = [
    {"id": "returns-01", "title": "Damaged item process", "text": "For an item that arrives damaged, ask the customer for a photo of the item and packaging within 7 days of delivery. Support may offer a replacement after reviewing the evidence. Do not promise a refund before a human review."},
    {"id": "shipping-02", "title": "Shipment tracking", "text": "Shipment status and estimated delivery dates must come from the order record or carrier tracking. If a parcel is marked delivered but cannot be found, verify the delivery address and escalate for carrier investigation."},
    {"id": "privacy-03", "title": "Account and privacy issues", "text": "Requests involving account access, payment data, identity documents, or deletion of personal data must be escalated to a trained human. Never request a full card number or password in a support reply."},
    {"id": "returns-04", "title": "Change of mind", "text": "Unopened products may be eligible for return within 30 days of delivery. Eligibility is checked by a support agent. Do not state that a return is approved until an agent confirms it."},
]


def terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def retrieve(query: str, limit: int = 3) -> list[dict[str, str]]:
    q = terms(query)
    ranked = []
    for doc in POLICIES:
        d = terms(doc["title"] + " " + doc["text"])
        overlap = len(q & d)
        score = overlap / max(1, len(q))
        if score:
            ranked.append((score, doc))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [{**doc, "score": round(score, 3)} for score, doc in ranked[:limit]]
