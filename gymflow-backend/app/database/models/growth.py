"""CRM, sales follow-up, campaigns, trials, revenue recovery and the shared event log."""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import (
    OpportunityStatus, OpportunityType, Priority, TaskKind, TaskStatus, TrialStatus,
)
from app.database.session import Base


class Campaign(IdMixin, TimestampMixin, TenantMixin, Base):
    """A marketing activity whose enquiries can be attributed (via ``code`` = utm_campaign)."""

    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("gym_id", "code", name="uq_campaigns_gym_code"),)

    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(64), default="other")  # a LeadSource value
    channel: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | active | ended
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)


class LeadInteraction(IdMixin, TenantMixin, Base):
    """Timeline entry on a lead: notes, calls, messages, stage changes, system events."""

    __tablename__ = "lead_interactions"

    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    # note | call | whatsapp | email | sms | chat | visit | stage_change | system
    kind: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str | None] = mapped_column(String(8))  # in | out
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    # True when this interaction counts as the gym responding to the lead.
    is_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class FollowUpTask(IdMixin, TimestampMixin, TenantMixin, Base):
    """A to-do for staff. Created by people, workflows or agents; de-duplicated by ``dedup_key``."""

    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        UniqueConstraint("gym_id", "dedup_key", name="uq_tasks_gym_dedup"),
        Index("ix_tasks_gym_status_due", "gym_id", "status", "due_at"),
    )

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[TaskKind] = mapped_column(enum_column(TaskKind), default=TaskKind.FOLLOW_UP)
    status: Mapped[TaskStatus] = mapped_column(enum_column(TaskStatus), default=TaskStatus.OPEN)
    priority: Mapped[Priority] = mapped_column(enum_column(Priority), default=Priority.MEDIUM)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("members.id", ondelete="CASCADE"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recovery_opportunities.id", ondelete="CASCADE"))
    trial_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trial_bookings.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual | workflow | agent
    draft_message: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str | None] = mapped_column(String(200))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    outcome: Mapped[str | None] = mapped_column(String(255))


class TrialBooking(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "trial_bookings"
    __table_args__ = (Index("ix_trials_gym_start", "gym_id", "starts_at"),)

    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    trainer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trainers.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[TrialStatus] = mapped_column(enum_column(TrialStatus), default=TrialStatus.BOOKED, index=True)
    source: Mapped[str] = mapped_column(String(32), default="staff")  # staff | crm | website | ai_agent
    notes: Mapped[str | None] = mapped_column(Text)
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    attended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    lost_reason: Mapped[str | None] = mapped_column(String(255))
    converted_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))


class RecoveryOpportunity(IdMixin, TimestampMixin, TenantMixin, Base):
    """Revenue at risk (renewals, dues, no-shows, neglected leads) and what happened to it.

    ``potential_revenue`` is an estimate and never counts as revenue. ``recovered_revenue`` is only set
    from a PAID payment record, and ``recovered_payment_id`` is unique so a payment is credited once.
    """

    __tablename__ = "recovery_opportunities"
    __table_args__ = (
        UniqueConstraint("gym_id", "dedup_key", name="uq_opps_gym_dedup"),
        Index("ix_opps_gym_status_type", "gym_id", "status", "type"),
    )

    type: Mapped[OpportunityType] = mapped_column(enum_column(OpportunityType))
    status: Mapped[OpportunityStatus] = mapped_column(enum_column(OpportunityStatus), default=OpportunityStatus.OPEN)
    priority: Mapped[Priority] = mapped_column(enum_column(Priority), default=Priority.MEDIUM)
    title: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("members.id", ondelete="CASCADE"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"))
    membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="CASCADE"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payments.id", ondelete="CASCADE"))
    trial_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trial_bookings.id", ondelete="CASCADE"))
    potential_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    next_action: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    # Renewal milestones already alerted on, e.g. ["30", "15", "7"] - prevents duplicate reminders.
    milestones: Mapped[list] = mapped_column(JSON, default=list)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_count: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str | None] = mapped_column(String(255))
    recovered_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    recovered_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("payments.id", ondelete="SET NULL"), unique=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_key: Mapped[str] = mapped_column(String(200))


class EventLog(IdMixin, TenantMixin, Base):
    """Append-only business-event and audit log (lead.created, payment.paid, trial.booked, ...)."""

    __tablename__ = "event_log"
    __table_args__ = (Index("ix_events_gym_type_time", "gym_id", "event_type", "created_at"),)

    event_type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    actor: Mapped[str] = mapped_column(String(32), default="user")  # user | system | agent | webhook
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
