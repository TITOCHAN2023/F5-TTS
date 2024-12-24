from redis import Redis

from logger import logger


redis_config = {
    "host": "localhost",
    "port": 6380,
    "db": 0,
    "password": "bobbyishandsome",
}
REDIS_HOST = redis_config["host"]
REDIS_PORT = redis_config["port"]
REDIS_PASSWORD = redis_config["password"]
@logger.catch
def init_redis() -> Redis:
    r = Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True, db=0)
    pong = r.ping()
    if not pong:
        raise ConnectionError(f"Redis connection failed: {pong}")
    logger.info("Init redis successfully")
    r.flushdb()
    return r


r = init_redis()
