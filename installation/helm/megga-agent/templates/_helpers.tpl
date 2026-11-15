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

{{/* La configuration de l'agent, en texte YAML : donnée en objet (values) ou en texte (--set-file). */}}
{{- define "megga-agent.config" -}}
{{- if kindIs "string" .Values.config -}}
{{ .Values.config }}
{{- else -}}
{{ toYaml .Values.config }}
{{- end -}}
{{- end -}}
