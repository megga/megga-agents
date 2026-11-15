{{- define "megga-agent.nom" -}}
{{- printf "%s-megga-agent" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "megga-agent.etiquettes" -}}
app.kubernetes.io/name: megga-agent
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Le pilote : d'autres étiquettes, pour que le Service et le Deployment de l'agent ne le prennent jamais pour lui. */}}
{{- define "megga-agent.etiquettes-pilote" -}}
app.kubernetes.io/name: megga-pilote
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "megga-agent.image" -}}
{{- if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else if .Values.image.tag -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- else -}}
{{- fail "image.digest (de préférence) ou image.tag : l'image signée par MEGGA" -}}
{{- end -}}
{{- end -}}

{{/* L'image d'un Deployment (dict "ctx" . "nom" <Deployment> "conteneur" <conteneur>). Avec les mises à jour par
le pilote, un « helm upgrade » garde l'image qu'il a posée tant que image.digest (ou tag) n'a pas changé dans les
valeurs : le Deployment retient en annotation l'image des valeurs à son dernier rendu. Sans accès au cluster
(helm template, Argo CD, Flux), lookup ne rend rien : l'image des valeurs. */}}
{{- define "megga-agent.image-en-place" -}}
{{- $ctx := .ctx -}}
{{- $image := include "megga-agent.image" $ctx -}}
{{- if and (eq $ctx.Values.pilotage.misesAJour true) (ne (toString $ctx.Values.pilotage.mode) "non") -}}
{{- $d := lookup "apps/v1" "Deployment" $ctx.Release.Namespace .nom -}}
{{- if and $d (eq (index ($d.metadata.annotations | default dict) "megga.ai/image-valeurs" | default "") $image) -}}
{{- range (($d.spec).template).spec.containers -}}
{{- if eq .name $.conteneur }}{{ $image = .image }}{{ end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{ $image }}
{{- end -}}

{{/* La configuration de l'agent, en texte YAML : donnée en objet (values) ou en texte (--set-file). */}}
{{- define "megga-agent.config" -}}
{{- if kindIs "string" .Values.config -}}
{{ .Values.config }}
{{- else -}}
{{ toYaml .Values.config }}
{{- end -}}
{{- end -}}
