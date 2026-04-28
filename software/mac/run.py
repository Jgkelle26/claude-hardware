"""Run the Clod Mac-side orchestrator."""
from __future__ import annotations

import asyncio

from mac.orchestrator import ClodOrchestrator


def main() -> None:
    print("Clod Mac Orchestrator")
    print("Press Enter to speak, Ctrl+C to quit.")
    print()
    orchestrator = ClodOrchestrator()
    asyncio.run(orchestrator.run())


if __name__ == "__main__":
    main()
