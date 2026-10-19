# Troubleshooting runbook

Commands assume the `vod` namespace. For Docker Compose use `docker compose logs api`.

## Videos stuck or failing

Symptoms: `GET /videos/{id}` shows `failed`, or the alert `VodHighProcessingFailureRate` fires.

1. Read the error stored on the video: `curl localhost:8000/videos/<id> | jq .error`
2. Check logs: `kubectl logs deploy/vod-api -n vod --tail=200 | grep <id>`
3. Common causes:
   - `file has no video stream` or `ffprobe failed`: the upload is not a valid video. Re-upload.
   - `ffmpeg failed`: check the stderr tail in the error. Try the file locally:
     `ffmpeg -i file.mp4 -f null -`
   - `AccessDenied` from S3: the pod's IAM role is missing the policy (`terraform output app_iam_policy_arn`)
     or the service account annotation in `k8s/serviceaccount.yaml` is wrong.
     Verify: `kubectl describe sa vod-api -n vod` and `kubectl exec deploy/vod-api -n vod -- env | grep AWS`.
4. A video left in `processing` after a pod restart was interrupted (processing is in-process).
   Re-upload it.

## Slow processing

Alert: `VodSlowProcessing` (p95 above 5 minutes).

- Check CPU throttling: `kubectl top pod -n vod`. If the pod is at its CPU limit (2 cores),
  raise `limits.cpu` in `k8s/deployment.yaml`, or lower the load.
- Large 1080p+ sources take longer. Consider a faster FFmpeg preset or moving transcoding to
  separate worker pods or AWS MediaConvert.

## API returns 5xx

Alert: `VodApi5xx`.

1. `kubectl get pods -n vod` and `kubectl describe pod <pod> -n vod` (look for `OOMKilled` or probe failures).
2. `kubectl logs deploy/vod-api -n vod --previous` for the crashed container.
3. `OOMKilled`: raise `limits.memory`. FFmpeg memory use grows with video resolution.
4. `/ready` failing: the SQLite volume is not mounted or is full.
   `kubectl exec deploy/vod-api -n vod -- df -h /data`

## Pod will not start

- `ImagePullBackOff`: the image URL in `k8s/deployment.yaml` is wrong, or the node role has no ECR pull permission.
- `Pending`: the PVC cannot bind. `kubectl describe pvc vod-data -n vod` (check the storage class and availability zone).
- `CrashLoopBackOff` on start: `kubectl logs ... --previous`. Check that `S3_BUCKET` is set when `STORAGE_BACKEND=s3`.

## Playback fails in the player

1. Open the `playback_url` directly. A `403` from CloudFront usually means the bucket policy
   does not reference the distribution (`terraform apply` again) or the S3 key does not exist.
2. Check the objects exist: `aws s3 ls s3://<bucket>/videos/<id>/ --recursive`
3. Playlist looks old after a re-upload: playlists are cached for 60 s. Wait or invalidate:
   `aws cloudfront create-invalidation --distribution-id <id> --paths "/videos/<id>/*"`

## Useful Prometheus queries

```
sum(rate(vod_http_requests_total[5m])) by (status)
sum(rate(vod_videos_processed_total[1h])) by (result)
histogram_quantile(0.95, sum(rate(vod_processing_seconds_bucket[15m])) by (le))
```
