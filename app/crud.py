from sqlalchemy.orm import Session
from . import models, schemas


def get_event(db: Session, event_id: int):
    return db.query(models.Event).filter(models.Event.id == event_id).first()


def get_events(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Event).offset(skip).limit(limit).all()


def create_event(db: Session, event: schemas.EventCreate):
    db_event = models.Event(
        name=event.name,
        tickets_sales_start=event.tickets_sales_start,
        tickets_sales_end=event.tickets_sales_end
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def update_event(db: Session, event_id: int, updated_event: schemas.EventBase):
    events_updated = db\
        .query(models.Event)\
        .filter(models.Event.id == event_id)\
        .update(updated_event)
    db.commit()
    return events_updated


def delete_event(db: Session, event_id: int):
    events_deleted = db\
        .query(models.Event)\
        .filter(models.Event.id == event_id)\
        .delete()
    db.commit()
    return events_deleted
