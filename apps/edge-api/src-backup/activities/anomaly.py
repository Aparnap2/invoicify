"""
Anomaly Detection Implementation (TDD - Step 3)
Fixed: CodeRabbit review issues - security, DRY, error handling
"""

import pickle
import logging
from typing import Optional
from pathlib import Path
from functools import lru_cache

from river import anomaly
from temporalio import activity

logger = logging.getLogger(__name__)


class COSConfigError(Exception):
    """Raised when COS configuration is invalid."""

    pass


class AnomalyDetector:
    """
    Anomaly detector using River ML HalfSpaceTrees.

    Provides online learning for invoice amount anomaly detection.
    Models can be persisted to IBM COS for vendor-specific learning.
    """

    def __init__(self, vendor_id: str, threshold: float = 0.7) -> None:
        """
        Initialize detector.

        Args:
            vendor_id: Unique vendor identifier
            threshold: Anomaly threshold (default 0.7)

        Raises:
            ValueError: If vendor_id is empty or threshold is invalid
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise ValueError("vendor_id must be a non-empty string")
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")

        self.vendor_id: str = vendor_id
        self.threshold: float = threshold
        self.model: Optional[anomaly.HalfSpaceTrees] = None
        self._init_model()

    def _init_model(self) -> None:
        """Initialize the River ML model."""
        if self.model is None:
            self.model = anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=100)
            logger.debug(f"Initialized model for vendor: {self.vendor_id}")

    def _ensure_model(self) -> None:
        """Ensure model is initialized."""
        if self.model is None:
            self._init_model()

    def score(self, amount: float) -> float:
        """
        Get anomaly score for an amount.

        Args:
            amount: Invoice amount to score

        Returns:
            Anomaly score between 0.0 (normal) and 1.0 (anomalous)

        Raises:
            ValueError: If amount is negative
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")

        self._ensure_model()
        features = {"amount": amount}
        score = self.model.score_one(features)

        logger.debug(f"Scored amount {amount} for {self.vendor_id}: {score:.4f}")
        return score

    def learn(self, amount: float) -> None:
        """
        Learn from an invoice amount (online learning).

        Args:
            amount: Invoice amount to learn from

        Raises:
            ValueError: If amount is negative
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")

        self._ensure_model()
        features = {"amount": amount}
        self.model.learn_one(features)

        logger.debug(f"Learned amount {amount} for vendor: {self.vendor_id}")

    def is_anomaly(self, amount: float) -> bool:
        """
        Check if amount is anomalous.

        Args:
            amount: Invoice amount to check

        Returns:
            True if amount is anomalous, False otherwise
        """
        score = self.score(amount)
        is_anom = score > self.threshold

        if is_anom:
            logger.warning(
                f"Anomaly detected for {self.vendor_id}: "
                f"amount={amount}, score={score:.4f}"
            )

        return is_anom

    def save(self, filepath: str) -> None:
        """
        Save model to local file.

        Args:
            filepath: Path to save pickle file

        Raises:
            ValueError: If no model to save
            IOError: If file cannot be written
        """
        if self.model is None:
            raise ValueError("No model to save")

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "wb") as f:
                pickle.dump(self.model, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info(f"Saved model for {self.vendor_id} to {filepath}")
        except IOError as e:
            logger.error(f"Failed to save model: {e}")
            raise

    def load(self, filepath: str) -> None:
        """
        Load model from local file.

        Args:
            filepath: Path to load pickle file from

        Raises:
            FileNotFoundError: If file doesn't exist
            pickle.UnpicklingError: If file is corrupted
        """
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")

        try:
            with open(path, "rb") as f:
                self.model = pickle.load(f)
            logger.info(f"Loaded model for {self.vendor_id} from {filepath}")
        except pickle.UnpicklingError as e:
            logger.error(f"Failed to load model (corrupted file): {e}")
            raise

    def _get_cos_client(self):
        """
        Get IBM COS client from environment variables.

        Returns:
            boto3 S3 client

        Raises:
            COSConfigError: If required environment variables are not set
        """
        import boto3
        from botocore.config import Config

        api_key = (
            Path("/run/secrets/ibm_api_key").read_text().strip()
            if Path("/run/secrets/ibm_api_key").exists()
            else None
        )

        if not api_key:
            api_key = __import__("os").getenv("IBM_CLOUD_API_KEY")

        if not api_key:
            raise COSConfigError(
                "IBM_CLOUD_API_KEY not found in environment or secrets"
            )

        instance_id = __import__("os").getenv("IBM_COS_INSTANCE_ID", "default")
        endpoint = __import__("os").getenv(
            "IBM_COS_ENDPOINT",
            "https://s3.us-south.cloud-object-storage.appdomain.cloud",
        )

        return boto3.client(
            service_name="s3",
            ibm_api_key_id=api_key,
            ibm_service_instance_id=instance_id,
            config=Config(signature_version="oauth"),
            endpoint_url=endpoint,
        )

    async def save_to_cos(self, bucket: str) -> None:
        """
        Save model to IBM COS.

        Args:
            bucket: COS bucket name

        Raises:
            COSConfigError: If COS is not configured
            RuntimeError: If upload fails
        """
        if self.model is None:
            raise ValueError("No model to save")

        try:
            cos_client = self._get_cos_client()

            # Serialize model
            model_bytes = pickle.dumps(self.model, protocol=pickle.HIGHEST_PROTOCOL)

            # Upload to COS
            key = f"ml-models/{self.vendor_id}.pkl"
            cos_client.put_object(Bucket=bucket, Key=key, Body=model_bytes)

            logger.info(f"Saved model for {self.vendor_id} to COS: {bucket}/{key}")

        except COSConfigError:
            raise
        except Exception as e:
            logger.error(f"Failed to save model to COS: {e}")
            raise RuntimeError(f"Failed to save model to COS: {e}") from e

    async def load_from_cos(self, bucket: str) -> None:
        """
        Load model from IBM COS.

        Args:
            bucket: COS bucket name

        Raises:
            COSConfigError: If COS is not configured
            RuntimeError: If download fails
        """
        try:
            cos_client = self._get_cos_client()

            key = f"ml-models/{self.vendor_id}.pkl"

            response = cos_client.get_object(Bucket=bucket, Key=key)
            model_bytes = response["Body"].read()

            self.model = pickle.loads(model_bytes)

            logger.info(f"Loaded model for {self.vendor_id} from COS: {bucket}/{key}")

        except COSConfigError:
            raise
        except Exception as e:
            logger.error(f"Failed to load model from COS: {e}")
            raise RuntimeError(f"Failed to load model from COS: {e}") from e


# Standalone activity functions for Temporal
_default_detector = None


def _get_default_detector() -> AnomalyDetector:
    """Get or create default anomaly detector."""
    global _default_detector
    if _default_detector is None:
        _default_detector = AnomalyDetector(vendor_id="default")
    return _default_detector


@activity.defn
async def detect_anomaly_activity(amount: float) -> float:
    """
    Temporal activity to detect anomaly.

    Args:
        amount: Invoice amount to score

    Returns:
        Anomaly score between 0.0 and 1.0
    """
    detector = _get_default_detector()
    return detector.score(amount)


@activity.defn
async def learn_anomaly_activity(amount: float) -> None:
    """
    Temporal activity to learn from invoice amount.

    Args:
        amount: Invoice amount to learn from
    """
    detector = _get_default_detector()
    detector.learn(amount)
