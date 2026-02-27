"""
Unit tests for Voice Agent Service Factory.

Tests service configuration and lazy initialization.

Note: We use monkeypatch to properly isolate environment variables
between tests, since the factory reads env vars at call time.
"""

import pytest
import os
from unittest.mock import patch, AsyncMock


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE FACTORY CONFIG TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestServiceFactoryConfig:
    """Test service factory configuration."""
    
    def test_stt_config_local(self, monkeypatch):
        """Test STT config for local provider."""
        from src.services.factory import get_stt_service_config
        
        monkeypatch.setenv("STT_PROVIDER", "local")
        
        config = get_stt_service_config()
        
        assert config["type"] == "openai_compatible"
        assert "open-sarika-stt" in config["base_url"]
        assert config["api_key"] == "local"
        assert config["model"] == "open-sarika"
    
    def test_stt_config_sarvam(self, monkeypatch):
        """Test STT config for Sarvam provider."""
        from src.services.factory import get_stt_service_config
        
        monkeypatch.setenv("STT_PROVIDER", "sarvam")
        monkeypatch.setenv("SARVAM_API_KEY", "test-key")
        monkeypatch.setenv("SARVAM_STT_MODEL", "saaras:v3")
        monkeypatch.setenv("VENDOR_LANGUAGE", "hi-IN")
        
        config = get_stt_service_config()
        
        assert config["type"] == "sarvam"
        assert config["api_key"] == "test-key"
        assert config["model"] == "saaras:v3"
    
    def test_tts_config_local(self, monkeypatch):
        """Test TTS config for local provider."""
        from src.services.factory import get_tts_service_config
        
        monkeypatch.setenv("TTS_PROVIDER", "local")
        
        config = get_tts_service_config()
        
        assert config["type"] == "openai_compatible"
        assert "kokoro-tts" in config["base_url"]
        assert config["model"] == "kokoro"
        assert config["voice"] == "af_heart"
    
    def test_tts_config_sarvam(self, monkeypatch):
        """Test TTS config for Sarvam provider."""
        from src.services.factory import get_tts_service_config
        
        monkeypatch.setenv("TTS_PROVIDER", "sarvam")
        monkeypatch.setenv("SARVAM_API_KEY", "test-key")
        monkeypatch.setenv("SARVAM_TTS_MODEL", "bulbul:v3")
        monkeypatch.setenv("SARVAM_TTS_SPEAKER", "meera")
        
        config = get_tts_service_config()
        
        assert config["type"] == "sarvam"
        assert config["api_key"] == "test-key"
        assert config["model"] == "bulbul:v3"
        assert config["speaker"] == "meera"
    
    def test_llm_config_ollama(self, monkeypatch):
        """Test LLM config for Ollama provider."""
        from src.services.factory import get_llm_client_config
        
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        
        provider, model, base_url = get_llm_client_config()
        
        assert provider == "openai_compatible"
        assert model == "qwen2.5:7b"
        assert "ollama:11434" in base_url
    
    def test_llm_config_azure(self, monkeypatch):
        """Test LLM config for Azure provider."""
        from src.services.factory import get_llm_client_config
        
        monkeypatch.setenv("LLM_PROVIDER", "azure_foundry")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        
        provider, model, base_url = get_llm_client_config()
        
        assert provider == "azure"
        assert model == "gpt-4o"
        assert base_url == "https://test.openai.azure.com"
    
    def test_llm_config_groq(self, monkeypatch):
        """Test LLM config for Groq provider."""
        from src.services.factory import get_llm_client_config
        
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        provider, model, base_url = get_llm_client_config()
        
        assert provider == "groq"
        assert model == "llama-3.3-70b-versatile"
        assert "groq.com" in base_url
    
    def test_invalid_stt_provider(self, monkeypatch):
        """Test error on invalid STT provider."""
        from src.services.factory import get_stt_service_config
        
        monkeypatch.setenv("STT_PROVIDER", "invalid")
        
        with pytest.raises(ValueError, match="Unknown STT_PROVIDER"):
            get_stt_service_config()
    
    def test_invalid_tts_provider(self, monkeypatch):
        """Test error on invalid TTS provider."""
        from src.services.factory import get_tts_service_config
        
        monkeypatch.setenv("TTS_PROVIDER", "invalid")
        
        with pytest.raises(ValueError, match="Unknown TTS_PROVIDER"):
            get_tts_service_config()
    
    def test_invalid_llm_provider(self, monkeypatch):
        """Test error on invalid LLM provider."""
        from src.services.factory import get_llm_client_config
        
        monkeypatch.setenv("LLM_PROVIDER", "invalid")
        
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            get_llm_client_config()


# ─────────────────────────────────────────────────────────────────────────────
# VOICE SERVICE FACTORY CLASS TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestVoiceServiceFactoryClass:
    """Test VoiceServiceFactory class."""
    
    def test_factory_initialization(self):
        """Test factory initializes with None configs."""
        from src.services.factory import VoiceServiceFactory
        
        factory = VoiceServiceFactory()
        
        assert factory._stt_config is None
        assert factory._tts_config is None
        assert factory._llm_config is None
    
    def test_factory_config_caching(self):
        """Test factory caches configurations."""
        from src.services.factory import VoiceServiceFactory
        
        factory = VoiceServiceFactory()
        
        # First call
        config1 = factory.get_stt_config()
        
        # Second call should return cached
        config2 = factory.get_stt_config()
        
        assert config1 is config2
    
    @pytest.mark.asyncio
    async def test_factory_get_stt_local(self):
        """Test factory creates local STT service."""
        from src.services.factory import VoiceServiceFactory
        
        with patch.dict(os.environ, {"STT_PROVIDER": "local"}):
            factory = VoiceServiceFactory()
            stt, model, language = factory.get_stt()
            
            assert model == "open-sarika"
            assert language == "hi"
    
    @pytest.mark.asyncio
    async def test_factory_get_llm_ollama(self):
        """Test factory creates Ollama LLM client."""
        from src.services.factory import VoiceServiceFactory
        
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            factory = VoiceServiceFactory()
            llm_client, model = factory.get_llm()
            
            assert model == "qwen2.5:7b"
            assert llm_client is not None
    
    def test_factory_lazy_initialization(self):
        """Test factory lazily initializes services."""
        from src.services.factory import VoiceServiceFactory
        
        factory = VoiceServiceFactory()
        
        # Services should be None initially
        assert factory._stt_service is None
        assert factory._tts_service is None
        assert factory._llm_client is None
        
        # Access config (not service) - should not create service
        factory.get_stt_config()
        
        # Service should still be None
        assert factory._stt_service is None


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_voice_factory(self):
        """Test get_voice_factory returns new instance."""
        from src.services.factory import get_voice_factory, VoiceServiceFactory
        
        factory = get_voice_factory()
        
        assert isinstance(factory, VoiceServiceFactory)
    
    def test_get_stt_service(self):
        """Test get_stt_service returns configured service."""
        from src.services.factory import get_stt_service
        
        with patch.dict(os.environ, {"STT_PROVIDER": "local"}):
            stt, model, language = get_stt_service()
            
            assert model == "open-sarika"
    
    def test_get_tts_service(self):
        """Test get_tts_service returns configured service."""
        from src.services.factory import get_tts_service
        
        with patch.dict(os.environ, {"TTS_PROVIDER": "local"}):
            tts, model, voice = get_tts_service()
            
            assert model == "kokoro"
            assert voice == "af_heart"
    
    def test_get_llm_client(self):
        """Test get_llm_client returns configured client."""
        from src.services.factory import get_llm_client
        
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            llm_client, model = get_llm_client()
            
            assert model == "qwen2.5:7b"
