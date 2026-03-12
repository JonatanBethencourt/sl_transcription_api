# End-to-End Setup (Copilot Agent Flow → GitHub Action) using a GitHub Token

This guide shows how to kick off the repository’s **Run Processor** workflow from your Copilot Agent using **Agent Flows only**, pass it the DOCX link, and (optionally) drop outputs directly into your OneDrive folder.

---

## What you’ll need

- ✅ A **GitHub token** with permission to dispatch workflows in this repo (the `workflow` scope is sufficient for API calls that trigger a run). You will store this **outside** the repo as a secret in Copilot Studio / Power Platform.  
  _Manual/API/CLI triggering of `workflow_dispatch` is officially supported._ [1](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)[2](https://stackoverflow.com/questions/70151645/how-can-i-trigger-a-workflow-dispatch-from-the-github-api)

- ✅ A DOCX file in OneDrive/SharePoint and a **sharing link** (we’ll generate an Anyone/View link inside the Agent Flow).  
  _We’ll convert it to a direct download link by appending `download=1`._ [3](https://www.sharepointdiary.com/2020/05/sharepoint-online-link-to-document-download-instead-of-open.html)[4](https://stackoverflow.com/questions/24924014/download-file-folder-from-sharepoint-using-curl-wget-automatically)

- (Optional) If you want the workflow to **upload outputs to OneDrive** automatically, create an Entra ID app with Graph **Application permissions** `Files.ReadWrite.All`, grant admin consent, and add these secrets in the GitHub repo:
  - `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`
  - `ONEDRIVE_USER_UPN` (e.g., `you@contoso.com`)
  - `ONEDRIVE_TARGET_FOLDER` (e.g., `Documents/Sl_transcription_api`)
  
  _We use the Microsoft Graph **Upload small files** endpoint (`PUT …/content`)._ [5](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0)

---

## 1) Files already in the repo

- `.github/workflows/run-processor.yml` — The Action you run via API/UI.  
- `processor.py` — The corrected script (outputs go to `outputs/` folder).  
- `data/rules.txt` — Your base lexicon.

> You can also run the workflow manually from GitHub → **Actions** → **Run workflow** to validate it before wiring the Agent Flow. [1](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

---

## 2) Create the Agent Flow (Copilot Studio)

> Agent Flows are deterministic automations that your agent can call as a **tool**. Create a flow with the **Run a flow from Copilot** trigger so your agent can invoke it during chat. [6](https://learn.microsoft.com/en-us/microsoft-copilot-studio/flows-overview)

1. **Copilot Studio → Flows → New agent flow → Start in designer**  
2. Trigger: **Run a flow from Copilot**  
3. Create **two inputs**:
   - `oneDriveFilePath` (string), e.g. `/Documents/Sl_transcription_api/input.docx`
   - `useAnonymousLink` (boolean, default `true`)
4. **Add action**: OneDrive for Business → **Create share link (for a file)**
   - File path: `oneDriveFilePath`
   - Link type: `View`, Scope: `Anyone` (so GitHub’s runner can download anonymously)
5. **Add action**: **Compose** to convert the sharing link to **direct download**
   - If URL doesn’t include `download=1`, append `&download=1`
6. **Add action**: **HTTP** → `POST` to GitHub REST API to dispatch the workflow  
   - URL:  
     ```
     https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/run-processor.yml/dispatches
     ```
   - Headers:
     - `Authorization: Bearer <GITHUB_TOKEN>` (store this as an **environment secret** in Power Platform, then reference it as `Bearer @{environment('GITHUB_PAT')}`)
     - `Accept: application/vnd.github+json`
   - Body (raw JSON):
     ```json
     {
       "ref": "main",
       "inputs": {
         "file_url": "@{outputs('Compose')}"
       }
     }
     ```
   - This endpoint triggers `workflow_dispatch` with inputs for the workflow file in your default branch. [1](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)[2](https://stackoverflow.com/questions/70151645/how-can-i-trigger-a-workflow-dispatch-from-the-github-api)
7. **Respond** to the user (optional): “Run started. I’ll put outputs in OneDrive (and also attach them to the run).”

> **Security**: Put the GitHub token in a **Power Platform environment variable (secret)** and reference it in the HTTP header, rather than pasting it in the flow.  
> **Direct download**: Adding `download=1` forces SharePoint/OneDrive to return the file bytes to `curl` in CI. [3](https://www.sharepointdiary.com/2020/05/sharepoint-online-link-to-document-download-instead-of-open.html)[4](https://stackoverflow.com/questions/24924014/download-file-folder-from-sharepoint-using-curl-wget-automatically)

---

## 3) Use the flow from your Copilot Agent

- Add the Agent Flow as a **tool** to your Copilot Agent (flows that use the “Run a flow from Copilot” trigger can be attached to agents).  
- In chat, ask something like:  
  > “Run the transcription extraction on `/Documents/Sl_transcription_api/input.docx` and save outputs to my Sl_transcription_api folder.”

The Agent will call the flow → the flow builds an Anyone/View link → converts to a direct download → **dispatches** the GitHub workflow via the REST API → the workflow runs `processor.py` and:
- always uploads `outputs/` as a CI artifact  
- (optional) uploads the generated files into your OneDrive folder using Microsoft Graph. [6](https://learn.microsoft.com/en-us/microsoft-copilot-studio/flows-overview)[1](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)[5](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0)

---

## 4) Troubleshooting

- **HTTP 401/403 from GitHub**: Check token scope and repo permissions; workflow file must be in the default branch and enabled. [1](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)  
- **DOCX download yields HTML**: Ensure the link ends with `download=1` or use an Anyone/View link; both patterns are known to force binary download. [3](https://www.sharepointdiary.com/2020/05/sharepoint-online-link-to-document-download-instead-of-open.html)[4](https://stackoverflow.com/questions/24924014/download-file-folder-from-sharepoint-using-curl-wget-automatically)  
- **No files in OneDrive**: If using the optional upload step, confirm the Entra app has Application permission `Files.ReadWrite.All` with admin consent. We use the Graph upload‑small‑files endpoint (`PUT …/content`). [5](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0)
``