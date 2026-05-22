from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_session_factory


def readonly_session() -> Generator[Session, None, None]:
    """Сессия БД только для чтения (без commit при выходе)."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def readwrite_session() -> Generator[Session, None, None]:
    """Сессия БД с commit при успехе (для изменяющих роутов)."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
