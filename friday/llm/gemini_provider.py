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
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
]


class GeminiProvider:
    """Adapter for Google AI Studio Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
    ) -> None:
        """Initialize the Gemini client.

        Args:
            api_key: Google AI Studio API key. If None, reads from GEMINI_API_KEY env var.
            model_name: Gemini model identifier (default: gemini-3.6-flash).
            system_instruction: Base persona instructions.
            temperature: Creativity control (0.0 to 1.0).
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
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
        """Generate a one-off completion from Gemini with multi-model failover.

        Args:
            prompt: User text prompt.

        Returns:
            The model's text response.
        """
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

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

        return "Boss, our cloud brain reached the daily quota across available free-tier Gemini models. Please generate a fresh free API key at https://aistudio.google.com/ and update your .env file, or give me some time to recharge."

    def chat(self, user_message: str) -> str:
        """Send a message within the stateful chat session with multi-model failover.

        Args:
            user_message: Message from the user.

        Returns:
            The assistant's text response.
        """
        if not self.is_configured():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file."
            )

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

        return "Boss, our cloud brain reached the daily quota across available free-tier Gemini models. Please generate a fresh free API key at https://aistudio.google.com/ and update your .env file, or give me some time to recharge."

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

        return "Boss, our cloud brain reached the daily quota across available free-tier Gemini models. Please generate a fresh free API key at https://aistudio.google.com/ and update your .env file, or give me some time to recharge."

    def reset_chat(self) -> None:
        """Reset the active chat session history."""
        if self._model is not None:
            self._chat = self._model.start_chat(history=[])
        else:
            self._chat = None
