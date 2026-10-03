"""Per-instance Bridge credentials (TODO 929e730). See
plans/bridge-per-instance-credentials.md and design-docs/isolation.md.

Before this, every Bridge caller shared one per-launch token and *claimed* its
identity in request headers, so a widget could assert another's identity. Now
each placed instance (and each hmsvc service) gets its own token and the server
maps token -> identity itself. Qt-free and thread-safe (the middleware runs on
the server thread, the window issues/revokes on the GUI thread).
"""
import secrets
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    widget_id: str
    instance_id: str


class CredentialRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_token: dict[str, Identity] = {}
        self._token_by_instance: dict[str, str] = {}

    def issue(self, widget_id: str, instance_id: str) -> str:
        """A fresh token bound to this instance; re-issuing for the same
        instance revokes its previous token."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            previous = self._token_by_instance.pop(instance_id, None)
            if previous is not None:
                self._by_token.pop(previous, None)
            self._by_token[token] = Identity(widget_id, instance_id)
            self._token_by_instance[instance_id] = token
        return token

    def issue_service(self, name: str) -> str:
        """A token for hmsvc service `name`, acting as the synthetic caller id
        `hmsvc:<name>` (also its mediator instance id)."""
        caller = f"hmsvc:{name}"
        return self.issue(caller, caller)

    def lookup(self, token: str | None) -> Identity | None:
        if not token:
            return None
        with self._lock:
            return self._by_token.get(token)

    def revoke_instance(self, instance_id: str) -> bool:
        with self._lock:
            token = self._token_by_instance.pop(instance_id, None)
            if token is None:
                return False
            self._by_token.pop(token, None)
            return True

    def revoke_service(self, name: str) -> bool:
        return self.revoke_instance(f"hmsvc:{name}")

    def revoke_all_widget_instances(self) -> int:
        """Revokes every non-service credential (a Desk switch clears the
        canvas); hmsvc credentials are managed by their own start/stop."""
        with self._lock:
            doomed = [i for i in self._token_by_instance if not i.startswith("hmsvc:")]
            for instance_id in doomed:
                self._by_token.pop(self._token_by_instance.pop(instance_id), None)
            return len(doomed)

    def active_count(self) -> int:
        with self._lock:
            return len(self._by_token)
