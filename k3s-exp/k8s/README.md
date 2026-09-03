# Deploying to k3s

Deploys the `k3s-exp` NiceGUI+FastAPI single-process build of the Northstar
assistant to a personal k3s cluster, reachable at `northstar.sv5.de` over
plain HTTP. Separate from, and does not touch, the root Streamlit+FastAPI
app or its own Docker packaging.

**Topology:** one image, one `Deployment` (1 replica — see the comment in
`deployment.yaml` for why that's a hard requirement, not a preference),
one `Service`, one Traefik `IngressRoute`. No registry — the image is
built locally and imported directly into the cluster node's containerd.

## Prerequisites

- Docker with `buildx` on your build machine (checked in this repo's dev
  session: `arm64` Mac + Docker Desktop's bundled buildx — cross-building
  for the VM's `x86_64` architecture).
- SSH access to the k3s VM, and enough free disk there to hold the image
  tar temporarily (the VM had ~15GB free at last check — the image itself
  is in the 4-5GB range after the CPU-only-torch optimization already
  applied to the root app's image; delete the tar after import, step 4).
- `kubectl` configured against the cluster (run directly on the VM via
  SSH, or from your build machine if its kubeconfig already points at
  this cluster).
- `northstar.sv5.de` must resolve to the VM's reachable IP — this is
  existing DNS/router infrastructure outside this repo's scope; confirm
  it resolves before step 8, not after.

## 1. Build (cross-built for the VM's architecture)

From the **repo root** (not from inside `k3s-exp/`):

```bash
docker buildx build --platform linux/amd64 \
  -f k3s-exp/Dockerfile \
  -t northstar-assistant-k3s-exp:latest \
  --load .
```

`--load` puts the built image into your local Docker daemon (needed for
step 2's `docker save`) rather than only buildx's build cache.

## 2. Save the image to a tar

```bash
docker save northstar-assistant-k3s-exp:latest -o northstar-assistant-k3s-exp.tar
```

## 3. Transfer it to the VM

```bash
scp northstar-assistant-k3s-exp.tar <user>@<vm-host>:/tmp/
```

## 4. Import into the VM's containerd, then delete the tar

SSH into the VM for this and the remaining steps:

```bash
ssh <user>@<vm-host>

sudo k3s ctr images import /tmp/northstar-assistant-k3s-exp.tar
rm /tmp/northstar-assistant-k3s-exp.tar   # frees the disk space — don't skip this
```

Confirm it landed:

```bash
sudo k3s ctr images list | grep northstar-assistant-k3s-exp
```

## 5. Create the namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

## 6. Create the secret (never committed)

```bash
kubectl create secret generic northstar-secrets \
  --namespace northstar \
  --from-literal=GROQ_API_KEY=<your-groq-api-key>
```

(`GITHUB_TOKEN` isn't needed — the configured live repository is public.
If you ever point this at a private repo, add
`--from-literal=GITHUB_TOKEN=<token>` to the command above and reference
it the same way `GROQ_API_KEY` is referenced in `deployment.yaml`.)

## 7. Apply the rest of the manifests

```bash
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingressroute.yaml
```

## 8. Verify

```bash
kubectl get pods -n northstar -w
```

Wait for `1/1 Running` (the `startupProbe`'s budget is ~3 minutes — heavy
imports plus the startup index sync take real time). Then:

```bash
kubectl logs -n northstar deploy/northstar-assistant
```

Look for a clean startup sync (no repeated tracebacks — a single caught
sync failure is non-fatal by design, see `app.py`'s `lifespan` handler).

Finally, open `http://northstar.sv5.de/` in a browser — chat and the
pending actions panel should work immediately. **`/evaluation` will say
"No results yet" until step 8a below** — that's expected on a fresh PVC,
not a bug. Confirm a pod restart doesn't lose state:

```bash
kubectl delete pod -n northstar -l app=northstar-assistant
# wait for the replacement pod to become Ready, then re-check the app —
# the semantic index and any feedback recorded should still be there.
```

## 8a. Populate the evaluation dashboard (one-time)

`data/generated/evaluation_results.json` is the Phase 8 harness's output —
it's git-ignored and never baked into the image (same reasoning as
`data/index`/`data/feedback`: it's runtime/local state). Nothing in the
running app writes it automatically; only running the harness does. On a
fresh `northstar-generated-data` PVC there's simply no file there yet,
which is exactly what "No results yet" means — this isn't a k8s-specific
bug, it's the same gap Phase 9's Docker packaging hit for the root app
(see `deliverables/DECISIONS.md`), fixed there with the equivalent
`docker compose cp`. Copy your existing local results file into the pod
once, from your own machine (where the file actually exists):

```bash
kubectl cp data/generated/evaluation_results.json \
  northstar/$(kubectl get pod -n northstar -l app=northstar-assistant -o jsonpath='{.items[0].metadata.name}'):/app/data/generated/evaluation_results.json
```

Refresh `http://northstar.sv5.de/evaluation` — it should now show the same
dashboard as local. This needs re-running any time the PVC is recreated
(e.g. after `kubectl delete pvc`), but survives ordinary pod restarts.

## Redeploying after a code change

Repeat steps 1-4 with the same image tag, then force the Deployment to
actually restart with the freshly-imported image (`imagePullPolicy: Never`
plus an unchanged tag means Kubernetes has no other signal that the image
changed):

```bash
kubectl rollout restart deployment/northstar-assistant -n northstar
```

## Troubleshooting

- **Pod stuck `Pending`**: `kubectl describe pod -n northstar <pod>` —
  almost always a PVC that hasn't bound yet (`local-path`'s provisioner
  runs on first use, should resolve within seconds) or a resource request
  the node can't currently satisfy.
- **Pod `CrashLoopBackOff`**: `kubectl logs -n northstar <pod> --previous`
  — check first for a missing/misspelled `northstar-secrets` key (a
  missing `GROQ_API_KEY` fails at first model call, not at startup, so
  this usually shows as a request-time error, not a crash).
- **`ErrImageNeverPull`**: the image wasn't actually imported on this
  node, or the tag doesn't match `deployment.yaml`'s `image:` field
  exactly — re-check step 4's `k3s ctr images list` output.
- **`northstar.sv5.de` doesn't load but the pod is `Running`**: check the
  IngressRoute actually registered (`kubectl get ingressroute -n
  northstar`) and that DNS resolves to the right IP — this is the one
  prerequisite this repo can't verify for you.
