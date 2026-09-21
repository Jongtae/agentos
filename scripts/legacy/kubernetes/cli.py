"""Administrator-only provisioning CLI. Always requires explicit kubeconfig."""
import argparse
import json
import re
import secrets
import subprocess


def manifests(owner, image, token):
    if not re.fullmatch('[a-z][a-z0-9-]{0,30}[a-z0-9]|[a-z]', owner):
        raise ValueError('owner must be a lowercase DNS label, 1–32 characters')
    ns = 'agent-' + owner
    def obj(api, kind, name, **fields):
        return dict(apiVersion=api, kind=kind, metadata={'name': name, 'namespace': ns}, **fields)
    labels = {'app': 'personal-agent'}
    return [
        {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': ns, 'labels': {
            'agentos.dev/managed': 'true', 'pod-security.kubernetes.io/enforce': 'restricted'}}},
        obj('v1', 'ServiceAccount', 'runtime', automountServiceAccountToken=False),
        obj('v1', 'Secret', 'identity', type='Opaque', stringData={'token': token}),
        obj('v1', 'PersistentVolumeClaim', 'data', spec={'accessModes': ['ReadWriteOnce'], 'resources': {'requests': {'storage': '1Gi'}}}),
        obj('v1', 'ResourceQuota', 'budget', spec={'hard': {'pods': '3', 'requests.cpu': '1', 'requests.memory': '512Mi', 'limits.cpu': '2', 'limits.memory': '1Gi', 'requests.storage': '2Gi', 'persistentvolumeclaims': '2'}}),
        obj('networking.k8s.io/v1', 'NetworkPolicy', 'isolate', spec={
            'podSelector': {}, 'policyTypes': ['Ingress', 'Egress'],
            'ingress': [{'from': [{'podSelector': {}}], 'ports': [{'protocol': 'TCP', 'port': 8080}]}], 'egress': []}),
        obj('v1', 'Service', 'runtime', spec={'selector': labels, 'ports': [{'port': 8080, 'targetPort': 8080}]}),
        obj('apps/v1', 'Deployment', 'runtime', spec={
            'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': labels},
            'template': {'metadata': {'labels': labels}, 'spec': {
                'serviceAccountName': 'runtime', 'automountServiceAccountToken': False,
                'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'runAsGroup': 10001, 'fsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [{'name': 'runtime', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                    'ports': [{'containerPort': 8080}],
                    'env': [{'name': 'AGENT_OWNER', 'value': owner}, {'name': 'AGENT_TOKEN', 'valueFrom': {'secretKeyRef': {'name': 'identity', 'key': 'token'}}}],
                    'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                    'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '256Mi'}},
                    'volumeMounts': [{'name': 'data', 'mountPath': '/data'}],
                    'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 8080}, 'initialDelaySeconds': 1, 'periodSeconds': 2},
                    'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 8080}, 'initialDelaySeconds': 5, 'periodSeconds': 10}}],
                'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'data'}}]}}})]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconfig', required=True)
    parser.add_argument('action', choices=['create', 'pause', 'resume', 'status', 'connect'])
    parser.add_argument('owner')
    parser.add_argument('--image', default='personal-agent:dev')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    # Validate before using the owner in any kubectl argument.
    objects = manifests(args.owner, args.image, secrets.token_urlsafe(32))
    ns = 'agent-' + args.owner
    base = ['kubectl', '--kubeconfig', args.kubeconfig]
    def run(*command, **kwargs):
        return subprocess.run(base + list(command), check=True, **kwargs)
    if args.action == 'create':
        existing = run('get', 'namespace', ns, '--ignore-not-found', '-o', 'name', capture_output=True, text=True)
        if existing.stdout.strip():
            parser.error('environment already exists; use resume (credentials are never silently rotated)')
        run('create', '-f', '-', input=json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': objects}), text=True, stdout=subprocess.DEVNULL)
        print('Created ' + ns + '. Token stored only in Kubernetes Secret identity.')
        run('-n', ns, 'rollout', 'status', 'deployment/runtime', '--timeout=120s')
    elif args.action in ('pause', 'resume'):
        run('-n', ns, 'scale', 'deployment/runtime', '--replicas=' + ('0' if args.action == 'pause' else '1'))
        if args.action == 'resume':
            run('-n', ns, 'rollout', 'status', 'deployment/runtime', '--timeout=120s')
    elif args.action == 'status':
        run('-n', ns, 'get', 'deployment,pod,pvc,service')
    else:
        run('-n', ns, 'port-forward', 'service/runtime', str(args.port)+':8080', '--address=127.0.0.1')


if __name__ == '__main__':
    main()
