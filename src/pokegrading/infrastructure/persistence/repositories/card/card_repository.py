from __future__ import annotations

import difflib
import hashlib
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pokegrading.domain.entities.card import Card
from pokegrading.domain.exceptions import CardAlreadyExistsError
from pokegrading.domain.repositories.card_repository import ICardRepository
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.infrastructure.persistence.models import CardORM


class CardRepositoryImpl(ICardRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_identity(self, identity: CardIdentityTuple) -> Card | None:
        # La identidad de una carta está compuesta por set + número + edición + idioma + finish.
        # Si alguna de esas piezas cambia, ya no se trata de la misma carta de catálogo.
        row = (
            self._db.query(CardORM)
            .filter(
                CardORM.set_name == identity.set_name,
                CardORM.card_number == identity.card_number,
                CardORM.edition == identity.edition,
                CardORM.language == identity.language,
                CardORM.finish == identity.finish,
            )
            .first()
        )
        return self._to_entity(row) if row else None

    def find_by_id(self, card_id: UUID) -> Card | None:
        # Búsqueda directa por clave primaria para operaciones puntuales del flujo de catálogo.
        row = self._db.query(CardORM).filter(CardORM.id == card_id).first()
        return self._to_entity(row) if row else None

    def find_all(self) -> list[Card]:
        # Orden descendente por fecha de creación para mostrar primero lo más reciente en la UI/admin.
        rows = self._db.query(CardORM).order_by(CardORM.created_at.desc()).all()
        return [self._to_entity(r) for r in rows]

    def find_top_candidates(self, query: str, limit: int = 3) -> list[tuple[Card, float]]:
        """Busca hasta `limit` cartas ACTIVE y devuelve cada una con su score de confianza.

        Scoring continuo con difflib.SequenceMatcher:
        - 1.0  → coincidencia exacta de nombre
        - 0.90+ → coincidencia de número de carta exacta
        - [0.0, 1.0) → similitud carácter-a-carácter (SequenceMatcher.ratio)

        La consulta SQL expande a tokens individuales para maximizar el recall
        (una carta "Pikachu V" aparece aunque la query sea sólo "Pikachu n60").
        El ranking final se hace en Python con el score continuo.
        """
        q = query.strip().lower()
        if not q:
            return []

        def _escape(s: str) -> str:
            # Escapamos caracteres especiales para que LIKE no interprete comodines provenientes del OCR.
            return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")

        # Condiciones LIKE: se incluye la query completa y cada token individual.
        # Esto prioriza recall sobre precisión en la primera pasada SQL, para no perder candidatos
        # útiles si EasyOCR devuelve texto ruidoso o incompleto.
        safe_q = _escape(q)
        tokens = q.split()
        like_conditions = [
            func.lower(CardORM.name).like(f"%{safe_q}%"),
            func.lower(CardORM.set_name).like(f"%{safe_q}%"),
            func.lower(CardORM.card_number).like(f"%{safe_q}%"),
        ]
        for tok in tokens:
            if len(tok) >= 2:  # evitar tokens de 1 carácter que generan demasiado ruido
                safe_tok = _escape(tok)
                like_conditions.append(func.lower(CardORM.name).like(f"%{safe_tok}%"))

        # Solo cartas activas: el catálogo público no debe devolver cartas pendientes de validación.
        # Se traen más filas de las que realmente se necesitan para poder reordenarlas después en Python.
        rows = (
            self._db.query(CardORM)
            .filter(
                CardORM.status == CardStatus.ACTIVE,
                or_(*like_conditions),
            )
            .limit(limit * 10)  # fetch extra para re-ranking en Python
            .all()
        )

        def _score(row: CardORM) -> float:
            # Normalizamos a minúsculas para comparar sin depender de mayúsculas/minúsculas.
            # Esto hace que la búsqueda sea robusta frente a OCR y a datos capturados por usuarios.
            name_l = row.name.lower()
            num_l = (row.card_number or "").lower()

            # Coincidencia exacta del nombre: es el mejor caso posible, por eso devuelve 1.0.
            if name_l == q:
                return 1.0

            # Coincidencia exacta del número de carta: también es una señal muy fuerte,
            # pero se mantiene una comparación secundaria con el nombre para no sobrevalorar
            # números cortos o ambiguos.
            if num_l and num_l == q:
                return max(difflib.SequenceMatcher(None, q, name_l).ratio(), 0.90)

            # Score de similitud continua entre la query y el nombre de la carta.
            # SequenceMatcher.ratio() produce un valor entre 0 y 1, útil para diferenciar
            # variantes muy cercanas entre sí sin crear saltos bruscos como un sistema por tiers.
            # Ejemplos:
            #   "pikachu" vs "pikachu v"    → 0.875
            #   "pikachu" vs "pikachu vmax" → 0.737
            #   "pikachu" vs "pikachu ex"   → 0.824
            name_sim = difflib.SequenceMatcher(None, q, name_l).ratio()

            # Bonus leve si parte de la query aparece en el número impreso.
            # No domina el ranking, pero ayuda a separar candidatos cuando OCR mezcla nombre y número.
            if num_l and q in num_l:
                name_sim = max(name_sim, 0.75)

            return round(name_sim, 4)

        # Se reordena en memoria porque el SQL previo solo garantiza candidatos plausibles,
        # no el orden final óptimo. Primero convertimos a entidad de dominio para no mezclar
        # la lógica de ranking con detalles ORM.
        scored = sorted(
            [(self._to_entity(r), _score(r)) for r in rows],
            key=lambda t: t[1],
            reverse=True,
        )
        return scored[:limit]

    def find_active_by_partial_identity(
        self,
        set_name: str,
        card_number: str,
        edition: str | None = None,
        language: str | None = None,
        finish: str | None = None,
    ) -> list[Card]:
        """B2B lookup (US-005): cartas ACTIVE por identidad parcial.

        `set_name`/`card_number` son obligatorios (igualdad case-insensitive).
        Los opcionales restringen el match cuando se proveen. El orden es
        estable y reproducible (`ORDER BY id`), de modo que dos consultas
        idénticas devuelven el mismo orden (AC-03).
        """
        query = self._db.query(CardORM).filter(
            CardORM.status == CardStatus.ACTIVE,
            func.lower(CardORM.set_name) == set_name.strip().lower(),
            func.lower(CardORM.card_number) == card_number.strip().lower(),
        )
        if edition:
            query = query.filter(func.lower(CardORM.edition) == edition.strip().lower())
        if language:
            query = query.filter(
                func.lower(CardORM.language) == language.strip().lower()
            )
        if finish:
            query = query.filter(func.lower(CardORM.finish) == finish.strip().lower())

        rows = query.order_by(CardORM.id).all()
        return [self._to_entity(r) for r in rows]

    def find_by_phash_near(
        self, phash: str, max_hamming: int = 12, limit: int = 3
    ) -> list[tuple[Card, int]]:
        """Recall en SQL (cartas activas con pHash de frente), precisión en Python.

        La distancia de Hamming se calcula comparando los enteros de 64 bits;
        es barato para el catálogo actual. A gran escala se sustituiría por un
        índice especializado (BK-tree / pg_bktree) — ver ADR/diseño pHash.
        """
        q = (phash or "").strip()
        if not q:
            return []
        try:
            target = int(q, 16)
        except ValueError:
            return []

        from pokegrading.infrastructure.persistence.models import CardImageORM

        rows = (
            self._db.query(CardORM, CardImageORM.phash)
            .join(CardImageORM, CardImageORM.card_id == CardORM.id)
            .filter(
                CardORM.status == CardStatus.ACTIVE,
                CardImageORM.side == "front",
                CardImageORM.phash.isnot(None),
            )
            .all()
        )

        scored: list[tuple[Card, int]] = []
        for card_row, card_phash in rows:
            try:
                distance = bin(target ^ int(card_phash, 16)).count("1")
            except (ValueError, TypeError):
                continue
            if distance <= max_hamming:
                scored.append((self._to_entity(card_row), distance))

        scored.sort(key=lambda t: t[1])
        return scored[:limit]

    def get_catalog_fingerprint(self) -> str:
        """Huella del catálogo activo para ETag (ADR-004 §5).

        Combina el conteo de cartas activas, la suma de versiones y el
        máximo `created_at`. Cambia ante altas, retiros, aprobaciones y
        ediciones que incrementen versión.
        """
        from sqlalchemy import func as sa_func

        count, version_sum, last_created = (
            self._db.query(
                sa_func.count(CardORM.id),
                sa_func.coalesce(sa_func.sum(CardORM.version), 0),
                sa_func.max(CardORM.created_at),
            )
            .filter(CardORM.status == CardStatus.ACTIVE)
            .one()
        )
        seed = f"{count}:{int(version_sum)}:{last_created.isoformat() if last_created else '-'}"
        digest = hashlib.sha256(seed.encode()).hexdigest()[:16]
        return f"cat-{digest}"

    def delete(self, card_id: UUID) -> bool:
        # Eliminación física simple: si la carta no existe, el repositorio informa False.
        row = self._db.query(CardORM).filter(CardORM.id == card_id).first()
        if row is None:
            return False
        self._db.delete(row)
        self._db.commit()
        return True

    def save(self, card: Card) -> Card:
        # Upsert manual: el agregado Card se persiste por id, no por identidad de negocio.
        # Esto permite actualizar estado y campos de auditoría sin crear filas duplicadas.
        row = self._db.query(CardORM).filter(CardORM.id == card.id).first()
        if row is None:
            # Inserción inicial: se copian todos los campos del agregado al modelo ORM.
            row = CardORM(
                id=card.id,
                name=card.name,
                set_name=card.identity.set_name,
                card_number=card.identity.card_number,
                edition=card.identity.edition,
                language=card.identity.language,
                finish=card.identity.finish,
                status=card.status,
                version=card.version,
                description=card.description,
                rarity=card.rarity,
                pokemon_type=card.pokemon_type,
                hp=card.hp,
                illustrator=card.illustrator,
                print_year=card.print_year,
                created_by=card.created_by,
                created_at=card.created_at,
                approved_by=card.approved_by,
                approved_at=card.approved_at,
            )
            self._db.add(row)
        else:
            # Actualización parcial: solo se permiten campos que el flujo de negocio puede mutar.
            # La identidad base de la carta se mantiene inmutable porque forma parte del contrato
            # del catálogo.
            row.status = card.status
            row.approved_by = card.approved_by
            row.approved_at = card.approved_at
            row.description = card.description
            row.rarity = card.rarity
            row.pokemon_type = card.pokemon_type
            row.hp = card.hp
            row.illustrator = card.illustrator
            row.print_year = card.print_year
        try:
            self._db.commit()
        except IntegrityError:
            # El error de integridad esperado aquí es la duplicación de identidad/campos únicos.
            # El dominio no debe conocer el detalle de SQLAlchemy, así que se traduce a una
            # excepción semántica del catálogo.
            self._db.rollback()
            raise CardAlreadyExistsError(str(card.identity))
        self._db.refresh(row)
        return self._to_entity(row)

    @staticmethod
    def _to_entity(row: CardORM) -> Card:
        # Traducción ORM -> dominio para evitar que el resto de la aplicación dependa
        # de SQLAlchemy o de los nombres exactos de columnas.
        return Card(
            id=row.id,
            identity=CardIdentityTuple(
                set_name=row.set_name,
                card_number=row.card_number,
                edition=row.edition,
                language=row.language,
                finish=row.finish,
            ),
            name=row.name,
            status=CardStatus(row.status) if isinstance(row.status, str) else row.status,
            version=row.version,
            created_by=row.created_by,
            created_at=row.created_at,
            description=row.description,
            rarity=getattr(row, "rarity", None),
            pokemon_type=getattr(row, "pokemon_type", None),
            hp=getattr(row, "hp", None),
            illustrator=getattr(row, "illustrator", None),
            print_year=getattr(row, "print_year", None),
            approved_by=row.approved_by,
            approved_at=row.approved_at,
        )
