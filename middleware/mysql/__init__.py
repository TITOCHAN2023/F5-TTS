from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session

import os
import json
from urllib.parse import quote_plus
from dotenv import load_dotenv
load_dotenv()

# MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
# MYSQL_HOST = os.getenv("MYSQL_HOST")
# MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
# MYSQL_PORT = os.getenv("MYSQL_PORT")
# MYSQL_USER = os.getenv("MYSQL_USER")
PGSQLDB_CONFIG= os.getenv("PGSQLDB_CONFIG")
from logger import logger

from .models import BaseSchema

# MYSQL_LINK = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
pgsqldb_config =eval(PGSQLDB_CONFIG)

@logger.catch
def init_mysql_session() -> sessionmaker[Session]:

    # engine = create_engine(
    #     MYSQL_LINK,
    #     connect_args={
    #         "charset": "utf8mb4",
    #     },
    #     pool_size=10,
    #     max_overflow=20,
    #     pool_pre_ping=True,
    #     pool_use_lifo=True,
    #     pool_recycle=3600,
    # )


    password = quote_plus(pgsqldb_config["password"])
    engine = create_engine(f'postgresql+psycopg2://{pgsqldb_config["user"]}:{password}@{pgsqldb_config["host"]}:{pgsqldb_config["port"]}/{pgsqldb_config["dbname"]}',echo=False,client_encoding='utf8')


    session = sessionmaker(bind=engine)

    BaseSchema.metadata.create_all(engine)
    logger.info("Init session successfully")

    return session


session = init_mysql_session()
