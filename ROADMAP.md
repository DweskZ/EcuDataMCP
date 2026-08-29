# Roadmap

Lista corta y accionable de lo que falta, lo que está hecho, y lo que se
decidió no hacer. Para el porqué de cada ítem — hallazgos, cifras
verificadas, dominios investigados, dead ends confirmados — ver
[RESEARCH.md](RESEARCH.md).

Leyenda: `[ ]` sin empezar · `[~]` parcial · `[x]` hecho

## Nuevas conexiones de datos

- [x] SRI — datasets page (`search_sri_datasets`).
- [x] BCE — indicadores vía BCEData (`search_indicadores_bce`/`get_indicador_bce`).
- [x] Supercías — compañías, ranking financiero, auditores.
- [x] IG-EPN — catálogo sísmico (`search_sismos`).
- [x] Cuenca en Datos — CKAN municipal vía `source="cuenca"` en los tools genéricos.
- [x] Registro Civil / demográfico-salud — cobertura sólida vía CKAN, sin gaps.
- [~] IESS — boletines/auditorías/actuariales scrapeables y confirmados, sin construir tool nuevo. → RESEARCH.md § IESS
- [~] SENESCYT/Educación Superior — cubierto vía CKAN; registro de títulos bloqueado por captcha (no automatizable). → RESEARCH.md § SENESCYT
- [ ] Ecuador en Cifras / INEC — portal real y vivo, candidato fuerte, sin construir. → RESEARCH.md § Ecuador en Cifras
- [ ] BCE — Información Estadística Mensual (IEM/IEEM), boletín mensual mucho más rico que BCEData. → RESEARCH.md § BCE
- [ ] SIPA (Ministerio de Agricultura) — **prioridad máxima**, 12+ Excel reales sin fricción, reemplaza la cobertura actual de cacao/MPCEIP. → RESEARCH.md § Sitios de ministerios individuales
- [ ] Contraloría General del Estado — informes de auditoría nacionales, mecanismo de descarga ya resuelto (CSV real vía `WFDescarga.aspx`). → RESEARCH.md § Sitios de ministerios individuales
- [ ] Registro Oficial (gaceta oficial) — candidato de alta prioridad para búsqueda por fecha; posiblemente no relevante, ver nota de alcance. → RESEARCH.md § Datos legislativos
- [ ] INEVAL — exámenes nacionales (Ser Bachiller/ENES, Ser Estudiante, Ser Maestro...), archivo real sin login/captcha. → RESEARCH.md § INEVAL
- [ ] Superbancos — Portal Estadístico con boletines financieros mensuales desde 1997. → RESEARCH.md § Sitios de ministerios individuales
- [ ] MEF — workbook fiscal (recaudación arancelaria y series GFSM 2013-2026, actualizado mensualmente). → RESEARCH.md § Recaudación arancelaria
- [ ] MINEDEC — registro histórico de matrícula básica 2009-2025. → RESEARCH.md § Sitios de ministerios individuales
- [ ] SEPS — boletines de calificadoras de riesgo (`estadisticas.seps.gob.ec`, subdominio alcanzable aunque el sitio principal bloquea bots). → RESEARCH.md § Sitios de ministerios individuales
- [ ] CNIG — matriz de femicidios (actualización semanal), sin confirmar link exacto de descarga. → RESEARCH.md § Sitios de ministerios individuales
- [ ] Permisos y portales municipales — sin investigar, alcance grande (~221 GADs). → RESEARCH.md § Permisos municipales
- [ ] IGM Geoportal — cartografía gated tras registro/login, no automatizable tal cual. → RESEARCH.md § Sitios de ministerios individuales
- [ ] Fuentes externas de sociedad civil (FCD, FARO) — análisis/narrativa, no datasets crudos; decisión de alcance pendiente (no es "gobierno"). → RESEARCH.md § Fuentes externas
- [ ] Gremios privados (AEADE, ASOBANCA, FEDEXPOR) — AEADE y FEDEXPOR confirmados y descargables; ASOBANCA Datalab sin resolver extracción (SPA). → RESEARCH.md § Gremios
- [ ] Vivienda MIDUVI — dominio caído a nivel TLS, sin reemplazo encontrado; CKAN cubre parcialmente. → RESEARCH.md § Vivienda
- [ ] Prensa — SECOM/Presidencia y Fundamedios, sin profundizar. → RESEARCH.md § Prensa
- [ ] Datos legislativos/normativos (jurisprudencia, proyectos de ley) — investigado a fondo; **Daniel señaló que puede no ser relevante** para el alcance del proyecto. → RESEARCH.md § Datos legislativos
- Confirmados sin acción posible (bloqueos reales, no falta de esfuerzo): CNE y micrositio de Interior (WAF Incapsula), Aduana/SENAE comercio exterior (no publicado, solo por oficio — FEDEXPOR cubre el hueco), Fiscalía (sin dataset agregado propio). → RESEARCH.md § Sitios de ministerios individuales

## Cabos operativos sueltos

- [x] Renovación de certificado TLS.

## Calidad de búsqueda y detección de series

- [x] Expansión de siglas/acrónimos en búsqueda.
- [x] `detect_series_pattern` — clasifica acumulado/incremental/indeterminado, verificado en vivo contra IESS y MPCEIP. → RESEARCH.md § detect_series_pattern
- [ ] Búsqueda semántica sobre el catálogo completo (hoy es solo keyword de CKAN).

## Formatos y tipos de recursos

- [x] `read_pdf`, prompts, stripping de geometría/WKT, decimales europeos, `.ods`, recursos sin extensión, `.tar.gz`, `.xls` legacy, `.zip` (truncado / sin miembro tabular / CSV malformado).
- [x] `.rar` — decidido explícitamente en contra (riesgo de subprocess/CVE), no implementar.

## Verificación end-to-end

- [x] Cifras reales verificadas contra el portal: SRI, IESS, MPCEIP, `.xls`/`.zip`, degradación cuando el portal no responde. → RESEARCH.md § Verificación end-to-end de cifras

## Arquitectura, más adelante

- [ ] `outputSchema` en los tools MCP.
- [ ] Manejo geoespacial (WKT/GeoJSON más allá del stripping actual).
- [ ] Tool de investigación "one-shot" (una sola llamada que combine búsqueda + preview + detección de serie).

## Notas

- 2026-08-13: el 403 de CKAN que parecía bloqueo geográfico era un bug de vhost (`www.datosabiertos.gob.ec` es el único subdominio conectado) — ya corregido.
