from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    email = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Recipient(Base):
    __tablename__ = "recipients"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    name = Column(String)
    custom_fields = Column(Text)  # JSON string for custom fields
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    user = relationship("User")


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    html_body = Column(Text, nullable=False)
    text_body = Column(Text)
    placeholders = Column(Text)  # JSON list of available placeholders
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User")


class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    key_value = Column(String, nullable=False)  # Encrypted
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    last_used = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")


class EmailLog(Base):
    __tablename__ = "email_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_email = Column(String, nullable=False, index=True)
    subject = Column(String)
    status = Column(String, nullable=False)  # sent, failed, pending
    error_message = Column(Text)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"))
    template_id = Column(Integer, ForeignKey("email_templates.id"))
    scheduled_job_id = Column(Integer, ForeignKey("scheduled_jobs.id"))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    user = relationship("User")
    api_key = relationship("ApiKey")
    template = relationship("EmailTemplate")
    job = relationship("ScheduledJob", back_populates="logs")


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    template_id = Column(Integer, ForeignKey("email_templates.id"))
    recipient_emails = Column(Text)  # JSON list
    schedule_type = Column(String, nullable=False)  # once, daily, weekly, monthly
    schedule_time = Column(DateTime)  # For one-time sends
    cron_expression = Column(String)  # For recurring
    is_active = Column(Boolean, default=True)
    next_run = Column(DateTime, index=True)
    last_run = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    template = relationship("EmailTemplate")
    logs = relationship("EmailLog", back_populates="job")


class AppConfig(Base):
    __tablename__ = "app_config"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)
    description = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SenderProfile(Base):
    __tablename__ = "sender_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)  # Profile name (e.g., "Marketing", "Support")
    email = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    is_default = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)  # Track if domain is verified in Resend
    domain = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")


# Database setup
def get_engine(database_url: str):
    return create_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})


def get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def init_db(engine):
    Base.metadata.create_all(bind=engine)
