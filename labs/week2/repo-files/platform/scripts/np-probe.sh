#!/usr/bin/env bash
# platform/scripts/np-probe.sh — NetworkPolicy check: can a pod with (or without) a label reach timescale or redis?
# Usage: np-probe.sh <namespace> <key=value|none> <timescale|redis>     prints REACHABLE or BLOCKED
set -euo pipefail
NS="${1:?}"; LABEL="${2:?}"; TARGET="${3:?}"
case "$TARGET" in
  timescale)
    IMAGE="timescale/timescaledb:2.31.0-pg18@sha256:0fcff5761363809d1242f2261a3482197b5a5337407f8b97a976fb174206d579"
    CMD="pg_isready -h timescale -p 5432 -t 5" ;;
  redis)
    IMAGE="redis:8.10.3-alpine@sha256:21090af93f8324db2f0f0f4f38a7c60369d47d917e000c3423d89d2ae2883537"
    CMD="timeout 5 redis-cli -h redis -p 6379 --no-auth-warning ping | grep -qE 'PONG|NOAUTH'" ;;
  *) echo "target must be timescale or redis"; exit 2 ;;
esac
NAME="np-probe-$RANDOM"
EXTRA=""
[ "$LABEL" = none ] || EXTRA="    ${LABEL%%=*}: \"${LABEL#*=}\""
kubectl -n "$NS" apply -f - >/dev/null <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $NAME
  labels:
    app.kubernetes.io/name: np-probe
$EXTRA
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  securityContext: {runAsNonRoot: true, runAsUser: 65534, runAsGroup: 65534, seccompProfile: {type: RuntimeDefault}}
  containers:
    - name: probe
      image: "$IMAGE"
      command: ["sh", "-c", "$CMD"]
      resources: {requests: {cpu: 10m, memory: 16Mi}, limits: {memory: 64Mi}}
      securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
YAML
phase=Pending
for _ in $(seq 1 40); do
  phase=$(kubectl -n "$NS" get pod "$NAME" -o jsonpath='{.status.phase}')
  case "$phase" in Succeeded|Failed) break ;; esac
  sleep 1
done
kubectl -n "$NS" delete pod "$NAME" --wait=false >/dev/null
if [ "$phase" = Succeeded ]; then r=REACHABLE; else r=BLOCKED; fi
echo "$r   label=$LABEL -> $TARGET"
