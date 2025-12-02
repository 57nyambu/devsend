import resend
import logging
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from devsend.models import ApiKey, EmailLog, Recipient
from datetime import datetime
import json
import re

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, db: Session):
        self.db = db
        
    def get_active_api_key(self, preferred_key_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[ApiKey]:
        """Get an active API key, prefer least recently used for rotation"""
        if preferred_key_id:
            query = self.db.query(ApiKey).filter(
                ApiKey.id == preferred_key_id,
                ApiKey.is_active == True
            )
            if user_id:
                query = query.filter(ApiKey.user_id == user_id)
            key = query.first()
            if key:
                return key
        
        # Auto-rotation: get least recently used active key
        query = self.db.query(ApiKey).filter(
            ApiKey.is_active == True
        )
        if user_id:
            query = query.filter(ApiKey.user_id == user_id)
        key = query.order_by(ApiKey.last_used.asc().nullsfirst()).first()
        
        return key
    
    def replace_placeholders(self, text: str, variables: Dict[str, str]) -> str:
        """Replace {{variable}} placeholders with actual values"""
        for key, value in variables.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text
    
    def send_email(
        self,
        recipient_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        sender_email: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_profile_id: Optional[int] = None,
        template_id: Optional[int] = None,
        scheduled_job_id: Optional[int] = None,
        variables: Optional[Dict[str, str]] = None,
        api_key_id: Optional[int] = None,
        max_retries: int = 3,
        user_id: Optional[int] = None
    ) -> bool:
        """Send an email with retry logic"""
        from devsend.config import settings
        from devsend.models import SenderProfile
        
        # Get sender from profile if provided
        if sender_profile_id:
            profile = self.db.query(SenderProfile).filter(SenderProfile.id == sender_profile_id).first()
            if profile:
                sender_email = profile.email
                sender_name = profile.display_name
        
        # Fall back to settings or use defaults
        sender_email = sender_email or settings.default_sender_email
        sender_name = sender_name or settings.default_sender_name
        variables = variables or {}
        
        # Replace placeholders
        subject = self.replace_placeholders(subject, variables)
        html_body = self.replace_placeholders(html_body, variables)
        if text_body:
            text_body = self.replace_placeholders(text_body, variables)
        
        api_key = self.get_active_api_key(api_key_id, user_id)
        if not api_key:
            self._log_email(
                recipient_email, subject, "failed", 
                "No active API key available", 
                template_id=template_id, 
                scheduled_job_id=scheduled_job_id,
                user_id=user_id
            )
            return False
        
        # Try sending with retries
        for attempt in range(max_retries):
            try:
                resend.api_key = api_key.key_value
                
                params = {
                    "from": f"{sender_name} <{sender_email}>",
                    "to": [recipient_email],
                    "subject": subject,
                    "html": html_body,
                }
                
                if text_body:
                    params["text"] = text_body
                
                response = resend.Emails.send(params)
                
                # Update API key usage
                api_key.usage_count += 1
                api_key.last_used = datetime.utcnow()
                self.db.commit()
                
                # Log success
                self._log_email(
                    recipient_email, subject, "sent", 
                    None, api_key.id, template_id, scheduled_job_id, user_id
                )
                
                logger.info(f"Email sent to {recipient_email}: {response}")
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Attempt {attempt + 1} failed for {recipient_email}: {error_msg}")
                
                if attempt == max_retries - 1:
                    # Final failure
                    self._log_email(
                        recipient_email, subject, "failed", 
                        error_msg, api_key.id, template_id, scheduled_job_id, user_id
                    )
                    return False
        
        return False
    
    def send_bulk(
        self,
        recipient_emails: List[str],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        sender_email: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_profile_id: Optional[int] = None,
        template_id: Optional[int] = None,
        scheduled_job_id: Optional[int] = None,
        personalize: bool = True,
        user_id: Optional[int] = None,
        custom_placeholders: Optional[Dict[str, str]] = None
    ) -> Dict[str, int]:
        """Send to multiple recipients"""
        results = {"sent": 0, "failed": 0}
        
        for email in recipient_emails:
            variables = {}
            
            # Start with custom placeholder defaults
            if custom_placeholders:
                variables.update(custom_placeholders)
            
            # Get recipient data for personalization (this overrides defaults)
            if personalize:
                query = self.db.query(Recipient).filter(Recipient.email == email)
                if user_id:
                    query = query.filter(Recipient.user_id == user_id)
                recipient = query.first()
                
                if recipient:
                    variables["name"] = recipient.name or variables.get("name", "")
                    variables["email"] = recipient.email
                    
                    # Add custom fields (these override defaults too)
                    if recipient.custom_fields:
                        try:
                            custom_data = json.loads(recipient.custom_fields)
                            variables.update(custom_data)
                        except:
                            pass
            
            # Ensure email is always set
            if "email" not in variables:
                variables["email"] = email
            
            success = self.send_email(
                recipient_email=email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                sender_email=sender_email,
                sender_name=sender_name,
                sender_profile_id=sender_profile_id,
                template_id=template_id,
                scheduled_job_id=scheduled_job_id,
                variables=variables,
                user_id=user_id
            )
            
            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1
        
        return results
    
    def _log_email(
        self,
        recipient_email: str,
        subject: str,
        status: str,
        error_message: Optional[str] = None,
        api_key_id: Optional[int] = None,
        template_id: Optional[int] = None,
        scheduled_job_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        """Log email send attempt"""
        log = EmailLog(
            recipient_email=recipient_email,
            subject=subject,
            status=status,
            error_message=error_message,
            api_key_id=api_key_id,
            template_id=template_id,
            scheduled_job_id=scheduled_job_id,
            user_id=user_id
        )
        self.db.add(log)
        self.db.commit()
