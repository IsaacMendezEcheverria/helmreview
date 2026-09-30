# Arquitectura

## Estructura del repositorio

```
helmreview/
├── src/helmreview/
│   ├── __init__.py          # __version__ (fuente única de la versión)
│   ├── __main__.py          # python -m helmreview
│   ├── cli.py               # argparse -> ReviewOptions -> review_chart -> reportes -> exit code
│   ├── options.py           # ReviewOptions: opciones independientes del CLI
│   ├── review.py            # review_chart(): orquesta una revisión completa
│   ├── models.py            # Finding, Capacity, Storage, ChartReport, severidades
│   ├── constants.py         # tablas de referencia (APIs deprecadas, OCP->K8s, capabilities...)
│   ├── quantities.py        # parseo/formato de CPU y memoria
│   ├── k8s.py               # utilidades sobre objetos K8s (selectors, pod template, imagen)
│   ├── helm.py              # llamadas a helm (lint, template, show) y parseo del render
│   ├── external.py          # kubeconform / kube-linter / trivy (opcional)
│   ├── checks/
│   │   ├── chart_meta.py    # Chart.yaml y archivos del chart
│   │   ├── manifests.py     # orquestación + checks por Kind (tabla KIND_CHECKS)
│   │   └── workloads.py     # pods: HA, recursos, probes, seguridad, SCC
│   └── report/
│       ├── tables.py        # cálculo de filas de capacidad/almacenamiento (compartido)
│       ├── console.py
│       ├── markdown.py
│       └── json_report.py
├── tests/
│   ├── conftest.py          # helpers: analyze_text, analyze_file, checks_for
│   ├── fixtures/charts/     # charts de prueba (sample = chart "limpio" para integración con helm)
│   ├── fixtures/rendered/   # YAML renderizados con problemas conocidos
│   └── test_*.py
├── docs/
├── .github/                 # GitHub Actions (ci, release), plantillas de issues/PR, Dependabot
├── .gitlab/                 # plantillas de issues/MR de GitLab
├── .gitlab-ci.yml           # pipeline de GitLab
└── .cloudbuild/             # Google Cloud Build (ci, release) y triggers de Secure Source Manager
```

Las tres configuraciones de CI hacen lo mismo; ver [ci-platforms.md](ci-platforms.md).

## Flujo de una revisión

```
cli.main(argv)
  └─ options_from_args()                → ReviewOptions
  └─ por cada chart: review.review_chart(chart, opts)
        ├─ helm.load_chart_yaml()       → checks.chart_meta.check_chart_meta()
        ├─ helm.dependency_build()      (si --dep-update)
        ├─ helm.lint()                  (si es directorio y no --skip-lint)
        ├─ helm.template()              (o lee --rendered)
        ├─ helm.parse_manifests()       → [(objeto, template_origen)]
        ├─ checks.manifests.analyze()
        │     ├─ _build_context()       → HPAs, PDBs, NetworkPolicies, workloads (relaciones cruzadas)
        │     ├─ checks globales        (api-deprecada, namespace-fijo)
        │     ├─ workloads.analyze_workload()   para Kinds en WORKLOADS
        │     └─ KIND_CHECKS[kind]()            para el resto
        └─ external.run_external()      (si --external)
  └─ report.print_console / write_markdown / write_json
  └─ exit code (0 / 1 / 2)
```

## Decisiones de diseño

- **Análisis sobre el render, no sobre los templates.** Se evalúa lo que realmente llegaría al cluster con los
  values de cada entorno. Por eso importa pasar los mismos `-f` que usa el pipeline de despliegue.
- **Sin acceso al cluster.** Todo es offline. La versión de K8s y las APIs de OpenShift se simulan con
  `--kube-version` y `--api-versions`.
- **IDs de checks estables.** Son el contrato con los usuarios (`--ignore`, filtros sobre el JSON). Ver
  docs/checks.md.
- **`ChartReport.add()` es el único punto de entrada de hallazgos.** Ahí se aplica `--ignore`, de modo que los
  checks no necesitan saber qué está ignorado.
- **Plataforma como parámetro de contexto**, no como fork del código. Los checks consultan `ctx.openshift` para
  ajustar severidad o agregar validaciones.
- **Única dependencia de runtime: PyYAML.** La herramienta debe poder instalarse en estaciones y runners con
  acceso limitado a internet.
