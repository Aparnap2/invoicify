"""
Parakeet STT Service for Pipecat (LinTO NeMo WebSocket).

Custom Pipecat STT Service for lintoai/linto-stt-nemo (Parakeet TDT 0.6B).
Connects via WebSocket for ultra-low latency streaming.

Protocol:
1. Send JSON config: {"config": {"sample_rate": 16000}}
2. Send raw binary audio chunks
3. Receive: {"partial": "..."} or {"text": "final text"}
"""

import json
import asyncio
import websockets
import structlog
from typing import Optional
from pipecat.services.ai_services import STTService
from pipecat.frames.frames import (
    AudioRawFrame, 
    TranscriptionFrame, 
    InterimTranscriptionFrame,
    SystemFrame,
    CancelFrame,
    StartFrame,
    EndFrame,
)

logger = structlog.get_logger()


class ParakeetSTTService(STTService):
    """
    Custom Pipecat STT Service for LinTO NeMo (Parakeet TDT).
    
    Usage:
        stt = ParakeetSTTService(ws_url="ws://localhost:80/streaming")
        pipeline.add(stt)
    """
    
    def __init__(
        self, 
        ws_url: str = "ws://localhost:80/streaming", 
        sample_rate: int = 16000,
        language: str = "en-US",
    ):
        """
        Initialize Parakeet STT.
        
        Args:
            ws_url: WebSocket URL for LinTO NeMo server
            sample_rate: Audio sample rate (16000 for Parakeet)
            language: Language code (en-US, hi-IN, etc.)
        """
        super().__init__()
        self._ws_url = ws_url
        self._sample_rate = sample_rate
        self._language = language
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._connected = False
    
    async def start(self, frame: SystemFrame):
        """Start STT service and connect to WebSocket."""
        await super().start(frame)
        
        try:
            self._ws = await websockets.connect(
                self._ws_url,
                ping_interval=30,
                ping_timeout=10,
            )
            
            # Send initial configuration expected by LinTO
            config = {
                "config": {
                    "sample_rate": self._sample_rate,
                    "language": self._language,
                    "use_partial": True,  # Enable partial transcripts
                }
            }
            await self._ws.send(json.dumps(config))
            
            # Start background task to receive messages
            self._receive_task = asyncio.create_task(self._receive_messages())
            self._connected = True
            
            logger.info("parakeet_stt_connected", url=self._ws_url)
            
        except Exception as e:
            logger.error("parakeet_stt_connection_failed", error=str(e), url=self._ws_url)
            raise
    
    async def stop(self, frame: SystemFrame):
        """Stop STT service and close WebSocket."""
        if self._ws:
            try:
                # Send EOF to cleanly close the LinTO transcription buffer
                await self._ws.send(json.dumps({"eof": 1}))
                await self._ws.close()
            except Exception as e:
                logger.warning("parakeet_stt_close_error", error=str(e))
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        self._connected = False
        await super().stop(frame)
    
    async def process_frame(self, frame):
        """
        Route Pipecat frames.
        
        - AudioRawFrame → WebSocket (binary)
        - CancelFrame → Stop and cleanup
        - Others → Pass through
        """
        if isinstance(frame, AudioRawFrame):
            if self._ws and self._ws.open:
                # Send raw audio bytes to Parakeet
                await self._ws.send(frame.audio)
        
        elif isinstance(frame, CancelFrame):
            await self.stop(frame)
            await self.push_frame(frame)
        
        elif isinstance(frame, (StartFrame, EndFrame)):
            await self.push_frame(frame)
        
        else:
            # Pass through other frames unchanged
            await self.push_frame(frame)
    
    async def _receive_messages(self):
        """
        Background task to receive transcripts from Parakeet.
        
        Messages:
        - {"partial": "..."} → InterimTranscriptionFrame
        - {"text": "..."} → TranscriptionFrame
        """
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.warning("parakeet_invalid_json", message=message[:100])
                    continue
                
                # Final transcription
                if "text" in data and data["text"].strip():
                    frame = TranscriptionFrame(
                        text=data["text"].strip(),
                        user_id="",  # Will be set by aggregator
                        timestamp=self.get_timestamp(),
                    )
                    logger.debug("parakeet_final_transcript", text=data["text"])
                    await self.push_frame(frame)
                
                # Interim/Partial transcription (for faster LLM TTFT)
                elif "partial" in data and data["partial"].strip():
                    frame = InterimTranscriptionFrame(
                        text=data["partial"].strip(),
                        user_id="",
                        timestamp=self.get_timestamp(),
                    )
                    await self.push_frame(frame)
                    
        except asyncio.CancelledError:
            logger.debug("parakeet_receive_cancelled")
        except websockets.ConnectionClosed as e:
            logger.warning("parakeet_connection_closed", code=e.code, reason=e.reason)
        except Exception as e:
            logger.error("parakeet_receive_error", error=str(e))
    
    def get_timestamp(self) -> str:
        """Get ISO format timestamp for frames."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Factory function for easy integration
# ─────────────────────────────────────────────────────────────────────────────

def create_parakeet_stt(
    ws_url: str = "ws://localhost:80/streaming",
    sample_rate: int = 16000,
    language: str = "en-US",
) -> ParakeetSTTService:
    """
    Create Parakeet STT service.
    
    Args:
        ws_url: LinTO NeMo WebSocket endpoint
        sample_rate: Audio sample rate
        language: Language code
    
    Returns:
        Configured ParakeetSTTService instance
    """
    return ParakeetSTTService(
        ws_url=ws_url,
        sample_rate=sample_rate,
        language=language,
    )
