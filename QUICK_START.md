# Quick Start

```powershell
Copy-Item .\toyota_archive_v0.3.db .\toyota_archive_v0.4.db
py .\cli.py --db .\toyota_archive_v0.4.db init
py .\cli.py --db .\toyota_archive_v0.4.db detect-source
py .\cli.py --db .\toyota_archive_v0.4.db extract-components --limit 20
py .\cli.py --db .\toyota_archive_v0.4.db component "Fuel Injector" --details --context
py .\cli.py --db .\toyota_archive_v0.4.db extract-procedures --limit 100
py .\cli.py --db .\toyota_archive_v0.4.db procedure "Fuel Injector"
```

Results include component, document title, TEA reference, category, section, page, and context.
