"""Engine factory for the API layer.

api/ may not import moneyflow.store (enforced by tests/test_architecture.py);
services own all store access, so the engine factory is re-exported here.
No SQL lives in this module.
"""

from moneyflow.store.db import get_engine

__all__ = ["get_engine"]
