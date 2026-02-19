"""
Service factory for Voice Agent — controlled entirely by environment variables.

Dev uses Docker local services (zero cost).
Prod uses Sarvam API + Kokoro Modal.
ZERO code changes between environments.

Usage:
    # Local dev
    STT_PROVIDER=local
    TTS_PROVIDER=local
    LLM_PROVIDER=ollama
    
    # Production
    STT_PROVIDER=sarvam
    TTS_PROVIDER=modal
    LLM_PROVIDER=azure_foundry
"""

import os
from typing import Any, Dict, Optional, Tuple
import structlog

logger = structlog.get_logger()

# Environment configuration
STT_PROVIDER = os.getenv("STT_PROVIDER", "local")  # local | sarvam
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "local")  # local | modal | sarvam
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # ollama | azure_foundry | groq


def get_stt_service_config() -> Dict[str, Any]:
    """
    Get STT service configuration.
    
    Returns:
        Dict with service type and config
    """
    if STT_PROVIDER == "local":
        # open-sarika in Docker — OpenAI-compatible
        return {
            "type": "openai_compatible",
            "base_url": os.getenv("STT_BASE_URL", "http://open-sarika-stt:8881"),
            "api_key": "local",
            "model": "open-sarika",
            "language": os.getenv("VENDOR_LANGUAGE", "hi"),
        }
    
    elif STT_PROVIDER == "sarvam":
        # Sarvam Saaras v3 API
        return {
            "type": "sarvam",
            "api_key": os.getenv("SARVAM_API_KEY"),
            "model": os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
            "language": os.getenv("VENDOR_LANGUAGE", "hi-IN"),
            "mode": os.getenv("SARVAM_STT_MODE", "transcribe"),  # transcribe | translate | codemix
        }
    
    elif STT_PROVIDER == "whisper":
        # Fallback: faster-whisper
        return {
            "type": "openai_compatible",
            "base_url": os.getenv("WHISPER_BASE_URL", "http://faster-whisper:8000"),
            "api_key": "local",
            "model": "large-v3",
            "language": os.getenv("WHISPER_LANGUAGE", "hi"),
        }
    
    raise ValueError(f"Unknown STT_PROVIDER: {STT_PROVIDER}")


def get_tts_service_config() -> Dict[str, Any]:
    """
    Get TTS service configuration.
    
    Returns:
        Dict with service type and config
    """
    if TTS_PROVIDER == "local":
        # Kokoro FastAPI in Docker — OpenAI-compatible
        return {
            "type": "openai_compatible",
            "base_url": os.getenv("TTS_BASE_URL", "http://kokoro-tts:8880"),
            "api_key": "local",
            "model": "kokoro",
            "voice": os.getenv("TTS_VOICE", "af_heart"),
            "speed": float(os.getenv("TTS_SPEED", "1.1")),
        }
    
    elif TTS_PROVIDER == "modal":
        # Kokoro on Modal — same OpenAI-compatible API, different URL
        return {
            "type": "openai_compatible",
            "base_url": os.getenv("KOKORO_MODAL_URL"),
            "api_key": "modal-no-key",
            "model": "kokoro",
            "voice": os.getenv("TTS_VOICE", "af_heart"),
            "speed": float(os.getenv("TTS_SPEED", "1.1")),
        }
    
    elif TTS_PROVIDER == "sarvam":
        # Sarvam Bulbul v3 API — best Indian voice quality
        return {
            "type": "sarvam",
            "api_key": os.getenv("SARVAM_API_KEY"),
            "model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
            "speaker": os.getenv("SARVAM_TTS_SPEAKER", "meera"),
            "language": os.getenv("VENDOR_LANGUAGE", "hi-IN"),
            "pitch": float(os.getenv("SARVAM_TTS_PITCH", "0")),
            "pace": float(os.getenv("SARVAM_TTS_PACE", "1.1")),
            "loudness": float(os.getenv("SARVAM_TTS_LOUDNESS", "1.0")),
            "sample_rate": int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "8000")),  # Telephony (Twilio)
        }
    
    raise ValueError(f"Unknown TTS_PROVIDER: {TTS_PROVIDER}")


def get_llm_client_config() -> Tuple[str, str, Optional[str]]:
    """
    Get LLM client configuration.
    
    Returns:
        Tuple of (provider_type, model_name, base_url)
    """
    if LLM_PROVIDER == "ollama":
        # Local Ollama — OpenAI-compatible
        return (
            "openai_compatible",
            os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1"),
        )
    
    elif LLM_PROVIDER == "azure_foundry":
        # Azure OpenAI Foundry
        return (
            "azure",
            os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
    
    elif LLM_PROVIDER == "groq":
        # Groq API
        return (
            "groq",
            os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "https://api.groq.com/openai/v1",
        )
    
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")


class VoiceServiceFactory:
    """
    Factory for creating voice services with lazy initialization.
    
    Usage:
        factory = VoiceServiceFactory()
        stt = factory.get_stt()
        tts = factory.get_tts()
        llm = factory.get_llm()
    """
    
    def __init__(self):
        """Initialize factory with config from environment."""
        self._stt_config = None
        self._tts_config = None
        self._llm_config = None
        self._stt_service = None
        self._tts_service = None
        self._llm_client = None
    
    def get_stt_config(self) -> Dict[str, Any]:
        """Get STT configuration (cached)."""
        if self._stt_config is None:
            self._stt_config = get_stt_service_config()
        return self._stt_config
    
    def get_tts_config(self) -> Dict[str, Any]:
        """Get TTS configuration (cached)."""
        if self._tts_config is None:
            self._tts_config = get_tts_service_config()
        return self._tts_config
    
    def get_llm_config(self) -> Tuple[str, str, Optional[str]]:
        """Get LLM configuration (cached)."""
        if self._llm_config is None:
            self._llm_config = get_llm_client_config()
        return self._llm_config
    
    def get_stt(self):
        """Get STT service instance."""
        if self._stt_service is None:
            config = self.get_stt_config()
            self._stt_service = self._create_stt_service(config)
        return self._stt_service
    
    def get_tts(self):
        """Get TTS service instance."""
        if self._tts_service is None:
            config = self.get_tts_config()
            self._tts_service = self._create_tts_service(config)
        return self._tts_service
    
    def get_llm(self):
        """Get LLM client instance."""
        if self._llm_client is None:
            provider, model, base_url = self.get_llm_config()
            self._llm_client = self._create_llm_client(provider, model, base_url)
        return self._llm_client
    
    def _create_stt_service(self, config: Dict[str, Any]):
        """Create STT service based on config."""
        if config["type"] == "openai_compatible":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key=config["api_key"],
                base_url=config["base_url"],
            ), config["model"], config.get("language", "hi")
        
        elif config["type"] == "sarvam":
            # Sarvam STT via HTTP
            return self._create_sarvam_stt(config)
        
        raise ValueError(f"Unknown STT type: {config['type']}")
    
    def _create_tts_service(self, config: Dict[str, Any]):
        """Create TTS service based on config."""
        if config["type"] == "openai_compatible":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key=config["api_key"],
                base_url=config["base_url"],
            ), config["model"], config.get("voice", "af_heart")
        
        elif config["type"] == "sarvam":
            # Sarvam Bulbul TTS via HTTP
            return self._create_sarvam_tts(config)
        
        raise ValueError(f"Unknown TTS type: {config['type']}")
    
    def _create_sarvam_stt(self, config: Dict[str, Any]):
        """Create Sarvam STT HTTP client."""
        import httpx
        
        class SarvamSTT:
            def __init__(self, cfg: Dict[str, Any]):
                self.api_key = cfg["api_key"]
                self.model = cfg["model"]
                self.language = cfg["language"]
                self.mode = cfg.get("mode", "transcribe")
            
            async def transcribe(self, audio_bytes: bytes) -> str:
                """Transcribe audio to text."""
                import base64
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Sarvam API expects base64-encoded audio
                    audio_b64 = base64.b64encode(audio_bytes).decode()
                    
                    response = await client.post(
                        "https://api.sarvam.ai/speech-to-text",
                        headers={
                            "api-subscription-key": self.api_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "audio": audio_b64,
                            "model": self.model,
                            "language": self.language,
                            "mode": self.mode,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result["transcription"]
        
        return SarvamSTT(config)
    
    def _create_sarvam_tts(self, config: Dict[str, Any]):
        """Create Sarvam Bulbul TTS HTTP client."""
        import httpx
        
        class SarvamTTS:
            def __init__(self, cfg: Dict[str, Any]):
                self.api_key = cfg["api_key"]
                self.model = cfg["model"]
                self.speaker = cfg.get("speaker", "meera")
                self.language = cfg.get("language", "hi-IN")
                self.pitch = cfg.get("pitch", 0)
                self.pace = cfg.get("pace", 1.1)
                self.loudness = cfg.get("loudness", 1.0)
                self.sample_rate = cfg.get("sample_rate", 8000)
            
            async def synthesize(self, text: str) -> bytes:
                """Synthesize speech from text."""
                import base64
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.sarvam.ai/text-to-speech",
                        headers={
                            "api-subscription-key": self.api_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "inputs": [text],
                            "target_language_code": self.language,
                            "speaker": self.speaker,
                            "pitch": self.pitch,
                            "pace": self.pace,
                            "loudness": self.loudness,
                            "speech_sample_rate": self.sample_rate,
                            "enable_preprocessing": True,
                            "model": self.model,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    audio_b64 = result["audios"][0]
                    return base64.b64decode(audio_b64)
        
        return SarvamTTS(config)
    
    def _create_llm_client(self, provider: str, model: str, base_url: Optional[str]):
        """Create LLM client based on provider."""
        if provider == "openai_compatible":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key="ollama",
                base_url=base_url,
            ), model
        
        elif provider == "azure":
            from openai import AsyncAzureOpenAI
            import os
            return AsyncAzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                api_version="2024-08-01-preview",
                azure_endpoint=base_url,
            ), model
        
        elif provider == "groq":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url=base_url,
            ), model
        
        raise ValueError(f"Unknown LLM provider: {provider}")


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions for direct usage
# ─────────────────────────────────────────────────────────────────────────────

def get_voice_factory() -> VoiceServiceFactory:
    """Get configured voice service factory."""
    return VoiceServiceFactory()


def get_stt_service():
    """Get STT service directly."""
    factory = get_voice_factory()
    return factory.get_stt()


def get_tts_service():
    """Get TTS service directly."""
    factory = get_voice_factory()
    return factory.get_tts()


def get_llm_client():
    """Get LLM client directly."""
    factory = get_voice_factory()
    return factory.get_llm()
