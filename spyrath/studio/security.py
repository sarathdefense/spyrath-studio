from __future__ import annotations
from dataclasses import dataclass
from .accounts import AccountStore, User

@dataclass(frozen=True)
class SecurityConfig:
    enabled: bool = False
    api_key_header: str = 'X-Spyrath-Key'

class AccessController:
    def __init__(self, accounts: AccountStore, config: SecurityConfig): self.accounts=accounts; self.config=config
    def authenticate(self, key: str | None) -> User:
        if not self.config.enabled: return User('local','Local User')
        user=self.accounts.authenticate(key)
        if user is None: raise PermissionError('Authentication required')
        return user
    def require_project(self, project_id:str, user:User)->None:
        if self.config.enabled and not self.accounts.owns(project_id,user.user_id): raise PermissionError('Project not found')
