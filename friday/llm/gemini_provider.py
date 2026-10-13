"""Gemini Provider - Google AI Studio REST/SDK adapter for Friday."""

from __future__ import annotations

import os
import warnings
from typing import Any, Generator, List, Optional

warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import GenerationConfig

load_dotenv()


DEFAULT_SYSTEM_INSTRUCTION = """You are Friday, an ultra-advanced, loyal, highly capable personal AI assistant.
You operate on a 'Cloud-Brain, Local-Body' architecture:
- Your reasoning and intelligence reside in the cloud (Gemini).
- Your physical senses and hands reside locally on the user's Windows machine.
The user is a 2nd-year B.Tech Electronics & Telecommunication Engineering (ENTC) student.
Hardware constraints: Intel i5-12450H CPU, 16 GB RAM, RTX 3050 GPU (4 GB VRAM reserved exclusively for CAD/engineering coursework, NEVER utilize for background ML models).
Keep responses clear, sharp, technically precise, and natural. Explain non-obvious engineering decisions when appropriate.
"""


FALLBACK_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]


class GeminiProvider:
    """Adapter for Google AI Studio Gemini API with model & key pool failover."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
    ) -> None:
        """Initialize the Gemini client.

        Args:
            api_key: Google AI Studio API key(s). Supports comma-separated keys for pool failover.
            model_name: Gemini model identifier (default: gemini-flash-lite-latest).
            system_instruction: Base persona instructions.
            temperature: Creativity control (0.0 to 1.0).
        """
        raw_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS", "")
        self.api_keys: List[str] = [k.strip() for k in raw_key.split(",") if k.strip()]
        self.current_key_idx: int = 0
        self.api_key: Optional[str] = self.api_keys[0] if self.api_keys else None

        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        self.system_instruction = system_instruction or DEFAULT_SYSTEM_INSTRUCTION
        self.temperature = temperature
        self._model: Optional[genai.GenerativeModel] = None
        self._chat: Optional[genai.ChatSession] = None

        if self.api_key:
            self._configure()

    def _configure(self) -> None:
        """Configure the genai client and prepare the model."""
        genai.configure(api_key=self.api_key, transport="rest")
        self._model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_instruction,
            generation_config=GenerationConfig(
                temperature=self.temperature,
            ),
        )
        self._chat = self._model.start_chat(history=[])

    def _rotate_to_next_key(self) -> bool:
        """Switch to next API key in the configured key pool if available."""
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            self.api_key = self.api_keys[self.current_key_idx]
            self._configure()
            return True
        return False

    def is_configured(self) -> bool:
        """Check whether the provider has a valid API key configured."""
        return bool(self.api_key and self._model is not None)

    def set_api_key(self, api_key: str) -> None:
        """Update or configure the API key at runtime."""
        self.api_key = api_key
        self._configure()

    def set_system_instruction(self, instruction: str) -> None:
        """Update system instructions and refresh model configuration."""
        self.system_instruction = instruction
        if self._model is not None:
            self._configure()

    def generate(self, prompt: str) -> str:
        """Generate a one-off completion from Gemini with multi-model and key pool failover.

        Args:
            prompt: User text prompt.

        Returns:
            The model's text response.
        """
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        total_keys = max(1, len(self.api_keys))
        for _ in range(total_keys):
            models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            for candidate in models_to_try:
                try:
                    if candidate != self.model_name or self._model is None:
                        self.model_name = candidate
                        self._configure()
                    assert self._model is not None
                    response = self._model.generate_content(prompt, request_options={"retry": None})
                    return response.text or ""
                except Exception as exc:
                    err_str = str(exc).lower()
                    if any(x in err_str for x in ("429", "quota", "not found", "503", "unavailable")):
                        continue
                    return f"I ran into an issue connecting to my cloud brain: {exc}"

            if not self._rotate_to_next_key():
                break

        return (
            "Boss, our cloud brain reached the daily quota across available free-tier Gemini models. "
            "To resolve this instantly, generate a fresh free API key at https://aistudio.google.com/ "
            "and add it to your .env file (you can supply multiple comma-separated keys: GEMINI_API_KEY=key1,key2)."
        )

    def chat(self, user_message: str) -> str:
        """Send a message within the stateful chat session with multi-model and key pool failover.

        Args:
            user_message: Message from the user.

        Returns:
            The assistant's text response.
        """
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        total_keys = max(1, len(self.api_keys))
        for _ in range(total_keys):
            models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            for candidate in models_to_try:
                try:
                    if candidate != self.model_name or self._chat is None:
                        self.model_name = candidate
                        self._configure()
                    assert self._chat is not None
                    response = self._chat.send_message(user_message, request_options={"retry": None})
                    return response.text or ""
                except Exception as exc:
                    err_str = str(exc).lower()
                    if any(x in err_str for x in ("429", "quota", "not found", "503", "unavailable")):
                        continue
                    return f"I ran into an issue connecting to my cloud brain: {exc}"

            if not self._rotate_to_next_key():
                break

        return (
            "Boss, our cloud brain reached the daily quota across available free-tier Gemini models. "
            "To resolve this instantly, generate a fresh free API key at https://aistudio.google.com/ "
            "and add it to your .env file (you can supply multiple comma-separated keys: GEMINI_API_KEY=key1,key2)."
        )

    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        """Generate streaming token chunks from Gemini with multi-model failover."""
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        total_keys = max(1, len(self.api_keys))
        for _ in range(total_keys):
            models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            for candidate in models_to_try:
                try:
                    if candidate != self.model_name or self._model is None:
                        self.model_name = candidate
                        self._configure()
                    assert self._model is not None
                    response = self._model.generate_content(prompt, stream=True, request_options={"retry": None})
                    for chunk in response:
                        try:
                            if chunk.text:
                                yield chunk.text
                        except Exception:
                            pass
                    return
                except Exception as exc:
                    err_str = str(exc).lower()
                    if any(x in err_str for x in ("429", "quota", "not found", "503", "unavailable")):
                        continue
                    yield f"I ran into an issue connecting to my cloud brain: {exc}"
                    return

            if not self._rotate_to_next_key():
                break

        yield "Boss, our cloud brain reached the daily quota across available free-tier Gemini models."

    def chat_stream(self, user_message: str) -> Generator[str, None, None]:
        """Stream chunks from active stateful chat session."""
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        total_keys = max(1, len(self.api_keys))
        for _ in range(total_keys):
            models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            for candidate in models_to_try:
                try:
                    if candidate != self.model_name or self._chat is None:
                        self.model_name = candidate
                        self._configure()
                    assert self._chat is not None
                    response = self._chat.send_message(user_message, stream=True, request_options={"retry": None})
                    for chunk in response:
                        try:
                            if chunk.text:
                                yield chunk.text
                        except Exception:
                            pass
                    return
                except Exception as exc:
                    err_str = str(exc).lower()
                    if any(x in err_str for x in ("429", "quota", "not found", "503", "unavailable")):
                        continue
                    yield f"I ran into an issue connecting to my cloud brain: {exc}"
                    return

            if not self._rotate_to_next_key():
                break

        yield "Boss, our cloud brain reached the daily quota across available free-tier Gemini models."

    def generate_with_image(self, prompt: str, image: Any) -> str:
        """Generate response given a text prompt and an image (path, bytes, or PIL Image).

        Args:
            prompt: Text prompt / instruction.
            image: File path string, bytes, or PIL Image instance.

        Returns:
            The model's text response.
        """
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        from PIL import Image
        import io

        if isinstance(image, str):
            img_obj = Image.open(image)
        elif isinstance(image, bytes):
            img_obj = Image.open(io.BytesIO(image))
        else:
            img_obj = image

        try:
            assert self._model is not None
            response = self._model.generate_content([prompt, img_obj])
            return response.text or ""
        except Exception as exc:
            if "not found" in str(exc).lower() and self.model_name != "gemini-1.5-flash":
                self.model_name = "gemini-1.5-flash"
                self._configure()
                assert self._model is not None
                response = self._model.generate_content([prompt, img_obj])
                return response.text or ""
            raise

    def generate_with_audio(self, prompt: str, audio_bytes: bytes) -> str:
        """Generate response given a text prompt/instruction and raw audio WAV bytes.

        Args:
            prompt: Text prompt / instruction.
            audio_bytes: Raw 16kHz WAV or PCM audio bytes.

        Returns:
            The model's text response.
        """
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        from google.generativeai.types import content_types
        audio_blob = content_types.to_blob({"mime_type": "audio/wav", "data": audio_bytes})

        total_keys = max(1, len(self.api_keys))
        for _ in range(total_keys):
            models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            for candidate in models_to_try:
                try:
                    if candidate != self.model_name or self._model is None:
                        self.model_name = candidate
                        self._configure()
                    assert self._model is not None
                    response = self._model.generate_content([audio_blob, prompt], request_options={"retry": None})
                    return response.text or ""
                except Exception as exc:
                    err_str = str(exc).lower()
                    if any(x in err_str for x in ("429", "quota", "not found", "503", "unavailable")):
                        continue
                    return f"I ran into an issue processing audio with my cloud brain: {exc}"

            if not self._rotate_to_next_key():
                break

        return (
            "Boss, our cloud brain reached the daily quota across available free-tier Gemini models. "
            "To resolve this instantly, generate a fresh free API key at https://aistudio.google.com/ "
            "and add it to your .env file (you can supply multiple comma-separated keys: GEMINI_API_KEY=key1,key2)."
        )

    def generate_with_audio_stream(self, prompt: str, audio_bytes: bytes) -> Generator[str, None, None]:
        """Stream response chunks from multimodal audio WAV input."""
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

        from google.generativeai.types import content_types
        audio_blob = content_types.to_blob({"mime_type": "audio/wav", "data": audio_bytes})

        total_keys = max(1, len(self.api_keys))
        for _ in range(total_keys):
            models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            for candidate in models_to_try:
                try:
                    if candidate != self.model_name or self._model is None:
                        self.model_name = candidate
                        self._configure()
                    assert self._model is not None
                    response = self._model.generate_content([audio_blob, prompt], stream=True, request_options={"retry": None})
                    for chunk in response:
                        try:
                            if chunk.text:
                                yield chunk.text
                        except Exception:
                            pass
                    return
                except Exception as exc:
                    err_str = str(exc).lower()
                    if any(x in err_str for x in ("429", "quota", "not found", "503", "unavailable")):
                        continue
                    yield f"I ran into an issue processing audio with my cloud brain: {exc}"
                    return

            if not self._rotate_to_next_key():
                break

        yield "Boss, our cloud brain reached the daily quota across available free-tier Gemini models."

    def reset_chat(self) -> None:
        """Reset the active chat session history."""
        if self._model is not None:
            self._chat = self._model.start_chat(history=[])
        else:
            self._chat = None
