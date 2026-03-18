from sqlalchemy import Column, String, Date, Text, Boolean, TIMESTAMP, ForeignKey, ARRAY, UniqueConstraint, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from db.connection import Base
import uuid

class UserConfig(Base):
    __tablename__ = "user_config"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id       = Column(String, nullable=False, unique=True)
    active_stores = Column(ARRAY(Text), nullable=False,
                           default=["trader_joes", "costco", "indian_store", "target"])
    num_people    = Column(Integer, nullable=False, default=1)
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                           onupdate=func.now())
    onboarding_complete = Column(Boolean, nullable=False, server_default='false')

class MealPlan(Base):
    __tablename__ = "meal_plans"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(String, nullable=False, default="default_user")
    week_start_date = Column(Date, nullable=False)
    meals           = Column(ARRAY(Text), nullable=False)
    num_people      = Column(Integer, nullable=False, default=1)
    active_stores   = Column(ARRAY(Text), nullable=False,
                             default=["trader_joes", "costco", "indian_store", "target"])
    status          = Column(String, nullable=False, default="pending")
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now())
    confirmed    = Column(Boolean, nullable=False, default=False)
    confirmed_at = Column(TIMESTAMP(timezone=True), nullable=True)


class GroceryList(Base):
    __tablename__ = "grocery_lists"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meal_plan_id = Column(UUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False)
    store        = Column(String, nullable=False)
    items        = Column(JSONB, nullable=False)
    created_at   = Column(TIMESTAMP(timezone=True), server_default=func.now())


class StorePreference(Base):
    __tablename__ = "store_preferences"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id            = Column(String, nullable=False, default="default_user")
    ingredient_pattern = Column(String, nullable=False)
    preferred_store    = Column(String, nullable=False)
    created_at         = Column(TIMESTAMP(timezone=True), server_default=func.now())


class FSAItem(Base):
    __tablename__ = "fsa_items"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_name  = Column(String, nullable=False, unique=True)
    category   = Column(String)
    eligible   = Column(Boolean, nullable=False)
    source_url = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Pantry(Base):
    __tablename__ = "pantry"
 
    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id                = Column(String, nullable=False, default="default_user")
    ingredient_name        = Column(String, nullable=False)
    quantity               = Column(Float, nullable=False, default=0)
    unit                   = Column(String, nullable=False)
    category               = Column(String, nullable=False)
    restock_threshold      = Column(Float, nullable=False, default=0)
    restock_threshold_unit = Column(String, nullable=False, server_default="g")  # ← NEW
    preferred_store        = Column(String, nullable=True)
    last_updated           = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

class Recipe(Base):
    __tablename__ = "recipes"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(String, nullable=False)
    name        = Column(String, nullable=False)
    servings    = Column(Integer, nullable=False, default=2)
    ingredients = Column(JSONB, nullable=False, default=list)
    created_at  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at  = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_recipe_user_name"),)

class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(String, nullable=False)
    meal_name       = Column(String, nullable=True)   # None = global
    ingredient_name = Column(String, nullable=False)
    reason          = Column(String, nullable=False)
    action_taken    = Column(String, nullable=False)
    action_data     = Column(JSONB, nullable=False, default=dict)
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now())