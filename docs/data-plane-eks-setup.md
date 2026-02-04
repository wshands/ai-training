# Customer EKS Setup Guide (Data-plane)

This guide helps a customer deploy the data-plane into an AWS EKS cluster.

## Prerequisites

- AWS account with permissions to create EKS clusters
- kubectl + helm installed locally
- VPC with outbound Internet (NAT) or private routing that can reach the control-plane HTTPS endpoint
- Access to the control-plane URL, tenant id, and data-plane token
## .1) Install eksctl on mac
```bash
brew tap aws/tap
brew install aws-tap/eksctl
```

## 1) Create an EKS cluster

You can use eksctl (simplest) or Terraform. Example with eksctl:

```bash
eksctl create cluster \
  --name ai-data-plane \
  --region us-west-2 \
  --nodegroup-name data-plane-ng \
  --nodes 2 \
  --nodes-min 1 \
  --nodes-max 5 \
  --managed
```

If training requires GPUs, choose a GPU node group (e.g., `g5.xlarge`).

## 2) Configure kubectl access

```bash
aws eks update-kubeconfig --region us-west-2 --name ai-data-plane
kubectl get nodes
```

## 3) Create the namespace

```bash
kubectl create namespace training-jobs
```

## 4) Install the data-plane chart

Helm runs from your local machine (or CI/CD runner) using a kubeconfig that
points to the target cluster. You are not running Helm inside the cluster.

Prepare a `values.yaml` (provided by your vendor):

```yaml
jobLauncher:
  trainingNamespace: "training-jobs"
  controlPlaneUrl: "https://control-plane.example.com"
  dataPlaneApiToken: "token-abc"
  dataPlaneTenantId: "org_123"
```

Install:

```bash
helm upgrade --install ai-data-plane ./deploy/helm/data-plane \
  --namespace training-jobs
```

## 5) Verify the deployment

```bash
kubectl get pods -n training-jobs
kubectl logs -n training-jobs -l app=job-launcher --tail=50
```

You should see `/internal/jobs` polling logs and job creation once a job is submitted.

## 6) RBAC notes

The job-launcher service account must be able to create Jobs and ConfigMaps in
the target namespace. The chart configures this by default.

## 7) Networking requirements

The data-plane needs outbound HTTPS access to the control-plane endpoint:

- `https://<control-plane-host>`

No inbound access is required.

### How to enable outbound HTTPS (typical setup)

Private subnets with NAT (recommended):

1) Create a NAT Gateway in a public subnet.
2) Add a default route in the private subnet route table:
   - `0.0.0.0/0 -> NAT Gateway`
3) Ensure the node security group allows egress on TCP 443.

Public subnets (simpler, less secure):

1) Place nodes in public subnets with public IPs.
2) Ensure egress on TCP 443 is allowed.

Private control-plane endpoints:

If your control-plane is not public:

- Use VPC peering, PrivateLink, or VPN between the customer VPC and your VPC.
- Route to the private ALB/NLB and allow outbound to that CIDR.

Quick connectivity check from a pod:

```bash
kubectl run -n training-jobs curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -I https://control-plane.example.com/health
```

## 8) Common issues

- **No jobs created:** tenant id mismatch or invalid token.
- **403 from control-plane:** token doesn’t match tenant.
- **Cannot reach control-plane:** missing NAT or outbound rules.
