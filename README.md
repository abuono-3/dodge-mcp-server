# Dodge Construction Network MCP Server

An MCP (Model Context Protocol) server that provides AI agents with access to the [Dodge Construction Network](https://www.construction.com/) API for searching construction projects, companies, and documents.

## Features

- **Project Search** — Filter by state, project type, stage, valuation, date ranges, work type, and more
- **Company Search** — Find contractors, architects, engineers, and owners with contact details
- **Project Documents** — Retrieve plans, specs, and addenda for specific projects
- **Spec Alerts** — Access spec alert names for filtered searches

## Setup

### 1. Install

```bash
cd dodge-mcp-server
pip install -e .
```

### 2. Configure

Set your Dodge API key as an environment variable:

```bash
export DODGE_API_KEY=your_api_key_here
```

Or create a `.env` file (copy from `.env.example`).

### 3. Add to Claude Desktop

Add to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dodge-construction": {
      "command": "dodge-mcp",
      "env": {
        "DODGE_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### 4. Add to Claude Code

```bash
claude mcp add dodge-construction -- dodge-mcp
```

Set the env var `DODGE_API_KEY` before running.

## Available Tools

### `search_projects`
Search for construction projects with filters for location, type, stage, valuation, dates, and more.

### `search_projects_raw`
Send a raw request body for advanced queries using the full Dodge API schema.

### `search_companies`
Search for companies and contacts in the Dodge network.

### `get_project_documents`
Retrieve plans, specs, and addenda for a specific project by ID.

### `get_spec_alert_names`
List all available spec alert identifiers.

## API Limits

Free trial: 25 projects/day, 25 companies/day, 25 documents/day.

## License

MIT
