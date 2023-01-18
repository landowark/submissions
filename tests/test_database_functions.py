from sqlalchemy import create_engine   
from sqlalchemy.orm import Session
from src.submissions.backend.db.models import *
from src.submissions.backend.db import get_kits_by_use
 
engine = create_engine("sqlite+pysqlite:///:memory:", echo=True, future=True)
session = Session(engine)
metadata.create_all(engine)