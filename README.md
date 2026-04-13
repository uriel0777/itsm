# SaaS Admin - ITSM Task Management App

A specialized Task Management and ticketing system with built-in Runbooks, Assets Vault (CMDB), and Automated Alert processing tailored for NOC and Infrastructure Teams.

## Stack
- Backend: Flask, SQLAlchemy
- Frontend: HTML/CSS/JS (Tailwind/Bootstrap custom style)
- Deployment: Windows Server 2012 (IIS / wfastcgi)

## Features
* **Auto-Ticketing:** Receives webhooks from monitoring scripts to automatically open and resolve tickets.
* **Runbook Engine:** Suggests precise fix commands based on incident regex logic.
* **Asset Vault:** Maintains the infrastructure tree with immediate action keys (e.g. `rdp://` launcher).
* **SLA Timers:** Auto calculation of elapsed time against priority targets.
