# Søndagsbatch — automatisk Instagram-publicering

Kører hver søndag via GitHub Actions. Ingen klik, ingen browser, ingen AI i loopet —
en almindelig planlagt proces henter "Scheduled"-poster fra Notion og publicerer dem
direkte til Instagram via Graph API.

## Engangsopsætning (dig, ikke Claude)

### 1. Opret et Notion internal integration
Dette script kan ikke genbruge din eksisterende Notion-MCP-forbindelse — den har sin
egen nøgle, som Claude ikke har adgang til. Du skal oprette en ny, separat nøgle:

1. Gå til https://www.notion.so/my-integrations
2. "New integration" → giv den et navn, fx "Sunday Batch Publisher"
3. Kopiér "Internal Integration Secret" — det er din `NOTION_API_KEY`
4. Åbn din Content Library-database i Notion → "..." menu → "Connections" →
   tilføj den nye integration, så den må læse/skrive i databasen

### 2. Find dit Notion database ID
Åbn Content Library som en fuld side i browseren. URL'en ser sådan ud:
`https://www.notion.so/xxxxxxxx?v=yyyyyyyy` — de 32 tegn i `xxxxxxxx` (uden bindestreger)
er dit `NOTION_DATABASE_ID`.

**Vigtigt:** Den `collection://...`-id Claude har brugt internt i denne session er
IKKE nødvendigvis samme format som det klassiske database-id, som Notions REST API
kræver. Bekræft ID'et via URL'en som beskrevet ovenfor, før du sætter secreten.

### 3. Opret et GitHub repo
Da du allerede er logget ind på GitHub, kan du:
- Oprette et nyt **privat** repo (fx `content-os-sunday-batch`)
- Lægge `publish_sunday_batch.py` og `.github/workflows/sunday-batch.yml` i det
  (behold mappestrukturen — workflow-filen SKAL ligge i `.github/workflows/`)

### 4. Tilføj de 4 secrets i GitHub
Repo → Settings → Secrets and variables → Actions → "New repository secret".
Tilføj disse fire (indsæt værdierne selv — Claude må aldrig skrive dem ind):

| Secret navn              | Værdi                                                   |
|---------------------------|----------------------------------------------------------|
| `NOTION_API_KEY`           | Din nye Notion internal integration secret (trin 1)      |
| `NOTION_DATABASE_ID`       | Dit Content Library database-id (trin 2)                 |
| `IG_ACCESS_TOKEN`          | Instagram Graph API access token (allerede i Notion under "🔐 Graph API Credentials — Content OS Publisher") |
| `IG_BUSINESS_ACCOUNT_ID`   | `1784142981340239`                                        |

### 5. Bekræft at planen er aktiv
GitHub Actions kører kun schemalagte workflows på repoets standardbranch (typisk
`main`), og kun hvis der har været aktivitet på repoet inden for de sidste 60 dage —
ellers bliver planlagte workflows automatisk pausede. Hvis det sker, genaktiverer du
den under Actions → "Sunday batch" → "Enable workflow".

### 6. Testkør det manuelt først
Før du stoler på søndagskørslen: Actions-fanen → "Søndagsbatch — Instagram
publicering" → "Run workflow" (workflow_dispatch). Tjek loggen for at se om det
opfører sig som forventet — helst på et testkort i Notion, ikke et rigtigt planlagt
opslag, første gang.

## Hvad scriptet gør
Se docstring i toppen af `publish_sunday_batch.py` — den følger nøjagtig samme logik
som "Søndagsbatch — opskrift" i Claude Operating Manual: validér felter, opret
media-container, vent til FINISHED, publicér, opdatér Notion-status til "Published"
først når Meta har bekræftet.

## Token-levetid
Access tokenet er ikke verificeret til at være long-lived. Hvis søndagskørslen
begynder at fejle med en 401/190-fejl, er tokenet sandsynligvis udløbet — det skal
så gengenereres via Meta for Developers og opdateres som GitHub secret. Dette er
endnu ikke testet i praksis (se "Åbne punkter" i Notion-credentials-siden).
