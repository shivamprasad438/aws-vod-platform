# AWS Video-on-Demand (VOD) Platform

A small video-on-demand backend. You upload a video, it is packaged into adaptive-bitrate
HLS (360p and 720p) with FFmpeg, published to Amazon S3, and delivered through CloudFront.
A FastAPI service exposes the metadata API. Everything is containerized and deployable on
Kubernetes (EKS) with Terraform-managed AWS resources, a GitHub Actions pipeline and
Prometheus/Grafana monitoring.

## Architecture

```
                 upload (POST /videos)
 client ─────────────────────────────────▶ FastAPI (Docker, Kubernetes/EKS)
   ▲                                          │  1. ffprobe  → metadata (duration, codec, resolution)
   │                                          │  2. ffmpeg   → HLS renditions + master.m3u8
   │ playback (HLS)                           │  3. upload   → S3 (private bucket)
   │                                          ▼
 CloudFront ◀── Origin Access Control ── Amazon S3          SQLite: video metadata + status
   (HTTPS, edge cache)                                      /metrics → Prometheus → Grafana
```

| Layer | Tooling |
|---|---|
| API and processing | Python, FastAPI, FFmpeg/FFprobe |
| Storage and delivery | Amazon S3 (private), CloudFront with Origin Access Control |
| Containers | Docker (non-root image), Docker Compose for local dev |
| Orchestration | Kubernetes manifests (Deployment, Service, Ingress/ALB, PVC, IRSA service account), optional Argo CD app |
| Infrastructure as code | Terraform: S3, CloudFront, IAM policy, ECR |
| CI/CD | GitHub Actions: lint, tests, image build and smoke test, Terraform validate, push to ECR |
| Monitoring | Prometheus metrics, alert rules, Grafana datasource |

## API

| Method | Path | Description |
|---|---|---|
| POST | `/videos` | Multipart upload (`file`, `title`). Returns `202` and a video id; processing runs in the background |
| GET | `/videos` | List videos (newest first) |
| GET | `/videos/{id}` | Status (`processing`, `ready`, `failed`), metadata, renditions, `playback_url` |
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks the database) |
| GET | `/metrics` | Prometheus metrics |

Interactive docs are at `/docs` when the server is running.

## Run locally

Requirements: Python 3.12+ and FFmpeg (`brew install ffmpeg` or `apt install ffmpeg`).

```bash
python -m venv .venv && source .venv/bin/activate
make install
make test          # 8 tests, including a real FFmpeg run and a mocked S3 upload
make run           # API on http://localhost:8000
make sample        # creates sample.mp4 (10 s, 720p)
make demo          # uploads it and prints the metadata and playback URL
```

In local mode, files are served from `/media/...`. To watch the stream, open the
`playback_url` in VLC or Safari, or use hls.js in a browser.

### Full local stack

```bash
docker compose up --build
```

API: http://localhost:8000/docs, Prometheus: http://localhost:9090,
Grafana: http://localhost:3000 (admin / admin, Prometheus is pre-configured as a datasource).

## Deploy on AWS

1. **Create AWS resources**
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars   # set a unique bucket_name
   terraform init && terraform plan && terraform apply
   ```
   Outputs: `bucket_name`, `cloudfront_domain`, `app_iam_policy_arn`, `ecr_repository_url`.

2. **Build and push the image**
   ```bash
   aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <ecr_repository_url>
   docker build -t <ecr_repository_url>:latest . && docker push <ecr_repository_url>:latest
   ```
   Or let the GitHub Actions `push-to-ecr` job do it (set the `AWS_ROLE_ARN` and `AWS_REGION`
   repository variables).

3. **Give the pod S3 access** with IRSA: create an IAM role for the `vod/vod-api` service
   account on your EKS cluster and attach `app_iam_policy_arn`. Put the role ARN in
   `k8s/serviceaccount.yaml`.

4. **Deploy**
   Fill in the `REPLACE_...` values in `k8s/configmap.yaml` and `k8s/deployment.yaml`, then:
   ```bash
   kubectl apply -f k8s/namespace.yaml
   kubectl apply -f k8s/
   ```
   Optional GitOps: `kubectl apply -f k8s/argocd-application.yaml` lets Argo CD keep the
   cluster in sync with this repo (edit `repoURL` first).

## Monitoring

Custom metrics: `vod_http_requests_total`, `vod_videos_processed_total{result}`,
`vod_processing_seconds`. Alert rules are in `monitoring/alerts.yml`. See
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for runbooks.

## Design decisions and limits

- **Private bucket + Origin Access Control.** Viewers can only reach video files through
  CloudFront; the bucket has public access blocked.
- **Cache headers.** Playlists cache for 60 s, segments are immutable and cache for a year.
- **No upscaling.** A 360p source only gets a 360p rendition.
- **Single replica.** Metadata is in SQLite on a persistent volume, so the API runs one pod.
  Processing happens in-process after the upload returns. For production scale, move metadata
  to RDS or DynamoDB and run transcoding as separate workers (SQS plus a worker deployment, or
  AWS MediaConvert).
- **Not included:** authentication, signed CloudFront URLs, DRM, and a player UI.

## Project layout

```
app/            FastAPI app, FFmpeg wrapper, storage backends, SQLite store
tests/          pytest suite (API, FFmpeg pipeline, mocked S3)
terraform/      S3, CloudFront (OAC), IAM policy, ECR
k8s/            Kubernetes manifests + Argo CD application
monitoring/     Prometheus config, alert rules, Grafana provisioning
docs/           Troubleshooting runbook
.github/        CI workflow
```
