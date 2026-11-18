import os
from redis import Redis
def push(queue,job_id):
    Redis.from_url(os.environ['REDIS_URL']).rpush(queue,job_id)
