# Deploying the demo at zero cost

This covers `demo/app_demo.py` (the sales-demo Streamlit wrapper) only. Real client
engagements stay local/script-based — nothing here changes that.

---

## Which option to pick

| | Best for | Cost | Persistent URL? | Private? |
|---|---|---|---|---|
| **A. Cloudflare Tunnel** | Live calls you're already on | Free, no account needed | No — new URL each run | Yes (URL dies when you stop it) |
| **B. Streamlit Community Cloud** | A link you send before/after a call | Free | Yes | Password-gated only |
| **C. Hugging Face Spaces** | A persistent link that isn't publicly reachable | Free | Yes | Yes — Space can be private |

**Recommendation: start with A.** You operate this live, on a call, while
screen-sharing. A tunnel means nothing is deployed, nothing is sitting on the
internet between calls, and there's no repo to push. Add B or C later only if a
prospect asks to click through it on their own time.

---

## Prerequisites (all options)

**Python version:** the host should run **Python 3.11–3.13**. Requirements are
pinned with `>=` rather than exact versions, so pip resolves whatever is
compatible with the host's Python. All dependencies ship prebuilt Linux wheels —
nothing compiles from source, which is the usual reason free deploys fail.

**The password must never be committed.** `.streamlit/secrets.toml` is already in
`.gitignore`. On hosted options (B and C) you set `DEMO_PASSWORD` through the
host's own secrets UI instead. The app reads it from `st.secrets` first, then
falls back to the `DEMO_PASSWORD` environment variable, so either mechanism works.

**Change the password from `orchid2017` before anything goes online.**

---

## Option A — Cloudflare Tunnel (recommended)

Runs the app on your laptop, exposes it at a temporary public HTTPS URL. Nothing
is deployed; when you stop it, the URL is dead.

### One-time setup

Install `cloudflared`:

```bash
winget install --id Cloudflare.cloudflared
```

### Every time you demo

Terminal 1 — start the app:

```bash
venv\Scripts\streamlit run demo\app_demo.py
```

Terminal 2 — open the tunnel:

```bash
cloudflared tunnel --url http://localhost:8501
```

`cloudflared` prints a URL like `https://random-words-here.trycloudflare.com`.
That's your demo link. Ctrl+C in terminal 2 kills it permanently.

**Notes:**
- No Cloudflare account required for these quick tunnels.
- The URL changes every run — that's a feature here, not a limitation.
- Your laptop must stay awake and online for the duration of the call.

---

## Option B — Streamlit Community Cloud (persistent link)

### 1. Make it a git repo and push to GitHub

The project isn't a git repo yet. From the project root:

```bash
git init
git add .
git commit -m "AR risk MVP with Streamlit demo wrapper"
```

Then create an empty repo on GitHub and push. **Verify `git status` shows no
`.streamlit/secrets.toml`** before pushing — it should already be excluded by
`.gitignore`, but check rather than assume.

A **private** repo works on the free tier and is the better choice here.

### 2. Deploy

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. "New app" → pick the repo/branch → set **Main file path** to `demo/app_demo.py`.
3. Before clicking Deploy, open **Advanced settings** and set the Python version
   to 3.12 or 3.13.
4. Deploy. First build takes a few minutes while dependencies install.

### 3. Set the password

App menu → **Settings → Secrets** → paste:

```toml
DEMO_PASSWORD = "your-real-password-here"
```

Save. The app restarts and picks it up.

### Caveats

- Apps **sleep after inactivity** and take ~30 seconds to wake. Open the URL five
  minutes before a call so the prospect never sees a cold start.
- Roughly 1 GB RAM. Fine for this workload.
- The app is reachable by anyone with the URL; the password gate is the only
  barrier (see security note below).

---

## Option C — Hugging Face Spaces (private persistent link)

Better than B if you want a link that isn't publicly reachable at all.

1. Create a Space at <https://huggingface.co/new-space> → SDK: **Streamlit** →
   visibility: **Private**.
2. Push the project to the Space's git remote (same as any git repo).
3. Rename `demo/app_demo.py` to `app.py` at the Space root, **or** add this front-matter to the top of
   the Space's `README.md`:

   ```yaml
   ---
   title: AR Risk Demo
   sdk: streamlit
   app_file: demo/app_demo.py
   ---
   ```

4. Space **Settings → Variables and secrets** → add secret `DEMO_PASSWORD`.

Free CPU tier gives 2 vCPU / 16 GB RAM — more headroom than Streamlit Cloud.
Private Spaces require a HF login to view, so the password becomes a second layer
rather than the only one.

---

## Security — an honest read

The password gate is **deliberately minimal**, and you should know exactly what it
does and doesn't do:

- It stops someone casually stumbling onto the app if the URL leaks.
- It is a plain string comparison with **no rate limiting and no lockout**. It
  would not survive a determined brute-force attempt.
- Session state is per-browser-session; closing the tab logs you out.

That's an appropriate level for a demo containing only synthetic and public
case-study data. **It is not appropriate for real client ledger data** — which is
exactly why real engagements stay on the local script pipeline, and why the upload
tab warns against pointing it at a prospect's actual file.

If a prospect ever asks to upload their own real ledger to a hosted instance, the
honest answer is that this deployment isn't built for that yet.
