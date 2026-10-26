from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


@dataclass
class Symbol:
    type: str
    pitch: str | None
    duration: str | None
    x: int
    y: int
    confidence: float
    width: int = 18
    height: int = 16
    id: str = ""


class BaseRecognizer(ABC):
    @abstractmethod
    async def recognize(self, image_path: str) -> list[Symbol]:
        """非同步辨識介面"""
        ...


class PlaceholderRecognizer(BaseRecognizer):
    """第一階段佔位實作；之後替換為實際 OMR 引擎。"""

    async def recognize(self, image_path: str) -> list[Symbol]:
        return [
            Symbol(
                id="sym-0",
                type="note",
                pitch=None,
                duration=None,
                x=0,
                y=0,
                width=18,
                height=16,
                confidence=0.0,
            )
        ]


def symbols_to_dict(symbols: list[Symbol]) -> list[dict]:
    return [asdict(symbol) for symbol in symbols]
