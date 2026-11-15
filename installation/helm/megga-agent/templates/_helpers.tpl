{{- define "megga-agent.nom" -}}
{{- printf "%s-megga-agent" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "megga-agent.etiquettes" -}}
app.kubernetes.io/name: megga-agent
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
