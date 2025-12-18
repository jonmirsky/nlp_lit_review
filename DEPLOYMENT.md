# Deployment Guide - Literature Review Visualizer

This guide walks you through deploying the Literature Review Visualizer to Render.com with your custom domain.

## Prerequisites

- GitHub account (https://github.com/jonmirsky)
- Render.com account (sign up at https://render.com)
- Custom domain (for production deployment)
- All RIS files and PDFs ready

## Step 1: Prepare Your Code for GitHub

### 1.1 Create GitHub Repository

1. Go to https://github.com/new
2. Create a new repository (e.g., `literature-review-visualizer`)
3. **Do NOT** initialize with README, .gitignore, or license (we already have files)

### 1.2 Copy PDFs to Project Structure

Your PDFs need to be in the project so they're included in the deployment. Create a script to copy them:

```bash
# Create Endnote data folder in project
mkdir -p Endnote/from_zotero_v3.Data

# Copy only PDF files (196MB total)
find /Users/jon/Documents/badjatia_hu/Endnote/from_zotero_v3.Data -name "*.pdf" -type f -exec cp {} Endnote/from_zotero_v3.Data/ \;
```

Or manually copy the PDFs to: `Endnote/from_zotero_v3.Data/`

### 1.3 Check .gitignore

Make sure `.gitignore` doesn't exclude necessary files. It should allow:
- `RIS_source_files/` (and all .txt files)
- `Endnote/from_zotero_v3.Data/` (PDF files)
- `static/` (React build)
- `templates/`
- Python files

### 1.4 Push to GitHub

```bash
cd /Users/jon/Documents/badjatia_hu/visualizer_nlp_lit_review

# Initialize git if not already done
git init
git add .
git commit -m "Initial commit - ready for deployment"

# Add your GitHub repository as remote
git remote add origin https://github.com/jonmirsky/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

Replace `YOUR_REPO_NAME` with your actual repository name.

## Step 2: Deploy to Render

### 2.1 Sign Up / Sign In to Render

1. Go to https://render.com
2. Sign up or sign in with your GitHub account
3. Authorize Render to access your GitHub repositories

### 2.2 Create New Web Service

1. In Render dashboard, click **"New +"** → **"Web Service"**
2. Connect your GitHub account if not already connected
3. Select your repository: `jonmirsky/YOUR_REPO_NAME`
4. Render will auto-detect settings from `render.yaml`:
   - **Name**: literature-review-visualizer (or your choice)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements_lit_review_visualizer.txt && npm install && npm run build`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free

### 2.3 Configure Environment Variables

In the Render dashboard, go to your service → **Environment** tab:

- `FLASK_DEBUG`: Set to `false` (for production)
- `PORT`: Automatically set by Render (don't change)

### 2.4 Deploy

1. Click **"Create Web Service"**
2. Render will start building (first build takes 5-10 minutes)
3. Watch the build logs for any errors
4. Once deployed, you'll get a URL like: `https://literature-review-visualizer.onrender.com`

## Step 3: Set Up Custom Domain

### 3.1 Add Custom Domain in Render

1. In your Render service dashboard, go to **"Settings"** → **"Custom Domains"**
2. Click **"Add Custom Domain"**
3. Enter your domain (e.g., `visualizer.yourdomain.com` or `yourdomain.com`)
4. Render will show you DNS records to add

### 3.2 Update DNS Records

Go to your domain registrar (where you bought the domain) and add the DNS records Render provides:

**For subdomain (recommended)**:
- Type: `CNAME`
- Name: `visualizer` (or your subdomain)
- Value: `literature-review-visualizer.onrender.com`

**For root domain**:
- Type: `A`
- Name: `@` (or root)
- Value: Render's IP address (provided by Render)

### 3.3 Wait for SSL Certificate

- Render automatically provisions SSL certificates via Let's Encrypt
- This usually takes 5-10 minutes after DNS propagates
- You'll see a green checkmark when SSL is active

## Step 4: Verify Deployment

1. Visit your custom domain
2. The app should load and display the visualization
3. Test clicking nodes to see paper lists
4. Test PDF opening (double-click papers)

## Troubleshooting

### Build Fails

- **"npm not found"**: Make sure Node.js is in the build environment (Render auto-detects from package.json)
- **"Module not found"**: Check that all dependencies are in `requirements_lit_review_visualizer.txt`
- **"Port already in use"**: Render sets PORT automatically, don't hardcode it

### App Doesn't Load

- Check Render logs: Dashboard → Your Service → **"Logs"** tab
- Verify environment variables are set correctly
- Check that data files (RIS files, PDFs) are in the repository

### PDFs Not Opening

- Verify PDFs are in `Endnote/from_zotero_v3.Data/` folder in the repo
- Check that PDF paths in RIS files match the server structure
- Look at browser console for errors

### Domain Not Working

- Wait 24-48 hours for DNS propagation (usually faster)
- Verify DNS records are correct using `dig` or online DNS checker
- Check Render dashboard for domain status

## Updating the Deployment

After making changes:

1. Commit changes to GitHub:
   ```bash
   git add .
   git commit -m "Your update message"
   git push
   ```

2. Render will automatically detect the push and redeploy
3. Monitor the build logs in Render dashboard

## File Size Considerations

- **Current PDF size**: 196MB (3,429 PDFs)
- **Render free tier**: 512MB disk space
- **GitHub free tier**: 1GB repository size

If you need more space in the future:
- Consider using AWS S3 or similar cloud storage for PDFs
- Update `pdf_resolver.py` to fetch from cloud storage
- This requires additional code changes

## Support

For issues:
- Check Render logs first
- Review GitHub repository for file structure
- Verify all environment variables are set
