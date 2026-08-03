"""Compatibility runtime providers."""

from alma_bridge.runtime.providers.container import ContainerRuntime
from alma_bridge.runtime.providers.native_alma import NativeAlmaRuntime
from alma_bridge.runtime.providers.proton import ProtonRuntime
from alma_bridge.runtime.providers.wine import WineRuntime

__all__ = [
    "ContainerRuntime",
    "NativeAlmaRuntime",
    "ProtonRuntime",
    "WineRuntime",
]
