Facebook Real Time Lead Stream Execution Guide
Windows and Docker setup for the event driven realtor lead filter
Purpose. This guide shows exactly how to start, test, and stop the project. The working demo processes each authorized post as an individual Kafka event, classifies its context, stores the decision, and sends qualified leads to a local email inbox.
Important access limit. The project does not scrape private Facebook groups or automate a personal login. During setup, use the included sample events. Later, connect an authorized Meta source, notification email workflow, or deliberate user submission.
Successful first run
•	All six Docker services show as running or healthy.
•	The API documentation opens at http://localhost:8000/docs.
•	The sample script returns three accepted event IDs.
•	Two qualified lead emails appear at http://localhost:8025.
•	The completed contractor request is rejected and does not create an email.
How the streaming flow works
Stage	Component	What happens
1	FastAPI	Accepts one authorized post event and returns HTTP 202.
2	Kafka	Stores and transports the event immediately on incoming-posts.
3	Classifier worker	Uses rules or an LLM to determine intent, category, urgency, and confidence.
4	PostgreSQL	Keeps the original event, classification, notification status, and timestamps.
5	Notifier worker	Consumes qualified-leads and sends email or an optional webhook.
Before you begin
You need a Windows computer with administrator access and an internet connection for the first Docker image download.
Requirement	How to check	Expected result
Docker Desktop	Open Docker Desktop	The status says the engine is running
PowerShell	Open Windows Terminal or PowerShell	A command window opens
Free ports	Ports 8000, 8025, 5432, and 29092	No other local service is using them
Project files	Extract the ZIP	The docker-compose.yml file is visible
Step 1  Install Docker Desktop
Download Docker Desktop from https://www.docker.com/products/docker-desktop/. Install it, restart Windows if requested, and leave Docker Desktop open. The first start may take several minutes.
Step 2  Extract and open the project
Extract the ZIP. Open the facebook-realtime-lead-stream folder in File Explorer, click the address bar, type powershell, and press Enter. PowerShell should open inside the project folder.
Get-ChildItem
Confirm that Dockerfile, docker-compose.yml, README.md, app, config, scripts, tests, and docs are listed.
Step 3  Create the environment file
Copy the safe example configuration to the local .env file used by Docker Compose.
Copy-Item .env.example .env
For the first run, keep CLASSIFIER_MODE=rules. This proves the complete streaming pipeline without an API key or model charge.
Step 4  Start the complete system
Build the Python application image and start Kafka, PostgreSQL, MailHog, the API, the classifier worker, and the notifier worker.
docker compose up --build -d
The first run downloads several images and can take a few minutes. Do not close Docker Desktop.
Step 5  Verify the services
Wait approximately one minute and check container status.
docker compose ps
Expected services:
•	kafka
•	postgres
•	mailhog
•	api
•	classifier-worker
•	notifier-worker
If a worker is restarting, inspect its logs before continuing:
docker compose logs --tail 100 classifier-worker
docker compose logs --tail 100 notifier-worker
Step 6  Open the local tools
Open these addresses in a browser. They are available only on your computer unless you deliberately deploy the project elsewhere.
Address	Purpose	Expected view
http://localhost:8000	Application home	Running message and navigation links
http://localhost:8000/docs	Interactive API	POST /events and GET /leads
http://localhost:8000/health	API health	A JSON status of ok
http://localhost:8025	Demo email inbox	An empty MailHog inbox before testing
Step 7  Send the sample stream
Run the included PowerShell script. It sends two active requests and one completed request as three separate events.
powershell -ExecutionPolicy Bypass -File .\scripts\send-sample.ps1
Each accepted event returns status accepted, a stable event ID, and the incoming-posts topic name.
Step 8  Check the result
Wait five to ten seconds and refresh the MailHog page at http://localhost:8025. You should see a realtor or buyer lead and a roofing lead. The completed request should not appear.
Start-Process http://localhost:8025
Start-Process http://localhost:8000/leads
Test your own message
Use the interactive API after the sample works.
•	Open http://localhost:8000/docs.
•	Select POST /events and then Try it out.
•	Enter development-key for X-API-Key.
•	Replace the request body with the example below.
•	Select Execute and look for HTTP status 202.
{
  "source": "manual",
  "source_message_id": "test-100",
  "group_name": "Frisco Neighbors",
  "author": "Example User",
  "text": "Can anyone recommend a realtor for a first-time buyer in Frisco?",
  "post_url": "https://example.com/post/test-100"
}
Enable OpenAI classification
Keep rules mode until the sample pipeline works. Then open .env in Notepad and change these values:
CLASSIFIER_MODE=hybrid
OPENAI_API_KEY=your_real_key_here
OPENAI_MODEL=gpt-5-mini
Save the file and rebuild only the classifier worker:
docker compose up --build -d classifier-worker
Hybrid mode uses the model when a key is available and falls back to deterministic rules if the model request fails. Never paste the key into source code, commit .env, or share it in screenshots.
Customize the realtor criteria
Edit these .env fields and then recreate the workers:
TARGET_GROUPS=Frisco Neighbors,Dallas Real Estate
MARKET_LOCATIONS=Dallas,Fort Worth,Frisco,Plano,McKinney,Denton
LEAD_CONFIDENCE_THRESHOLD=0.80
Edit config/lead_rules.json to add or remove request phrases, categories, service types, urgency phrases, or completed-request phrases.
docker compose up --build -d --force-recreate classifier-worker notifier-worker
Connect an authorized real time source
The core system is source-neutral. Every approved source must send one JSON request to POST /events when a new message arrives.
Source option	How it connects	Requirement
Facebook notification email	Gmail or Outlook trigger sends each email to the API	The account must receive usable notification content
n8n email workflow	Email Trigger then HTTP Request to /events	Authorized mailbox credentials and API key
Approved Meta application	Approved event is transformed into the project JSON format	The required Meta product and permissions
User submission	A form or browser extension sends the visible post	A deliberate action by the signed-in user
Recommended n8n flow
Build this only after the local sample passes:
•	Use a Gmail or IMAP Trigger that fires for each new Facebook notification email.
•	Extract group name, author, message text, source message ID, and source URL.
•	Use an HTTP Request node with POST http://YOUR_SERVER:8000/events.
•	Add Content-Type application/json and X-API-Key using an n8n credential or secret.
•	Map the email values into the event schema and activate the workflow.
Do not expose localhost to the public internet without authentication, TLS, firewall rules, and a deployment plan.
Connect n8n HubSpot or another destination
The notifier can POST every qualified lead to one webhook. Add the production URL to .env:
NOTIFICATION_WEBHOOK_URL=https://your-n8n.example/webhook/qualified-lead
The request includes the full lead JSON and an Idempotency-Key header containing the stable event ID. In n8n, use this value to avoid creating duplicate CRM records. Keep a human approval step before contacting a poster.
Operations and troubleshooting
Problem	Check	Action
docker command is not recognized	Docker Desktop installation	Install Docker Desktop, restart Windows, and reopen PowerShell
API page does not open	docker compose ps and api logs	Wait for Kafka health or run docker compose logs api
No emails appear	notifier-worker logs	Confirm MailHog is running and SMTP_HOST is mailhog
Every API request returns 401	X-API-Key header	Use the same value as INGEST_API_KEY in .env
A good post is rejected	classifier mode, rules, and confidence	Add relevant phrases or enable hybrid classification
Duplicate source alerts	source_message_id	Provide the stable email or platform message ID on every event
Port already in use	Ports 8000, 8025, 5432, 29092	Stop the conflicting application or change the host-side Compose port
Useful commands
Purpose	PowerShell command
Show service status	docker compose ps
Follow all logs	docker compose logs -f
Follow classifier logs	docker compose logs -f classifier-worker
Restart services	docker compose up -d --force-recreate
Stop and keep data	docker compose down
Delete the local database volume	docker compose down -v
Data warning. docker compose down -v permanently removes the local PostgreSQL volume. Use it only when you intentionally want a clean reset.
Run automated tests
Testing outside Docker is optional. If Python is installed on Windows, run:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -q
A successful result shows six passing tests.
Before production use
•	Replace development-key with a long random secret.
•	Deploy behind HTTPS and restrict network access.
•	Use secure managed Kafka and PostgreSQL services or harden the self-hosted services.
•	Use a real SMTP provider or an approved webhook with secrets stored outside source code.
•	Add central logs, Kafka consumer-lag alerts, uptime checks, and cost monitoring.
•	Define retention and deletion rules for post text, author names, and URLs.
•	Confirm Meta, group, privacy, mailbox, and CRM rules before processing live content.
•	Keep human approval before contacting a poster or creating an outreach message.
Project file map
Path	Purpose
app/main.py	FastAPI event intake and lead-query endpoints
app/worker.py	Kafka consumer and classification pipeline
app/classifier.py	Rules and optional OpenAI classification
app/notifier.py	Email and webhook delivery
app/db.py	PostgreSQL schema and persistence
config/lead_rules.json	Customizable categories and intent phrases
scripts/send-sample.ps1	Windows sample-event sender
tests	Automated classifier and API tests
docker-compose.yml	Complete local streaming environment
Final verification
The project is working when all of these statements are true:
1. The API accepts a new event with status 202.
2. The classifier worker logs a qualified or rejected decision within seconds.
3. Qualified events appear in PostgreSQL and at GET /leads.
4. Only qualified events create MailHog email or webhook notifications.
5. Repeating the same source message ID does not create a second stored classification or notification.
