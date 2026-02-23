# GitHub Actions Deployment Setup

This guide explains how to set up deployment using GitHub Actions.

## Why GitHub Actions?

- ✅ Docker available by default (required for Python Lambda layer bundling)
- ✅ Better control over build environment
- ✅ Works perfectly with your existing setup (tested locally)
- ✅ Amplify Hosting still used for frontend
- ✅ Simple setup with AWS access keys

## Setup Steps

### 1. Create IAM User for GitHub Actions

Create a deployment user with programmatic access:

```bash
# Create the user
aws iam create-user --user-name github-actions-presidio-deploy

# Attach required policies
aws iam attach-user-policy \
  --user-name github-actions-presidio-deploy \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess

# Create access keys
aws iam create-access-key --user-name github-actions-presidio-deploy
```

> **Note**: Save the `AccessKeyId` and `SecretAccessKey` from the output - you'll need them for GitHub secrets.

> **Security**: For production, create a custom policy with least-privilege permissions for CloudFormation, Lambda, API Gateway, S3, IAM, etc. instead of PowerUserAccess.

### 2. Configure GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions

**Add these secrets** (New repository secret):

| Secret Name | Value | Where to find it |
|-------------|-------|------------------|
| `AWS_ACCESS_KEY_ID` | Access key ID from step 1 | From `create-access-key` output |
| `AWS_SECRET_ACCESS_KEY` | Secret access key from step 1 | From `create-access-key` output |
| `AMPLIFY_APP_ID` | Your Amplify App ID | Amplify Console → Overview |

**Add this variable** (New repository variable):

| Variable Name | Value |
|---------------|-------|
| `AWS_REGION` | `eu-central-1` (or your preferred region) |

### 3. Update Amplify Build Settings

In Amplify Console:

1. Go to your app → Hosting → Build settings
2. Update `amplify.yml` to only build frontend:

```yaml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - cd app && npm ci
    build:
      commands:
        - cd app && npm run build
  artifacts:
    baseDirectory: app/dist
    files:
      - '**/*'
  cache:
    paths:
      - app/node_modules/**/*
```

3. Make sure "Auto build" is ENABLED for the main branch (so frontend updates trigger builds)

### 4. Disable Backend Builds in Amplify

Since GitHub Actions handles backend deployment now:

1. In Amplify Console, go to Build settings
2. The backend phase should be removed from `amplify.yml` (see step 5)

## How It Works

### Backend Deployment (GitHub Actions)
- Push to `main` branch → GitHub Actions workflow triggers
- Workflow uses Docker (available by default) to build Python dependencies
- Deploys backend via `ampx pipeline-deploy`
- Generates `amplify_outputs.json`

### Frontend Deployment (Amplify Hosting)
- GitHub Actions completes → Amplify detects the push
- Amplify builds frontend using latest `amplify_outputs.json`
- Deploys frontend to Amplify Hosting

## Testing the Setup

1. Commit and push your changes:
   ```bash
   git add .github/workflows/deploy.yml
   git commit -m "feat: add GitHub Actions deployment"
   git push origin main
   ```

2. Watch the deployment:
   - GitHub: Actions tab → Watch "Deploy Backend" workflow
   - AWS: CloudFormation console → Watch stack updates
   - Amplify: Build logs → Watch frontend build

## Troubleshooting

### "Error: The security token included in the request is invalid"
- Check that `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets are correct
- Verify the IAM user has the required permissions

### "Error: Missing app-id" or workflow completes but doesn't deploy
- Verify `AMPLIFY_APP_ID` secret is set correctly
- Check GitHub Actions logs for the "skipping Amplify deploy" message

### Docker errors
- Should not happen in GitHub Actions (Docker is pre-installed)

## Rolling Back to Amplify CI/CD (if needed)

If you want to go back:
1. Re-enable backend builds in `amplify.yml`
2. Disable/delete the GitHub Actions workflow
3. Push to trigger an Amplify build

