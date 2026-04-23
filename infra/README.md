# Azure VM Deployment Notes

This template provisions:
- Linux VM
- Standard public IP
- NSG for SSH/HTTP/HTTPS
- Managed data disk for SQLite, uploads, and duplicate-review files
- cloud-init bootstrap to clone and run the app behind Nginx

## Inputs
- `location`: `Canada Central`
- `sshPublicKey`: your SSH public key
- `allowedSshSource`: your trusted IP/CIDR
- `repoUrl`: GitHub repo URL for `CricketCanClubsApp`

## Data Safety
Runtime files are stored on the attached data disk mounted at `/srv/cricket-data`:
- `data/`
- `uploads/`
- `duplicates/`

The bootstrap copies `seed.json` to the runtime data disk on first boot if needed.

## Notes
- If the GitHub repo is private, the clone step will need repository access or a deploy key.
- The VM size defaults to `Standard_B2ms`; increase it if you later move heavier OCR/LLM workloads onto the server.
