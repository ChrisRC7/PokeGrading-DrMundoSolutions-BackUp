# Diagramas de actividad — Preprocesar carta y Calificar carta (Sprint 4)

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 4
**Relacionado:** [ADR-005](./ADR-005-preprocesamiento-y-calificacion.md) · [diagramas-secuencia.md](./diagramas-secuencia.md)

> Estos diagramas hacen *zoom* sobre los nodos `preprocesar` y `calificar` del [flujo de grading completo de Sprint 3 §1](../../Sprint3/DOC/diagramas-actividad.md). Mermaid renderizable en GitHub / wiki Azure DevOps.

---

## 1. Preprocesar carta

```mermaid
flowchart TD
    start([Submission PENDING]) --> proc[Marcar PROCESSING]
    proc --> iso{¿Se aísla la carta del fondo?}
    iso -- no --> manual[Submission MANUAL_REVIEW<br/>calificación manual]:::warn
    iso -- si --> persp{¿Perspectiva corregible?}
    persp -- no --> recap[Submission NEEDS_RECAPTURE<br/>solicitar recapturar]:::err
    persp -- si --> crop[Recortar al borde de la carta]
    crop --> color[Normalizar color]
    color --> seg[Segmentar en 4 regiones:<br/>centering, corners, edges, surface]
    seg --> hash[Calcular pHash por región]
    hash --> save[Persistir RegionImage ×4]
    save --> ok([Submission PREPROCESSED<br/>avanza a calificación]):::ok

    classDef ok fill:#e0ffe0,stroke:#0a0;
    classDef warn fill:#fff3d0,stroke:#c80;
    classDef err fill:#ffe0e0,stroke:#c00;
```

| AC | Reflejado en |
|---|---|
| AC-P1 | nodos `persp` → `crop` → `color` |
| AC-P2 | nodo `seg` (4 regiones) |
| AC-P3 | salida `ok` (PREPROCESSED → calificación) |
| AC-P4 | rama `iso -- no` → MANUAL_REVIEW |
| AC-P5 | rama `persp -- no` → NEEDS_RECAPTURE |

---

## 2. Calificar carta

```mermaid
flowchart TD
    start([Submission PREPROCESSED]) --> idem{¿Existe evaluación<br/>misma sesión + versión?}
    idem -- si --> reuse([Devolver evaluación existente<br/>sin recalcular]):::reuse
    idem -- no --> regions[Cargar 4 regiones del envío<br/>pHash + recorte]
    regions --> ref[Resolver carta de referencia:<br/>segmentar imagen de catálogo<br/>región-contra-región + pHash]
    ref --> base{¿Ground truth suficiente<br/>para set+finish?}
    base -- si --> bcal[Baseline CALIBRADO set:finish]
    base -- no --> bglob[Baseline GLOBAL]
    bcal --> sub
    bglob --> sub[Subgrade por región 1.0-10.0:<br/>pHash parecido + diferencia de<br/>píxeles daño rayones/marcas]

    sub --> ins{¿Todos los subgrades<br/>tienen insumos suficientes?}
    ins -- no --> man1[Submission MANUAL_REVIEW]:::warn
    ins -- si --> coh[final = min candidato, peor+0.5<br/>banda = incertidumbre]
    coh --> internal{¿Coherencia interna OK?<br/>dispersión ≤ umbral}
    internal -- no --> man2[Submission MANUAL_REVIEW<br/>revisión humana]:::warn
    internal -- si --> persist[Persistir CardEvaluation<br/>algorithm_version + baseline_ref<br/>append-only, inmutable]
    persist --> graded([Submission GRADED<br/>grado ± banda]):::ok

    classDef ok fill:#e0ffe0,stroke:#0a0;
    classDef warn fill:#fff3d0,stroke:#c80;
    classDef reuse fill:#e0f0ff,stroke:#06c;
```

| AC | Reflejado en |
|---|---|
| AC-G1 | nodo `sub` (subgrade por dimensión, 1.0–10.0 = pHash + daño local) |
| AC-G2 | bifurcación `base` (calibrado vs. global, registrado en output) |
| AC-G3 | nodo `coh` (`final = min(candidato, peor+0.5)`) |
| AC-G4 | nodo `coh` (banda de incertidumbre) |
| AC-G5 | nodo `persist` (versión + append-only inmutable) |
| AC-G6 | bifurcación `idem` (reuse sin recalcular) |
| AC-G7 | rama `ins -- no` → MANUAL_REVIEW |
| AC-G8 | rama `internal -- no` → MANUAL_REVIEW |

---

## 3. Ubicación dentro del flujo de grading (Sprint 3)

```mermaid
flowchart LR
    A[US-003 Enviar<br/>Submission PENDING] --> B[Identificar carta<br/>pHash / OCR]
    B --> C[**Preprocesar** §1<br/>PREPROCESSED]
    C --> D[**Calificar** §2<br/>GRADED ± banda]
    C -. AC-P4/P5 .-> M[MANUAL_REVIEW /<br/>NEEDS_RECAPTURE]
    D -. AC-G7/G8 .-> M
```

Los nodos en negrita son las dos actividades nuevas de Sprint 4. El resto ya existía en Sprint 1–3.

---

## Referencias

- [ADR-005](./ADR-005-preprocesamiento-y-calificacion.md)
- [diseno-preprocesamiento-calificacion.md](./diseno-preprocesamiento-calificacion.md)
- [diagramas-secuencia.md](./diagramas-secuencia.md)
- [diagramas-actividad.md (Sprint 3)](../../Sprint3/DOC/diagramas-actividad.md)
