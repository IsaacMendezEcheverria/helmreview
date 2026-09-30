# Política de seguridad

## Versiones con soporte

| Versión | Soporte |
|---|---|
| 1.x | ✅ Correcciones de seguridad |
| < 1.0 | ❌ |

## Cómo reportar una vulnerabilidad

**No abras un issue público.** Usa uno de estos canales privados:

- **GitHub:** pestaña *Security* → *Report a vulnerability* (GitHub Private Vulnerability Reporting).
- **GitLab:** crea un issue marcado como *confidencial*.
- **Correo:** isaac.mendez@siproset.com, con el asunto `[helmreview] seguridad`.

Incluye la versión (`helmreview --version`), cómo reproducirlo y el impacto que observas. **No incluyas
secretos ni values reales de producción.**

## Qué esperar

- Acuse de recibo en un máximo de 5 días hábiles.
- Evaluación inicial y plan de corrección en un máximo de 15 días hábiles.
- Publicación coordinada: la corrección sale en una versión PATCH y se menciona en la sección **Seguridad** del
  CHANGELOG, con crédito para quien lo reportó si así lo desea.

## Alcance

helmreview se ejecuta localmente y lee charts, values y manifiestos renderizados. Son relevantes, por ejemplo:

- Ejecución de comandos arbitrarios a partir de un chart, values o argumentos manipulados.
- Escritura de archivos fuera de las rutas indicadas (`--report`, `--json`, `--save-rendered`).
- Exposición de valores de Secrets en los reportes más allá de lo necesario para identificar el hallazgo.

Los hallazgos de las herramientas externas opcionales (kubeconform, kube-linter, trivy) deben reportarse a sus
propios proyectos.
