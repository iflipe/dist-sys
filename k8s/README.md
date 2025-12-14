# Kubernetes Manifests

The `k8s/` folder contains minimal manifests for running the three replicas inside a local Minikube or any Kubernetes cluster.

## Files

- `configmap.yaml` – shared configuration (total servers + initial leader seed).
- `deployments.yaml` – three single-replica Deployments (`coord-node1..3`) that set per-node IDs and ring neighbors while reusing the shared ConfigMap.
- `services.yaml` – cluster-internal Services so pods can reach each other via stable DNS hostnames (e.g., `http://coord-node2:8000`).

## Usage

1. Build and push an image the cluster can pull (or use `minikube image load`):
   ```sh
   docker build -t coordination-service:latest .
   minikube image load coordination-service:latest
   ```
2. Apply the resources:
   ```sh
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/deployments.yaml
   kubectl apply -f k8s/services.yaml
   ```
3. Confirm pods are healthy:
   ```sh
   kubectl get pods -l app=coordination
   ```
4. To reach a specific replica from your machine, use `kubectl port-forward svc/coord-node1 8000:8000` (and similar for the others).
