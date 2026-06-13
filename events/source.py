from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .signal import RawSignal, utc_now


@dataclass(frozen=True, slots=True)
class CLITextSignalSource:
    source: str = "cli_input"

    def create_signal(
        self,
        text: str,
        trace_id: str,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RawSignal:
        return RawSignal(
            trace_id=trace_id,
            source=self.source,
            timestamp=timestamp or utc_now(),
            payload={"text": text},
            signal_type="cli_text",
            metadata=metadata or {},
        )
