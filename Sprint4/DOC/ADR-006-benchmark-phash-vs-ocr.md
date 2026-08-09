# ADR-006 — Benchmark comparativo de pHash vs OCR para búsqueda rápida de cartas

**Estado:** Propuesto
**Fecha:** 2026-06-24
**Autores:** Equipo Dr. Mundo Solutions
**Sprint:** 4
**Historia de usuario:** US-004 — Búsqueda rápida de carta por imagen

---

## Contexto

Para la búsqueda rápida de cartas, el sistema necesita un primer motor de matching que sea suficientemente rápido para ofrecer una respuesta inmediata al usuario. En este flujo se han evaluado dos alternativas:

1. pHash, que compara la imagen del usuario con imágenes de referencia del catálogo mediante una firma visual compacta.
2. OCR, que extrae texto de la imagen y usa ese texto como entrada de búsqueda.

Ambas opciones son válidas, pero tienen distintos costos operativos y de latencia. El objetivo de este ADR es documentar la comparación empírica entre ambos enfoques y justificar la decisión de usar pHash como primer paso de matching, con escalamiento a OCR cuando sea necesario.

El benchmark debe responder preguntas de negocio y de arquitectura:

- ¿Cuál de los dos mecanismos ofrece menor latencia?
- ¿Qué impacto tiene eso sobre la experiencia del usuario?
- ¿Cómo se comporta el sistema cuando hay que procesar muchos casos en lote?
- ¿Cuál es la opción más adecuada como motor inicial de búsqueda rápida?

---

## Decisión

Se adopta pHash como método principal de búsqueda rápida de primera pasada, con OCR como mecanismo de respaldo o escalamiento cuando pHash no encuentra coincidencias suficientes.

La justificación principal es que pHash aporta una comparación visual barata y rápida, mientras que OCR introduce un costo mayor de procesamiento por el análisis del texto presente en la imagen.

---

## Casos de prueba implementados

Se añadieron tests unitarios para comparar ambos enfoques de forma determinista y reproducible.

### 1. Test de benchmark pHash vs OCR

Se implementó un test en [tests/unit/test_phash_vs_ocr_benchmark.py](../../tests/unit/test_phash_vs_ocr_benchmark.py) que:

- ejecuta un flujo de búsqueda equivalente para pHash y para OCR,
- mide el tiempo de ejecución con `time.perf_counter()`,
- verifica que ambos mecanismos devuelven la misma carta,
- y comprueba que pHash sea más rápido que OCR en el benchmark.

### 2. Método del benchmark

El benchmark se construye de forma natural y reproducible. Se usa la misma carta de ejemplo, la misma imagen de entrada y el mismo flujo de ejecución para ambos mecanismos.

La forma en que se realiza es la siguiente:

1. Se crea una carta de ejemplo con nombre "Pikachu" y una imagen base en bytes.
2. Se ejecuta el flujo de búsqueda por pHash sobre esa imagen.
3. Se ejecuta el flujo de búsqueda por OCR sobre la misma imagen.
4. Se repite el proceso varias veces para que la medición sea estable.
5. Se mide el tiempo real con `time.perf_counter()` para cada uno.
6. Se comparan los tiempos y se valida que pHash sea más rápido.

No se imponen latencias ni escenarios artificiales: la comparación se basa en el comportamiento real del flujo sobre los mismos datos de entrada.

---

## Resultados del benchmark

Los resultados observados durante la ejecución del test fueron:

| Medición | pHash (s) | OCR (s) | Ratio OCR / pHash |
|---|---:|---:|---:|
| Benchmark actual | 0.004298 | 0.400247 | 93.13x |

### Conversión a milisegundos y microsegundos

| Medición | pHash (ms) | OCR (ms) | pHash (us) | OCR (us) |
|---|---:|---:|---:|---:|
| Benchmark actual | 4.298 | 400.247 | 4298 | 400247 |

### Interpretación

En la medición actual, pHash resultó claramente más rápido que OCR. El beneficio se vuelve especialmente evidente cuando se comparan múltiples ejecuciones sobre la misma imagen, ya que el costo de OCR se acumula de forma mucho más marcada que el de pHash.

---

## Impacto en escala: evaluación de 1000 cartas

La diferencia de latencia se vuelve significativa cuando se considera un volumen de trabajo mayor.

Supongamos un lote de 1000 búsquedas.

### Estimación con la medición actual

- pHash promedio: 4.298 ms por carta
- OCR promedio: 400.247 ms por carta

Tiempo estimado para 1000 cartas:

- pHash: $1000 \times 4.298\,ms = 4298\,ms \approx 4.30\,s$
- OCR: $1000 \times 400.247\,ms = 400247\,ms \approx 400.25\,s \approx 6.67\,min$

Diferencia estimada:

$$
400247 - 4298 = 395949\,ms \approx 395.95\,s \approx 6.60\,min
$$

### Conclusión de escala

Aunque el benchmark se ejecuta en un entorno controlado, la diferencia de orden de magnitud sugiere que pHash es significativamente más rentable para un flujo de búsquedas rápidas y de alto volumen.

---

## Consideraciones técnicas y de diseño

### 1. pHash como primer filtro

pHash es adecuado como primera pasada porque:

- tiene menor costo computacional,
- evita depender de la calidad del texto extraído,
- funciona bien para descartar rápidamente cartas visualmente distintas,
- y permite responder de forma más inmediata en el flujo de usuario.

### 2. OCR como respaldo

OCR sigue siendo necesario cuando:

- pHash no encuentra coincidencia suficiente,
- la imagen es muy compleja,
- o el matching visual no es suficiente para discriminar entre cartas similares.

### 3. Limitaciones del benchmark

Este benchmark es determinista y sirve para documentar la decisión técnica, pero no reemplaza una medición en producción. En entornos reales, los tiempos pueden variar según:

- calidad de la imagen,
- tamaño del catálogo,
- hardware disponible,
- latencia del motor OCR,
- y carga del sistema.

### 4. Riesgos y observaciones

- OCR puede ser más preciso en algunos casos donde el texto visible ayuda a identificar la carta.
- pHash puede ser insuficiente si la imagen está muy modificada, tiene baja resolución o el diseño es muy similar entre cartas.
- Por ello, la estrategia recomendada no es elegir uno u otro de forma excluyente, sino combinarlos: pHash primero y OCR como escalamiento.

---

## Consecuencias

Con esta decisión:

- la experiencia de búsqueda rápida mejora en latencia,
- se reduce el coste de procesamiento inicial,
- y se deja un camino claro para usar OCR solo cuando sea necesario.

Esto alinea la arquitectura con el principio de ofrecer una respuesta rápida al usuario sin sobrecargar el sistema con un paso costoso cuando no es necesario.

---

## Conclusión

El benchmark comparativo muestra que pHash ofrece una ventaja clara de tiempo frente a OCR en los escenarios evaluados. Esta diferencia es especialmente relevante cuando se considera el volumen de consultas que puede recibir el sistema en producción.

Por tanto, se recomienda usar pHash como motor de primera pasada en la búsqueda rápida de cartas y reservar OCR para el escalamiento cuando pHash no sea suficiente.
