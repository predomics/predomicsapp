{{/*
PredomicsApp Helm Chart — Template Helpers
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "predomicsapp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "predomicsapp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label.
*/}}
{{- define "predomicsapp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "predomicsapp.labels" -}}
helm.sh/chart: {{ include "predomicsapp.chart" . }}
{{ include "predomicsapp.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "predomicsapp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "predomicsapp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Secret name — use existing secret or generate one.
*/}}
{{- define "predomicsapp.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- include "predomicsapp.fullname" . }}
{{- end }}
{{- end }}

{{/*
Application image (tag defaults to the chart appVersion).
*/}}
{{- define "predomicsapp.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) }}
{{- end }}

{{/*
Name of the bundled PostgreSQL service / statefulset.
*/}}
{{- define "predomicsapp.postgresqlName" -}}
{{- printf "%s-postgresql" (include "predomicsapp.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Public URL of the application ("" when unknown).
*/}}
{{- define "predomicsapp.publicUrl" -}}
{{- if .Values.publicUrl }}
{{- .Values.publicUrl | trimSuffix "/" }}
{{- else if .Values.ingress.enabled }}
{{- printf "%s://%s" (ternary "https" "http" .Values.ingress.tls.enabled) .Values.ingress.host }}
{{- end }}
{{- end }}

{{/*
Configuration checks that should stop an install/upgrade early.
*/}}
{{- define "predomicsapp.validate" -}}
{{- if ne (int .Values.replicaCount) 1 }}
{{- fail "replicaCount must be 1: PredomicsApp keeps job state in the process and uses a ReadWriteOnce volume." }}
{{- end }}
{{- if and (not .Values.postgresql.enabled) (not .Values.externalDatabase.url) (not .Values.secrets.existingSecret) }}
{{- fail "postgresql.enabled=false requires externalDatabase.url (or secrets.existingSecret with a `database-url` key)." }}
{{- end }}
{{- end }}
