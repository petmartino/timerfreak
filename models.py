"""
TimerFreak Database Models
Copyright (c) 2025 - Pet Martino

This software is licensed under the MIT License.
See the LICENSE file for more details.
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import DateTime, Integer, String, ForeignKey, Boolean, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

db = SQLAlchemy()


class SubscriptionTier(enum.Enum):
    """Subscription tiers for monetization"""
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class User(UserMixin, db.Model):
    """User account model"""
    __tablename__ = 'user'
    
    id = db.Column(Integer, primary_key=True)
    email = db.Column(String(255), unique=True, nullable=False, index=True)
    username = db.Column(String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(String(255), nullable=True)  # Null for OAuth-only users
    display_name = db.Column(String(100), nullable=True)
    
    # Account status
    is_active = db.Column(Boolean, default=True, nullable=False)
    is_verified = db.Column(Boolean, default=False, nullable=False)
    verification_token = db.Column(String(100), unique=True, nullable=True)
    reset_token = db.Column(String(100), unique=True, nullable=True)
    
    # Subscription info
    subscription_tier = db.Column(SQLEnum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    subscription_expires = db.Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = db.Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    oauth_accounts = relationship('OAuthAccount', backref='user', cascade='all, delete-orphan')
    sequences = relationship('Sequence', backref='owner', lazy='dynamic')
    activity_logs = relationship('UserActivityLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def get_id(self):
        """Return user ID for Flask-Login"""
        return str(self.id)
    
    @property
    def is_pro(self):
        """Check if user has Pro subscription"""
        return self.subscription_tier == SubscriptionTier.PRO and (
            self.subscription_expires is None or self.subscription_expires > datetime.now(timezone.utc)
        )
    
    @property
    def is_team(self):
        """Check if user has Team subscription"""
        return self.subscription_tier == SubscriptionTier.TEAM and (
            self.subscription_expires is None or self.subscription_expires > datetime.now(timezone.utc)
        )


class OAuthAccount(db.Model):
    """OAuth provider accounts linked to users"""
    __tablename__ = 'oauth_account'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    provider = db.Column(String(50), nullable=False)  # google, github, etc.
    provider_user_id = db.Column(String(255), nullable=False)
    access_token = db.Column(String(2048), nullable=True)
    refresh_token = db.Column(String(2048), nullable=True)
    token_expires = db.Column(DateTime(timezone=True), nullable=True)
    
    # Profile info from provider
    profile_data = db.Column(Text, nullable=True)  # JSON string with profile info
    
    created_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('provider', 'provider_user_id', name='unique_provider_account'),
    )
    
    def __repr__(self):
        return f'<OAuthAccount {self.provider}:{self.provider_user_id}>'


class UserActivityLog(db.Model):
    """User activity logging for analytics and security"""
    __tablename__ = 'user_activity_log'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    action = db.Column(String(100), nullable=False, index=True)  # login, logout, create_sequence, etc.
    category = db.Column(String(50), nullable=False, index=True)  # auth, sequence, timer, subscription
    
    # Context info
    ip_address = db.Column(String(45), nullable=True)  # IPv6 max length
    user_agent = db.Column(String(500), nullable=True)
    session_id = db.Column(String(100), nullable=True, index=True)
    
    # Optional references to related objects
    sequence_id = db.Column(String(20), nullable=True, index=True)
    timer_order = db.Column(Integer, nullable=True)
    
    # Additional data (JSON string)
    extra_data = db.Column(Text, nullable=True)
    
    timestamp = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    def __repr__(self):
        return f'<UserActivityLog {self.id} - {self.user_id} - {self.action}>'


# Import and update existing models from app.py
class TimerCategory(db.Model):
    """Fixed categories for classifying timer sequences (admin-managed only)"""
    __tablename__ = 'timer_category'

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(50), unique=True, nullable=False)
    slug = db.Column(String(50), unique=True, nullable=False)
    description = db.Column(String(200), nullable=True)
    sort_order = db.Column(Integer, nullable=False, default=0)
    is_active = db.Column(Integer, nullable=False, default=1)

    # Relationship
    sequences = relationship('Sequence', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<TimerCategory {self.name}>'


class Sequence(db.Model):
    """Timer sequence model - updated with owner reference"""
    __tablename__ = 'sequence'

    id = db.Column(String(20), primary_key=True)
    name = db.Column(String(100), index=True)
    theme = db.Column(String(50), nullable=True)
    featured = db.Column(Integer, default=0, nullable=False, index=True)
    created_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Owner reference (nullable for backward compatibility with anonymous sequences)
    owner_id = db.Column(Integer, ForeignKey('user.id'), nullable=True, index=True)
    is_public = db.Column(Boolean, default=True, nullable=False, index=True)

    # Category reference (nullable - admin managed only)
    category_id = db.Column(Integer, ForeignKey('timer_category.id'), nullable=True, index=True)

    # Relationships
    timers = relationship('Timer', backref='sequence', cascade="all, delete-orphan", order_by="Timer.timer_order")

    def __repr__(self):
        return f'<Sequence {self.id}>'


class Timer(db.Model):
    """Individual timer within a sequence"""
    __tablename__ = 'timer'

    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False, index=True)
    timer_name = db.Column(String(100))
    duration = db.Column(Integer, nullable=False)
    timer_order = db.Column(Integer, nullable=False, index=True)
    color = db.Column(String(7), default="#0cd413")
    alarm_sound = db.Column(String(100))

    # Loop settings for the sequence
    loop_default = db.Column(Boolean, default=False, nullable=False, server_default='0')
    loop_count = db.Column(Integer, nullable=True)  # NULL means unlimited loops

    def __repr__(self):
        return f'<Timer {self.id}>'


class Sound(db.Model):
    """Available alarm sounds"""
    __tablename__ = 'sound'
    
    id = db.Column(Integer, primary_key=True)
    filename = db.Column(String(100), nullable=False, unique=True)
    name = db.Column(String(100), nullable=False)
    default = db.Column(Integer, default=0, nullable=False, index=True)
    
    def to_dict(self):
        return {"filename": self.filename, "name": self.name, "default": self.default}
    
    def __repr__(self):
        return f'<Sound {self.name} ({self.filename})>'


class CounterLog(db.Model):
    """Timer activity logs - updated with owner reference"""
    __tablename__ = 'counter_log'
    
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False, index=True)
    timer_order = db.Column(Integer, nullable=True)
    event_type = db.Column(String(50), nullable=False, index=True)
    timestamp = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Owner reference (denormalized for faster queries)
    owner_id = db.Column(Integer, ForeignKey('user.id'), nullable=True, index=True)
    
    # Relationship
    sequence_rel = relationship('Sequence', backref='logs')
    
    def __repr__(self):
        return f'<CounterLog {self.id} - {self.event_type} - Seq: {self.sequence_id}>'


class PreviewTempData(db.Model):
    """Temporary storage for form data when user goes back from preview"""
    __tablename__ = 'preview_temp_data'

    id = db.Column(Integer, primary_key=True)
    preview_token = db.Column(String(50), unique=True, nullable=False, index=True)
    session_id = db.Column(String(100), nullable=True, index=True)
    sequence_name = db.Column(String(100), nullable=True)
    timers_data = db.Column(Text, nullable=True)  # JSON string of timer data
    loop_default = db.Column(Boolean, default=False, nullable=False, server_default='0')
    loop_count = db.Column(Integer, nullable=True)
    created_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f'<PreviewTempData {self.session_id}>'


class SequenceShare(db.Model):
    """Shared timer sequences with tracking"""
    __tablename__ = 'sequence_share'
    
    id = db.Column(Integer, primary_key=True)
    sequence_id = db.Column(String(20), ForeignKey('sequence.id'), nullable=False, index=True)
    share_token = db.Column(String(50), unique=True, nullable=False, index=True)
    
    # Share settings
    is_public = db.Column(Boolean, default=True, nullable=False)
    allow_copy = db.Column(Boolean, default=True, nullable=False)
    
    # Tracking
    view_count = db.Column(Integer, default=0, nullable=False)
    copy_count = db.Column(Integer, default=0, nullable=False)
    
    created_at = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = db.Column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    sequence = relationship('Sequence', backref='shares')
    
    def __repr__(self):
        return f'<SequenceShare {self.share_token}>'
