"""seed_grading_baseline.py — Siembra el baseline global de grading.

Inserta el registro `global` en `grading_baselines` con los parámetros
(d_min, d_max) por región por defecto. Sin este registro, GradeCardUseCase
no tiene fallback cuando no existe un baseline calibrado por (set, finish).

Uso:
    python scripts/seed_grading_baseline.py

El script es idempotente: si el baseline global ya existe, no hace nada.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Asegurar que el paquete sea encontrable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from pokegrading.config import get_settings
from pokegrading.domain.value_objects.grading_region import GradingRegion

# Parámetros (d_min, d_max) globales por región.
# d_min: distancia de Hamming por debajo de la cual se asigna score=10.0
# d_max: distancia de Hamming por encima de la cual se asigna score=1.0
# Valores razonables para pHash de 64 bits:
#   - centering: más tolerante (margen impreso varía según el lote)
#   - corners/edges: menos tolerante (desgaste físico se nota más)
#   - surface: tolerancia media (rayones vs holo dependen del acabado)
_GLOBAL_PARAMS: dict[str, list[int]] = {
    GradingRegion.CENTERING.value: [4, 20],
    GradingRegion.CORNERS.value: [2, 18],
    GradingRegion.EDGES.value: [3, 22],
    GradingRegion.SURFACE.value: [4, 28],
}

_GLOBAL_REF = "global"


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        existing = session.execute(
            text("SELECT id FROM grading_baselines WHERE ref = :ref"),
            {"ref": _GLOBAL_REF},
        ).fetchone()

        if existing:
            print(f"[seed] Baseline '{_GLOBAL_REF}' already exists — skipping.")
            return

        session.execute(
            text(
                """
                INSERT INTO grading_baselines
                    (id, ref, is_calibrated, ground_truth_count, params_json, created_at)
                VALUES
                    (:id, :ref, :is_calibrated, :ground_truth_count, :params_json, :created_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "ref": _GLOBAL_REF,
                "is_calibrated": False,
                "ground_truth_count": 0,
                "params_json": json.dumps(_GLOBAL_PARAMS),
                "created_at": datetime.now(tz=timezone.utc),
            },
        )
        session.commit()
        print(f"[seed] Baseline '{_GLOBAL_REF}' inserted OK.")
        print(f"       Params: {json.dumps(_GLOBAL_PARAMS, indent=2)}")


if __name__ == "__main__":
    main()
