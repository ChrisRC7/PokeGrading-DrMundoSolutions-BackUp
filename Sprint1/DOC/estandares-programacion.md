# Estándares de Programación — PokéGrading

---

## Alcance

Este documento define las convenciones de código obligatorias para todos los lenguajes
y herramientas del stack de PokéGrading (Sprint 1 en adelante).
Su cumplimiento es condición del **Definition of Done**.

---

## Python 3.12+

### Formato y linting

| Herramienta | Regla | Configuración |
|---|---|---|
| Black | Formateo automático obligatorio; longitud de línea 88 caracteres | pyproject.toml |
| isort | Orden de imports compatible con Black (profile = "black") | pyproject.toml |
| ruff / flake8 | Sin errores E ni W bloqueantes antes del commit | pyproject.toml / .flake8 |
| mypy | Type hints obligatorios en funciones públicas; modo básico en Sprint 1 | mypy.ini |

Fragmento de configuración mínima en `pyproject.toml`:

```toml
[tool.black]
line-length = 88

[tool.isort]
profile = "black"

[tool.ruff]
line-length = 88
select = ["E", "W", "F"]
```

### Nomenclatura

| Elemento | Convención | Ejemplo |
|---|---|---|
| Variables y funciones | snake_case | card_grade, calculate_score() |
| Clases y excepciones | PascalCase | EvaluationService, CardNotFoundError |
| Constantes de módulo | UPPER_SNAKE_CASE | MAX_CONFIDENCE = 1.0 |
| Archivos y módulos | snake_case | scoring_pipeline.py |
| Paquetes | snake_case sin guiones | image_processing/ |
| Parámetros privados | _snake_case con guión bajo inicial | _cached_result |

### Type hints

Obligatorios en toda función y método público. El tipo de retorno siempre se declara
explícitamente. Usar `T | None` en lugar de `Optional[T]` (sintaxis Python 3.10+):

```python
def calculate_centering(image: np.ndarray, threshold: float = 0.8) -> float:
    ...

def find_card(card_id: int) -> Card | None:
    ...
```

### Docstrings

Estilo **Google**. Obligatorios en toda clase y en toda función con más de 2 parámetros.
Los endpoints de FastAPI usan el docstring como descripción en la documentación OpenAPI.

```python
def calculate_centering(image: np.ndarray, threshold: float = 0.8) -> float:
    """Calcula el ratio de centering de la carta.

    Args:
        image: Imagen preprocesada en formato BGR.
        threshold: Valor mínimo aceptable para considerar la carta centrada.

    Returns:
        Ratio de centering entre 0.0 y 1.0.

    Raises:
        ValueError: Si la imagen no tiene dimensiones válidas.
    """
```

### Estructura de carpetas

```
src/
  domain/           # Entidades, value objects, interfaces de repositorio
  application/      # Servicios de aplicación, casos de uso
  infrastructure/   # Implementaciones: DB, Azure Blob, APIs externas
  api/              # Routers FastAPI, schemas Pydantic, dependencias
  core/             # Configuración, logging, excepciones base
tests/
  unit/             # Tests sin dependencias externas
  integration/      # Tests con base de datos de prueba
```

---

## FastAPI

| Aspecto | Regla |
|---|---|
| Routers | Un archivo por dominio funcional; ejemplo: evaluation_router.py, card_router.py |
| Schemas Pydantic | Separar Request y Response schema; nunca exponer entidades de dominio directamente |
| HTTP status codes | 200 para consulta, 201 para creación, 202 para tarea asíncrona, 422 para validación |
| Manejo de errores | Usar HTTPException con detalle estructurado; nunca retornar 500 sin log previo |
| Async | Todo endpoint con I/O de red o base de datos debe ser async def |
| Versioning | Prefijo /api/v1/ en todos los routers desde el primer endpoint |
| Dependencias | Inyectar sesión de DB y servicios mediante Depends(); no instanciar en el endpoint |

---

## SQLAlchemy / Alembic

| Aspecto | Regla |
|---|---|
| Modelos ORM | Heredar de Base declarativo; nombres de tabla en snake_case plural (evaluations, cards) |
| Relaciones | Definir relationship() con lazy="select" por defecto; documentar cambios a joined |
| Migraciones Alembic | Nombre: YYYYMMDD_descripcion_corta.py; una migración por cambio lógico |
| Transacciones | El servicio de aplicación controla el commit; el repositorio nunca llama a commit() |
| SQL crudo | Prohibido en capas de dominio y aplicación; solo en repositorios con justificación |

---

## pytest

| Aspecto | Regla |
|---|---|
| Nombre de test | test_accion_condicion_resultado; describe qué se prueba y qué se espera |
| Fixtures | Definir en conftest.py al nivel más bajo necesario; no duplicar fixtures entre carpetas |
| Cobertura mínima | >= 75% en src/domain/ y src/application/; medido con pytest-cov en CI |
| Tests asíncronos | Usar pytest-asyncio para tests de endpoints y repositorios async |
| Datos de prueba | Sin datos reales de cartas PSA certificadas; usar fixtures sintéticas documentadas |

Ejemplo de nombre correcto:

```
test_calculate_centering_given_centered_card_returns_value_above_threshold
test_evaluate_card_when_market_api_unavailable_returns_degraded_result
test_create_evaluation_given_invalid_image_raises_validation_error
```

---

## OpenCV / Pillow

| Aspecto | Regla |
|---|---|
| Formato interno | Usar BGR (OpenCV nativo) dentro del pipeline de procesamiento; convertir a RGB solo en salida |
| Tipos de datos | Declarar dtype explícito al crear arrays (np.uint8, np.float32); no asumir dtype de entrada |
| Recursos | Liberar memoria de imágenes grandes al finalizar cada etapa del pipeline |
| Constantes | Definir umbrales y parámetros como constantes nombradas en core/config.py; no hardcodear |
| Logging | Loguear dimensiones y dtype al inicio y al final de cada etapa; nunca la imagen completa |

---

## Seguridad del código

- Ningún secreto, token ni contraseña puede existir en el código ni en el historial de Git.
  Verificado por pre-commit + detect-secrets antes de cada commit.
- Toda entrada externa se valida con Pydantic antes de llegar a la capa de dominio.
- Los logs nunca incluyen datos personales, imágenes ni tokens; solo identificadores y metadatos.
- Las dependencias tienen versiones fijas en pyproject.toml o requirements.txt;
  no usar rangos abiertos (`>=`) en producción.
- Las variables de entorno (DATABASE_URL, AZURE_STORAGE_KEY, etc.) se leen desde
  un archivo .env excluido de Git; usar python-dotenv o Azure Key Vault.

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*
