# Dot WIP

Generates Work In Progress reports for Hunch clients.

## Endpoint

**POST /wip**

```json
{
  "clientCode": "TOW"
}
```

Returns HTML email with all active projects for that client.

## Environment Variables

- `AIRTABLE_API_KEY` - Airtable API token
