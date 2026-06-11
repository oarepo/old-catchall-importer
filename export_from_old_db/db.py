import contextlib

import sqlalchemy
from sqlalchemy.orm import Session

engine = sqlalchemy.create_engine(
    "postgresql://catchall:catchall@localhost:5832/catchall"
)


@contextlib.contextmanager
def get_session():
    with Session(engine) as session:
        yield session
