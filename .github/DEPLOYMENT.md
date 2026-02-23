# GitHub Actions Deployment Setup

This guide explains how to set up deployment using GitHub Actions.

## Why GitHub Actions?

- ✅ Docker available by default (required for Python Lambda layer bundling)
- ✅ Build backend and frontend in one place
- ✅ Deploy to your existing Amplify app (HTTPS, custom domains, etc.)
- ✅ Simple, no extra infrastructure needed

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

> **Important**: The `AMPLIFY_APP_ID` is still used by `ampx pipeline-deploy` to deploy the backend. If you haven't created an Amplify app yet:
> ```bash
> # Create a minimal Amplify app (just for backend deployment)
> aws amplify create-app --name presidio-amplify --region $(aws configure get region)
> # Note the appId from the output
> ```

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

### 3. Disconnect Repository from Amplify App

Since GitHub Actions will deploy everything via API:

1. Go to Amplify Console → Your App → App settings → General
2. Under "Repository details", click **Disconnect repository**
3. Confirm the disconnection

This allows manual deployments via the Amplify API while keeping all Amplify Hosting features (HTTPS, custom domains, CDN).

## How It Works

**Single GitHub Actions workflow builds and deploys everything:**

1. **Push to `main`** → workflow triggers
2. **Install dependencies** (Node.js, npm packages)
3. **Deploy backend**: 
   - Uses Docker to bundle Python Lambda layer
   - Runs `ampx pipeline-deploy` to deploy CloudFormation stack
   - Generates `amplify_outputs.json` with API endpoint
4. **Build frontend**: 
   - Installs app dependencies
   - Runs `npm run build` (reads API URL from `amplify_outputs.json`)
5. **Deploy frontend to Amplify Hosting**:
   - Zips the built frontend
   - Uses Amplify `create-deployment` API to upload
   - Amplify serves the static files with HTTPS, CDN, etc.

✅ **No coordination needed** - everything happens in one workflow
✅ **`amplify_outputs.json` never committed** - stays in `.gitignore`
✅ **Fast builds** - Docker and all tools available
✅ **Amplify benefits** - HTTPS, custom domains, CDN, monitoring
✅ **Simple** - one workflow, Amplify app disconnected from repository

## Testing the Setup

1. Commit and push your changes:
   ```bash
   git add .github/workflows/deploy.yml .github/DEPLOYMENT.md amplify.yml
   git commit -m "feat: add GitHub Actions deployment"
   git push origin main
   ```

2. Watch the deployment:
   - **GitHub**: Actions tab → Watch "Deploy Backend" workflow
   - **AWS CloudFormation**: Watch stack updates
   - **Amplify Console**: Check deployment status

3. Access your app:
   - Frontend: Your Amplify app URL (e.g., `https://main.xxx.amplifyapp.com`)
   - Backend API: Check CloudFormation outputs for `PresidioApiUrl`

## Troubleshooting

### "Error: The security token included in the request is invalid"
- Check that `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets are correct
- Verify the IAM user has PowerUserAccess permissions

### "Error: Missing app-id" or workflow completes but doesn't deploy
- Verify `AMPLIFY_APP_ID` secret is set correctly
- Check GitHub Actions logs for the "skipping Amplify deploy" message

### Frontend shows "Failed to fetch" or can't connect to API
- Verify `amplify_outputs.json` was generated (check workflow logs)
- Check the API URL in the browser console
- Verify CORS is enabled on the API (it should be by default)

### "Access Denied" when deploying to Amplify
- Ensure the IAM user has permissions for `amplify:CreateDeployment` and `amplify:StartDeployment`
- PowerUserAccess should include these by default

### Docker errors
- Should not happen in GitHub Actions (Docker is pre-installed)

