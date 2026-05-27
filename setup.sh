#!/bin/bash
# =============================================================
# Dodge MCP Server — Setup Script
# Run this on your machine to:
#   1. Initialize git and push to GitHub
#   2. Install the MCP server
#   3. Configure Claude Desktop to use it
# =============================================================

set -e

echo "=== Dodge MCP Server Setup ==="
echo ""

# --- Step 1: Git init and push ---
echo "Step 1: Initializing git repo..."
cd "$(dirname "$0")"

if [ ! -d ".git" ]; then
    git init -b main
    git add -A
    git config user.email "abuono.326@gmail.com"
    git config user.name "Andrew Buono"
    git commit -m "Initial commit: Dodge Construction Network MCP Server"
    echo "Git repo initialized and committed."
else
    echo "Git repo already exists, skipping init."
fi

echo ""
echo ">>> MANUAL STEP: Create a new repo on GitHub called 'dodge-mcp-server'"
echo ">>> Then run:"
echo ">>>   git remote add origin https://github.com/YOUR_USERNAME/dodge-mcp-server.git"
echo ">>>   git push -u origin main"
echo ""

# --- Step 2: Install the MCP server ---
echo "Step 2: Installing dodge-mcp-server..."
pip install -e .
echo "Installed successfully."
echo ""

# --- Step 3: Verify ---
echo "Step 3: Verifying installation..."
python -c "from dodge_mcp.server import mcp; print('MCP server imports OK')"
echo ""

# --- Step 4: Show Claude Desktop config ---
echo "Step 4: Add to Claude Desktop config"
echo ""
echo "Add this to your claude_desktop_config.json:"
echo '(Usually at ~/Library/Application Support/Claude/claude_desktop_config.json)'
echo ""
echo '{
  "mcpServers": {
    "dodge-construction": {
      "command": "dodge-mcp",
      "env": {
        "DODGE_API_KEY": "f2bddfc77c434295a5deee5258b3b9f7"
      }
    }
  }
}'
echo ""
echo "=== Setup complete! ==="
echo "Restart Claude Desktop to pick up the new MCP server."
