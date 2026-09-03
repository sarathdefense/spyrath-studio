from __future__ import annotations
import os
from .accounts import AccountStore
from .security import AccessController, SecurityConfig

def create_access_controller(metadata_db, enabled: bool) -> AccessController:
    accounts=AccountStore(metadata_db)
    bootstrap=os.getenv('SPYRATH_BOOTSTRAP_API_KEY')
    if enabled and bootstrap:
        accounts.ensure_user(os.getenv('SPYRATH_BOOTSTRAP_USER','admin'), os.getenv('SPYRATH_BOOTSTRAP_NAME','Spyrath Admin'), bootstrap)
    return AccessController(accounts, SecurityConfig(enabled=enabled))
