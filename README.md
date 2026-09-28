# Facebook Real-Time Lead Stream

An event-driven pipeline for processing authorized Facebook post events, classifying potential real-estate and service leads, storing decisions, and sending qualified leads to a local inbox or webhook.

> **Important:** This project is designed for authorized data sources and deliberate user submissions. It does **not** scrape private Facebook groups or automate a personal Facebook login.

## 🚀 Overview

The system processes each incoming post as an individual Kafka event:

1. **FastAPI** receives an authorized post event.
2. **Kafka** transports the event through the streaming pipeline.
3. **Classifier Worker** determines intent, category, urgency, and confidence using rules or an optional OpenAI model.
4. **PostgreSQL** stores the original event, classification, notification status, and timestamps.
5. **Notifier Worker** sends qualified leads to email or an optional webhook.

This provides a local, Dockerized demonstration of a real-time lead qualification workflow.

## 🏗️ Architecture

```text
Authorized Source
      │
      ▼
   FastAPI
 POST /events
      │
      ▼
    Kafka
 incoming-posts
      │
      ▼
Classifier Worker
 Rules / OpenAI
      │
      ├──────────────► PostgreSQL
      │
      ▼
qualified-leads
      │
      ▼
Notifier Worker
      │
      ├──────────────► MailHog
      │
      └──────────────► Optional Webhook / n8n / CRM
```

## 🧰 Tech Stack

- **Python**
- **FastAPI**
- **Apache Kafka**
- **PostgreSQL**
- **Docker / Docker Compose**
- **PowerShell**
- **MailHog**
- **OpenAI API** (optional hybrid classification)
- **n8n** (optional workflow integration)

## 📁 Project Structure

```text
facebook-realtime-lead-stream/
│
├── app/
│   ├── main.py              # FastAPI event intake and lead endpoints
│   ├── worker.py            # Kafka consumer and classification pipeline
│   ├── classifier.py        # Rules and optional OpenAI classification
│   ├── notifier.py          # Email and webhook delivery
│   └── db.py                # PostgreSQL schema and persistence
│
├── config/
│   └── lead_rules.json      # Lead categories and intent phrases
│
├── scripts/
│   └── send-sample.ps1      # Windows sample-event sender
│
├── tests/                   # Automated tests
├── docs/                    # Project documentation
├── docker-compose.yml       # Complete local streaming environment
├── Dockerfile
├── .env.example
├── requirements-dev.txt
└── README.md
```

## ✅ Requirements

Before starting, install:

- Windows
- Docker Desktop
- PowerShell
- Internet connection for the initial Docker image download

The default local setup uses these ports:

| Port | Service |
|---|---|
| `8000` | FastAPI |
| `8025` | MailHog |
| `5432` | PostgreSQL |
| `29092` | Kafka |

## ⚡ Quick Start

### 1. Clone the repository

```powershell
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd facebook-realtime-lead-stream
```

### 2. Create the environment file

```powershell
Copy-Item .env.example .env
```

For the first run, keep:

```env
CLASSIFIER_MODE=rules
```

This allows the complete pipeline to run without an API key or model cost.

### 3. Start the system

```powershell
docker compose up --build -d
```

The first startup may take several minutes while Docker downloads the required images.

### 4. Verify services

```powershell
docker compose ps
```

You should see:

- `kafka`
- `postgres`
- `mailhog`
- `api`
- `classifier-worker`
- `notifier-worker`

If a worker is restarting, check its logs:

```powershell
docker compose logs --tail 100 classifier-worker
docker compose logs --tail 100 notifier-worker
```

## 🌐 Local Endpoints

Once the services are running:

| URL | Purpose |
|---|---|
| http://localhost:8000 | Application home |
| http://localhost:8000/docs | Interactive FastAPI documentation |
| http://localhost:8000/health | API health check |
| http://localhost:8000/leads | Qualified lead records |
| http://localhost:8025 | MailHog email inbox |

The API should return a healthy status from:

```text
http://localhost:8000/health
```

## 🧪 Run the Sample Stream

The included PowerShell script sends three separate events:

- Two active requests that should qualify as leads
- One completed request that should be rejected

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\send-sample.ps1
```

Then open:

```text
http://localhost:8025
```

You should see qualified lead emails while the completed request should not generate a notification.

You can also view qualified leads at:

```text
http://localhost:8000/leads
```

## 🔌 Test the API Manually

Open:

```text
http://localhost:8000/docs
```

Select:

```text
POST /events
```

Use the development API key configured in `.env`.

Example request:

```json
{
  "source": "manual",
  "source_message_id": "test-100",
  "group_name": "Frisco Neighbors",
  "author": "Example User",
  "text": "Can anyone recommend a realtor for a first-time buyer in Frisco?",
  "post_url": "https://example.com/post/test-100"
}
```

A successful request should return:

```text
HTTP 202
```

## 🤖 Optional OpenAI Classification

The default rules-based classifier is recommended for the first successful run.

After the local pipeline works, configure hybrid classification in `.env`:

```env
CLASSIFIER_MODE=hybrid
OPENAI_API_KEY=your_real_key_here
OPENAI_MODEL=gpt-5-mini
```

Then rebuild the classifier worker:

```powershell
docker compose up --build -d classifier-worker
```

Hybrid mode uses the model when available and falls back to deterministic rules if the model request fails.

### 🔐 Security

Never:

- Commit `.env`
- Put API keys directly in source code
- Share API keys in screenshots
- Publish secrets in GitHub

Use `.env.example` for safe configuration templates.

## 🎯 Lead Criteria

Lead targeting can be customized through `.env`:

```env
TARGET_GROUPS=Frisco Neighbors,Dallas Real Estate
MARKET_LOCATIONS=Dallas,Fort Worth,Frisco,Plano,McKinney,Denton
LEAD_CONFIDENCE_THRESHOLD=0.80
```

Additional categories, request phrases, service types, urgency phrases, and completed-request phrases can be edited in:

```text
config/lead_rules.json
```

After changing worker configuration:

```powershell
docker compose up --build -d --force-recreate classifier-worker notifier-worker
```

## 🔄 Connecting an Authorized Real-Time Source

The core pipeline is source-neutral. An approved source can send a JSON event to:

```text
POST /events
```

Possible integrations include:

- Authorized Facebook/Meta application events
- Facebook notification email
- Gmail or Outlook workflows
- n8n
- User-submitted forms
- Browser-based deliberate user submissions

### n8n Example

A possible workflow is:

```text
Gmail / IMAP Trigger
        ↓
Extract post information
        ↓
HTTP Request
POST /events
        ↓
Classifier
        ↓
Qualified Lead
        ↓
Webhook / CRM
```

The event can contain:

- Group name
- Author
- Message text
- Source message ID
- Source URL

Do not expose a local development API to the public internet without proper authentication, TLS, firewall controls, and a deployment plan.

## 🔗 Webhook / CRM Integration

Qualified leads can optionally be sent to an n8n or CRM webhook:

```env
NOTIFICATION_WEBHOOK_URL=https://your-n8n.example/webhook/qualified-lead
```

The notification includes the lead JSON and a stable event ID through the `Idempotency-Key` header.

This can be used to prevent duplicate CRM records.

A human approval step should remain in place before contacting a post author.

## 🧪 Automated Tests

Testing outside Docker is optional.

If Python is installed:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -q
```

The documented successful test run contains six passing tests.

## 🛠️ Useful Docker Commands

Check service status:

```powershell
docker compose ps
```

Follow all logs:

```powershell
docker compose logs -f
```

Follow classifier logs:

```powershell
docker compose logs -f classifier-worker
```

Restart services:

```powershell
docker compose up -d --force-recreate
```

Stop services while keeping data:

```powershell
docker compose down
```

Delete the local PostgreSQL volume:

```powershell
docker compose down -v
```

> **Warning:** `docker compose down -v` permanently removes the local PostgreSQL volume. Use it only when you intentionally want a clean reset.

## 🐛 Troubleshooting

### Docker command is not recognized

Install Docker Desktop, restart Windows, and reopen PowerShell.

### API page does not open

Check:

```powershell
docker compose ps
docker compose logs api
```

Kafka may still be becoming healthy during initial startup.

### No emails appear

Check:

```powershell
docker compose logs notifier-worker
```

Also confirm MailHog is running and:

```env
SMTP_HOST=mailhog
```

### API returns `401`

Confirm that the `X-API-Key` header matches:

```env
INGEST_API_KEY=...
```

### A good post is rejected

Check:

- Classifier mode
- Lead rules
- Confidence threshold
- Relevant phrases in `config/lead_rules.json`

### Duplicate source alerts

Every incoming event should contain a stable:

```text
source_message_id
```

This helps prevent duplicate classifications and notifications.

## 🚀 Production Considerations

Before using this system with real data:

- Replace `development-key` with a long random secret.
- Deploy behind HTTPS.
- Restrict network access.
- Use secure managed Kafka and PostgreSQL or properly hardened infrastructure.
- Use a real SMTP provider or secured webhook.
- Store secrets outside source code.
- Add centralized logging.
- Monitor Kafka consumer lag.
- Add uptime monitoring and cost monitoring.
- Define retention and deletion rules for post text, author names, and URLs.
- Confirm applicable Meta, group, privacy, mailbox, and CRM requirements.
- Keep human approval before contacting a poster or generating outreach.

## 🔒 Responsible Data Use

This project is intended for authorized, transparent data flows.

It should not be used to:

- Scrape private Facebook groups
- Automate personal Facebook logins
- Circumvent platform access controls
- Collect data without appropriate authorization
- Automatically contact people without appropriate review

Use an approved Meta integration, notification workflow, or deliberate user submission when processing real content.

## ✅ Final Verification

The project is working when:

- The API accepts a new event with status `202`.
- The classifier produces a qualified or rejected decision within seconds.
- Qualified events appear in PostgreSQL and `GET /leads`.
- Only qualified events create MailHog emails or webhook notifications.
- Repeating the same source message ID does not create a duplicate stored classification or notification.

## 📚 Documentation

For detailed Windows and Docker execution instructions, see the project execution guide.

---

## 👤 Author

**Aman Ansari**

AI & Data Science | Machine Learning | Data Engineering | Cloud

