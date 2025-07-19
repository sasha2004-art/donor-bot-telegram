import datetime
from typing import List
from sqlalchemy import (
    String, BigInteger, ForeignKey,
    Integer, Boolean, DateTime, Date, Text, func, Float, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    university: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    faculty: Mapped[str] = mapped_column(String(100), nullable=True)
    study_group: Mapped[str] = mapped_column(String(50), nullable=True)
    gender: Mapped[str] = mapped_column(String(10), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(50), default='student', index=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    category: Mapped[str] = mapped_column(String(50), default='student', server_default='student')
    is_dkm_donor: Mapped[bool] = mapped_column(Boolean, default=False, server_default='f')
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False, server_default='f')
    graduation_year: Mapped[int] = mapped_column(Integer, nullable=True)

    donations: Mapped[List["Donation"]] = relationship(back_populates="user")
    registrations: Mapped[List["EventRegistration"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    waivers: Mapped[List["MedicalWaiver"]] = relationship(back_populates="user")
    orders: Mapped[List["MerchOrder"]] = relationship(foreign_keys="MerchOrder.user_id", back_populates="user", cascade="all, delete-orphan")
    blocks_given: Mapped[List["UserBlock"]] = relationship(foreign_keys="UserBlock.admin_id", back_populates="admin")
    blocks_received: Mapped[List["UserBlock"]] = relationship(foreign_keys="UserBlock.user_id", back_populates="blocked_user")


class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    event_datetime: Mapped[datetime.datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(Text)
    blood_center_name: Mapped[str] = mapped_column(String(255), nullable=True)
    
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    donation_type: Mapped[str] = mapped_column(String(50))
    points_per_donation: Mapped[int] = mapped_column(Integer)
    participant_limit: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registration_is_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default='t')
    registrations: Mapped[List["EventRegistration"]] = relationship(back_populates="event")
    feedbacks: Mapped[List["Feedback"]] = relationship(back_populates="event")


class EventRegistration(Base):
    __tablename__ = 'event_registrations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), index=True)
    status: Mapped[str] = mapped_column(String(50), default='registered')
    registration_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="registrations")
    event: Mapped["Event"] = relationship(back_populates="registrations")

class Donation(Base):
    __tablename__ = 'donations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), nullable=True, index=True)
    donation_date: Mapped[datetime.date] = mapped_column(Date)
    donation_type: Mapped[str] = mapped_column(String(50))
    points_awarded: Mapped[int] = mapped_column(Integer)
    feedback_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default='f', nullable=False)

    user: Mapped["User"] = relationship(back_populates="donations")
    event: Mapped["Event"] = relationship()
    
class Feedback(Base):
    __tablename__ = 'feedbacks'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'))
    
    well_being_score: Mapped[int] = mapped_column(Integer, nullable=True) # 1-5
    well_being_comment: Mapped[str] = mapped_column(Text, nullable=True)
    
    organization_score: Mapped[int] = mapped_column(Integer, nullable=True) # 1-10
    what_liked: Mapped[str] = mapped_column(Text, nullable=True)
    what_disliked: Mapped[str] = mapped_column(Text, nullable=True)
    other_suggestions: Mapped[str] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship()
    event: Mapped["Event"] = relationship(back_populates="feedbacks")

class MedicalWaiver(Base):
    __tablename__ = 'medical_waivers'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    start_date: Mapped[datetime.date] = mapped_column(Date)
    end_date: Mapped[datetime.date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(50))

    user: Mapped["User"] = relationship(back_populates="waivers")

class MerchItem(Base):
    __tablename__ = 'merch_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    photo_file_id: Mapped[str] = mapped_column(String(255))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    orders: Mapped[List["MerchOrder"]] = relationship(back_populates="item")

class MerchOrder(Base):
    __tablename__ = 'merch_orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('merch_items.id'))
    order_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(50), default='pending_pickup')
    completed_by_admin_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    completion_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="orders")
    item: Mapped["MerchItem"] = relationship(back_populates="orders")
    completed_by_admin: Mapped["User"] = relationship(foreign_keys=[completed_by_admin_id])


class UserBlock(Base):
    __tablename__ = 'user_blocks'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    admin_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    block_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    blocked_user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="blocks_received")
    admin: Mapped["User"] = relationship(foreign_keys=[admin_id], back_populates="blocks_given")
    
class Survey(Base):
    __tablename__ = 'surveys'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answers_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    verdict_text: Mapped[str] = mapped_column(Text, nullable=True)
    
    user: Mapped["User"] = relationship()
    
    
class InfoText(Base):
    __tablename__ = 'info_texts'
    section_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    section_title: Mapped[str] = mapped_column(String(100))
    section_text: Mapped[str] = mapped_column(Text)
    
class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str] = mapped_column(Text, nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), default='unanswered', index=True) # unanswered, answered
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_by_admin_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    answered_by_admin: Mapped["User"] = relationship(foreign_keys=[answered_by_admin_id])
    
    
    
class NoShowReport(Base):
    __tablename__ = 'no_show_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), index=True)
    reason: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship()
    event: Mapped["Event"] = relationship()
    
class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())