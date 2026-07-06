from dataclasses import dataclass, field


@dataclass
class Detection:
    """텍스트 내 PII 탐지 결과 (문자 오프셋 기준 스팬)."""

    type: str            # NAME | RRN | CARD | ACCOUNT | ADDRESS | PHONE | EMAIL
    text: str
    start: int
    end: int
    confidence: float
    source: str = "rule"  # rule | llm
    token_ids: list = field(default_factory=list)

    def overlaps(self, other: "Detection") -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "source": self.source,
            "token_ids": self.token_ids,
        }
