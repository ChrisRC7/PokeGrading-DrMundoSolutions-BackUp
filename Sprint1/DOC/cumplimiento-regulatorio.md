# Cumplimiento Regulatorio — PokéGrading

---

## Alcance

Este documento identifica los marcos legales y regulatorios a los que está sujeta
la aplicación PokéGrading, junto con el estado de cumplimiento actual y la estrategia
de respuesta del equipo. Las estrategias marcadas como *Por definir* deben completarse
antes del cierre del Sprint correspondiente.

---

## Registro de regulaciones

### 1. Protección de datos personales — Ley 8968 (Costa Rica)

| Elemento | Detalle |
|---|---|
| Marco legal | Ley de Protección de la Persona frente al Tratamiento de sus Datos Personales, Costa Rica, 2011 |
| Autoridad reguladora | Agencia de Protección de Datos de los Habitantes (PRODHAB) |
| Aplica porque | La aplicación recopila nombre, correo electrónico e imágenes de usuarios residentes en Costa Rica |
| Sprint de cumplimiento | Sprint 1 (base) — revisión en Sprint 3 |
| Estado actual | En análisis |

**Obligaciones identificadas:**

| Obligación | Descripción | Estrategia de respuesta |
|---|---|---|
| Consentimiento informado | El usuario debe aceptar explícitamente el tratamiento de sus datos antes de crear una cuenta | Por definir |
| Principio de finalidad | Los datos solo pueden usarse para el fin declarado (pre-grading de cartas); no para marketing ni reventa | Por definir |
| Retención limitada | Las imágenes deben eliminarse a los 90 días de la evaluación (RNF SP4) | Configurar política de lifecycle en Azure Blob Storage |
| Derecho de acceso y supresión | El usuario puede solicitar ver o eliminar sus datos en cualquier momento | Por definir |
| Notificación de brechas | Reportar incidentes de seguridad a PRODHAB en un plazo razonable | Por definir |

---

### 2. Propiedad intelectual — The Pokémon Company (TPC)

| Elemento | Detalle |
|---|---|
| Marco legal | Derechos de propiedad intelectual y marca registrada de The Pokémon Company International |
| Aplica porque | La aplicación procesa imágenes de cartas Pokémon y referencia nombres, sets y ediciones oficiales |
| Sprint de cumplimiento | Sprint 1 (definición) — revisión continua |
| Estado actual | En análisis |

**Obligaciones identificadas:**

| Obligación | Descripción | Estrategia de respuesta |
|---|---|---|
| Uso no comercial de imágenes | Las imágenes de cartas procesadas son propiedad de TPC; el sistema no puede almacenarlas ni redistribuirlas sin licencia | Almacenamiento temporal cifrado; eliminación automática post-evaluación; no exponer imágenes en API pública |
| No suplantación de grado oficial | El sistema debe dejar claro que el resultado es una estimación (pre-grading), no una calificación oficial PSA/BGS/CGC | Agregar disclaimer obligatorio en toda respuesta de evaluación |
| Catálogo de referencia | El uso de nombres y sets oficiales en el catálogo interno debe limitarse a identificación; no para reproducción comercial | Por definir |

---

### 3. Términos de uso de APIs externas — PokéMarket API

| Elemento | Detalle |
|---|---|
| Marco legal | Términos de servicio del proveedor de la API de precios PokéMarket |
| Aplica porque | La aplicación consume la API de PokéMarket para estimaciones de valor de mercado (Etapa 7 del flujo) |
| Sprint de cumplimiento | Sprint 2 (integración) |
| Estado actual | Pendiente de revisión del contrato |

**Obligaciones identificadas:**

| Obligación | Descripción | Estrategia de respuesta |
|---|---|---|
| Rate limits | Respetar los límites de llamadas por minuto/hora definidos por PokéMarket | Implementar Circuit Breaker y cache de respuestas (TTL configurable) |
| Atribución | Indicar la fuente del precio cuando se muestra al usuario | Por definir |
| Prohibición de scraping | No extraer datos fuera de los endpoints documentados de la API | Por definir |
| Uso de datos de precios | Los precios obtenidos no pueden revenderse ni publicarse masivamente | Por definir |

---

### 4. Seguridad de aplicaciones web — OWASP Top 10

| Elemento | Detalle |
|---|---|
| Marco | OWASP Top 10 Web Application Security Risks (2021) |
| Aplica porque | Requisito no funcional S4 y S5 del proyecto; buena práctica para toda API REST |
| Sprint de cumplimiento | Sprint 1 en adelante (continuo) |
| Estado actual | Parcialmente implementado (pre-commit + detect-secrets activo) |

**Controles por riesgo OWASP:**

| Riesgo | Control implementado o planificado |
|---|---|
| A01 Broken Access Control | RBAC por rol de usuario; validación de scope en cada endpoint; por definir en Sprint 2 |
| A02 Cryptographic Failures | HTTPS obligatorio; secretos en Azure Key Vault; imágenes cifradas en tránsito y en reposo |
| A03 Injection | Validación de entradas con Pydantic; ORM SQLAlchemy (sin SQL crudo en dominio) |
| A04 Insecure Design | Arquitectura por capas con dominio aislado; patrones Repository y Facade |
| A05 Security Misconfiguration | Variables de entorno en Key Vault; sin credenciales en Git (detect-secrets) |
| A06 Vulnerable Components | Versiones fijas en pyproject.toml; revisión periódica con pip-audit |
| A07 Authentication Failures | Por definir: proveedor de identidad (Azure AD B2C o similar) en Sprint 2 |
| A08 Data Integrity Failures | Evaluaciones inmutables post-creación (RNF R4); firma de artefactos en CI |
| A09 Logging Failures | Logging estructurado obligatorio; sin datos personales en logs |
| A10 SSRF | Validar y restringir URLs de callbacks externos; no exponer endpoints internos |

---

### 5. Cumplimiento de plataforma — Microsoft Azure

| Elemento | Detalle |
|---|---|
| Marco | Microsoft Azure Compliance Offerings; términos de servicio de Azure |
| Aplica porque | La infraestructura completa se despliega en Azure (restricción técnica del proyecto) |
| Sprint de cumplimiento | Sprint 1 |
| Estado actual | Heredado de los controles de Azure |

**Compromisos relevantes:**

| Área | Cobertura de Azure | Responsabilidad del equipo |
|---|---|---|
| ISO 27001 | Azure está certificado; aplica a la infraestructura gestionada | Configurar controles de acceso y auditoría en los recursos creados |
| Retención de datos | Azure Blob lifecycle policies disponibles | Configurar y documentar las reglas de expiración |
| Disponibilidad (SLA) | Azure garantiza SLA por servicio (>= 99.9% para servicios PaaS) | Diseñar para degradación elegante cuando el SLA no se cumple |
| Residencia de datos | La región de despliegue determina dónde se almacenan los datos | Seleccionar región dentro de restricciones del proyecto y documentarlo |

---

## Matriz de estado consolidado

| Regulación | Estado | Responsable | Sprint objetivo |
|---|---|---|---|
| Ley 8968 — Consentimiento y retención | En análisis | Por asignar | Sprint 2 |
| TPC — Disclaimer de estimación | Por implementar | Desarrollador de UI/API | Sprint 2 |
| TPC — Eliminación de imágenes | Parcial (RNF SP4 documentado) | Desarrollador de infraestructura | Sprint 1 |
| PokéMarket — Revisión de términos | Pendiente | Tech Lead | Sprint 2 |
| PokéMarket — Circuit Breaker | Por implementar | Desarrollador de integración | Sprint 2 |
| OWASP — Validación de entradas | Parcial (Pydantic activo) | Todo el equipo | Sprint 1 |
| OWASP — Autenticación | Por definir | Tech Lead | Sprint 2 |
| Azure — Lifecycle de imágenes | Por configurar | Desarrollador de infraestructura | Sprint 1 |

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*
