{{- define "enterprise-knowledge-os.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "enterprise-knowledge-os.labels" -}}
app.kubernetes.io/name: {{ include "enterprise-knowledge-os.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "enterprise-knowledge-os.selectorLabels" -}}
app.kubernetes.io/name: {{ include "enterprise-knowledge-os.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
