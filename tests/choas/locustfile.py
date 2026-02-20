from locust import HttpUser, task, between

class LivePulseUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def health(self):
        self.client.get("/health")

    @task(2)
    def leaderboard(self):
        self.client.get("/api/v1/leaderboard")
