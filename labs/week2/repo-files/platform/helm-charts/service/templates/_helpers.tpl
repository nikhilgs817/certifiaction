{{/* platform/helm-charts/service/templates/_helpers.tpl — names, labels and the pod spec shared by every workload */}}
{{- define "svc.name" -}}
{{- default .Release.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "svc.labels" -}}
app.kubernetes.io/name: {{ include "svc.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | default "none" | trunc 12 | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* selector labels never change after the first deploy (Deployment selectors are immutable) */}}
{{- define "svc.selector" -}}
app.kubernetes.io/name: {{ include "svc.name" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "svc.image" -}}
{{ required "image.repository is required" .Values.image.repository }}:{{ .Values.image.tag | default "pending" }}
{{- end -}}

{{- define "svc.env" -}}
{{- if or .Values.env .Values.envFromSecrets }}
envFrom:
  {{- if .Values.env }}
  - configMapRef:
      name: {{ include "svc.name" . }}-env
  {{- end }}
  {{- range .Values.envFromSecrets }}
  - secretRef:
      name: {{ . }}
  {{- end }}
{{- end }}
{{- if or .Values.secretEnv .Values.extraEnv }}
env:
  {{- range .Values.secretEnv }}
  - name: {{ .name }}
    valueFrom:
      secretKeyRef:
        name: {{ .secretName }}
        key: {{ .key }}
        optional: {{ .optional | default false }}
  {{- end }}
  {{- with .Values.extraEnv }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- end }}
{{- end -}}

{{/* pod spec. Call with: dict "root" $ "component" "api" "image" "<ref>" "command" [] "args" [] "resources" {} "main" true "restartPolicy" "" */}}
{{- define "svc.podSpec" -}}
{{- $v := .root.Values -}}
serviceAccountName: {{ include "svc.name" .root }}
automountServiceAccountToken: {{ $v.serviceAccount.automountToken }}
{{- if $v.imagePullSecret.name }}
imagePullSecrets:
  - name: {{ $v.imagePullSecret.name }}
{{- end }}
securityContext:
  {{- toYaml $v.podSecurityContext | nindent 2 }}
{{- with .restartPolicy }}
restartPolicy: {{ . }}
{{- end }}
containers:
  - name: {{ .component }}
    image: {{ .image | default (include "svc.image" .root) | quote }}
    imagePullPolicy: {{ $v.image.pullPolicy }}
    {{- with .command }}
    command:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- with .args }}
    args:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- if .main }}
    ports:
      - name: http
        containerPort: {{ $v.containerPort }}
      {{- if and $v.metrics.enabled $v.metrics.port }}
      - name: metrics
        containerPort: {{ $v.metrics.port }}
      {{- end }}
    startupProbe:
      httpGet: {path: {{ $v.probes.startup.path }}, port: http}
      periodSeconds: {{ $v.probes.startup.periodSeconds }}
      failureThreshold: {{ $v.probes.startup.failureThreshold }}
    livenessProbe:
      httpGet: {path: {{ $v.probes.liveness.path }}, port: http}
      periodSeconds: {{ $v.probes.liveness.periodSeconds }}
      failureThreshold: {{ $v.probes.liveness.failureThreshold }}
    readinessProbe:
      httpGet: {path: {{ $v.probes.readiness.path }}, port: http}
      periodSeconds: {{ $v.probes.readiness.periodSeconds }}
      failureThreshold: {{ $v.probes.readiness.failureThreshold }}
    {{- end }}
    {{- include "svc.env" .root | nindent 4 }}
    resources:
      {{- toYaml .resources | nindent 6 }}
    securityContext:
      {{- toYaml $v.securityContext | nindent 6 }}
    {{- if $v.tmpDir.enabled }}
    volumeMounts:
      - name: tmp
        mountPath: /tmp
    {{- end }}
{{- if $v.tmpDir.enabled }}
volumes:
  - name: tmp
    emptyDir:
      sizeLimit: {{ $v.tmpDir.sizeLimit }}
{{- end }}
{{- end -}}
