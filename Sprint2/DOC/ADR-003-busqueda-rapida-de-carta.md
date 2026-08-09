# ADR-003 — Diseño de "Realizar búsqueda rápida de carta" (US-004)

**Estado:** Aceptado  
**Fecha:** 2026-05-31  
**Autores:** Equipo Dr. Mundo Solutions  
**Sprint:** 2  
**Historia de usuario:** US-004

---

## Contexto

El flujo de envío de una carta para graduación requiere que el usuario (submitter) identifique qué carta está enviando. Dado que el sistema gestiona un catálogo con múltiples variantes de un mismo Pokémon (distintos sets, ediciones, idiomas, acabados), no es práctico que el usuario explore el catálogo manualmente.

Se necesita un mecanismo que:

1. Reciba la imagen de la **cara delantera** de la carta física.
2. Identifique automáticamente de qué carta se trata comparándola con el catálogo.
3. Devuelva los **3 mejores candidatos** con su nivel de confianza.
4. Si el candidato principal supera un umbral configurable, lo **acepte automáticamente** y avance al siguiente paso del flujo.
5. Si no supera el umbral, presente los candidatos al usuario para que **elija manualmente**.

---

## Decisión

Se implementa la búsqueda rápida como un pipeline de tres etapas independientes, conectadas mediante las interfaces de Clean Architecture:

```
Imagen de la carta
       │
       ▼ Etapa 1 — Extracción OCR
  EasyOCRCardMatchingService
  extract_tokens_raw() → lista[str]
  _parse_card_tokens() → { name, hp, card_number }
       │
       ▼ Etapa 2 — Búsqueda en catálogo
  CardRepositoryImpl.find_top_candidates(query, limit=3)
  → lista[(Card, float)]  ← scoring con difflib.SequenceMatcher
       │
       ▼ Etapa 3 — Decisión de auto-aceptación
  QuickSearchCardUseCase
  auto_accepted = candidates[0].confidence_score >= threshold (0.60)
```

Cada etapa tiene una interfaz abstracta (`ICardMatchingService`, `ICardRepository`) que permite sustituir las implementaciones sin tocar la lógica de negocio.

---

## Diseño detallado

### Etapa 1 — Identificación de la carta a partir de la imagen

#### 1.1 Tecnología de OCR

**Tecnología elegida:** EasyOCR v1.7.2 (modelo CRAFT + CRNN, CPU, inglés)

EasyOCR reconoce texto en imágenes naturales. Para cartas Pokémon TCG los campos
identificadores están impresos de forma consistente:

```
┌─────────────────────────────────────┐
│  [NOMBRE]                  [HP] HP  │  ← parte superior
│  Stage 1 / Basic / V / GX …        │
│                                     │
│  [descripción, ataques, etc.]       │  ← texto de ruido
│                                     │
│  [set logo]    [número]/[total]     │  ← parte inferior
└─────────────────────────────────────┘
```

EasyOCR devuelve una lista plana de strings por orden de aparición en la imagen
(de arriba a abajo, izquierda a derecha). El nombre y el HP se leen primero; el
número de carta al final.

#### 1.2 Patrón Singleton lazy

El modelo EasyOCR (~500 MB de pesos en RAM) se carga **una sola vez por proceso**
usando un singleton a nivel de clase. Las requests subsiguientes reutilizan el
reader ya inicializado.

```python
class EasyOCRCardMatchingService(ICardMatchingService):
    _reader: ClassVar[object | None] = None   # singleton

    @classmethod
    def _get_reader(cls) -> object:
        if cls._reader is None:
            import easyocr   # importación diferida (torch tarda ~5 s al importar)
            cls._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return cls._reader
```

La importación de `easyocr` es **diferida** para no penalizar el arranque del servidor.
El modelo se inicializa en la primera request que llega a `/search/quick` o `/search/ocr-extract`.

#### 1.3 Extracción de campos estructurados (`_parse_card_tokens`)

EasyOCR devuelve todos los tokens, incluyendo texto de ataques, costos de energía,
descripción del Pokémon, etc. Buscar con todo ese texto en la BD generaría consultas
que nunca coinciden con los nombres limpios almacenados en el catálogo.

La función `_parse_card_tokens(tokens: list[str]) -> dict` extrae solo los campos útiles:

| Campo | Estrategia de detección | Ejemplo |
|---|---|---|
| `card_number` | Regex `\b\d{1,3}/\d{1,3}\b` sobre el texto completo | `"025/185"` |
| `hp` | Número inmediatamente antes o después del token `"HP"` | `120` (de `"120 HP"`) |
| `name` | Primeros 1–3 tokens significativos antes del HP/número/stage | `"Pikachu"`, `"Tapu Koko GX"` |

El nombre se construye tomando los primeros tokens que no sean: indicadores de stage (`Basic`, `Stage 1`…), números puros, el token `HP`, ni el número de carta.

**Query enfocada resultante:**

```
tokens OCR: ["EDSE", "Pikachu", "n60", "Moflete", "Estático", "120", "HP", "025/185", ...]
                                                                                     ↓
_parse_card_tokens → { name: "EDSE Pikachu n60", card_number: "025/185" }
                                                                                     ↓
focused_q = "EDSE Pikachu n60"   (los 3 tokens de nombre únicamente)
```

#### 1.4 Interfaz abstracta `ICardMatchingService`

```python
class ICardMatchingService(ABC):
    @abstractmethod
    def extract_features(self, image_data: bytes) -> str:
        """Retorna texto de búsqueda derivado de la imagen."""

    @abstractmethod
    def extract_tokens_raw(self, image_data: bytes) -> list[str]:
        """Retorna todos los tokens OCR sin filtrar."""
```

En tests se usa `StubCardMatchingService`, que retorna `""` sin necesidad de GPU ni modelo descargado.

---

### Etapa 2 — Búsqueda en catálogo con scoring continuo

#### 2.1 Método `find_top_candidates`

```python
CardRepositoryImpl.find_top_candidates(query: str, limit: int = 3) -> list[tuple[Card, float]]
```

**Paso A — Recall (SQL):** Se construye una consulta con múltiples condiciones `LIKE`, una por cada token de la query y una por la query completa, unidas con `OR`. Esto maximiza las cartas candidatas recuperadas:

```sql
SELECT * FROM catalog_cards
WHERE status = 'active'
  AND (
    lower(name)        LIKE '%edse pikachu n60%'
    OR lower(name)     LIKE '%edse%'
    OR lower(name)     LIKE '%pikachu%'
    OR lower(name)     LIKE '%n60%'
    ...
  )
LIMIT 30  -- fetch extra para re-ranking en Python
```

Solo se busca en cartas con `status = 'active'` (las `pending` aún no están validadas por el admin).

**Paso B — Precision (Python):** Sobre el conjunto recuperado se calcula un **score de similitud continuo** con `difflib.SequenceMatcher`:

```python
score = difflib.SequenceMatcher(None, query, card.name.lower()).ratio()
# ratio() = 2 * matching_chars / total_chars → [0.0, 1.0]
```

Casos especiales:
- `name_l == query` → score = `1.0` (coincidencia exacta, sin calcular)
- `card_number == query` → score = `max(SequenceMatcher.ratio(), 0.90)` (señal muy fuerte)

Los resultados se ordenan por score descendente y se devuelven los `limit=3` mejores.

#### 2.2 ¿Por qué `difflib.SequenceMatcher` y no tiers fijos?

El diseño original usaba tiers fijos (1.0 / 0.85 / 0.70). El problema es que múltiples cartas del mismo Pokémon obtenían el mismo score y el ranking no era determinista:

| Carta | Score tier fijo | Score SequenceMatcher (query="pikachu") |
|---|---|---|
| "Pikachu" (exacto) | 1.0 | **1.000** |
| "Pikachu V" | 0.85 | **0.875** |
| "Pikachu ex" | 0.85 | **0.824** |
| "Pikachu VMAX" | 0.85 | **0.737** |

Con SequenceMatcher cada candidato tiene un score único y el ranking refleja cuál se parece más al texto que el OCR leyó.

#### 2.3 Almacenamiento de datos para la búsqueda

Los datos necesarios para ejecutar `find_top_candidates` viven en la tabla `catalog_cards`:

```
catalog_cards
├── name         VARCHAR(255)   ← campo principal de búsqueda
├── set_name     VARCHAR(100)   ← campo secundario de búsqueda
├── card_number  VARCHAR(20)    ← campo de búsqueda por número
├── status       ENUM           ← filtro obligatorio: solo 'active'
├── language     VARCHAR(50)    ← devuelto en la respuesta
├── rarity       VARCHAR(50)    ← devuelto en la respuesta
├── pokemon_type VARCHAR(50)    ← devuelto en la respuesta
└── hp           INTEGER        ← devuelto en la respuesta
```

No existe una tabla separada para el índice de búsqueda. La búsqueda ocurre directamente sobre `catalog_cards` con `LIKE`. Para Sprint 2 (catálogo de cientos a miles de cartas) esto es suficiente.

---

### Etapa 3 — Decisión de auto-aceptación (`QuickSearchCardUseCase`)

```python
auto_accepted = candidates[0].confidence_score >= confidence_threshold
```

El umbral por defecto es **0.60** (configurable por request vía el parámetro `confidence_threshold`).

**Flujo completo del use case:**

```
QuickSearchInput(image_front_data, query_hint, confidence_threshold=0.60, limit=3)
   │
   ├─ query_hint presente? → usarlo directamente (evita correr OCR dos veces)
   │
   └─ query_hint ausente? → extract_features(image) → effective_query
   │
   ├─ effective_query vacío? → raise ImageNotIdentifiableError (→ HTTP 422)
   │
   ├─ find_top_candidates(effective_query, limit=3)
   │
   ├─ sin candidatos? → raise NoMatchFoundError (→ HTTP 404)
   │
   └─ construir QuickSearchOutput(candidates, auto_accepted)
```

**Criterios de aceptación implementados:**

| AC | Descripción | Implementación |
|---|---|---|
| AC-01 | Devuelve hasta 3 candidatos ordenados por confianza desc | `find_top_candidates(limit=3)` + sort por score |
| AC-02 | Si el top supera el umbral, `auto_accepted=True` | `candidates[0].score >= threshold` |
| AC-03 | Sin coincidencias → 404 | `raise NoMatchFoundError` → `HTTP 404` |
| AC-04 | Imagen no identificable → 422 | `raise ImageNotIdentifiableError` → `HTTP 422` |
| AC-05 | Sin token → 401 | `Depends(get_current_user)` → `HTTP 401` |

---

### Endpoints HTTP

#### `POST /api/v2/search/quick`

```
Content-Type: multipart/form-data
Authorization: Bearer <token>

image_front:          (file, JPEG/PNG, requerido)
q:                    (string, opcional — query manual, omitido en producción)
confidence_threshold: (float, default 0.60)
```

**Respuesta exitosa (200):**

```json
{
  "candidates": [
    {
      "rank": 1,
      "candidate_card_id": "06a1bdeb-...",
      "confidence_score": 1.0,
      "name": "EDSE Pikachu n60",
      "set_name": "Ocr",
      "card_number": "1",
      "language": "en",
      "rarity": null,
      "pokemon_type": null,
      "hp": null
    },
    { "rank": 2, "confidence_score": 0.769, "name": "Pikachu n60", ... },
    { "rank": 3, "confidence_score": 0.571, "name": "Pikachu",     ... }
  ],
  "auto_accepted": true,
  "total": 3,
  "ocr_text": "EDSE Pikachu n60 Moflete Estático Lanza moneda ..."
}
```

**Respuestas de error:**

| Código | Causa | `detail` |
|---|---|---|
| 401 | Sin token / token inválido | `"Not authenticated"` |
| 404 | Query válida pero sin coincidencias | `{ "message": "...", "ocr_text": "...", "focused_q": "..." }` |
| 422 | Imagen ilegible / sin texto reconocible | `"Image not identifiable"` |
| 422 | No se envió `image_front` | `"image_front is required."` |
| 422 | Formato de imagen no soportado | `"image_front must be a JPEG or PNG image."` |

#### `POST /api/v2/search/ocr-extract`

Endpoint auxiliar para el panel de administración. Recibe la misma imagen y devuelve los campos parseados para pre-rellenar el formulario de alta de carta:

```json
{
  "raw_text": "EDSE Pikachu n60 Moflete Estático ...",
  "detected": {
    "name": "EDSE Pikachu n60",
    "hp": 60,
    "card_number": "025/185"
  }
}
```

---

### Diseño de almacenamiento específico para búsqueda rápida

```
┌────────────────────────────────────────────────────────────────────┐
│  REQUEST: POST /search/quick                                       │
│  image_front (bytes, JPEG/PNG)                                     │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │  RAM proceso │  EasyOCR Reader singleton
                    │  (~500 MB)   │  Pesos: ~/.EasyOCR/model/
                    └──────┬───────┘
                           │ lista[str] tokens OCR
                           │ _parse_card_tokens()
                           │ focused_q = "EDSE Pikachu n60"
                    ┌──────▼────────────────────┐
                    │  PostgreSQL               │
                    │  catalog_cards            │
                    │  WHERE status='active'    │
                    │  AND name LIKE '%..%'     │
                    │  LIMIT 30                 │
                    └──────┬────────────────────┘
                           │ list[(CardORM, float)]
                           │ Python: SequenceMatcher re-ranking
                    ┌──────▼────────────────────┐
                    │  QuickSearchCardUseCase   │
                    │  auto_accepted?           │
                    │  → QuickSearchOutput      │
                    └──────┬────────────────────┘
                           │
                    ┌──────▼───────────────────────┐
                    │  HTTP 200 JSON               │
                    │  candidates[0..2] + ocr_text │
                    └──────────────────────────────┘
```

**Las imágenes enviadas en el request NO se almacenan durante la búsqueda.** Los bytes se leen en memoria (`await image_front.read()`), se pasan a EasyOCR, y se descartan. El almacenamiento de la imagen ocurre **después**, en el flujo de envío (`POST /submissions`), una vez que el usuario confirma la carta identificada.

---

## Ventajas y desventajas del diseño

### Identificación por OCR (EasyOCR)

| | Detalle |
|---|---|
| ✅ **Sin base de datos de imágenes de referencia** | La identificación se basa en el texto impreso en la carta, no en comparación pixel a pixel. No se necesita una imagen de referencia por carta en el catálogo. |
| ✅ **Funciona con imágenes imperfectas** | EasyOCR tolera cierta inclinación, iluminación irregular y baja resolución (mínimo 150×150 px). |
| ✅ **Multi-idioma posible** | El modelo puede extenderse a `["en", "es"]` con un cambio de configuración; actualmente solo `"en"` porque los nombres de cartas TCG son en inglés. |
| ✅ **Sin API externa de pago** | EasyOCR corre en CPU local sin llamadas a Google Vision, AWS Textract ni similares. |
| ❌ **Sensible a texto de ataques/habilidades** | OCR lee todos los tokens de la carta. Sin `_parse_card_tokens()`, la query contendría texto irrelevante (nombres de ataques, descripciones) que nunca coincide con el catálogo. |
| ❌ **Tasa de error en nombres con fuentes estilizadas** | Las cartas más antiguas usan fuentes decorativas que EasyOCR puede leer incorrectamente (ej. "Pikachu" → "Pikachu" correcto, pero "Pik4chu" posible en fuentes muy estilizadas). |
| ❌ **Latencia de ~1–3 segundos por request** | OCR sobre CPU tarda 1–3 segundos por imagen. No es tiempo real pero es aceptable para un flujo de envío donde el usuario está interactuando activamente. |
| ❌ **Primera request lenta (~5 s)** | El singleton tarda ~5 segundos en inicializarse la primera vez (carga de pesos PyTorch). |

### Búsqueda con `LIKE` + `SequenceMatcher`

| | Detalle |
|---|---|
| ✅ **Sin infraestructura adicional** | No se necesita Elasticsearch, Redis Search ni extensión `pg_trgm`. La búsqueda corre sobre PostgreSQL estándar. |
| ✅ **Scoring diferenciado entre variantes** | `SequenceMatcher.ratio()` produce scores distintos para "Pikachu V" (0.875) vs "Pikachu VMAX" (0.737), permitiendo un ranking real. |
| ✅ **Tolerante a errores de OCR** | Si EasyOCR lee "Pikacnu" en lugar de "Pikachu", `SequenceMatcher` aún produce un score alto (~0.93) porque 6 de 7 caracteres coinciden. |
| ❌ **`LIKE '%query%'` no usa índices B-tree** | Con un catálogo grande (decenas de miles de cartas) esta consulta haría full scan. Mitigación futura: índice GIN con `pg_trgm` o `tsvector`. |
| ❌ **Sin sinónimos ni corrección semántica** | "Lightning" y "Eléctrico" no son el mismo tipo aunque signifiquen lo mismo. `SequenceMatcher` no entiende semántica. |
| ❌ **Limit pre-fetch puede perder candidatos** | Si `LIMIT 30` en SQL no incluye el candidato correcto, Python nunca lo verá. En catálogos con muchas cartas similares esto puede ser un problema. |

### Arquitectura Clean (puertos y adaptadores)

| | Detalle |
|---|---|
| ✅ **Testeable sin GPU** | `StubCardMatchingService.extract_features()` retorna `""`. Los 10 tests de integración de búsqueda corren en SQLite sin necesidad de EasyOCR. |
| ✅ **Swappable** | Reemplazar EasyOCR por un modelo propio o por un servicio cloud (Azure Computer Vision) es un cambio localizado a `EasyOCRCardMatchingService`; el use case no se modifica. |
| ❌ **Doble parsing en el router** | El router llama `extract_tokens_raw()` + `_parse_card_tokens()` antes de invocar el use case, y pasa el resultado como `query_hint`. El use case usa `query_hint` directamente. Este acoplamiento implícito requiere que el caller siempre pre-procese antes de delegar. |

---

## Consecuencias

| Aspecto | Veredicto Sprint 2 | Acción futura |
|---|---|---|
| EasyOCR CPU como motor OCR | ✅ Suficiente | Evaluar GPU o Azure Computer Vision para < 500 ms |
| `_parse_card_tokens` manual | ✅ Funcional | Mejorar con NLP o fine-tuning si la tasa de error sube |
| Búsqueda `LIKE` + SequenceMatcher | ✅ Suficiente para catálogo pequeño | Añadir índice GIN (`pg_trgm`) en Sprint 3+ |
| Imágenes NO almacenadas durante búsqueda | ✅ Correcto | Sin cambio necesario |
| Umbral configurable (default 0.60) | ✅ Ajustable por request | Calibrar con datos reales en producción |

---

## Referencias

- [EasyOCR — GitHub](https://github.com/JaidedAI/EasyOCR)
- [difflib.SequenceMatcher — Python docs](https://docs.python.org/3/library/difflib.html#difflib.SequenceMatcher)
- [SQLAlchemy — ORM Querying](https://docs.sqlalchemy.org/en/20/orm/queryguide/)
- [ADR-002 — Diseño de Almacenamiento del Sistema](./ADR-002-diseno-almacenamiento.md)
- [decisiones-diseno.md — Clean Architecture](./decisiones-diseno.md)
