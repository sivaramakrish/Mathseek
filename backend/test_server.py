from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.testclient import TestClient
import pytest
from datetime import timedelta
from main import (
    app, 
    authenticate_user, 
    create_access_token, 
    ACCESS_TOKEN_EXPIRE_MINUTES, 
    users_db, 
    pwd_context,
    UserCreate,  
    UserInDB, 
    call_deepseek_api,
    cost_tracker
)

app = FastAPI()

# Initialize OAuth2 with token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# Define protected endpoint
@app.get("/protected")
async def protected_endpoint(token: str = Depends(oauth2_scheme)):
    return {"status": "protected", "message": "Access granted"}

# Define token endpoint
@app.post("/auth/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Initialize test client
client = TestClient(app)

# Test data
TEST_USER = {"username": "testuser", "password": "testpass"}
INVALID_USER = {"username": "wronguser", "password": "wrongpass"}
CHAT_REQUEST = {
    "prompt": "What is the capital of France?",
    "tone": "friendly",
    "language": "en"
}

# Test fixture for setting up test user
@pytest.fixture(autouse=True)
def setup_test_user():
    """Setup test user before each test"""
    # Clear existing users
    users_db.clear()
    
    # Create test user
    hashed_password = pwd_context.hash(TEST_USER["password"])
    users_db[TEST_USER["username"]] = {
        "username": TEST_USER["username"],
        "hashed_password": hashed_password
    }
    
    # Reset cost tracker
    cost_tracker.reset()
    
    yield
    
    # Cleanup
    users_db.clear()
    cost_tracker.reset()

# Helper function to get token
@pytest.fixture
def get_token():
    """Get test user token"""
    response = client.post("/auth/token", data=TEST_USER)
    assert response.status_code == 200
    return response.json()["access_token"]

# Mock the API response for testing
@pytest.fixture
def mock_api_response():
    """Mock the API response"""
    mock_response = {
        "choices": [{
            "message": {
                "content": "The capital of France is Paris."
            }
        }],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 64,
            "total_tokens": 79
        }
    }
    return mock_response

# Token generation tests
def test_token_generation():
    """Test successful token generation"""
    response = client.post("/auth/token", data=TEST_USER)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "token_type" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_invalid_credentials():
    """Test token generation with invalid credentials"""
    response = client.post("/auth/token", data=INVALID_USER)
    assert response.status_code == 401
    assert "detail" in response.json()

# User authentication tests
def test_authenticate_user_valid():
    """Test successful user authentication"""
    user = authenticate_user(TEST_USER["username"], TEST_USER["password"])
    assert user is not None
    assert user.username == TEST_USER["username"]

def test_authenticate_user_invalid():
    """Test failed user authentication"""
    user = authenticate_user(INVALID_USER["username"], INVALID_USER["password"])
    assert user is None

# Protected endpoint tests
def test_protected_endpoint_with_token():
    """Test accessing protected endpoint with valid token"""
    # Get token first
    token_response = client.post("/auth/token", data=TEST_USER)
    token = token_response.json()["access_token"]
    
    # Access protected endpoint
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_protected_endpoint_without_token():
    """Test accessing protected endpoint without token"""
    response = client.get("/protected")
    assert response.status_code == 401

# Chat endpoint tests
def test_chat_endpoint(get_token, mock_api_response):
    """Test chat endpoint with valid token"""
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Mock the API call
    from main import call_deepseek_api
    call_deepseek_api = lambda prompt: mock_api_response
    
    response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
    assert response.status_code == 200
    
    data = response.json()
    assert "response" in data
    assert "tokens_used" in data
    assert isinstance(data["tokens_used"], int)
    assert data["response"] != ""

def test_chat_endpoint_invalid_token():
    """Test chat endpoint with invalid token"""
    headers = {"Authorization": "Bearer invalid_token", "Content-Type": "application/json"}
    
    response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
    assert response.status_code == 401
    assert "detail" in response.json()

def test_chat_endpoint_no_token():
    """Test chat endpoint without token"""
    response = client.post("/chat", json=CHAT_REQUEST)
    assert response.status_code == 401
    assert "detail" in response.json()

def test_chat_endpoint_rate_limit(get_token):
    """Test rate limiting on chat endpoint"""
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Make 11 requests (10 is the limit)
    for i in range(11):
        response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
        if i < 10:
            assert response.status_code == 200
        else:
            assert response.status_code == 429
            assert "detail" in response.json()

def test_chat_endpoint_invalid_request(get_token):
    """Test chat endpoint with invalid request data"""
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Test with missing prompt
    invalid_request = {"tone": "friendly", "language": "en"}
    response = client.post("/chat", headers=headers, json=invalid_request)
    assert response.status_code == 422  # Unprocessable entity
    
    # Test with invalid tone
    invalid_request = {"prompt": "Hello", "tone": "invalid", "language": "en"}
    response = client.post("/chat", headers=headers, json=invalid_request)
    assert response.status_code == 200  # Should still work with default tone

def test_budget_management():
    """Test budget management endpoints"""
    # Test initial budget
    response = client.get("/budget")
    assert response.status_code == 200
    budget_data = response.json()
    assert budget_data["current_budget"] == 2.0
    
    # Test setting new budget
    new_budget = 1.5
    response = client.post("/budget", json={"amount": new_budget})
    assert response.status_code == 200
    assert response.json()["new_budget"] == new_budget
    
    # Test budget history
    response = client.get("/budget/history")
    assert response.status_code == 200
    history = response.json()["history"]
    assert len(history) >= 1
    
    # Test usage tracking
    response = client.get("/usage")
    assert response.status_code == 200
    usage = response.json()
    assert "total_cost" in usage
    assert "budget_remaining" in usage

def test_budget_alerts(get_token, mock_api_response):
    """Test budget alert system"""
    # Set a low budget to trigger alerts
    response = client.post("/budget", json={"amount": 0.1})
    assert response.status_code == 200
    
    # Make a request that should trigger an alert
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Mock the API call
    from main import call_deepseek_api
    call_deepseek_api = lambda prompt: mock_api_response
    
    response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
    assert response.status_code == 200
    
    # Check for alerts
    response = client.get("/budget/alerts")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) >= 1
    
    # Reset budget
    response = client.post("/budget", json={"amount": 2.0})
    assert response.status_code == 200

def test_usage_projection(get_token, mock_api_response):
    """Test usage projection system"""
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Make a few requests to establish usage pattern
    for _ in range(3):
        # Mock the API call
        from main import call_deepseek_api
        call_deepseek_api = lambda prompt: mock_api_response
        
        response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
        assert response.status_code == 200
    
    # Get usage projection
    response = client.get("/usage/projection")
    assert response.status_code == 200
    projection = response.json()
    assert "avg_cost_per_request" in projection
    assert "estimated_remaining_requests" in projection
    assert "projected_total_cost" in projection

def test_rate_limiting(get_token):
    """Test rate limiting on chat endpoint"""
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Make 11 requests (10 is the limit)
    for i in range(11):
        response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
        if i < 10:
            assert response.status_code == 200
        else:
            assert response.status_code == 429
            assert "detail" in response.json()

def test_budget_exceeded(get_token, mock_api_response):
    """Test behavior when budget is exceeded"""
    # Set a very low budget
    response = client.post("/budget", json={"amount": 0.01})
    assert response.status_code == 200
    
    # Try to make a request that should exceed budget
    token = get_token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Mock the API call
    from main import call_deepseek_api
    call_deepseek_api = lambda prompt: mock_api_response
    
    response = client.post("/chat", headers=headers, json=CHAT_REQUEST)
    assert response.status_code == 400
    assert "Budget exceeded" in response.json()["detail"]

# Token expiration test (requires mocking time)
@pytest.mark.skip(reason="Requires time mocking")
def test_token_expiration():
    """Test token expiration"""
    pass

# Existing endpoints
@app.get("/test")
async def test_endpoint():
    return {"status": "working", "message": "Minimal test successful"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    pytest.main(["-v", "test_server.py"])
