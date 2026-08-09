# Estrategia de Control de Código — PokéGrading

---

## Repositorio

| Campo | Valor |
|---|---|
| Plataforma | GitHub |
| URL | https://github.com/Randall-BL/PokeGrading-DrMundoSolutions |
| Visibilidad | Privado |
| Rama principal protegida | main |
| Rama de integración del sprint | develop |
| Gestión de tareas vinculada | Azure DevOps (backlog y sprints) |

---

## Acceso al repositorio

### Requisitos previos

- Cuenta de GitHub con acceso concedido por el maintainer del equipo.
- Git instalado localmente (versión 2.40+).
- Python 3.12+ y pre-commit instalados para los hooks locales.

Solicitar acceso enviando al maintainer el nombre de usuario de GitHub y el rol en el equipo.

### Clonar por primera vez

```bash
git clone https://github.com/Randall-BL/PokeGrading-DrMundoSolutions.git
cd PokeGrading-DrMundoSolutions
```

### Configuración inicial obligatoria

```bash
# Identidad de Git (si no está configurada globalmente)
git config user.name  "Nombre Apellido"
git config user.email "correo@estudiantec.cr"

# Instalar hooks de pre-commit (bloquea secretos antes del commit)
pip install pre-commit
pre-commit install
```

### Permisos por rol

| Rol | Nivel de acceso | Puede hacer merge a main |
|---|---|---|
| Maintainer / Tech Lead | Write + administración de ramas | Si (con 2 aprobaciones) |
| Developer (miembro del equipo) | Write en ramas propias; PR para develop | No directamente |
| Reviewer externo / cliente | Read | No |

---

## Estrategia de branches

### Diagrama de estructura

```
main                     <-- producción estable; tag por cierre de sprint
  |
  develop                <-- integración continua del sprint activo
    |
    DevelopYitan         <-- rama personal de Yitan
    DevelopRandall       <-- rama personal de Randall
    Develop<Nombre>      <-- una rama por desarrollador
```

### Tipos de rama y reglas

| Tipo | Patrón de nombre | Origen | Merge hacia | Eliminación |
|---|---|---|---|---|
| Principal | main | — | — | Nunca |
| Integración | develop | main | main (fin de sprint) | Nunca |
| Personal por desarrollador | Develop<Nombre> | develop | develop | Nunca (persiste todo el proyecto) |

### Reglas obligatorias

- Nunca hacer commit directo a `main` ni a `develop`.
- Cada desarrollador trabaja exclusivamente en su rama `Develop<Nombre>`.
- La rama personal no se fusiona directamente a `main`; solo a `develop` mediante PR.
- Mantener la rama personal sincronizada con `develop` regularmente para evitar conflictos.

### Crear la rama personal (solo la primera vez)

```bash
git checkout develop
git pull origin develop
git checkout -b DevelopYitan
git push -u origin DevelopYitan
```

### Sincronizar la rama personal con develop

```bash
git checkout DevelopYitan
git fetch origin
git rebase origin/develop
```

---

## Proceso de Pull Request

### Cuándo abrir un PR

Abrir el PR cuando la historia cumple todos los criterios de las capas de Código y
Funcionalidad del DoD. No abrir PRs parciales salvo que sean Draft PR explícitos.

### Pasos

**1. Sincronizar la rama con develop antes de abrir el PR:**

```bash
git fetch origin
git rebase origin/develop
```

**2. Subir los cambios al repositorio remoto:**

```bash
git push origin DevelopYitan
```

**3. Crear el PR en GitHub:**

- Base: `develop` — Compare: `DevelopYitan` (o la rama del desarrollador correspondiente)
- Título siguiendo el formato definido (ver abajo).
- Descripción: enlace a la historia en Azure DevOps, resumen de cambios,
  instrucciones de prueba manual si aplica.
- Asignar al menos **1 reviewer** distinto al autor.
- Vincular el PR al ítem de Azure DevOps usando la palabra clave `AB#<id>` en la descripción.

**4. Revisión de código:**

- El reviewer lee los cambios, deja comentarios y aprueba o solicita cambios.
- El autor responde todos los comentarios y hace push de correcciones a la misma rama.
- No forzar el merge mientras existan comentarios sin resolver.

**5. CI verde:**

- El pipeline de Azure DevOps (lint -> tests -> build) debe completar exitosamente
  antes de poder hacer merge.

**6. Merge** (ver sección siguiente).

### Formato de título de PR

```
[Sprint N][Develop<Nombre>] Verbo en infinitivo + descripción corta del conjunto de cambios
```

Ejemplos:

```
[Sprint 1][DevelopYitan] Implementar identificación de carta por imagen
[Sprint 1][DevelopRandall] Corregir cálculo de centering en cartas rotadas
[Sprint 1][DevelopYitan] Agregar endpoint de consulta de historial de evaluaciones
```

---

## Proceso de Merge

| Aspecto | Regla |
|---|---|
| Estrategia Develop<Nombre> -> develop | Squash and merge; preserva historial limpio en develop |
| Estrategia develop -> main | Merge commit con tag de versión; al cierre de cada sprint |
| Aprobaciones mínimas Develop<Nombre> -> develop | 1 aprobación de reviewer distinto al autor |
| Aprobaciones mínimas develop -> main | 2 aprobaciones |
| CI | Pipeline en verde obligatorio antes de habilitar el botón de merge |
| Rama Develop<Nombre> | Persiste durante todo el proyecto; no se elimina tras el merge |}

---

## Protecciones de rama

### Rama main

- PR obligatorio; mínimo 2 aprobaciones.
- El CI (lint + tests + build) debe estar en verde.
- Force push y eliminación directa deshabilitados.
- Solo el maintainer puede crear el merge hacia main.

### Rama develop

- PR obligatorio; mínimo 1 aprobación.
- El CI debe estar en verde.
- Force push deshabilitado.

---

## Convenciones de commits

Formato: `tipo(alcance): descripción corta en tiempo presente`

| Tipo | Cuándo usarlo |
|---|---|
| feat | Nueva funcionalidad visible para el usuario o el sistema |
| fix | Corrección de un defecto |
| test | Agregar o corregir tests sin cambiar lógica de producción |
| docs | Cambios exclusivamente de documentación |
| refactor | Refactoring sin cambio de comportamiento observable |
| chore | Mantenimiento: dependencias, CI, configuración de herramientas |
| perf | Mejora de rendimiento sin cambio funcional |

Ejemplos:

```
feat(scoring): implementar cálculo de subgrade para esquinas
fix(api): corregir código de estado en respuesta de evaluación fallida
test(domain): agregar tests unitarios para CenteringCalculator
docs(adr): agregar ADR-001 decisión de PostgreSQL como motor principal
chore(ci): actualizar versión de ruff a 0.4.0
```

Reglas adicionales:

- Máximo 72 caracteres en la línea de encabezado.
- Si el commit cierra un ítem de Azure DevOps, agregar en el cuerpo: `Closes AB#<id>`.
- Sin commits con mensajes genéricos como "fix", "wip", "cambios" o "update".

---

## Flujo completo — resumen

```
1. git checkout DevelopYitan
2. git fetch origin && git rebase origin/develop   (sincronizar antes de trabajar)
3. (commits locales siguiendo convención de mensajes)
4. git push origin DevelopYitan
5. Abrir PR en GitHub (base: develop, 1 reviewer, CI verde)
6. Code review -> correcciones -> aprobación
7. Squash and merge a develop
8. (fin de sprint) PR develop -> main, 2 aprobaciones, tag vX.Y.Z
```

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*
