from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class Symbol:
    type: str
    pitch: Optional[str]
    duration: Optional[str]
    x: int
    y: int
    confidence: float


class BaseRecognizer:
    def recognize(self, image_path: str) -> List[Symbol]:
        raise NotImplementedError


class PlaceholderRecognizer(BaseRecognizer):
    """第一階段佔位實作；之後替換為實際 OMR 引擎。"""

    def recognize(self, image_path: str) -> List[Symbol]:
        return [
            Symbol(
                type="note",
                pitch=None,
                duration=None,
                x=0,
                y=0,
                confidence=0.0,
            )
        ]


def symbols_to_dict(symbols: List[Symbol]) -> list[dict]:
    return [asdict(symbol) for symbol in symbols]
