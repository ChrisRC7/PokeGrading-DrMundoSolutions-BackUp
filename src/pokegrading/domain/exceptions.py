from __future__ import annotations


class PokegradingError(Exception):
    """Base exception for all domain errors.

    Todas las excepciones del dominio heredan de esta clase para que la capa API
    pueda mapearlas a códigos HTTP sin acoplarse a excepciones de infraestructura.
    """


class EmailAlreadyExistsError(PokegradingError):
    def __init__(self, email: str) -> None:
        # Se usa en registro de usuario y en save() del repositorio cuando la
        # restricción única del email falla a nivel de BD.
        super().__init__(f"An account with email '{email}' already exists")
        self.email = email


class DisclosureNotAcceptedError(PokegradingError):
    def __init__(self) -> None:
        # La app exige aceptar el aviso legal antes de crear cuenta.
        super().__init__(
            "You must accept the service disclosure to create an account. "
            "PokéGrading provides informative estimates and does not replace "
            "professional grading (PSA, BGS, CGC)."
        )


class CardAlreadyExistsError(PokegradingError):
    def __init__(self, identity: str) -> None:
        # La identidad de catálogo se define por set + número + edición + idioma + finish.
        super().__init__(
            f"A card with identity '{identity}' already exists in the catalog"
        )
        self.identity = identity


class UnauthorizedError(PokegradingError):
    def __init__(self, detail: str = "Insufficient permissions") -> None:
        # Error semántico para distinguir falta de permiso de un fallo técnico.
        super().__init__(detail)


class UserNotFoundError(PokegradingError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"User '{identifier}' not found")


class CardNotFoundError(PokegradingError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Card '{identifier}' not found in catalog")


class InvalidCredentialsError(PokegradingError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class CountryNotSupportedError(PokegradingError):
    def __init__(self, country: str) -> None:
        super().__init__(
            f"Country '{country}' is not supported. "
            "Supported countries: CR, PA, MX, CO, CL, AR"
        )
        self.country = country


class PasswordTooWeakError(PokegradingError):
    def __init__(self, reason: str = "") -> None:
        msg = "Password does not meet security requirements"
        if reason:
            msg = f"{msg}: {reason}"
        super().__init__(msg)


class BlockedEmailDomainError(PokegradingError):
    def __init__(self, domain: str) -> None:
        super().__init__(
            f"Email domain '{domain}' is not allowed. "
            "Please use a permanent email address."
        )
        self.domain = domain


class InvalidRarityError(PokegradingError):
    def __init__(self, rarity: str) -> None:
        super().__init__(
            f"Rarity '{rarity}' is not valid. "
            "Valid values: Common, Uncommon, Rare, Holo Rare, Ultra Rare, Secret Rare"
        )
        self.rarity = rarity


class InvalidPokemonTypeError(PokegradingError):
    def __init__(self, pokemon_type: str) -> None:
        super().__init__(
            f"Pokémon type '{pokemon_type}' is not valid. "
            "Valid values: Fire, Water, Grass, Electric, Psychic, Fighting, "
            "Darkness, Metal, Fairy, Dragon, Colorless, Normal"
        )
        self.pokemon_type = pokemon_type


class InvalidLanguageError(PokegradingError):
    def __init__(self, language: str) -> None:
        super().__init__(
            f"Language '{language}' is not supported. "
            "Valid values: en, ja, es, fr, de, it, pt, ko, zh, pl, nl, th"
        )
        self.language = language


class InvalidImageError(PokegradingError):
    def __init__(self, reason: str) -> None:
        # Se usa cuando la imagen no cumple condiciones mínimas de lectura/seguridad.
        super().__init__(f"Image is not valid: {reason}")
        self.reason = reason


class BothImagesRequiredError(PokegradingError):
    def __init__(self, missing_side: str) -> None:
        # US-003 siempre necesita frente y reverso; no existe envío parcial válido.
        super().__init__(
            f"Both front and back images are required. Missing: '{missing_side}'"
        )
        self.missing_side = missing_side


class InvalidFileFormatError(PokegradingError):
    def __init__(self, side: str) -> None:
        super().__init__(
            f"Image '{side}' has an unsupported format. "
            "Supported formats: JPEG, PNG"
        )
        self.side = side


class FileTooLargeError(PokegradingError):
    def __init__(self, side: str, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            f"Image '{side}' is too large "
            f"({size_bytes / (1024 * 1024):.1f} MB). "
            f"Maximum allowed: {max_bytes // (1024 * 1024)} MB"
        )
        self.side = side


class PolyglotDetectedError(PokegradingError):
    def __init__(self, side: str) -> None:
        # Protege contra archivos que son válidos en dos formatos a la vez.
        super().__init__(
            f"Image '{side}' appears to contain embedded non-image data "
            "and was rejected for security reasons."
        )
        self.side = side


class ImageQualityBelowThresholdError(PokegradingError):
    def __init__(self, side: str, score: float, threshold: float) -> None:
        # El score representa calidad de lectura; no es una calificación humana de la carta.
        super().__init__(
            f"Image quality for '{side}' ({score:.0%}) is below the minimum "
            f"threshold ({threshold:.0%}). "
            "Ensure the image is well-lit, in focus, and properly framed."
        )
        self.side = side
        self.score = score


class NoMatchFoundError(PokegradingError):
    """No catalog cards match the given search query above the confidence threshold.

    Se lanza cuando la búsqueda rápida recupera candidatos, pero ninguno supera
    el umbral definido para auto-aceptación o para mostrar resultados útiles.
    """

    def __init__(self, query: str) -> None:
        super().__init__(
            f"No cards matching '{query}' were found in the catalog. "
            "Consider using the specialized search or entering details manually."
        )
        self.query = query


class ImageNotIdentifiableError(PokegradingError):
    """The submitted image cannot be used for automatic card identification.

    Se usa cuando la imagen no puede convertirse en una query útil (OCR vacío,
    archivo corrupto o sin información visual suficiente).
    """

    def __init__(self) -> None:
        super().__init__(
            "The submitted image could not be identified automatically. "
            "Please provide a name hint (q=) or enter card details manually."
        )


# ── B2B API (US-005) ─────────────────────────────────────────────────────────
# Todas las excepciones B2B comparten un formato de error único (ADR-004 §6):
# code estable + mensaje legible + campo/carta afectada + trace_id.


class B2BError(PokegradingError):
    """Base de los errores del API B2B que rechazan la consulta completa.

    Lleva los atributos que alimentan el formato de error único. El handler
    HTTP (api/b2b/v1) los serializa y añade el `trace_id` de la request.
    """

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        card_ref: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.card_ref = card_ref


class InvalidApiKeyError(B2BError):
    code = "INVALID_API_KEY"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("La API key es inválida o no existe.")


class ApiKeyRevokedError(B2BError):
    code = "API_KEY_REVOKED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("La API key proporcionada fue revocada.")


class ApiKeySuspendedError(B2BError):
    code = "API_KEY_SUSPENDED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("La API key proporcionada está suspendida.")


class ApiKeyExpiredError(B2BError):
    code = "API_KEY_EXPIRED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("La API key proporcionada expiró.")


class B2BCustomerSuspendedError(B2BError):
    code = "CUSTOMER_SUSPENDED"
    http_status = 403

    def __init__(self) -> None:
        super().__init__("El Customer B2B asociado está suspendido.")


class EmptyLookupQueryError(B2BError):
    code = "EMPTY_QUERY"
    http_status = 422

    def __init__(self) -> None:
        super().__init__("La consulta no incluye ninguna carta.")


class MalformedLookupQueryError(B2BError):
    code = "MALFORMED_QUERY"
    http_status = 422

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, field=field)


class IdempotencyKeyReuseError(B2BError):
    code = "IDEMPOTENCY_KEY_REUSED"
    http_status = 409

    def __init__(self) -> None:
        super().__init__(
            "El request_id ya fue usado con un contenido distinto dentro de la ventana."
        )


class RateLimitExceededError(B2BError):
    code = "RATE_LIMIT_EXCEEDED"
    http_status = 429

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Se excedió el límite de cartas consultadas. "
            f"Reintente en {retry_after_seconds} segundos."
        )
        self.retry_after_seconds = retry_after_seconds


# ── Sprint 4: Preprocesamiento y Calificación ─────────────────────────────────

class SubmissionNotFoundError(PokegradingError):
    def __init__(self, submission_id: object) -> None:
        super().__init__(f"Submission '{submission_id}' not found.")
        self.submission_id = submission_id


class CardNotPreprocessedError(PokegradingError):
    def __init__(self, submission_id: object) -> None:
        super().__init__(
            f"Submission '{submission_id}' must be in PREPROCESSED status before grading."
        )
        self.submission_id = submission_id


class CardIsolationFailedError(PokegradingError):
    """No se pudo aislar la carta del fondo (AC-P4 → MANUAL_REVIEW).

    No se mapea a HTTP: es una señal interna entre el servicio de
    preprocesamiento y el use case para derivar al estado MANUAL_REVIEW.
    """

    def __init__(self, reason: str = "Could not isolate card from background.") -> None:
        super().__init__(reason)


class UncorrectableDistortionError(PokegradingError):
    """Distorsión imposible de corregir (AC-P5 → NEEDS_RECAPTURE).

    Igual que CardIsolationFailedError: rama de negocio, no error HTTP.
    """

    def __init__(self, reason: str = "Image distortion cannot be corrected.") -> None:
        super().__init__(reason)


class InsufficientGradingInputError(PokegradingError):
    """Insumos insuficientes para calificar una región (AC-G7 → MANUAL_REVIEW).

    Se lanza desde IRegionGradingService cuando el pHash de referencia
    está ausente o la región es ilegible.
    """

    def __init__(self, region: str) -> None:
        super().__init__(f"Insufficient grading input for region '{region}'.")
        self.region = region


class IncoherentGradeError(PokegradingError):
    """Los subgrades son internamente incoherentes (AC-G8 → MANUAL_REVIEW).

    Se lanza cuando la dispersión entre subgrades supera UMBRAL_INCOHERENCIA.
    """

    def __init__(self, dispersion: float) -> None:
        super().__init__(
            f"Subgrade dispersion ({dispersion:.2f}) exceeds coherence threshold."
        )
        self.dispersion = dispersion
