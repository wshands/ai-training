
"""Training job runner that delegates to customer code."""

import asyncio
import sys

from customer.train import run_training
from runtime import run_training_job, setup_logging


def main() -> int:
    setup_logging()
    return asyncio.run(run_training_job(run_training))


if __name__ == "__main__":
    sys.exit(main())
