# Screenshots — Enable SD-Access Service runbook

Drop the captured images here using the filenames referenced in
[`../enable-sda-service.md`](../enable-sda-service.md):

| File | What it shows |
|---|---|
| `01-ncsp11008-task.png` | The failing `POST /sda/fabricSites` task (NCSP11008) |
| `02-software-mgmt-sd-access-available.png` | System → Software Management, SD Access under *Available Applications* |
| `03-magctl-no-sda.png` | maglev console: `magctl appstack status sda` → "No resources found" |
| `04-tick-sd-access.png` | SD Access ticked, Install button shown |
| `05-install-in-progress.png` | "Installation of Optional Packages is in progress" banner |
| `06-release-activities-inprogress.png` | Release Activities, INSTALL_OPTIONAL_PACKAGE In Progress |
| `07-release-activities-success.png` | Release Activities, **Success**, Duration 44m 31s |
| `08-wired-data-collection.png` | Wired Client Data Collection enabled (Telemetry) |
| `09-fabric-site-created.png` | Fabric site present (Provision / `catc_fabric_sites`) |

The prose runbook stands alone; images are enhancement.
