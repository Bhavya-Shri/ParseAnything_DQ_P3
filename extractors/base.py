"""Shared extractor interface. P1 calls extract(); each engine implements this."""

from abc import ABC, abstractmethod

from extractors.schema_ref import load_schema

Block = load_schema().Block


class Extractor(ABC):
    name: str

    @abstractmethod
    def can_handle(self, region) -> bool:
        """True when this extractor can read the region."""

    @abstractmethod
    def extract(self, region, context) -> list[Block]:
        """Return blocks for one region. Do not raise for a bad read."""
