{{- define "soe-sidecar.name" -}}
{{- .Values.app.name | default .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "soe-sidecar.labels" -}}
app.kubernetes.io/name: {{ include "soe-sidecar.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "soe-sidecar.selectorLabels" -}}
app.kubernetes.io/name: {{ include "soe-sidecar.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
