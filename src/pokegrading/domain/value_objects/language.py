"""Language value object — idiomas soportados para la UI y para la identidad de cartas Pokémon.

Los idiomas de impresión de cartas siguen los idiomas oficiales de The Pokémon Company.
"""
from __future__ import annotations

from enum import Enum


class SupportedLanguage(str, Enum):
    """Idiomas válidos tanto para la UI del sistema como para la identidad de cartas Pokémon.

    Estos son los idiomas oficiales en que The Pokémon Company imprime cartas.
    Se usan para validar el campo `language` al agregar una carta al catálogo.
    """
    EN = "en"   # English (el más común, primera impresión)
    JA = "ja"   # 日本語 (Japanese — primera impresión histórica)
    ES = "es"   # Español
    FR = "fr"   # Français
    DE = "de"   # Deutsch
    IT = "it"   # Italiano
    PT = "pt"   # Português (Brasil)
    KO = "ko"   # 한국어 (Korean)
    ZH = "zh"   # 中文 (Chinese Traditional — Taiwan/Hong Kong)
    PL = "pl"   # Polski
    NL = "nl"   # Nederlands
    TH = "th"   # ภาษาไทย (Thai)
