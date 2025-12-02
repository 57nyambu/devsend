from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import json
import logging

from devsend.config import settings
from devsend.database import get_db, get_db_engine
from devsend.models import (
    Recipient, EmailTemplate, ApiKey, EmailLog, 
    ScheduledJob, AppConfig, SenderProfile, init_db
)
from devsend.email_service import EmailService
from devsend.scheduler import start_scheduler, schedule_job, load_all_jobs, stop_scheduler
from devsend.auth import authenticate_user, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    engine = get_db_engine()
    init_db(engine)
    
    # Start scheduler
    start_scheduler(settings.database_url)
    
    # Load all scheduled jobs
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    load_all_jobs(db, settings.database_url)
    db.close()
    
    logger.info("DevSend started successfully")
    
    yield
    
    # Shutdown
    stop_scheduler()
    logger.info("DevSend shut down")


app = FastAPI(title="DevSend", version="1.0.0", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="devsend/templates")
app.mount("/static", StaticFiles(directory="devsend/static"), name="static")


# Custom exception handler for authentication errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # For 401 Unauthorized, redirect to login for HTML requests, return JSON for API requests
    if exc.status_code == 401:
        # Check if this is an HTML request (browser) vs API request
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header or (request.url.path.startswith("/") and not request.url.path.startswith("/api/")):
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # For API requests or other errors, return JSON
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Auth endpoints
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/api/signup")
async def signup(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    from devsend.models import User
    from devsend.auth import get_password_hash
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Check if email already exists
    if email:
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Validate password length
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    # Create new user
    hashed_password = get_password_hash(password)
    new_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        is_active=True,
        is_admin=False
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "Account created successfully", "user_id": new_user.id}


@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(username, password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": username, "user_id": user.id})
    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    
    # Set cookie for HTML page authentication
    response.set_cookie(
        key="token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    
    return response


# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    
    # Get stats for current user
    total_recipients = db.query(Recipient).filter(
        Recipient.user_id == user_id,
        Recipient.is_active == True
    ).count()
    total_templates = db.query(EmailTemplate).filter(EmailTemplate.user_id == user_id).count()
    total_jobs = db.query(ScheduledJob).filter(
        ScheduledJob.user_id == user_id,
        ScheduledJob.is_active == True
    ).count()
    
    recent_logs = db.query(EmailLog).filter(
        EmailLog.user_id == user_id
    ).order_by(EmailLog.created_at.desc()).limit(10).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "total_recipients": total_recipients,
        "total_templates": total_templates,
        "total_jobs": total_jobs,
        "recent_logs": recent_logs
    })


# Recipients
@app.get("/recipients", response_class=HTMLResponse)
async def recipients_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    recipients = db.query(Recipient).filter(
        Recipient.user_id == user_id
    ).order_by(Recipient.created_at.desc()).all()
    return templates.TemplateResponse("recipients.html", {
        "request": request,
        "active_page": "recipients",
        "recipients": recipients
    })


@app.get("/api/recipients")
async def get_recipients(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    recipients = db.query(Recipient).filter(
        Recipient.user_id == user_id,
        Recipient.is_active == True
    ).order_by(Recipient.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "email": r.email,
            "name": r.name,
            "custom_fields": r.custom_fields
        }
        for r in recipients
    ]


@app.post("/api/recipients")
async def create_recipient(
    email: str = Form(...),
    name: str = Form(""),
    custom_fields: str = Form("{}"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    recipient = Recipient(user_id=user_id, email=email, name=name, custom_fields=custom_fields)
    db.add(recipient)
    db.commit()
    return {"id": recipient.id, "message": "Recipient created"}


@app.delete("/api/recipients/{recipient_id}")
async def delete_recipient(recipient_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    recipient = db.query(Recipient).filter(
        Recipient.id == recipient_id,
        Recipient.user_id == user_id
    ).first()
    if recipient:
        db.delete(recipient)
        db.commit()
        return {"message": "Recipient deleted"}
    raise HTTPException(status_code=404, detail="Recipient not found")


# Templates
@app.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    email_templates = db.query(EmailTemplate).filter(
        EmailTemplate.user_id == user_id
    ).order_by(EmailTemplate.created_at.desc()).all()
    return templates.TemplateResponse("templates.html", {
        "request": request,
        "active_page": "templates",
        "templates": email_templates
    })


@app.post("/api/templates")
async def create_template(
    name: str = Form(...),
    subject: str = Form(...),
    html_body: str = Form(...),
    text_body: str = Form(""),
    placeholders: str = Form("[]"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    template = EmailTemplate(
        user_id=user_id,
        name=name,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        placeholders=placeholders
    )
    db.add(template)
    db.commit()
    return {"id": template.id, "message": "Template created"}


@app.get("/api/templates/{template_id}")
async def get_template(template_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.user_id == user_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "id": template.id,
        "name": template.name,
        "subject": template.subject,
        "html_body": template.html_body,
        "text_body": template.text_body,
        "placeholders": template.placeholders
    }


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.user_id == user_id
    ).first()
    if template:
        db.delete(template)
        db.commit()
        return {"message": "Template deleted"}
    raise HTTPException(status_code=404, detail="Template not found")


# API Keys
@app.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    api_keys = db.query(ApiKey).filter(
        ApiKey.user_id == user_id
    ).order_by(ApiKey.created_at.desc()).all()
    return templates.TemplateResponse("api_keys.html", {
        "request": request,
        "active_page": "api-keys",
        "api_keys": api_keys
    })


@app.post("/api/api-keys")
async def create_api_key(
    name: str = Form(...),
    key_value: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    api_key = ApiKey(user_id=user_id, name=name, key_value=key_value)
    db.add(api_key)
    db.commit()
    return {"id": api_key.id, "message": "API key added"}


@app.delete("/api/api-keys/{key_id}")
async def delete_api_key(key_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == user_id
    ).first()
    if api_key:
        db.delete(api_key)
        db.commit()
        return {"message": "API key deleted"}
    raise HTTPException(status_code=404, detail="API key not found")


# Scheduled Jobs
@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    jobs = db.query(ScheduledJob).filter(
        ScheduledJob.user_id == user_id
    ).order_by(ScheduledJob.created_at.desc()).all()
    templates_list = db.query(EmailTemplate).filter(EmailTemplate.user_id == user_id).all()
    return templates.TemplateResponse("jobs.html", {
        "request": request,
        "active_page": "jobs",
        "jobs": jobs,
        "templates": templates_list
    })


@app.post("/api/jobs")
async def create_job(
    request: Request,
    name: str = Form(...),
    template_id: int = Form(...),
    recipient_emails: str = Form(...),
    schedule_type: str = Form(...),
    schedule_time: str = Form(None),
    cron_expression: str = Form(""),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    
    # Parse recipients
    emails = [e.strip() for e in recipient_emails.split(",") if e.strip()]
    
    # Parse schedule time
    schedule_dt = None
    if schedule_time:
        schedule_dt = datetime.fromisoformat(schedule_time.replace('Z', '+00:00'))
    
    # Extract custom placeholder values from form
    form_data = await request.form()
    custom_placeholders = {}
    for key, value in form_data.items():
        if key.startswith("placeholder_"):
            placeholder_name = key.replace("placeholder_", "")
            if value.strip():  # Only include non-empty values
                custom_placeholders[placeholder_name] = value.strip()
    
    job = ScheduledJob(
        user_id=user_id,
        name=name,
        template_id=template_id,
        recipient_emails=json.dumps(emails),
        schedule_type=schedule_type,
        schedule_time=schedule_dt,
        cron_expression=cron_expression,
        next_run=schedule_dt,
        custom_data=json.dumps(custom_placeholders) if custom_placeholders else None
    )
    db.add(job)
    db.commit()
    
    # Add to scheduler
    schedule_job(job, settings.database_url)
    
    return {"id": job.id, "message": "Job scheduled"}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    job = db.query(ScheduledJob).filter(
        ScheduledJob.id == job_id,
        ScheduledJob.user_id == user_id
    ).first()
    if job:
        from devsend.scheduler import scheduler
        try:
            scheduler.remove_job(f"job_{job_id}")
        except:
            pass
        db.delete(job)
        db.commit()
        return {"message": "Job deleted"}
    raise HTTPException(status_code=404, detail="Job not found")


# Email Logs
@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    logs = db.query(EmailLog).filter(
        EmailLog.user_id == user_id
    ).order_by(EmailLog.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "active_page": "logs",
        "logs": logs
    })


# Send Email Now Page
@app.get("/send", response_class=HTMLResponse)
async def send_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    email_templates = db.query(EmailTemplate).filter(EmailTemplate.user_id == user_id).all()
    recipients_count = db.query(Recipient).filter(
        Recipient.user_id == user_id,
        Recipient.is_active == True
    ).count()
    return templates.TemplateResponse("send.html", {
        "request": request,
        "active_page": "send",
        "templates": email_templates,
        "recipients_count": recipients_count
    })


# Send Email Now API
@app.post("/api/send")
async def send_email_now(
    request: Request,
    template_id: int = Form(...),
    recipient_emails: str = Form(...),
    sender_profile_id: int = Form(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = current_user["user_id"]
        
        template = db.query(EmailTemplate).filter(
            EmailTemplate.id == template_id,
            EmailTemplate.user_id == user_id
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Verify sender profile exists and is verified
        sender_profile = db.query(SenderProfile).filter(
            SenderProfile.id == sender_profile_id,
            SenderProfile.user_id == user_id
        ).first()
        if not sender_profile:
            raise HTTPException(status_code=404, detail="Sender profile not found")
        
        if not sender_profile.is_verified:
            raise HTTPException(status_code=400, detail=f"Sender profile '{sender_profile.name}' is not verified. Please verify the domain in Resend first.")
        
        emails = [e.strip() for e in recipient_emails.split(",") if e.strip()]
        
        if not emails:
            raise HTTPException(status_code=400, detail="No valid email addresses provided")
        
        # Extract custom placeholder values from form
        form_data = await request.form()
        custom_placeholders = {}
        for key, value in form_data.items():
            if key.startswith("placeholder_"):
                placeholder_name = key.replace("placeholder_", "")
                if value.strip():  # Only include non-empty values
                    custom_placeholders[placeholder_name] = value.strip()
    
        email_service = EmailService(db)
        results = email_service.send_bulk(
            recipient_emails=emails,
            subject=template.subject,
            html_body=template.html_body,
            text_body=template.text_body,
            template_id=template.id,
            sender_profile_id=sender_profile_id,
            user_id=user_id,
            custom_placeholders=custom_placeholders
        )
        
        return {"message": f"Sent: {results['sent']}, Failed: {results['failed']}", "results": results}
    
    except Exception as e:
        logger.error(f"Error in send_email_now: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error sending emails: {str(e)}")


# Sender Profiles
@app.get("/senders", response_class=HTMLResponse)
async def senders_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    senders = db.query(SenderProfile).filter(
        SenderProfile.user_id == user_id
    ).order_by(SenderProfile.is_default.desc(), SenderProfile.created_at.desc()).all()
    return templates.TemplateResponse("senders.html", {
        "request": request,
        "active_page": "senders",
        "senders": senders
    })


@app.get("/api/senders")
async def get_senders(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["user_id"]
    senders = db.query(SenderProfile).filter(
        SenderProfile.user_id == user_id
    ).order_by(SenderProfile.is_default.desc(), SenderProfile.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "display_name": s.display_name,
            "domain": s.domain,
            "is_default": s.is_default,
            "is_verified": s.is_verified,
            "created_at": s.created_at.isoformat()
        }
        for s in senders
    ]


@app.post("/api/senders")
async def create_sender(
    name: str = Form(...),
    email: str = Form(...),
    display_name: str = Form(...),
    is_default: bool = Form(False),
    is_verified: bool = Form(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    
    # Extract domain from email
    domain = email.split("@")[1] if "@" in email else ""
    
    # If this sender is marked as default, unset other defaults for this user
    if is_default:
        db.query(SenderProfile).filter(SenderProfile.user_id == user_id).update({SenderProfile.is_default: False})
    
    sender = SenderProfile(
        user_id=user_id,
        name=name,
        email=email,
        display_name=display_name,
        domain=domain,
        is_default=is_default,
        is_verified=is_verified
    )
    db.add(sender)
    db.commit()
    
    return {"id": sender.id, "message": "Sender profile created"}


@app.patch("/api/senders/{sender_id}/default")
async def set_default_sender(
    sender_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    
    sender = db.query(SenderProfile).filter(
        SenderProfile.id == sender_id,
        SenderProfile.user_id == user_id
    ).first()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    
    # Unset all defaults for this user
    db.query(SenderProfile).filter(SenderProfile.user_id == user_id).update({SenderProfile.is_default: False})
    
    # Set this one as default
    sender.is_default = True
    db.commit()
    
    return {"message": "Default sender updated"}


@app.patch("/api/senders/{sender_id}/verify")
async def toggle_verified(
    sender_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    
    sender = db.query(SenderProfile).filter(
        SenderProfile.id == sender_id,
        SenderProfile.user_id == user_id
    ).first()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    
    sender.is_verified = not sender.is_verified
    db.commit()
    
    return {"message": "Verification status updated", "is_verified": sender.is_verified}


@app.delete("/api/senders/{sender_id}")
async def delete_sender(
    sender_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["user_id"]
    
    sender = db.query(SenderProfile).filter(
        SenderProfile.id == sender_id,
        SenderProfile.user_id == user_id
    ).first()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    
    if sender.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default sender. Set another sender as default first.")
    
    db.delete(sender)
    db.commit()
    
    return {"message": "Sender profile deleted"}


# Profile Management
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    from devsend.models import User
    
    user_id = current_user["user_id"]
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user statistics
    stats = {
        "recipients": db.query(Recipient).filter(Recipient.user_id == user_id).count(),
        "templates": db.query(EmailTemplate).filter(EmailTemplate.user_id == user_id).count(),
        "emails_sent": db.query(EmailLog).filter(
            EmailLog.user_id == user_id,
            EmailLog.status == "sent"
        ).count(),
        "active_jobs": db.query(ScheduledJob).filter(
            ScheduledJob.user_id == user_id,
            ScheduledJob.is_active == True
        ).count()
    }
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "active_page": "profile",
        "user": user,
        "stats": stats
    })


@app.patch("/api/profile/email")
async def update_email(
    email: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from devsend.models import User
    
    user_id = current_user["user_id"]
    
    # Check if email already exists for another user
    existing_user = db.query(User).filter(
        User.email == email,
        User.id != user_id
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use by another account"
        )
    
    # Update user email
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.email = email
    db.commit()
    
    return {"message": "Email updated successfully"}


@app.patch("/api/profile/password")
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from devsend.models import User
    from devsend.auth import verify_password, get_password_hash
    
    user_id = current_user["user_id"]
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify current password
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Validate new password
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )
    
    # Update password
    user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}


# Sample Templates
@app.post("/api/templates/create-samples")
async def create_sample_templates(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create professional sample templates for the user"""
    user_id = current_user["user_id"]
    
    # Check if samples already exist
    existing = db.query(EmailTemplate).filter(
        EmailTemplate.user_id == user_id,
        EmailTemplate.name.like("Sample:%")
    ).count()
    
    if existing > 0:
        raise HTTPException(status_code=400, detail="Sample templates already exist")
    
    sample_templates = [
        {
            "name": "Sample: Marketing Email",
            "subject": "Discover What's New at {{company}}",
            "html_body": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; }
        .header { background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); padding: 30px 20px; text-align: center; }
        .content { padding: 40px 30px; color: #333333; line-height: 1.6; }
        .content h1 { color: #1e40af; font-size: 28px; }
        .cta-button { display: inline-block; background: linear-gradient(135deg, #d4af37 0%, #f4d03f 100%); color: #000000; padding: 15px 40px; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 20px 0; }
        .highlight-box { background-color: #f0f9ff; border-left: 4px solid #1e40af; padding: 20px; margin: 20px 0; }
        .footer { background-color: #1e293b; color: #ffffff; padding: 30px; text-align: center; font-size: 14px; }
        .footer a { color: #d4af37; text-decoration: none; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1 style="color: white; margin: 0;">{{company}}</h1>
        </div>
        <div class="content">
            <h1>Hello {{name}}! 👋</h1>
            <p>We're excited to share something special with you today!</p>
            <div class="highlight-box">
                <h2>Why Choose Us?</h2>
                <p>✓ Industry-leading solutions</p>
                <p>✓ Trusted by thousands</p>
                <p>✓ 24/7 dedicated support</p>
            </div>
            <p style="text-align: center;">
                <a href="{{link}}" class="cta-button">Learn More</a>
            </p>
            <p>Best regards,<br>The {{company}} Team</p>
        </div>
        <div class="footer">
            <p>© 2024 {{company}}. All rights reserved.</p>
            <p><a href="{{unsubscribe}}">Unsubscribe</a></p>
        </div>
    </div>
</body>
</html>''',
            "text_body": "Hello {{name}}! We're excited to share something special with you. Visit {{link}} to learn more.",
            "placeholders": '["name", "email", "company", "link", "unsubscribe"]'
        },
        {
            "name": "Sample: Promotional Offer",
            "subject": "🎉 Exclusive 50% OFF - Limited Time!",
            "html_body": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; }
        .header { background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%); padding: 30px 20px; text-align: center; color: white; }
        .content { padding: 40px 30px; color: #333333; line-height: 1.6; }
        .promo-box { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 3px dashed #d4af37; padding: 30px; margin: 20px 0; text-align: center; }
        .promo-code { font-size: 32px; font-weight: bold; color: #92400e; letter-spacing: 2px; }
        .cta-button { display: inline-block; background: linear-gradient(135deg, #d4af37 0%, #f4d03f 100%); color: #000000; padding: 18px 50px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 18px; }
        .footer { background-color: #1e293b; color: #ffffff; padding: 30px; text-align: center; font-size: 14px; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1 style="margin: 0; font-size: 36px;">🔥 FLASH SALE 🔥</h1>
        </div>
        <div class="content">
            <h1 style="text-align: center;">Hi {{name}}!</h1>
            <p style="text-align: center; font-size: 18px;">We have an <strong>exclusive offer</strong> just for you!</p>
            <div class="promo-box">
                <h2 style="color: #92400e; margin-top: 0;">LIMITED TIME OFFER</h2>
                <p style="font-size: 28px; margin: 10px 0;"><strong>50% OFF</strong></p>
                <p style="font-size: 18px;">Use Code:</p>
                <div class="promo-code">SAVE50</div>
            </div>
            <p style="text-align: center; font-size: 16px;">
                ✓ Valid for 48 hours only<br>
                ✓ Free shipping included<br>
                ✓ No minimum purchase
            </p>
            <p style="text-align: center;">
                <a href="{{link}}" class="cta-button">Shop Now</a>
            </p>
            <p style="text-align: center; color: #dc2626; font-weight: bold;">⏰ Hurry! Offer expires soon</p>
        </div>
        <div class="footer">
            <p>© 2024 {{company}}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>''',
            "text_body": "FLASH SALE! Get 50% OFF with code SAVE50. Valid for 48 hours only. Shop now: {{link}}",
            "placeholders": '["name", "company", "link"]'
        },
        {
            "name": "Sample: Welcome Email",
            "subject": "Welcome to {{company}} - Let's Get Started! 🎊",
            "html_body": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; }
        .header { background: linear-gradient(135deg, #10b981 0%, #34d399 100%); padding: 40px 20px; text-align: center; color: white; }
        .content { padding: 40px 30px; color: #333333; line-height: 1.6; }
        .steps-box { background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 20px; margin: 20px 0; }
        .step { margin: 15px 0; padding-left: 30px; }
        .cta-button { display: inline-block; background: linear-gradient(135deg, #10b981 0%, #34d399 100%); color: white; padding: 15px 40px; text-decoration: none; border-radius: 5px; font-weight: bold; }
        .footer { background-color: #1e293b; color: #ffffff; padding: 30px; text-align: center; font-size: 14px; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1 style="margin: 0; font-size: 36px;">🎊 Welcome!</h1>
        </div>
        <div class="content">
            <h1>Hi {{name}},</h1>
            <p style="font-size: 18px;">We're thrilled to have you join <strong>{{company}}</strong>! 🎉</p>
            <p>You're now part of a community dedicated to excellence and innovation.</p>
            <div class="steps-box">
                <h2 style="color: #10b981; margin-top: 0;">🚀 Get Started in 3 Steps:</h2>
                <div class="step"><strong>1.</strong> Complete your profile</div>
                <div class="step"><strong>2.</strong> Explore our features</div>
                <div class="step"><strong>3.</strong> Join our community</div>
            </div>
            <h2>What You'll Get:</h2>
            <p>✓ Regular updates and exclusive content<br>
               ✓ Priority customer support<br>
               ✓ Access to premium features<br>
               ✓ Special offers and promotions</p>
            <p style="text-align: center;">
                <a href="{{link}}" class="cta-button">Complete Your Profile</a>
            </p>
            <p>If you have any questions, we're here to help!</p>
            <p>Welcome aboard!<br>The {{company}} Team</p>
        </div>
        <div class="footer">
            <p>© 2024 {{company}}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>''',
            "text_body": "Welcome to {{company}}, {{name}}! We're excited to have you. Get started: {{link}}",
            "placeholders": '["name", "company", "link"]'
        },
        {
            "name": "Sample: Newsletter",
            "subject": "📰 Your Monthly Update from {{company}}",
            "html_body": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; }
        .header { background: linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%); padding: 30px 20px; text-align: center; color: white; }
        .content { padding: 40px 30px; color: #333333; line-height: 1.6; }
        .article { border-bottom: 2px solid #e5e7eb; padding: 20px 0; }
        .article h2 { color: #7c3aed; }
        .cta-button { display: inline-block; background: linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; }
        .footer { background-color: #1e293b; color: #ffffff; padding: 30px; text-align: center; font-size: 14px; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1 style="margin: 0;">📰 Monthly Newsletter</h1>
        </div>
        <div class="content">
            <h1>Hi {{name}},</h1>
            <p>Here's what's new this month at {{company}}!</p>
            
            <div class="article">
                <h2>🎯 Feature Highlights</h2>
                <p>We've just released exciting new features designed to make your life easier. Check out our latest innovations!</p>
                <p><a href="{{link}}" class="cta-button">Learn More</a></p>
            </div>
            
            <div class="article">
                <h2>📚 Latest Blog Posts</h2>
                <p>• How to Maximize Your Productivity<br>
                   • Industry Trends You Need to Know<br>
                   • Customer Success Stories</p>
            </div>
            
            <div class="article">
                <h2>💡 Tips & Tricks</h2>
                <p>Did you know? You can save time by using our advanced features. Visit our knowledge base for expert tips.</p>
            </div>
            
            <p style="text-align: center; margin-top: 30px;">
                <a href="{{link}}" class="cta-button">Read Full Newsletter</a>
            </p>
            
            <p>Stay tuned for more updates!<br>The {{company}} Team</p>
        </div>
        <div class="footer">
            <p>© 2024 {{company}}. All rights reserved.</p>
            <p><a href="{{unsubscribe}}" style="color: #d4af37;">Unsubscribe</a></p>
        </div>
    </div>
</body>
</html>''',
            "text_body": "Your monthly newsletter from {{company}}. Read more: {{link}}",
            "placeholders": '["name", "company", "link", "unsubscribe"]'
        }
    ]
    
    created_count = 0
    for template_data in sample_templates:
        template = EmailTemplate(
            user_id=user_id,
            name=template_data["name"],
            subject=template_data["subject"],
            html_body=template_data["html_body"],
            text_body=template_data["text_body"],
            placeholders=template_data["placeholders"]
        )
        db.add(template)
        created_count += 1
    
    db.commit()
    
    return {"message": f"Created {created_count} sample templates successfully"}


# Logout endpoint
@app.post("/api/logout")
async def logout():
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key="token")
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
