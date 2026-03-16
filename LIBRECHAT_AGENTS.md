# 🤖 Creating Agents in LibreChat

This guide explains how to create and configure specialized AI agents within the LibreChat Analysis Hub. In this project, agents are used as **AI SRE Analysts** that can interact with your monitoring data.

## 1. Creating Agents via the UI

LibreChat provides a user-friendly interface for creating agents without touching configuration files.

1.  **Access LibreChat**: Open `http://localhost:3080` in your browser.
2.  **Open Agents Panel**: Click on the **Agents** icon in the side panel or select "Agents" from the model dropdown.
3.  **New Agent**: Click the **+ Create Agent** button.
4.  **Configure Persona**:
    - **Name**: Give your agent a name (e.g., "Database Specialist").
    - **Description**: Briefly describe its expertise.
    - **Instructions**: Provide detailed system prompts (e.g., "You are a database expert...").
5.  **Attach Tools**: If you have specific OpenAPI actions defined (like the monitoring tools), you can enable them for this agent.

## 2. Pre-configuring Agents via `librechat.yaml`

For "System Agents" that should be available to all users by default, use the `modelSpecs` configuration.

### Example: The AI SRE Analyst
The current **AI SRE Analyst** is defined in `LibreChat/librechat.yaml`:

```yaml
modelSpecs:
  list:
    - name: "ai-sre-analyst"
      label: "AI SRE Analyst"
      description: "Expert SRE focused on Monitoring and RCA."
      group: "Google"
      preset:
        endpoint: "google"
        model: "gemini-2.0-flash"
        instructions: |
          You are an expert AI SRE...
          Use your tools to analyze Prometheus metrics.
```

### To add a new pre-configured agent:
1.  Open `LibreChat/librechat.yaml`.
2.  Add a new entry to the `modelSpecs.list` section.
3.  Restart the LibreChat container: `docker-compose restart librechat`.

## 3. Connecting Agents to Monitoring Tools (Actions)

To give an agent "superpowers" (like querying your live health data), you must connect it to the Backend API.

### Step 1: Define the Action
Actions are defined using OpenAPI specifications. Our project uses `LibreChat/monitoring-actions.json`.

### Step 2: Configure the Bridge
In `librechat.yaml`, ensure the backend domain is allowed:

```yaml
actions:
  allowedDomains:
    - "host.docker.internal:8001"
```

### Step 3: Use Tools in Instructions
In your agent's instructions, explicitly tell it when and how to use the tools:
- "If a user asks about health, use `get_latest_health`."
- "To see recent traces, use `list_sessions`."

## 4. Best Practices for Monitoring Agents
- **Specificity**: Give agents specific scopes (e.g., "Network Expert", "Database Guru").
- **Verification**: Always instruct agents to "never make up data" and to report if a tool returns an error.
- **Formatting**: Tell agents to use markdown tables for metric data to improve readability.
