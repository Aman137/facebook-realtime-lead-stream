# Facebook Real Time Lead Stream

This project processes each authorized Facebook-related post or notification as soon as it arrives. FastAPI accepts the event, Kafka transports it, a Python worker classifies its context, PostgreSQL stores the decision, and a notification worker sends qualified leads by email or webhook.

The project does not scrape Facebook, automate a personal login, or bypass private-group access. Connect only an approved Meta source, notification email workflow, browser extension with explicit user action, or another source the user is authorized to provide.

## Architecture

```text
Authorized source -> FastAPI -> Kafka -> AI classifier -> PostgreSQL
                                      -> qualified-leads -> Email or webhook
```

This is event streaming, not scheduled batch processing. Every accepted event receives its own Kafka message and is processed independently.

## What is included

- FastAPI event intake and interactive API documentation
- Apache Kafka in KRaft mode
- Rule-based classifier that runs without API charges
- Optional OpenAI structured-output classification
- PostgreSQL audit history and deduplication
- Email notifications through a local MailHog inbox
- Optional webhook output for n8n, HubSpot, Slack-compatible workflows, or another service
- Retry handling and a failed-events Kafka topic
- Automated unit tests
- Windows PowerShell and Python sample-event scripts
- A Word execution guide in `docs`

## Fastest Windows setup

1. Install and open Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Extract this ZIP.
3. Open PowerShell in the extracted `facebook-realtime-lead-stream` folder.
4. Create the environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Build and start everything:

   ```powershell
   docker compose up --build -d
   ```

6. Wait about one minute, then check the services:

   ```powershell
   docker compose ps
   ```

7. Open http://localhost:8000/docs and http://localhost:8025.
8. Send three test events:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\send-sample.ps1
   ```

9. Wait a few seconds and refresh http://localhost:8025. Two lead emails should appear. The completed contractor request should be rejected.
10. View stored leads at http://localhost:8000/leads.

## Enable AI classification

The default `rules` mode is free and confirms the full streaming pipeline. After it works, edit `.env`:

```env
CLASSIFIER_MODE=hybrid
OPENAI_API_KEY=your_real_key_here
OPENAI_MODEL=gpt-5-mini
```

Restart only the classifier worker:

```powershell
docker compose up --build -d classifier-worker
```

Never commit `.env` or share an API key.

## Send a custom event

In the FastAPI page at http://localhost:8000/docs:

1. Open `POST /events`.
2. Select **Try it out**.
3. Add the `X-API-Key` header value `development-key`.
4. Use this body:

```json
{
  "source": "manual",
  "source_message_id": "my-test-001",
  "group_name": "Frisco Neighbors",
  "author": "Example User",
  "text": "Can anyone recommend a realtor for a first-time buyer in Frisco?",
  "post_url": "https://example.com/post/my-test-001"
}
```

## Connect a real authorized source

Send each authorized new message to `POST http://YOUR_SERVER:8000/events` with `X-API-Key`. Suitable adapters include:

- Gmail or Outlook automation that forwards matching Facebook notification emails
- n8n email trigger followed by an HTTP Request node
- An approved Meta application if the required access is available
- A browser extension where the signed-in user explicitly submits the visible post

Do not use an unofficial scraper for private groups.

## Connect n8n or a CRM

Create a production Webhook workflow in n8n and place its URL in `.env`:

```env
NOTIFICATION_WEBHOOK_URL=https://your-n8n.example/webhook/qualified-lead
```

The notifier sends the complete structured lead as JSON with the event ID in the `Idempotency-Key` header. Use the n8n workflow to create a HubSpot contact or task only after you have the correct credentials and authorization.

## Useful commands

```powershell
# Follow all logs
docker compose logs -f

# Follow only classification
docker compose logs -f classifier-worker

# Restart after changing .env
docker compose up -d --force-recreate

# Stop the project but keep database data
docker compose down

# Stop and delete local database data
docker compose down -v
```

The final command deletes the Docker volume and should only be used when you intentionally want a clean reset.

## Run tests locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -q
```

## Production checklist

- Replace `development-key` with a long random secret.
- Use managed Kafka and PostgreSQL or secure the self-hosted services.
- Use TLS for every public endpoint.
- Restrict network access and rotate credentials.
- Configure real SMTP or an approved webhook.
- Add centralized logs and Kafka consumer-lag alerts.
- Define data retention and deletion rules.
- Require human review before contacting any poster.
- Confirm Meta, group, privacy, email, and CRM rules before connecting live data.

