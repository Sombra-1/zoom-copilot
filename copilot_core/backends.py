"""Provider dispatch shared by text and vision without changing legacy payloads."""
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlsplit
import ipaddress

from .codex_client import Cancelled


def backend_is_local(settings):
    name = settings.get("backend")
    if name in ("builtin", "demo"):
        return True
    if name != "ollama":
        return False
    try:
        host = urlsplit(settings.get("ollama_host", "")).hostname or ""
        if host.lower().rstrip(".") == "localhost":
            return True
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Backend:
    text: Callable
    vision: Optional[Callable] = None
    local: bool = False


class BackendRegistry:
    def __init__(self):
        self._providers = {}

    def register(self, name, backend):
        self._providers[name] = backend

    def get(self, name):
        try:
            return self._providers[name]
        except KeyError:
            raise ValueError(f"Unknown backend: {name}") from None

    def supports_vision(self, name):
        return self.get(name).vision is not None

    def ask(self, messages, settings, prompt, max_tokens=300, active=None):
        if active is not None and not active():
            raise Cancelled("Request cancelled")
        return self.get(settings["backend"]).text(
            messages, settings, prompt, max_tokens, active)

    def see(self, image, context, settings, active=None):
        provider = self.get(settings["backend"])
        if provider.vision is None:
            raise RuntimeError("Select a vision-capable backend: Codex, Claude or Ollama.")
        if settings.get("vision_mode", "off") == "off":
            raise RuntimeError("Vision is off. Select a vision mode before capturing.")
        if active is not None and not active():
            raise Cancelled("Vision request cancelled")
        return provider.vision(image, context, settings, active)
