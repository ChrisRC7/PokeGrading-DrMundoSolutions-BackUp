"""Backfill del pHash de las imágenes de referencia ya cargadas (US-004 / Sprint 3).

Recorre `card_images` con `phash IS NULL`, calcula el pHash a partir del binario
y lo persiste. Idempotente: se puede correr varias veces sin efectos adversos.

Uso:
    python scripts/backfill_phash.py
"""
from __future__ import annotations

from pokegrading.infrastructure.matching.phash_image_hash_service import (
    PHashImageHashService,
)
from pokegrading.infrastructure.persistence.database import SessionLocal
from pokegrading.infrastructure.persistence.models import CardImageORM


def main() -> None:
    hash_svc = PHashImageHashService()
    db = SessionLocal()
    updated = 0
    skipped = 0
    try:
        rows = db.query(CardImageORM).filter(CardImageORM.phash.is_(None)).all()
        for row in rows:
            phash = hash_svc.compute_phash(row.data)
            if phash:
                row.phash = phash
                updated += 1
            else:
                skipped += 1
        db.commit()
    finally:
        db.close()

    print(f"Backfill de pHash completado: {updated} actualizadas, {skipped} omitidas.")


if __name__ == "__main__":
    main()
