import os
import unittest
import requests
import redis

class TestAnonymousToken(unittest.TestCase):
    BASE_URL = "http://localhost:8000"
    
    def test_health_check(self):
        response = requests.get(f"{self.BASE_URL}/health")
        self.assertEqual(response.status_code, 200)
        
    def test_token_generation(self):
        response = requests.post(f"{self.BASE_URL}/api/anonymous/token")
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_token_lifecycle(self):
    # Generate token
    token_res = requests.post(f"{self.BASE_URL}/api/anonymous/token")
    token = token_res.json()["token"]
    
    # Verify Redis data
    redis_url = os.getenv("REDIS_URL")
    with redis.Redis.from_url(redis_url) as r:
        data = r.hgetall(f"anonymous:{token}")
        self.assertEqual(int(data[b"quota_remaining"]), 1000)
        
    # Use token
    requests.post(f"{self.BASE_URL}/chat", 
        headers={"X-Anonymous-Token": token},
        json={"message": "Test"}
    )
    
    # Verify quota decremented
    with redis.Redis.from_url(redis_url) as r:
        new_quota = int(r.hget(f"anonymous:{token}", "quota_remaining"))
        self.assertEqual(new_quota, 999)
        
    def test_quota_usage(self):
        token = requests.post(f"{self.BASE_URL}/api/anonymous/token").json()["token"]
        print(f"\nTesting with token: {token}")  # Debug output
        
        # First verify the token exists in Redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            with redis.Redis.from_url(redis_url) as r:
                token_data = r.hgetall(f"anonymous:{token}")
                print("Redis token data:", token_data)
                self.assertIn(b"quota_remaining", token_data)  # Verify token exists
        
        response = requests.post(
            f"{self.BASE_URL}/chat",
            headers={
                "X-Anonymous-Token": token,
                "Content-Type": "application/json"
            },
            json={"message": "Test"}
        )
        print("Response status:", response.status_code)
        print("Response body:", response.text)
        
        self.assertIn(response.status_code, [200, 429])

if __name__ == "__main__":
    unittest.main()