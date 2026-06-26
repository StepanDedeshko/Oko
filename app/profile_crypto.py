import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


ENCRYPTED_PROFILE_EXPORT_TYPE = "oko_profile_credentials_encrypted"
ENCRYPTED_PROFILE_EXPORT_VERSION = 1
KDF_NAME = "PBKDF2HMAC-SHA256"
KDF_ITERATIONS = 390_000
SALT_SIZE = 16


def _derive_key(password: str, salt: bytes) -> bytes:
    password = password or ""
    if not password:
        raise ValueError("Password is required")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_profile_payload(payload: dict, password: str) -> dict:
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    return {
        "type": ENCRYPTED_PROFILE_EXPORT_TYPE,
        "version": ENCRYPTED_PROFILE_EXPORT_VERSION,
        "kdf": KDF_NAME,
        "iterations": KDF_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
    }


def decrypt_profile_payload(encrypted_payload: dict, password: str) -> dict:
    if not isinstance(encrypted_payload, dict):
        raise ValueError("Invalid encrypted profile payload")

    if encrypted_payload.get("type") != ENCRYPTED_PROFILE_EXPORT_TYPE:
        raise ValueError("Unsupported encrypted profile type")

    if encrypted_payload.get("version") != ENCRYPTED_PROFILE_EXPORT_VERSION:
        raise ValueError("Unsupported encrypted profile version")

    try:
        salt = base64.b64decode(encrypted_payload.get("salt", "").encode("ascii"))
        token = encrypted_payload.get("token", "").encode("ascii")
    except Exception as exc:
        raise ValueError("Invalid encrypted profile data") from exc

    try:
        key = _derive_key(password, salt)
        raw = Fernet(key).decrypt(token)
        payload = json.loads(raw.decode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid profile password or corrupted file") from exc
    except Exception as exc:
        raise ValueError("Invalid encrypted profile data") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid decrypted profile payload")

    return payload
