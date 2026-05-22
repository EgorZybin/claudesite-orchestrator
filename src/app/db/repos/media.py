from sqlalchemy.orm import Session

from app.db.models.media import Media


class MediaRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        *,
        site_id: int,
        storage_path: str,
        mime_type: str,
        page_id: int | None = None,
        width: int | None = None,
        height: int | None = None,
        alt_text: str | None = None,
        extra: dict | None = None,
    ) -> Media:
        row = Media(
            site_id=site_id,
            page_id=page_id,
            storage_path=storage_path,
            mime_type=mime_type,
            width=width,
            height=height,
            alt_text=alt_text,
            extra=extra,
        )
        self._s.add(row)
        self._s.flush()
        return row
