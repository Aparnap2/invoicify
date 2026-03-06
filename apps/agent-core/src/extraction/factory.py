"""Extractor factory based on EXTRACTOR_MODE.

This module provides a single import point to get the appropriate
invoice extractor based on the EXTRACTOR_MODE environment variable.

Supported modes:
    - fixture: Hardcoded test data (fastest, for CI/queue testing)
    - azure_di: Azure Document Intelligence (production)
    - sarvam: Sarvam OCR API (production alternative)
    - ollama: Local Ollama models (local dev only)

Usage:
    from src.extraction.factory import get_extractor
    
    extractor = get_extractor()
    result = await extractor.extract("/path/to/invoice.pdf", "INV-123")

Environment Variables:
    EXTRACTOR_MODE: One of 'fixture', 'azure_di', 'sarvam', 'ollama'
                    (default: 'azure_di')
    
    For azure_di mode:
        - AZURE_DI_ENDPOINT: Azure Document Intelligence endpoint
        - AZURE_DI_KEY: Azure Document Intelligence API key
    
    For sarvam mode:
        - SARVAM_AI_API_KEY: Sarvam API subscription key
"""

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Valid extractor modes
VALID_MODES = {"fixture", "azure_di", "sarvam", "ollama"}


def _validate_azure_credentials() -> None:
    """Validate Azure Document Intelligence credentials.
    
    Raises:
        ValueError: If required Azure credentials are missing.
    
    Required environment variables:
        - AZURE_DI_ENDPOINT (or AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT)
        - AZURE_DI_KEY (or AZURE_DOCUMENT_INTELLIGENCE_KEY)
    """
    # Support both naming conventions
    endpoint_vars = ["AZURE_DI_ENDPOINT", "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
    key_vars = ["AZURE_DI_KEY", "AZURE_DOCUMENT_INTELLIGENCE_KEY"]
    
    endpoint = next((os.getenv(var) for var in endpoint_vars if os.getenv(var)), None)
    key = next((os.getenv(var) for var in key_vars if os.getenv(var)), None)
    
    missing = []
    if not endpoint:
        missing.append(f"{endpoint_vars[0]} (or {endpoint_vars[1]})")
    if not key:
        missing.append(f"{key_vars[0]} (or {key_vars[1]})")
    
    if missing:
        logger.error(
            "azure_credentials_missing",
            missing_vars=missing,
        )
        raise ValueError(
            f"EXTRACTOR_MODE=azure_di requires: {', '.join(missing)}"
        )
    
    logger.debug("azure_credentials_validated")


def _validate_sarvam_credentials() -> None:
    """Validate Sarvam OCR credentials.
    
    Raises:
        ValueError: If required Sarvam credentials are missing.
    
    Required environment variables:
        - SARVAM_AI_API_KEY (or SARVAM_API_KEY)
    """
    # Support both naming conventions
    key_vars = ["SARVAM_AI_API_KEY", "SARVAM_API_KEY"]
    
    api_key = next((os.getenv(var) for var in key_vars if os.getenv(var)), None)
    
    if not api_key:
        logger.error(
            "sarvam_credentials_missing",
            missing_vars=key_vars,
        )
        raise ValueError(
            f"EXTRACTOR_MODE=sarvam requires: {key_vars[0]} (or {key_vars[1]})"
        )
    
    logger.debug("sarvam_credentials_validated")


def get_extractor() -> Any:
    """Get invoice extractor based on EXTRACTOR_MODE env var.
    
    Routes to the appropriate extractor implementation based on the
    EXTRACTOR_MODE environment variable. Validates credentials before
    returning production extractors.
    
    Returns:
        Extractor instance with .extract(file_path, invoice_id) method.
        The extractor mode is set appropriately for the selected backend.
    
    Raises:
        ValueError: If EXTRACTOR_MODE is invalid or required env vars missing.
    
    Example:
        >>> import os
        >>> os.environ["EXTRACTOR_MODE"] = "azure_di"
        >>> extractor = get_extractor()
        >>> result = await extractor.extract("invoice.pdf", "INV-123")
    """
    mode = os.getenv("EXTRACTOR_MODE", "azure_di").lower()
    
    logger.info("extractor_factory_called", requested_mode=mode)
    
    # Validate mode
    if mode not in VALID_MODES:
        logger.error(
            "invalid_extractor_mode",
            requested_mode=mode,
            valid_modes=sorted(VALID_MODES),
        )
        raise ValueError(
            f"Invalid EXTRACTOR_MODE: '{mode}'. "
            f"Valid modes are: {', '.join(sorted(VALID_MODES))}"
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # FIXTURE MODE
    # ─────────────────────────────────────────────────────────────────────────
    if mode == "fixture":
        logger.info("extractor_mode_fixture", validation_skipped=True)
        from .sarvam_extractor import InvoiceExtractor
        
        extractor = InvoiceExtractor()
        extractor.mode = "fixture"
        logger.info("fixture_extractor_created")
        return extractor
    
    # ─────────────────────────────────────────────────────────────────────────
    # AZURE DOCUMENT INTELLIGENCE MODE
    # ─────────────────────────────────────────────────────────────────────────
    elif mode == "azure_di":
        logger.info("extractor_mode_azure_di", validating_credentials=True)
        _validate_azure_credentials()
        
        from .azure_extractor import AzureDocumentIntelligenceExtractor
        
        extractor = AzureDocumentIntelligenceExtractor()
        logger.info("azure_extractor_created")
        return extractor
    
    # ─────────────────────────────────────────────────────────────────────────
    # SARVAM OCR MODE
    # ─────────────────────────────────────────────────────────────────────────
    elif mode == "sarvam":
        logger.info("extractor_mode_sarvam", validating_credentials=True)
        _validate_sarvam_credentials()
        
        from .sarvam_extractor import InvoiceExtractor
        
        extractor = InvoiceExtractor()
        logger.info("sarvam_extractor_created")
        return extractor
    
    # ─────────────────────────────────────────────────────────────────────────
    # OLLAMA LOCAL MODE
    # ─────────────────────────────────────────────────────────────────────────
    elif mode == "ollama":
        logger.info("extractor_mode_ollama", validation_skipped=True)
        from .sarvam_extractor import InvoiceExtractor
        
        extractor = InvoiceExtractor()
        extractor.mode = "ollama"
        logger.info("ollama_extractor_created")
        return extractor
    
    # This should never be reached due to validation above
    raise ValueError(f"Unhandled EXTRACTOR_MODE: {mode}")


def get_available_modes() -> set[str]:
    """Get the set of valid extractor modes.
    
    Returns:
        Set of valid mode strings.
    """
    return VALID_MODES.copy()


def get_current_mode() -> str:
    """Get the current EXTRACTOR_MODE from environment.
    
    Returns:
        Current mode string (default: 'azure_di' if not set).
    """
    return os.getenv("EXTRACTOR_MODE", "azure_di").lower()
