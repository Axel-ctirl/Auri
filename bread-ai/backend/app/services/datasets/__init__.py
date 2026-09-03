"""Dataset collection, cleaning, validation and reporting."""

from .collect import (
    EXTERNAL_SOURCES,
    LANGUAGE_EXTENSIONS,
    SUPPORTED_LANGUAGES,
    CollectionOptions,
    TermsNotAcceptedError,
    collect_huggingface,
    collect_local_code,
    collect_local_english,
)
from .licenses import DEFAULT_ALLOWED_LICENSES, detect_repository_license, is_allowed
from .manifest import DatasetManifest, standard_warnings
from .quality import build_report, clean_file, clean_records, dedupe_records, validate_file
from .records import (
    RecordMeta,
    make_chat_record,
    make_text_record,
    read_jsonl,
    record_text,
    write_jsonl,
)
from .secrets import contains_secret, redact, scan_text

__all__ = [
    "DEFAULT_ALLOWED_LICENSES",
    "EXTERNAL_SOURCES",
    "LANGUAGE_EXTENSIONS",
    "SUPPORTED_LANGUAGES",
    "CollectionOptions",
    "DatasetManifest",
    "RecordMeta",
    "TermsNotAcceptedError",
    "build_report",
    "clean_file",
    "clean_records",
    "collect_huggingface",
    "collect_local_code",
    "collect_local_english",
    "contains_secret",
    "dedupe_records",
    "detect_repository_license",
    "is_allowed",
    "make_chat_record",
    "make_text_record",
    "read_jsonl",
    "record_text",
    "redact",
    "scan_text",
    "standard_warnings",
    "validate_file",
    "write_jsonl",
]
