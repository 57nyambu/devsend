# DevSend - Email Scheduling & Sending Tool

A simple, secure email automation tool using the Resend API. Schedule emails, manage templates, and track delivery with an easy-to-use web interface.

## Features

- 📧 Send emails via Resend API
- 📅 Schedule emails (once, daily, weekly, monthly)
- 📝 Rich HTML email templates with placeholders
- 👥 Recipient management with metadata
- 🔑 Multiple API key support with auto-rotation
- 📊 Email delivery logging
- 🔒 Secure admin authentication
- 🎯 Bulk sending with personalization

## Quick Start

### Windows Quick Start (Recommended)

**Double-click** `start.bat` or run in PowerShell:

```powershell
.\start.ps1
```

This will automatically:
- Create a virtual environment
- Install all dependencies
- Create `.env` file from template
- Start the application

### Manual Setup

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Configure Environment

Copy `.env.example` to `.env` and update:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:
```
SECRET_KEY=your-secret-key-here
DEBUG=True
DATABASE_URL=sqlite:///./devsend.db

ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password

DEFAULT_SENDER_EMAIL=noreply@yourdomain.com
DEFAULT_SENDER_NAME=YourApp
```

#### 3. Run the Application

```bash
python -m devsend.main
```

Or using uvicorn directly:

```bash
uvicorn devsend.main:app --reload
```

The application will be available at `http://localhost:8000`

#### 4. Login

Navigate to `http://localhost:8000` and login with:
- Username: `admin`
- Password: (what you set in `.env`)

## Usage Guide

### First-Time Setup

1. **Add Resend API Keys**
   - Get your API key from [Resend Dashboard](https://resend.com/api-keys)
   - Navigate to **API Keys** in DevSend
   - Click "Add API Key" and paste your key
   - Keys are automatically rotated for load balancing

2. **Verify Sender Domain**
   - Make sure your sender email domain is verified in Resend
   - Update `DEFAULT_SENDER_EMAIL` in `.env`

### Create Email Templates

1. Go to **Templates** → "Create Template"
2. Add a name and subject
3. Write HTML body with placeholders like `{{name}}` or `{{email}}`
4. Available placeholders: `{{name}}`, `{{email}}`, plus any custom metadata

**Example Template:**
```html
<h1>Hello {{name}}!</h1>
<p>Welcome to our service. Your email is {{email}}.</p>
<p>Best regards,<br>The Team</p>
```

### Manage Recipients

1. Navigate to **Recipients** → "Add Recipient"
2. Add email, name, and optional JSON metadata
3. Metadata example: `{"company": "Acme Inc", "plan": "premium"}`

### Schedule Emails

1. Go to **Scheduled Jobs** → "Schedule Job"
2. Select a template
3. Add recipient emails (comma-separated)
4. Choose schedule type:
   - **Once**: Single send at specific time
   - **Daily**: Repeat every day at same time
### Send Emails Immediately

1. Navigate to **Send Now** in the top menu
2. Select a template
3. Enter recipient email addresses (comma-separated)
4. Preview the email
5. Click "Send Now"

### View Logs

Navigate to **Logs** to see all sent emails with status and error messages. Features include:
- Real-time search filtering
- Export to CSV
- Status indicators
- Error message details
6. Optional: Use custom cron expression (e.g., `0 9 * * 1` for Mondays at 9 AM)

### View Logs

Navigate to **Logs** to see all sent emails with status and error messages.

## Project Structure

```
sender/
├── devsend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration management
│   ├── models.py            # Database models
│   ├── database.py          # Database connection
│   ├── auth.py              # Authentication logic
│   ├── email_service.py     # Resend API integration
│   ├── scheduler.py         # APScheduler jobs
│   ├── static/
│   │   └── app.js          # Frontend JavaScript
│   └── templates/          # HTML templates
│       ├── login.html
│       ├── dashboard.html
│       ├── recipients.html
│       ├── templates.html
│       ├── api_keys.html
│       ├── jobs.html
│       └── logs.html
├── requirements.txt
├── .env.example
└── README.md
```

## Database Schema

- **recipients**: Email addresses with names and metadata
- **email_templates**: Reusable templates with placeholders
- **api_keys**: Resend API keys with usage tracking
- **email_logs**: All send attempts with status
- **scheduled_jobs**: Recurring or one-time email jobs
- **app_config**: Application settings

## API Endpoints

### Authentication
- `POST /api/login` - Login and get JWT token

### Recipients
- `GET /recipients` - List all recipients
- `POST /api/recipients` - Create recipient
- `DELETE /api/recipients/{id}` - Delete recipient

### Templates
- `GET /templates` - List all templates
- `POST /api/templates` - Create template
- `GET /api/templates/{id}` - Get template details
- `DELETE /api/templates/{id}` - Delete template

### API Keys
- `GET /api-keys` - List all API keys
- `POST /api/api-keys` - Add API key
- `DELETE /api/api-keys/{id}` - Delete API key

### Jobs
- `GET /jobs` - List scheduled jobs
- `POST /api/jobs` - Create scheduled job
- `DELETE /api/jobs/{id}` - Delete job

### Logs
- `GET /logs` - View email logs

### Send
- `POST /api/send` - Send email immediately

## Production Deployment

### 1. Use PostgreSQL

Update `.env`:
```
DATABASE_URL=postgresql://user:password@localhost/devsend
```

### 2. Set Strong Credentials

```
SECRET_KEY=<generate-strong-random-key>
ADMIN_PASSWORD=<strong-password>
DEBUG=False
```

### 3. Use HTTPS

Deploy behind a reverse proxy (nginx/Caddy) with SSL certificate.

### 4. Run with Gunicorn

```bash
pip install gunicorn
gunicorn devsend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 5. Background Scheduler

The scheduler runs automatically within the FastAPI application. For production, consider:
- Running as a systemd service
- Using supervisor or PM2 for process management
- Container deployment (Docker)

## Sample Email Templates

### Welcome Email
```html
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h1 style="color: #333;">Welcome, {{name}}! 🎉</h1>
    <p>Thanks for signing up. We're excited to have you on board.</p>
    <p>Your registered email is: <strong>{{email}}</strong></p>
    <a href="https://yourapp.com/get-started" style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">Get Started</a>
</div>
```

### Weekly Newsletter
```html
<div style="font-family: Arial, sans-serif;">
    <h2>Weekly Update for {{name}}</h2>
    <p>Here's what's new this week...</p>
    <ul>
        <li>Feature Update: New dashboard</li>
        <li>Blog Post: Best practices</li>
        <li>Community: Join our forum</li>
    </ul>
</div>
```

## Troubleshooting

### Emails Not Sending
1. Check API key is valid and active
2. Verify sender email domain is verified in Resend
3. Check logs for error messages
4. Ensure rate limits aren't exceeded

### Scheduler Not Running
1. Check application logs
2. Verify jobs are marked as "Active"
3. Restart the application

### Database Errors
1. Delete `devsend.db` and restart (dev only)
2. Check DATABASE_URL is correct
3. Ensure database server is running (PostgreSQL)

## Security Notes

- Always use HTTPS in production
- Change default admin credentials
- Keep SECRET_KEY secure and unique
- Never commit `.env` file to version control
- API keys are stored in plaintext (consider encryption for production)
- Rate limiting is basic (enhance for production)

## License

MIT License - feel free to use and modify as needed.

## Support

For issues with:
- **Resend API**: Check [Resend Documentation](https://resend.com/docs)
- **DevSend**: Review logs and error messages

---

Built with FastAPI, SQLAlchemy, and Resend API.
