"""Secret storage abstraction with Windows Credential Manager backend.

Uses `pywin32`'s `win32cred` module to talk to the Windows Credential Manager.
Secrets are stored as generic credentials with TargetName
"feishu-bot-claude-win:<key>" so they don't collide with other apps.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class KeychainStore(ABC):
    """Abstract secret store. Backed by Windows Credential Manager in production."""

    @abstractmethod
    def put(self, key: str, secret: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class InMemoryKeychainStore(KeychainStore):
    """In-memory store for tests. Not persistent, not secure."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def put(self, key: str, secret: str) -> None:
        self._data[key] = secret

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class WindowsCredentialStore(KeychainStore):
    """Windows Credential Manager backend via pywin32 `win32cred`.

    Each binding's app-secret lives under a TargetName of
    `feishu-bot-claude-win:<key>`. Secret is stored as UTF-16-LE bytes in the
    CredentialBlob field (this is what `win32cred` expects).
    """

    def __init__(self, target_prefix: str = "feishu-bot-claude-win") -> None:
        self._prefix = target_prefix

    def _target(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def put(self, key: str, secret: str) -> None:
        import win32cred  # imported lazily so tests can run without pywin32 on macOS dev hosts
        cred = {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": self._target(key),
            "UserName": key,
            "CredentialBlob": secret,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }
        win32cred.CredWrite(cred, 0)

    def get(self, key: str) -> str | None:
        import win32cred
        try:
            cred = win32cred.CredRead(
                Type=win32cred.CRED_TYPE_GENERIC,
                TargetName=self._target(key),
            )
        except Exception as e:
            # win32cred raises win32.error with winerror 1168 ERROR_NOT_FOUND.
            winerror = getattr(e, "winerror", None)
            if winerror == 1168:
                return None
            raise
        blob = cred.get("CredentialBlob")
        if blob is None:
            return None
        # Windows returns bytes; pywin32 stores strings as UTF-16-LE.
        if isinstance(blob, bytes):
            try:
                return blob.decode("utf-16-le")
            except UnicodeDecodeError:
                return blob.decode("utf-8", errors="replace")
        return str(blob)

    def delete(self, key: str) -> None:
        import win32cred
        try:
            win32cred.CredDelete(
                TargetName=self._target(key),
                Type=win32cred.CRED_TYPE_GENERIC,
            )
        except Exception as e:
            winerror = getattr(e, "winerror", None)
            if winerror == 1168:  # ERROR_NOT_FOUND
                return
            raise
