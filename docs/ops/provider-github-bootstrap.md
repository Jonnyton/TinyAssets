# Provider GitHub Bootstrap

Sandboxed providers may not run as the interactive Windows user. When that
happens, `gh` can fail before doing useful work because it tries to read the
host user's GitHub CLI config under `%APPDATA%`.

Run this at session start when local `gh` or `git push` is needed:

```powershell
python scripts/provider_github_bootstrap.py
```

Shell note: a prompt like `C:\Users\...\Workflow>` is `cmd.exe`; a prompt like
`PS C:\Users\...\Workflow>` is PowerShell. Use the matching commands.

The script generates ignored local wrappers:

- `.tmp-gh.cmd` for Windows shells
- `.tmp-gh.ps1` for PowerShell with execution-policy bypass
- `.tmp-gh.sh` for POSIX shells

Token source order is:

1. `GH_TOKEN`
2. `GITHUB_TOKEN`
3. `WORKFLOW_PUSH_TOKEN`
4. `GITHUB_PAT`
5. `.cowork-bootstrap/github.token`

After diagnostics show a current token and reachable GitHub network, wire git
push for this checkout:

```powershell
python scripts/provider_github_bootstrap.py --write-git-credentials
```

Do not paste tokens into chat or commit them. Refresh
`.cowork-bootstrap/github.token` when the bootstrap reports an invalid token.

PowerShell token refresh:

```powershell
New-Item -ItemType Directory -Force .cowork-bootstrap | Out-Null
gh auth token | Set-Content -NoNewline .cowork-bootstrap\github.token
```

`cmd.exe` token refresh:

```bat
if not exist .cowork-bootstrap mkdir .cowork-bootstrap
for /f "delims=" %T in ('gh auth token') do @echo %T>.cowork-bootstrap\github.token
```

In a `.bat` file, use `%%T` instead of `%T`.
