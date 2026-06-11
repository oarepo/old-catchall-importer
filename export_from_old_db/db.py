import contextlib

import sqlalchemy
from sqlalchemy.orm import Session

engine = sqlalchemy.create_engine(
    "postgresql://nr_data_prod:nr_data_prod@localhost:5832/nr_data_prod"
)

@contextlib.contextmanager
def get_session():
    with Session(engine) as session:
        yield session
