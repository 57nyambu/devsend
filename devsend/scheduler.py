from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from devsend.models import ScheduledJob, EmailTemplate
from devsend.email_service import EmailService
import json

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def execute_scheduled_job(job_id: int, db_url: str):
    """Execute a scheduled email job"""
    from devsend.models import get_engine
    from devsend.database import get_db_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = get_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job or not job.is_active:
            logger.warning(f"Job {job_id} not found or inactive")
            return
        
        template = db.query(EmailTemplate).filter(EmailTemplate.id == job.template_id).first()
        if not template:
            logger.error(f"Template {job.template_id} not found for job {job_id}")
            return
        
        # Parse recipients
        recipients = json.loads(job.recipient_emails)
        
        # Send emails
        email_service = EmailService(db)
        results = email_service.send_bulk(
            recipient_emails=recipients,
            subject=template.subject,
            html_body=template.html_body,
            text_body=template.text_body,
            template_id=template.id,
            scheduled_job_id=job.id,
            user_id=job.user_id
        )
        
        # Update job
        job.last_run = datetime.utcnow()
        
        # Calculate next run for recurring jobs
        if job.schedule_type != "once":
            job.next_run = calculate_next_run(job)
        else:
            job.is_active = False
        
        db.commit()
        
        logger.info(f"Job {job_id} executed: {results['sent']} sent, {results['failed']} failed")
        
    except Exception as e:
        logger.error(f"Error executing job {job_id}: {str(e)}")
        db.rollback()
    finally:
        db.close()


def calculate_next_run(job: ScheduledJob) -> datetime:
    """Calculate next run time based on schedule type"""
    now = datetime.utcnow()
    
    if job.schedule_type == "daily":
        # Run at same time tomorrow
        next_run = job.schedule_time or now
        next_run = next_run + timedelta(days=1)
        return next_run
    
    elif job.schedule_type == "weekly":
        # Run same day/time next week
        next_run = job.schedule_time or now
        next_run = next_run + timedelta(weeks=1)
        return next_run
    
    elif job.schedule_type == "monthly":
        # Run same day/time next month
        next_run = job.schedule_time or now
        if next_run.month == 12:
            next_run = next_run.replace(year=next_run.year + 1, month=1)
        else:
            next_run = next_run.replace(month=next_run.month + 1)
        return next_run
    
    return now


def schedule_job(job: ScheduledJob, db_url: str):
    """Add a job to the scheduler"""
    job_id = f"job_{job.id}"
    
    # Remove existing job if present
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    if not job.is_active:
        return
    
    try:
        if job.schedule_type == "once":
            # One-time job
            trigger = DateTrigger(run_date=job.schedule_time)
            scheduler.add_job(
                execute_scheduled_job,
                trigger=trigger,
                id=job_id,
                args=[job.id, db_url],
                replace_existing=True
            )
        
        elif job.cron_expression:
            # Custom cron
            parts = job.cron_expression.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                )
                scheduler.add_job(
                    execute_scheduled_job,
                    trigger=trigger,
                    id=job_id,
                    args=[job.id, db_url],
                    replace_existing=True
                )
        
        elif job.schedule_type == "daily":
            # Daily at specific time
            time = job.schedule_time or datetime.utcnow()
            trigger = CronTrigger(hour=time.hour, minute=time.minute)
            scheduler.add_job(
                execute_scheduled_job,
                trigger=trigger,
                id=job_id,
                args=[job.id, db_url],
                replace_existing=True
            )
        
        elif job.schedule_type == "weekly":
            # Weekly at specific time
            time = job.schedule_time or datetime.utcnow()
            day_of_week = time.weekday()
            trigger = CronTrigger(
                day_of_week=day_of_week,
                hour=time.hour,
                minute=time.minute
            )
            scheduler.add_job(
                execute_scheduled_job,
                trigger=trigger,
                id=job_id,
                args=[job.id, db_url],
                replace_existing=True
            )
        
        elif job.schedule_type == "monthly":
            # Monthly at specific time
            time = job.schedule_time or datetime.utcnow()
            trigger = CronTrigger(
                day=time.day,
                hour=time.hour,
                minute=time.minute
            )
            scheduler.add_job(
                execute_scheduled_job,
                trigger=trigger,
                id=job_id,
                args=[job.id, db_url],
                replace_existing=True
            )
        
        logger.info(f"Scheduled job {job_id} ({job.schedule_type})")
        
    except Exception as e:
        logger.error(f"Failed to schedule job {job.id}: {str(e)}")


def load_all_jobs(db: Session, db_url: str):
    """Load all active jobs into scheduler"""
    jobs = db.query(ScheduledJob).filter(ScheduledJob.is_active == True).all()
    for job in jobs:
        schedule_job(job, db_url)
    logger.info(f"Loaded {len(jobs)} scheduled jobs")


def start_scheduler(db_url: str):
    """Start the background scheduler"""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the background scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
