"""Anomaly detection activity using River ML."""

import os
import pickle
import logging
from typing import Optional

import ibm_boto3
import boto3
from ibm_botocore.config import Config
from river import anomaly

logger = logging.getLogger(__name__)


async def detect_anomaly(amount: float, vendor_id: str) -> dict:
    """
    Detect if invoice amount is anomalous for vendor using River ML.

    Args:
        amount: Invoice amount
        vendor_id: Vendor identifier

    Returns:
        Dict with score, is_anomaly flag, and vendor_id
    """
    try:
        # Load existing model or create new one
        model = await load_model(vendor_id)
        if model is None:
            logger.info(f"Creating new anomaly model for vendor: {vendor_id}")
            model = anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=100)

        # Create feature vector
        features = {"amount": amount}

        # Get anomaly score
        score = model.score_one(features)

        # Learn from this observation (online learning)
        model.learn_one(features)

        # Persist updated model
        await save_model(vendor_id, model)

        # Determine if anomaly
        is_anomaly = score > 0.7

        logger.info(
            f"Anomaly detection for {vendor_id}: "
            f"amount={amount}, score={score:.4f}, is_anomaly={is_anomaly}"
        )

        return {"score": score, "is_anomaly": is_anomaly, "vendor_id": vendor_id}

    except Exception as e:
        logger.error(f"Error in anomaly detection: {e}")
        raise


async def load_model(vendor_id: str) -> Optional[anomaly.HalfSpaceTrees]:
    """
    Load River ML model from storage (IBM COS or DigitalOcean Spaces).

    Args:
        vendor_id: Vendor identifier

    Returns:
        Loaded model or None if not found
    """
    try:
        storage_client = _get_storage_client()
        bucket = _get_storage_bucket()
        key = f"ml-models/{vendor_id}.pkl"

        response = storage_client.get_object(Bucket=bucket, Key=key)
        model_bytes = response["Body"].read()
        model = pickle.loads(model_bytes)

        logger.debug(f"Loaded model for vendor: {vendor_id}")
        return model

    except Exception as e:
        # Handle NoSuchKey and other errors gracefully
        error_msg = str(e).lower()
        if "nosuchkey" in error_msg or "not found" in error_msg:
            logger.debug(f"No existing model for vendor: {vendor_id}")
            return None
        logger.error(f"Error loading model: {e}")
        return None


async def save_model(vendor_id: str, model: anomaly.HalfSpaceTrees) -> None:
    """
    Save River ML model to storage (IBM COS or DigitalOcean Spaces).

    Args:
        vendor_id: Vendor identifier
        model: Trained model to save
    """
    try:
        storage_client = _get_storage_client()
        bucket = _get_storage_bucket()
        key = f"ml-models/{vendor_id}.pkl"

        # Serialize model
        model_bytes = pickle.dumps(model)

        # Upload to storage
        storage_client.put_object(Bucket=bucket, Key=key, Body=model_bytes)

        logger.debug(f"Saved model for vendor: {vendor_id}")

    except Exception as e:
        logger.error(f"Error saving model: {e}")
        raise


def _get_storage_client():
    """
    Get storage client (IBM COS or DigitalOcean Spaces).
    
    Returns:
        S3-compatible client
    """
    # Check if DigitalOcean Spaces is configured
    if os.getenv("DO_SPACES_ENDPOINT"):
        return _get_do_spaces_client()
    else:
        return _get_ibm_cos_client()


def _get_ibm_cos_client():
    """Get IBM COS client."""
    return ibm_boto3.client(
        service_name="s3",
        ibm_api_key_id=os.getenv("IBM_CLOUD_API_KEY"),
        ibm_service_instance_id=os.getenv("IBM_COS_INSTANCE_ID"),
        config=Config(signature_version="oauth"),
        endpoint_url=os.getenv(
            "IBM_COS_ENDPOINT",
            "https://s3.us-south.cloud-object-storage.appdomain.cloud",
        ),
    )


def _get_do_spaces_client():
    """Get DigitalOcean Spaces client."""
    endpoint = os.getenv("DO_SPACES_ENDPOINT", "https://nyc3.digitaloceanspaces.com")
    # Extract region from endpoint (e.g., nyc3 from https://nyc3.digitaloceanspaces.com)
    region = endpoint.split(".")[0].split("//")[-1] if "//" in endpoint else "nyc3"
    
    return boto3.client(
        service_name="s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("DO_SPACES_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("DO_SPACES_SECRET_KEY"),
        region_name=region,
    )


def _get_storage_bucket() -> str:
    """
    Get storage bucket name.
    
    Returns:
        Bucket name
    """
    if os.getenv("DO_SPACES_ENDPOINT"):
        return os.getenv("DO_SPACES_BUCKET", "invoicify-storage")
    else:
        return os.getenv("IBM_COS_BUCKET", "nivi-lake-prod")
