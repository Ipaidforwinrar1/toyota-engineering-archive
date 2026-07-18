# Database Backup Rule

Use the release database as the stable rollback point and do day-to-day extraction work on a separate working copy.

## Stable Snapshot

- `toyota_archive_v0.4.2.db`
- Do not modify this file during experiments.
- Use it to restore the v0.4.2 milestone.

## Working Copy

- `toyota_archive_working.db`
- Use this file for extraction experiments and v0.4.3 development.
- This file is ignored by Git.

## Refresh Working Copy

```powershell
Copy-Item .\toyota_archive_v0.4.2.db .\toyota_archive_working.db -Force
```

## Recommended Commands

```powershell
py .\cli.py --db .\toyota_archive_working.db stats
py .\cli.py --db .\toyota_archive_working.db extract-procedures
```
