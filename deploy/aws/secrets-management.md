# Production Secret Management & Rotation Architecture

## 1. Zero Secrets in Source Control
No production credentials, database connection strings, or API keys are stored in code, Git history, or Docker images.

## 2. Secret Provisioning in AWS Secrets Manager
Secrets are provisioned via AWS Secrets Manager using KMS encryption (`aws/secretsmanager`):

```bash
aws secretsmanager create-secret \
  --name "telecom/churn/prod" \
  --description "Production credentials for Telecom Churn ML Platform" \
  --secret-string '{"API_KEY":"GENERATE_HIGH_ENTROPY_64_CHAR_HEX"}'
```

## 3. ECS Runtime Injection
ECS Task Definitions reference secrets directly from Secrets Manager:
```json
{
  "name": "CHURN_API_KEY",
  "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:telecom/churn/prod:API_KEY::"
}
```
The AWS ECS container agent securely injects the secret value directly into process environment variables in container memory at container launch.

## 4. 90-Day Secret Rotation Procedure
1. Generate new API key in Secrets Manager as `API_KEY_NEXT`.
2. Update application to accept both active key and next key during a 48-hour cutover grace period.
3. Notify authorized client services to update their `X-API-Key` headers.
4. Promote `API_KEY_NEXT` to primary `API_KEY`.
5. Invalidate old key and verify zero rejected authorized requests.
