# 🚀 Deployment Guide: GeM Filter Optimizer

Because our system is optimized into a **Monolithic Architecture** (One Server runs both Python and the React Frontend), you only need to deploy **one single item** to the cloud!

Here are the recommended FREE and low-cost platforms that will support our specific timeout durations and concurrent scrape loads perfectly.

---

## 🏆 Recommendation 1: Render.com (Best Overall)
Render offers a robust Free Tier that natively supports our Docker architecture and has zero time limit restrictions on standard HTTP connections.

### Pros for our tool:
✅ **Generous Timeouts**: Unlike Vercel (10s), Render permits requests up to **10 minutes**, handling our 90-second Deep Scrapes perfectly.
✅ **Automatic Monolith Support**: It reads our `Dockerfile` and serves both frontend and backend instantly.
✅ **Zero Maintenance**: Automated Git push deployments.

### Step-by-Step Setup on Render:
1. **Login** to [Render.com](https://render.com) and connect your GitHub account.
2. Click **"New +"** -> Select **"Web Service"**.
3. Choose your repository `imsky1812/GeM-Filter-Optimizer`.
4. **Settings to Apply**:
   - **Name**: `gem-filter-optimizer`
   - **Runtime**: Select `Docker`
   - **Instance Type**: `Free`
5. Click **Deploy Web Service**.
6. **Done!** Render will build the multistage container and give you a public URL (e.g., `gem-optimizer.onrender.com`).

*⚠️ Note on Free Tier: If inactive for 15 minutes, the server goes to sleep. The FIRST load will take 30 seconds to wake up, but all deep scrapes afterward will be lightning fast.*

---

## 🏅 Recommendation 2: Koyeb.com (Fastest Startup)
Koyeb provides incredible performance on free tiers and does NOT sleep automatically like Render does.

### Pros for our tool:
✅ **Global Edge Distribution**: Extreme-speed latency.
✅ **High Memory Allocation**: Gives you 512MB of active RAM for free.
✅ **Persistent Active State**: Does not suffer from "sleep mode" cold starts.

### Step-by-Step Setup on Koyeb:
1. Create an account at [Koyeb.com](https://www.koyeb.com).
2. Click **Create Service**.
3. Select **GitHub** as the Source.
4. Choose your repo and set the builder type to **Dockerfile**.
5. Click **Deploy**.
6. In environment settings, ensure PORT is set to `8000`.

---

## 🚀 Recommendation 3: Hugging Face Spaces (The Secret "Always-On" Hack)
Hugging Face gives out massive computing power (16GB RAM / 2 vCPU) for absolute free if you host via a "Docker Space".

### Pros for our tool:
✅ **Massive Performance**: Much stronger CPU/RAM than Render/Koyeb.
✅ **Constant Uptime**: Rarely ever throttles.

### Step-by-Step Setup:
1. Create an account on [HuggingFace.co](https://huggingface.co).
2. Click **New Space**.
3. Name your space and select **SDK: Docker** -> **Template: Blank**.
4. Create space, go to "Files and Versions" -> "Add File" -> Upload all your files (or sync via Git).
5. Hugging Face automatically sees your `Dockerfile` and launches it on an enterprise server instantly for free!

---

## ⚠️ Mandatory Configuration Notice
Whichever provider you select, wait for the deploy log to finish. Once you see:
`INFO: Production frontend mounted successfully`
You can officially share the dynamic link with your clients!

*Reminder: Always inform clients who choose cloud tiers that the very first page load of the day might have a slight "startup buffer" while the secure container stabilizes.*
