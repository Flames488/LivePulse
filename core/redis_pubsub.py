
import redis, os, json
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
def publish(channel, data): redis_client.publish(channel, json.dumps(data))
