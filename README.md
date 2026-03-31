# CheckoutOS on K3s/AWS — end-to-end deployment pack

This pack takes your existing **checkout-app-v2** Flask microservices application and gives you the missing deployment layer:
- image build and push scripts
- Kubernetes manifests for K3s
- deployment and validation scripts
- a step-by-step runbook

It assumes:
- your **application source** is already available locally in `checkout-app/`
- your **K3s cluster is already running** on AWS
- Traefik is installed by K3s and listening on node ports 80/443
- your AWS NLB already forwards 80/443 to the K3s nodes

## What is included

```text
checkout-k8s-pack/
├─ manifests/
│  ├─ 00-namespace.yaml
│  ├─ 01-configmap.yaml
│  ├─ 02-secret.yaml
│  ├─ 03-postgres-pvc.yaml
│  ├─ 04-postgres-deployment.yaml
│  ├─ 05-postgres-service.yaml
│  ├─ 10-pricing-deployment.yaml
│  ├─ 11-pricing-service.yaml
│  ├─ 12-inventory-deployment.yaml
│  ├─ 13-inventory-service.yaml
│  ├─ 14-checkout-deployment.yaml
│  ├─ 15-checkout-service.yaml
│  ├─ 16-gateway-deployment.yaml
│  ├─ 17-gateway-service.yaml
│  ├─ 18-quote-deployment.yaml
│  ├─ 19-quote-service.yaml
│  ├─ 20-ingress.yaml
│  └─ 21-toolbox.yaml
├─ scripts/
│  ├─ dockerhub-build-push.sh
│  ├─ ecr-build-push.sh
│  ├─ deploy.sh
│  ├─ smoke-tests.sh
│  └─ db-check.sh
└─ optional/
   └─ keda-note.md
```

## Important note about Dockerfiles

Your application already includes service Dockerfiles in:
- `checkout-app/gateway/Dockerfile`
- `checkout-app/checkout/Dockerfile`
- `checkout-app/pricing/Dockerfile`
- `checkout-app/inventory/Dockerfile`
- `checkout-app/quote/Dockerfile`

This pack **reuses those Dockerfiles**. You do not need to create new ones unless you want to harden them further.

## 1. Build and push container images

You have two choices.

### Option A — Docker Hub

Edit the script variables if needed, then run:

```bash
cd checkout-k8s-pack/scripts
chmod +x *.sh
./dockerhub-build-push.sh /path/to/checkout-app YOUR_DOCKERHUB_USERNAME v1
```

This builds and pushes:
- `YOUR_DOCKERHUB_USERNAME/gateway:v1`
- `YOUR_DOCKERHUB_USERNAME/checkout:v1`
- `YOUR_DOCKERHUB_USERNAME/pricing:v1`
- `YOUR_DOCKERHUB_USERNAME/inventory:v1`
- `YOUR_DOCKERHUB_USERNAME/quote:v1`

### Option B — Amazon ECR

```bash
cd checkout-k8s-pack/scripts
chmod +x *.sh
./ecr-build-push.sh /path/to/checkout-app <AWS_ACCOUNT_ID> eu-west-2 v1
```

This creates ECR repositories if missing, logs in, builds, tags, and pushes the images.

## 2. Set registry values for deployment

The deployment script renders the manifests using these values:
- `IMAGE_REGISTRY`
- `IMAGE_TAG`

Examples:

### Docker Hub
```bash
export IMAGE_REGISTRY=docker.io/YOUR_DOCKERHUB_USERNAME
export IMAGE_TAG=v1
```

### ECR
```bash
export IMAGE_REGISTRY=<ACCOUNT_ID>.dkr.ecr.eu-west-2.amazonaws.com
export IMAGE_TAG=v1
```

## 3. Review database secret

Edit `manifests/02-secret.yaml` if you want different Postgres values. The defaults are:
- `DB_NAME=checkoutdb`
- `DB_USER=checkoutuser`
- `DB_PASSWORD=checkoutpass`

These match your current application.

## 4. Deploy the stack

Run on the **K3s master** node:

```bash
cd checkout-k8s-pack/scripts
chmod +x *.sh
export IMAGE_REGISTRY=docker.io/YOUR_DOCKERHUB_USERNAME
export IMAGE_TAG=v1
./deploy.sh ../manifests
```

That applies the manifests in the right order.

## 5. Verify the deployment

Run on the master:

```bash
kubectl get pods -n shop
kubectl get svc -n shop
kubectl get ingress -n shop
kubectl get pvc -n shop
kubectl get endpoints,endpointslices -n shop
```

Then use the toolbox pod:

```bash
kubectl exec -it toolbox -n shop -- sh
curl http://gateway-svc:5000/health
curl http://checkout-svc:5001/health
curl http://pricing-svc:5002/health
curl http://inventory-svc:5003/health
curl http://quote-svc:5004/health
exit
```

## 6. Smoke tests through the public URL

Find your NLB DNS name or public endpoint and run:

```bash
./smoke-tests.sh http://YOUR_PUBLIC_URL
```

This tests:
- `/health`
- `/api/ping`
- `/api/arch`
- happy-path checkout
- out-of-stock checkout
- quote preview

## 7. Check PostgreSQL persistence

After one successful checkout:

```bash
./db-check.sh
```

That will:
- query `checkout_audit`
- restart Postgres
- query again

## 8. Manifests summary

### Namespace and config
- `00-namespace.yaml` — creates namespace `shop`
- `01-configmap.yaml` — app ports and non-secret environment values
- `02-secret.yaml` — Postgres credentials

### Data layer
- `03-postgres-pvc.yaml`
- `04-postgres-deployment.yaml`
- `05-postgres-service.yaml`

### App services
- pricing: `10`, `11`
- inventory: `12`, `13`
- checkout: `14`, `15`
- gateway: `16`, `17`
- quote: `18`, `19`

### Ingress and diagnostics
- `20-ingress.yaml`
- `21-toolbox.yaml`

## 9. Image references used by the manifests

Each Deployment uses this pattern:
- `__IMAGE_REGISTRY__/gateway:__IMAGE_TAG__`
- `__IMAGE_REGISTRY__/checkout:__IMAGE_TAG__`
- `__IMAGE_REGISTRY__/pricing:__IMAGE_TAG__`
- `__IMAGE_REGISTRY__/inventory:__IMAGE_TAG__`
- `__IMAGE_REGISTRY__/quote:__IMAGE_TAG__`

The deploy script replaces those placeholders.

## 10. Notes about your current application

Your current app already works well for Kubernetes:
- health endpoints exist for all services
- environment variables are already used correctly
- Postgres init logic is handled by `checkout`
- Dockerfiles are already production-style enough for coursework use

One application mismatch you may still want to fix later is `/api/arch`, which currently returns a detailed JSON object instead of a simple architecture label string.

## 11. Optional KEDA note

This pack deploys the **base working stack first**.

Your current gateway proxies `/api/quote` to the quote service. To implement KEDA scale-to-zero cleanly for the quote path, you usually want either:
- a direct ingress route for quote through the KEDA HTTP add-on, or
- the gateway’s `QUOTE_URL` changed to target the KEDA interceptor path

A short note is included in `optional/keda-note.md`.

## 12. Recommended execution order

1. Build and push images
2. Confirm K3s cluster is healthy
3. Deploy namespace, config, secret, and Postgres
4. Deploy pricing, inventory, checkout, gateway, quote
5. Apply ingress
6. Validate with toolbox
7. Validate through public URL
8. Run persistence and failure checks

## 13. Clean-up

To remove the app stack but keep the cluster:

```bash
kubectl delete namespace shop
```

To remove the AWS infrastructure, use your Terraform folder:

```bash
terraform destroy
```

