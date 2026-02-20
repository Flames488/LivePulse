
import time

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_time=60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure = None

    def call(self, func, *args, **kwargs):
        if self.failures >= self.failure_threshold:
            if time.time() - self.last_failure < self.recovery_time:
                raise Exception("Circuit open")
            else:
                self.failures = 0
        try:
            return func(*args, **kwargs)
        except Exception:
            self.failures += 1
            self.last_failure = time.time()
            raise
