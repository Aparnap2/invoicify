"""
open-sarika local STT server
OpenAI-compatible /v1/audio/transcriptions endpoint
Same interface as Sarvam API — zero code change to swap

Supports:
- Hindi (hi)
- Gujarati (gu)
- Marathi (mr)
- English (en)
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from transformers import pipeline
import soundfile as sf
import numpy as np
import io
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Open-Sarika STT Server")

MODEL_NAME = os.getenv("MODEL_NAME", "theharshithh/open-sarika")
DEVICE = os.getenv("DEVICE", "cpu")
SUPPORTED_LANGUAGES = os.getenv("SUPPORTED_LANGUAGES", "hi,gu,mr,en").split(",")

# Global pipeline variable
asr_pipeline = None


def load_model():
    """Load ASR model at startup."""
    global asr_pipeline
    
    logger.info(f"Loading {MODEL_NAME} on {DEVICE}...")
    
    try:
        asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=MODEL_NAME,
            device=0 if DEVICE == "cuda" else -1,
        )
        logger.info("Model loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise


@app.on_event("startup")
async def startup_event():
    """Load model on startup."""
    load_model()


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(default="hi"),
    model: str = Form(default="open-sarika"),
    response_format: str = Form(default="json"),
):
    """
    Transcribe audio file to text.
    
    OpenAI-compatible endpoint for speech-to-text.
    
    Args:
        file: Audio file (WAV, MP3, etc.)
        language: Language code (hi, gu, mr, en)
        model: Model name (ignored, always uses open-sarika)
        response_format: Response format (json, text, verbose_json)
    
    Returns:
        JSON with transcribed text
    """
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {language}. Supported: {SUPPORTED_LANGUAGES}"
        )
    
    try:
        audio_bytes = await file.read()
        audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes))
        
        # Resample to 16kHz if needed
        if sample_rate != 16000:
            import librosa
            audio_array = librosa.resample(
                audio_array,
                orig_sr=sample_rate,
                target_sr=16000,
            )
        
        # Convert to mono if stereo
        if audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)
        
        # Run ASR
        result = asr_pipeline(
            {
                "array": audio_array.astype(np.float32),
                "sampling_rate": 16000,
            },
            generate_kwargs={
                "language": language,
                "task": "transcribe",
            },
        )
        
        text = result["text"].strip()
        
        if response_format == "text":
            return JSONResponse(text, media_type="text/plain")
        
        return JSONResponse({"text": text})
        
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/audio/translations")
async def translate(file: UploadFile = File(...)):
    """
    Translate Indian language audio → English text.
    
    Uses Whisper's translate task to convert Hindi/Gujarati/Marathi
    speech directly to English text.
    
    Args:
        file: Audio file in Indian language
    
    Returns:
        JSON with English translation
    """
    try:
        audio_bytes = await file.read()
        audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes))
        
        # Resample to 16kHz
        if sample_rate != 16000:
            import librosa
            audio_array = librosa.resample(
                audio_array,
                orig_sr=sample_rate,
                target_sr=16000,
            )
        
        # Convert to mono
        if audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)
        
        # Run ASR with translate task
        result = asr_pipeline(
            {
                "array": audio_array.astype(np.float32),
                "sampling_rate": 16000,
            },
            generate_kwargs={"task": "translate"},  # → English
        )
        
        return JSONResponse({"text": result["text"].strip()})
        
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    return JSONResponse({
        "object": "list",
        "data": [
            {
                "id": "open-sarika",
                "object": "model",
                "created": 1707091200,
                "owned_by": "theharshithh",
                "permission": [],
                "root": "open-sarika",
                "parent": None,
            }
        ],
    })


@app.get("/health")
async def health():
    """Health check endpoint."""
    return JSONResponse({
        "status": "ok",
        "model": MODEL_NAME,
        "device": DEVICE,
        "supported_languages": SUPPORTED_LANGUAGES,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8881)
