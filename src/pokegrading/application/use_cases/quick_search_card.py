from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pokegrading.application.ports.card_matching_service import ICardMatchingService
from pokegrading.domain.entities.search_result import SearchResult
from pokegrading.domain.exceptions import ImageNotIdentifiableError, NoMatchFoundError
from pokegrading.domain.repositories.card_repository import ICardRepository

# Umbral por defecto (configurable por llamada)
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.60


@dataclass(frozen=True)
class QuickSearchInput:
    """Parámetros de entrada para la búsqueda rápida de carta.

    Attributes
    ----------
    image_front_data:
        Bytes de la imagen de frente de la carta.
    query_hint:
        Texto de respaldo para modo desarrollo (nombre de la carta).
        En producción este campo es ignorado; los features se extraen de la imagen.
    confidence_threshold:
        Umbral mínimo de confianza para considerar un candidato como «aceptado
        automáticamente».  Rango [0.0, 1.0].
    limit:
        Número máximo de candidatos a devolver (máx. 3 por especificación).
    """

    image_front_data: bytes
    query_hint: str | None = None
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    limit: int = 3


@dataclass(frozen=True)
class QuickSearchOutput:
    """Resultado de la búsqueda rápida.

    Attributes
    ----------
    candidates:
        Lista de hasta ``limit`` candidatos ordenados por confianza desc.
    auto_accepted:
        True si el candidato #1 supera ``confidence_threshold``.
    """

    candidates: list[SearchResult]
    auto_accepted: bool


class QuickSearchCardUseCase:
    """US-004 — Realizar búsqueda rápida de carta.

    Flujo:
    1. Delega la extracción de features a ``ICardMatchingService``.
    2. Si no hay features Y no hay ``query_hint`` → ``ImageNotIdentifiableError``.
    3. Busca hasta ``limit`` candidatos en el catálogo vía
       ``ICardRepository.find_top_candidates``.
    4. Si no hay candidatos → ``NoMatchFoundError``.
    5. ``auto_accepted = candidates[0].confidence >= threshold``.
    """

    def __init__(
        self,
        card_repo: ICardRepository,
        matching_svc: ICardMatchingService,
    ) -> None:
        self._card_repo = card_repo
        self._matching_svc = matching_svc

    def execute(self, inp: QuickSearchInput) -> QuickSearchOutput:
        # Paso 1 — Determinar query efectiva.
        # Si el caller ya procesó la imagen y pasó un query_hint, usarlo directo
        # (evita correr OCR dos veces y evita que el texto completo contamine la búsqueda).
        # Si no hay query_hint, extraer features de la imagen como respaldo.
        effective_query = (inp.query_hint or "").strip()
        if not effective_query:
            features = self._matching_svc.extract_features(inp.image_front_data).strip()
            effective_query = features

        # Paso 2 — Verificar que hay algo con qué buscar
        # Si la query está vacía, la imagen no aporta información suficiente para identificar la carta.
        if not effective_query:
            raise ImageNotIdentifiableError()

        # Paso 3 — Buscar candidatos en el catálogo
        # El repositorio decide cómo puntuar; el use case solo consume la lista ordenada.
        raw = self._card_repo.find_top_candidates(effective_query, limit=inp.limit)

        # Paso 4 — Verificar que hay resultados
        # Sin candidatos no hay forma de presentar opciones razonables al usuario.
        if not raw:
            raise NoMatchFoundError(effective_query)

        # Paso 5 — Construir resultados tipados
        # Convertimos el tuple (Card, score) en un DTO de dominio más cómodo para la API.
        candidates = [
            SearchResult(
                candidate_card_id=card.id,
                confidence_score=score,
                rank=rank,
                name=card.name,
                set_name=card.identity.set_name,
                card_number=card.identity.card_number,
                language=card.identity.language,
                rarity=card.rarity,
                pokemon_type=card.pokemon_type,
                hp=card.hp,
            )
            for rank, (card, score) in enumerate(raw, start=1)
        ]

        # Auto-aceptación: si la mejor coincidencia supera el umbral, el flujo puede avanzar
        # sin obligar al usuario a elegir manualmente entre los 3 candidatos.
        auto_accepted = candidates[0].confidence_score >= inp.confidence_threshold

        return QuickSearchOutput(candidates=candidates, auto_accepted=auto_accepted)
