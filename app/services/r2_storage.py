"""
Cloudflare R2 (S3-compatible) Object Storage Service for DataPulse Curated Datasets.

Design goals:
  - Lightweight AWS Signature Version 4 (SigV4) client built on httpx + Python stdlib
    (no heavy botocore dependency, keeping Render Free memory footprint minimal).
  - Strictly environment-driven credentials; never commits or logs secrets.
  - Safe deterministic object-key generation preventing path traversal.
  - Gzip compression on upload and bounded decompression (gzip-bomb protection) on retrieval.
  - Mandatory SHA-256 checksum verification before any curated CSV is trusted or hydrated.
  - Bounded exponential-backoff retries for transient transport / 5xx errors.
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import hmac
import io
import logging
import re
import time
import urllib.parse
from typing import Any, Callable, Dict, Optional

import httpx

from app.config import settings
from app.services.storage import DATASET_ID_REGEX

logger = logging.getLogger(__name__)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SAFE_VERSION_RE = re.compile(r"^[a-zA-Z0-9._-]{1,32}$")
_SAFE_OBJECT_KEY_RE = re.compile(r"^curated/ds_[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+/[a-f0-9]{64}\.csv\.gz$")
_SAFE_COMMUNITY_OBJECT_KEY_RE = re.compile(r"^community/ds_[a-zA-Z0-9_-]+/[a-f0-9]{64}\.csv\.gz$")


class R2StorageError(Exception):
    """Base error for Cloudflare R2 object storage operations."""


class R2ConfigurationError(R2StorageError):
    """Raised when R2 endpoint, bucket, or credentials are missing or invalid."""


class R2ObjectNotFoundError(R2StorageError):
    """Raised when a requested curated object does not exist in R2."""


class R2ChecksumMismatchError(R2StorageError):
    """Raised when downloaded CSV bytes fail SHA-256 verification."""


class R2SizeLimitError(R2StorageError):
    """Raised when compressed or decompressed CSV payload exceeds hard bounds."""


def compute_sha256_bytes(data: bytes) -> str:
    """Compute lowercase hexadecimal SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def build_curated_object_key(
    dataset_id: str,
    sha256_checksum: str,
    source_version: str = "v1",
) -> str:
    """
    Generate a safe, immutable, traversal-proof R2 object key:
      curated/<dataset_id>/<source_version>/<sha256>.csv.gz
    """
    ds_id = (dataset_id or "").strip()
    digest = (sha256_checksum or "").strip().lower()
    ver = (source_version or "v1").strip()

    if not ds_id or len(ds_id) > 64 or not DATASET_ID_REGEX.match(ds_id):
        raise ValueError(f"Invalid dataset_id for object key: {dataset_id!r}")
    if not _SHA256_RE.match(digest):
        raise ValueError("Invalid SHA-256 checksum; expected 64 lowercase hex characters.")
    if not _SAFE_VERSION_RE.match(ver) or ".." in ver:
        raise ValueError(f"Invalid source_version for object key: {source_version!r}")

    key = f"curated/{ds_id}/{ver}/{digest}.csv.gz"
    if not _SAFE_OBJECT_KEY_RE.match(key):
        raise ValueError(f"Constructed object key failed safety validation: {key!r}")
    return key


def validate_curated_object_key(object_key: str) -> str:
    """Validate that an object key matches the strict curated namespace with no traversal."""
    cleaned = (object_key or "").strip().lstrip("/")
    if not cleaned or ".." in cleaned or not _SAFE_OBJECT_KEY_RE.match(cleaned):
        raise ValueError(f"Unsafe or malformed curated object key: {object_key!r}")
    return cleaned


def build_community_object_key(dataset_id: str, sha256_checksum: str) -> str:
    """
    Generate a safe, immutable, traversal-proof R2 object key for community uploads:
      community/<dataset_id>/<sha256>.csv.gz
    """
    ds_id = (dataset_id or "").strip()
    digest = (sha256_checksum or "").strip().lower()
    if not ds_id or len(ds_id) > 64 or not DATASET_ID_REGEX.match(ds_id):
        raise ValueError(f"Invalid dataset_id for community object key: {dataset_id!r}")
    if not _SHA256_RE.match(digest):
        raise ValueError("Invalid SHA-256 checksum; expected 64 lowercase hex characters.")
    key = f"community/{ds_id}/{digest}.csv.gz"
    if not _SAFE_COMMUNITY_OBJECT_KEY_RE.match(key):
        raise ValueError(f"Constructed community object key failed safety validation: {key!r}")
    return key


def validate_dataset_object_key(object_key: str) -> str:
    """Validate an object key in either the curated/ or community/ namespace with no traversal."""
    cleaned = (object_key or "").strip().lstrip("/")
    if not cleaned or ".." in cleaned:
        raise ValueError(f"Unsafe or malformed dataset object key: {object_key!r}")
    if _SAFE_OBJECT_KEY_RE.match(cleaned) or _SAFE_COMMUNITY_OBJECT_KEY_RE.match(cleaned):
        return cleaned
    raise ValueError(f"Unsafe or malformed dataset object key: {object_key!r}")


def compress_csv_bytes(csv_bytes: bytes) -> bytes:
    """Deterministically gzip-compress CSV bytes (mtime=0 for reproducible archives)."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=6, mtime=0) as gz:
        gz.write(csv_bytes)
    return buf.getvalue()


def decompress_csv_bytes(gz_bytes: bytes, max_uncompressed_bytes: int) -> bytes:
    """
    Safely decompress gzip bytes while enforcing a strict maximum uncompressed byte ceiling
    (defends against gzip bombs on memory-constrained hosts).
    """
    if max_uncompressed_bytes <= 0:
        raise R2SizeLimitError("Invalid maximum uncompressed byte limit.")
    out = bytearray()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(gz_bytes), mode="rb") as gz:
            while True:
                chunk = gz.read(65536)
                if not chunk:
                    break
                if len(out) + len(chunk) > max_uncompressed_bytes:
                    raise R2SizeLimitError(
                        f"Decompressed CSV exceeds hard size ceiling ({max_uncompressed_bytes} bytes)."
                    )
                out.extend(chunk)
    except R2SizeLimitError:
        raise
    except Exception as exc:
        raise R2StorageError(f"Failed to decompress gzip CSV object: {exc}") from exc
    return bytes(out)


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sign_sigv4_headers(
    method: str,
    endpoint_url: str,
    bucket: str,
    object_key: str,
    access_key_id: str,
    secret_access_key: str,
    region: str = "auto",
    payload: bytes = b"",
    extra_headers: Optional[Dict[str, str]] = None,
    now_utc: Optional[datetime.datetime] = None,
) -> tuple[str, Dict[str, str]]:
    """
    Build path-style S3/R2 URL and AWS Signature Version 4 headers.
    Never logs or embeds secret keys in the returned headers.
    """
    parsed = urllib.parse.urlparse(endpoint_url.rstrip("/"))
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise R2ConfigurationError("R2_ENDPOINT_URL must be a valid HTTP(S) URL.")

    dt = now_utc or datetime.datetime.now(datetime.timezone.utc)
    amz_date = dt.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = dt.strftime("%Y%m%d")

    encoded_bucket = urllib.parse.quote(bucket, safe="")
    encoded_key = urllib.parse.quote(object_key.lstrip("/"), safe="/-_.~")
    base_path = parsed.path.rstrip("/")
    canonical_uri = f"{base_path}/{encoded_bucket}/{encoded_key}"
    full_url = f"{parsed.scheme}://{parsed.netloc}{canonical_uri}"

    payload_hash = hashlib.sha256(payload).hexdigest()

    headers_to_sign: Dict[str, str] = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if extra_headers:
        for k, v in extra_headers.items():
            headers_to_sign[k.lower().strip()] = str(v).strip()

    sorted_header_keys = sorted(headers_to_sign.keys())
    canonical_headers = "".join(f"{k}:{headers_to_sign[k]}\n" for k in sorted_header_keys)
    signed_headers = ";".join(sorted_header_keys)

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    k_date = _hmac_sha256(("AWS4" + secret_access_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, "s3")
    k_signing = _hmac_sha256(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    out_headers = {k: v for k, v in headers_to_sign.items() if k != "host"}
    out_headers["Authorization"] = authorization
    return full_url, out_headers


class R2StorageClient:
    """
    S3-compatible Cloudflare R2 client for curated dataset `.csv.gz` objects.
    Accepts an optional httpx transport for deterministic offline unit testing.
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        bucket_name: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.endpoint_url = (endpoint_url if endpoint_url is not None else settings.R2_ENDPOINT_URL) or ""
        self.bucket_name = (bucket_name if bucket_name is not None else settings.R2_BUCKET_NAME) or ""
        self.access_key_id = (access_key_id if access_key_id is not None else settings.R2_ACCESS_KEY_ID) or ""
        self.secret_access_key = (
            secret_access_key if secret_access_key is not None else settings.R2_SECRET_ACCESS_KEY
        ) or ""
        self.region = (region if region is not None else settings.R2_REGION) or "auto"
        self.timeout_seconds = max(1, int(timeout_seconds or settings.R2_TIMEOUT_SECONDS or 30))
        self.max_retries = max(1, int(max_retries or settings.R2_MAX_RETRIES or 3))
        self._transport = transport
        self._sleep = sleep_fn

    @property
    def is_configured(self) -> bool:
        return bool(
            self.endpoint_url.strip()
            and self.bucket_name.strip()
            and self.access_key_id.strip()
            and self.secret_access_key.strip()
        )

    def _require_configured(self) -> None:
        missing = []
        if not self.endpoint_url.strip():
            missing.append("R2_ENDPOINT_URL")
        if not self.bucket_name.strip():
            missing.append("R2_BUCKET_NAME")
        if not self.access_key_id.strip():
            missing.append("R2_ACCESS_KEY_ID")
        if not self.secret_access_key.strip():
            missing.append("R2_SECRET_ACCESS_KEY")
        if missing:
            raise R2ConfigurationError(
                f"Cloudflare R2 storage is not configured. Missing environment variable(s): {', '.join(missing)}."
            )

    def _send_with_retries(
        self,
        method: str,
        object_key: str,
        payload: bytes = b"",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        self._require_configured()
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            url, headers = _sign_sigv4_headers(
                method=method,
                endpoint_url=self.endpoint_url,
                bucket=self.bucket_name,
                object_key=object_key,
                access_key_id=self.access_key_id,
                secret_access_key=self.secret_access_key,
                region=self.region,
                payload=payload,
                extra_headers=extra_headers,
            )
            try:
                with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
                    resp = client.request(method=method, url=url, headers=headers, content=payload if payload else None)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("R2 %s %s transient error (attempt %d/%d): %s", method, object_key, attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    self._sleep(min(2.0, 0.25 * (2 ** (attempt - 1))))
                    continue
                raise R2StorageError(f"R2 request failed after {self.max_retries} attempts: {exc}") from exc

            if resp.status_code == 404:
                raise R2ObjectNotFoundError(f"R2 object not found: {object_key}")
            if resp.status_code in (401, 403):
                raise R2ConfigurationError(f"R2 rejected credentials or bucket permissions (HTTP {resp.status_code}).")
            if resp.status_code >= 500 or resp.status_code == 429:
                last_exc = R2StorageError(f"R2 server returned HTTP {resp.status_code} for {object_key}")
                logger.warning("R2 %s %s returned HTTP %d (attempt %d/%d)", method, object_key, resp.status_code, attempt, self.max_retries)
                if attempt < self.max_retries:
                    self._sleep(min(2.0, 0.25 * (2 ** (attempt - 1))))
                    continue
                raise last_exc
            if resp.status_code >= 400:
                raise R2StorageError(f"R2 request failed with HTTP {resp.status_code} for {object_key}")
            return resp

        raise R2StorageError(f"R2 request failed: {last_exc}")

    def upload_compressed_csv(
        self,
        dataset_id: str,
        csv_bytes: bytes,
        source_version: str = "v1",
        max_uncompressed_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validate size bounds, compute SHA-256 of raw CSV bytes, gzip-compress,
        and upload to R2 under a safe deterministic object key.
        """
        hard_limit = max_uncompressed_bytes or (max(1, int(settings.CURATED_HARD_MAX_MB)) * 1024 * 1024)
        if not csv_bytes:
            raise ValueError("Cannot upload empty CSV payload to R2.")
        if len(csv_bytes) > hard_limit:
            raise R2SizeLimitError(
                f"CSV payload ({len(csv_bytes)} bytes) exceeds hard ceiling ({hard_limit} bytes)."
            )

        sha256_hex = compute_sha256_bytes(csv_bytes)
        object_key = build_curated_object_key(
            dataset_id=dataset_id,
            sha256_checksum=sha256_hex,
            source_version=source_version,
        )
        gz_payload = compress_csv_bytes(csv_bytes)

        self._send_with_retries(
            method="PUT",
            object_key=object_key,
            payload=gz_payload,
            extra_headers={
                "content-type": "application/gzip",
                "x-amz-meta-sha256": sha256_hex,
                "x-amz-meta-dataset-id": dataset_id,
            },
        )
        return {
            "object_storage_key": object_key,
            "sha256_checksum": sha256_hex,
            "csv_bytes": len(csv_bytes),
            "compressed_bytes": len(gz_payload),
        }

    def upload_community_csv(
        self,
        dataset_id: str,
        csv_bytes: bytes,
        max_uncompressed_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validate size bounds, compute SHA-256 of raw CSV bytes, gzip-compress,
        and persist a community-uploaded CSV to Cloudflare R2 under community/<id>/<sha256>.csv.gz.
        """
        hard_limit = max_uncompressed_bytes or settings.max_upload_bytes
        if not csv_bytes:
            raise ValueError("Cannot upload empty CSV payload to R2.")
        if len(csv_bytes) > hard_limit:
            raise R2SizeLimitError(
                f"CSV payload ({len(csv_bytes)} bytes) exceeds hard ceiling ({hard_limit} bytes)."
            )

        sha256_hex = compute_sha256_bytes(csv_bytes)
        object_key = build_community_object_key(dataset_id=dataset_id, sha256_checksum=sha256_hex)
        gz_payload = compress_csv_bytes(csv_bytes)

        self._send_with_retries(
            method="PUT",
            object_key=object_key,
            payload=gz_payload,
            extra_headers={
                "content-type": "application/gzip",
                "x-amz-meta-sha256": sha256_hex,
                "x-amz-meta-dataset-id": dataset_id,
                "x-amz-meta-dataset-type": "community",
            },
        )
        return {
            "object_storage_key": object_key,
            "sha256_checksum": sha256_hex,
            "csv_bytes": len(csv_bytes),
            "compressed_bytes": len(gz_payload),
        }

    def delete_object(self, object_storage_key: str) -> None:
        """Delete a validated dataset object from R2 (used for atomic upload rollbacks)."""
        safe_key = validate_dataset_object_key(object_storage_key)
        try:
            self._send_with_retries(method="DELETE", object_key=safe_key)
        except R2ObjectNotFoundError:
            return

    def download_and_verify_csv(
        self,
        object_storage_key: str,
        expected_sha256: str,
        max_uncompressed_bytes: Optional[int] = None,
    ) -> bytes:
        """
        Retrieve a `.csv.gz` object from R2 (curated or community), safely decompress with bounded memory,
        and verify its raw SHA-256 digest matches `expected_sha256` in constant time.
        """
        safe_key = validate_dataset_object_key(object_storage_key)
        clean_expected = (expected_sha256 or "").strip().lower()
        if not _SHA256_RE.match(clean_expected):
            raise R2ChecksumMismatchError("Invalid expected SHA-256 checksum on dataset metadata.")

        hard_limit = max_uncompressed_bytes or (max(1, int(settings.CURATED_HARD_MAX_MB)) * 1024 * 1024)
        resp = self._send_with_retries(method="GET", object_key=safe_key)
        compressed_bytes = resp.content
        if len(compressed_bytes) > hard_limit:
            raise R2SizeLimitError(
                f"Compressed object ({len(compressed_bytes)} bytes) exceeds hard ceiling ({hard_limit} bytes)."
            )

        csv_bytes = decompress_csv_bytes(compressed_bytes, max_uncompressed_bytes=hard_limit)
        actual_sha256 = compute_sha256_bytes(csv_bytes)
        if not hmac.compare_digest(actual_sha256, clean_expected):
            raise R2ChecksumMismatchError(
                f"SHA-256 checksum verification failed for '{safe_key}': expected {clean_expected[:12]}..., got {actual_sha256[:12]}..."
            )
        return csv_bytes

