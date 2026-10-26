# jellyfin-plugins

Personal Jellyfin plugin catalog. It holds only built plugins and the catalog
manifest; source code lives in private repositories.

## Add to Jellyfin

Dashboard → Plugins → Repositories (Catalog → ⚙ in Jellyfin 12) → **+**, then:

- **Name:** furyetti
- **URL:** `https://raw.githubusercontent.com/furyetti/jellyfin-plugins/main/manifest.json`

## Plugins

| Plugin | Based on | Changes |
|---|---|---|
| Smart Collections | [johnpc/jellyfin-plugin-smart-collections](https://github.com/johnpc/jellyfin-plugin-smart-collections) (MIT) | Suggested collections from the most common tags, genres and tag pairs; admin-only plugin API |

Releases are published with `scripts/publish-catalog.sh` from the plugin's fork.
