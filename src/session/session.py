from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Valid end_reason values for a closed session (see docs/realtime-reader/rules.md).
END_REASON_LEFT = "left"
END_REASON_SHIFT_END = "shift_end"
END_REASON_SIGNAL_LOST = "signal_lost"
END_REASON_ERROR = "error"


# One completed presence session for a single machine.
@dataclass(frozen=True, slots=True)
class Session:
    machine_id: str
    session_date: str
    start_time: datetime
    end_time: datetime
    duration_min: float
    end_reason: str
