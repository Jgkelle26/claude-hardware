"""Pluggable visual themes for the Clod 64x64 RGB LED matrix display."""

from __future__ import annotations

from clod.themes.base import ThemeRenderer
from clod.themes.bear import BearTheme
from clod.themes.character import CharacterTheme
from clod.themes.composition import CompositionTheme
from clod.themes.ethereal import EtherealTheme
from clod.themes.particles import ParticleCloudTheme
from clod.themes.theme_manager import ThemeManager

__all__: list[str] = [
    "ThemeRenderer",
    "ThemeManager",
    "BearTheme",
    "CompositionTheme",
    "EtherealTheme",
    "ParticleCloudTheme",
    "CharacterTheme",
]
