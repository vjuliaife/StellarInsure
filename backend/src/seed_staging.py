"""Seed script for staging environment data."""

from decimal import Decimal
import os
import time
import logging

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Policy, PolicyStatus, PolicyType, User

logger = logging.getLogger(__name__)


def seed(db: Session) -> None:
    first = (
        db.query(User)
        .filter(User.stellar_address == "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF")
        .first()
    )
    second = (
        db.query(User)
        .filter(User.stellar_address == "GBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBWHF")
        .first()
    )

    if not first:
        first = User(
            stellar_address="GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
            email="staging-user-1@stellarinsure.test",
        )
        db.add(first)

    if not second:
        second = User(
            stellar_address="GBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBWHF",
            email="staging-user-2@stellarinsure.test",
        )
        db.add(second)

    db.flush()

    existing_policy = (
        db.query(Policy)
        .filter(Policy.policyholder_id == first.id, Policy.trigger_condition == "seeded-weather-threshold")
        .first()
    )
    if not existing_policy:
        now = int(time.time())
        db.add(
            Policy(
                policyholder_id=first.id,
                policy_type=PolicyType.weather,
                coverage_amount=Decimal("1000.0000000"),
                premium=Decimal("25.0000000"),
                start_time=now,
                end_time=now + 2_592_000,
                trigger_condition="seeded-weather-threshold",
                status=PolicyStatus.active,
                claim_amount=Decimal("0"),
            )
        )

    db.commit()


def main() -> None:
    environment = os.getenv("ENVIRONMENT", "development")
    if environment != "staging":
        raise RuntimeError("Seeding aborted: ENVIRONMENT must be 'staging'.")

    db = SessionLocal()
    try:
        seed(db)
        logger.info("Staging seed completed successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
