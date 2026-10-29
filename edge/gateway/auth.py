from __future__ import annotations

import base64
from pathlib import Path
import secrets
import ssl
import time
from typing import Dict, Optional, Tuple
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
import jwt

from edge.config import GatewayConfig


class GatewayAuthenticator:
    """
    End-to-End Cryptographic Authentication for the Jetson Mobile Telemetry Bridge:
      - Issues cryptographic nonces (`challenge`) for mobile clients.
      - Verifies Ed25519 signatures over `device_id:nonce:timestamp` using registered
        mobile public keys.
      - Mints and verifies short-lived EdDSA (Ed25519) JWT access tokens.
      - Builds TLS 1.3 + optional mTLS `ssl.SSLContext` when server/CA certificates exist.
    """

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self._server_priv_key = Ed25519PrivateKey.generate()
        self._server_pub_key = self._server_priv_key.public_key()
        self._authorized_keys: Dict[str, Ed25519PublicKey] = {}
        self._active_challenges: Dict[str, Tuple[str, float]] = {}

        for dev_id, pub_pem_or_b64 in config.authorized_mobile_pubkeys.items():
            self.register_device_public_key(dev_id, pub_pem_or_b64)

    def register_device_public_key(self, device_id: str, pub_key_str: str) -> None:
        clean = pub_key_str.strip()
        if clean.startswith("-----BEGIN"):
            pub = serialization.load_pem_public_key(clean.encode("utf-8"))
        else:
            raw_bytes = base64.b64decode(clean)
            pub = Ed25519PublicKey.from_public_bytes(raw_bytes)
        if isinstance(pub, Ed25519PublicKey):
            self._authorized_keys[device_id] = pub

    def issue_challenge(self, device_id: str) -> str:
        nonce = secrets.token_hex(24)
        self._active_challenges[device_id] = (nonce, time.time() + 60.0)
        return nonce

    def verify_challenge_and_issue_jwt(
        self,
        device_id: str,
        nonce: str,
        signature_b64: str,
        public_key_b64: Optional[str] = None,
    ) -> Optional[str]:
        """
        Verifies the Ed25519 signature over `f"{device_id}:{nonce}"` and returns a signed
        short-lived EdDSA JWT token.
        """
        chall = self._active_challenges.pop(device_id, None)
        if chall is None:
            return None
        expected_nonce, exp_ts = chall
        if expected_nonce != nonce or time.time() > exp_ts:
            return None

        pub_key = self._authorized_keys.get(device_id)
        if pub_key is None and public_key_b64 and not self.config.authorized_mobile_pubkeys:
            # First-time TOFU registration when authorized_mobile_pubkeys is unpopulated
            self.register_device_public_key(device_id, public_key_b64)
            pub_key = self._authorized_keys.get(device_id)

        if pub_key is None:
            return None

        message = f"{device_id}:{nonce}".encode("ascii")
        try:
            sig_bytes = base64.b64decode(signature_b64)
            pub_key.verify(sig_bytes, message)
        except (InvalidSignature, ValueError):
            return None

        now = int(time.time())
        claims = {
            "sub": device_id,
            "iss": "jetson-orin-edge-gateway",
            "iat": now,
            "exp": now + self.config.jwt_ttl_seconds,
            "scope": "telemetry:read orders:write killswitch:execute",
        }
        return jwt.encode(claims, self._server_priv_key, algorithm="EdDSA")

    def verify_jwt(self, token: str) -> Optional[Dict[str, object]]:
        try:
            payload = jwt.decode(
                token,
                self._server_pub_key,
                algorithms=["EdDSA"],
                issuer="jetson-orin-edge-gateway",
            )
            return payload
        except Exception:
            return None

    def build_tls13_context(self) -> Optional[ssl.SSLContext]:
        cert_path = Path(self.config.tls_cert_path)
        key_path = Path(self.config.tls_key_path)
        if not (cert_path.exists() and key_path.exists()):
            return None

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

        ca_path = Path(self.config.mtls_ca_path)
        if ca_path.exists():
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(cafile=str(ca_path))
        return ctx
