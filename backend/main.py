from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as aioredis
import logging
from typing import Optional, List
import os
import httpx
from pydantic import BaseModel
from dotenv import load_dotenv
import asyncio
import atexit
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
import logging
from enum import Enum
import tiktoken
from typing import Dict
import random
from fastapi import Body
from google.oauth2 import id_token
from google.auth.transport import requests
import uuid
import redis
from datetime import datetime

# Initialize FastAPI app
app = FastAPI()

# Token tracking database models
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

class User(BaseModel):
    id: str
    name: str
    email: str
    tier: str = "free"
    daily_token_limit: int = 10000
    monthly_token_limit: int = 0
    created_at: datetime = datetime.utcnow()

class TokenUsage(BaseModel):
    user_id: str
    tokens_used: int
    operation: str
    timestamp: datetime = datetime.utcnow()

# Database setup (in production use MongoDB/PostgreSQL)
users_db: Dict[str, User] = {}
token_usage_db: List[TokenUsage] = []

def reset_daily_limits():
    # In production, run this daily via cron job
    for user in users_db.values():
        if user.tier == "free":
            user.daily_token_limit = 10000

@app.post("/track-usage")
async def track_usage(
    user_id: str = Body(...),
    tokens_used: int = Body(...),
    operation: str = Body(...)
):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Record usage
    usage = TokenUsage(
        user_id=user_id,
        tokens_used=tokens_used,
        operation=operation
    )
    token_usage_db.append(usage)
    
    # Update user's daily usage
    user = users_db[user_id]
    user.daily_token_limit -= tokens_used
    
    return {"status": "success", "remaining": user.daily_token_limit}

@app.get("/usage-history/{user_id}")
async def get_usage_history(user_id: str):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    history = [u for u in token_usage_db if u.user_id == user_id]
    return {"history": history, "total_used": sum(u.tokens_used for u in history)}

logging.basicConfig(level=logging.DEBUG)

# Configuration
load_dotenv('config.env')
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', 'your-google-client-id')

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Redis setup
redis_conn = aioredis.from_url(
    "redis://localhost:6379",
    decode_responses=True,
    socket_connect_timeout=5,
    retry_on_timeout=True
)

security = HTTPBearer()

# Rate Limiter Setup
@app.on_event("startup")
async def startup():
    try:
        await FastAPILimiter.init(redis_conn)
        logging.info("Redis rate limiter initialized")
        
        # Verify API key is loaded
        DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        if not DEEPSEEK_API_KEY:
            logging.error("DEEPSEEK_API_KEY not found in environment")
            raise ValueError("Missing DEEPSEEK_API_KEY in environment")
        logging.info("DeepSeek API key verified")
    except Exception as e:
        logging.error(f"Startup error: {e}")
        raise

# Auth Utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request):
    # Explicit header check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Existing token validation logic
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Your existing user validation
        user = users_db.get(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return {"sub": user_id}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

# New dependency for anonymous or authenticated users
async def get_user_or_anonymous(request: Request):
    try:
        # First try authenticated user
        user = await get_current_user(request)
        logging.debug(f"Authenticated user: {user['sub']}")
        return user
    except HTTPException as auth_error:
        logging.debug(f"Auth failed: {auth_error.detail}")
        # Fall back to anonymous token check
        if request.url.path.startswith("/chat"):
            token = request.headers.get("X-Anonymous-Token")
            logging.debug(f"Checking anonymous token: {token}")
            if token:
                async with redis.Redis.from_url(os.getenv("REDIS_URL")) as redis_client:
                    quota = await redis_client.hget(f"anonymous:{token}", "quota_remaining")
                    logging.debug(f"Token quota: {quota}")
                    if quota and int(quota) > 0:
                        logging.debug(f"Anonymous access granted for token: {token}")
                        return {"sub": f"anonymous:{token}", "tier": "anonymous"}
        raise HTTPException(status_code=401, detail="Not authenticated")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Models
class UserTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    CUSTOM = "custom"

class UserCreate(BaseModel):
    username: str
    password: str
    email: str = None
    tier: UserTier = UserTier.FREE

class UserInDB(UserCreate):
    hashed_password: str
    daily_token_limit: int = 10000  # Default for free tier
    monthly_token_limit: int = 0    # 0 means unlimited for paid tiers
    tokens_used_today: int = 0
    tokens_used_month: int = 0
    last_reset_date: datetime = None

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float

class UserUsage(BaseModel):
    daily_limit: int
    monthly_limit: int
    daily_used: int
    monthly_used: int
    remaining_daily: int
    remaining_monthly: int

class ChatRequest(BaseModel):
    prompt: str
    tone: Optional[str] = "friendly"
    language: Optional[str] = "en"
    tokens_needed: int

class ChatResponse(BaseModel):
    response: str
    tokens_used: int

class BudgetRequest(BaseModel):
    amount: float

# Helper function for DeepSeek API
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from cost_tracking import cost_tracker

# Initialize OpenAI client with DeepSeek endpoint
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

async def call_deepseek_api(prompt: str) -> dict:
    """Call DeepSeek API using OpenAI SDK"""
    try:
        # Prepare messages with tone and language context
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": prompt}
        ]
        
        # Make the API call
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
            stream=False
        )
        
        # Convert to our expected format
        return {
            "choices": [{
                "message": {
                    "content": response.choices[0].message.content
                }
            }],
            "usage": {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
        }
    except Exception as e:
        logging.error(f"DeepSeek API error: {str(e)}", exc_info=True)
        error_msg = str(e)
        
        # Handle specific error types
        if "Invalid API key" in error_msg:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        elif "Insufficient Balance" in error_msg:
            raise HTTPException(
                status_code=402,
                detail="Insufficient balance",
                headers={"Retry-After": "86400"}  # 24 hours
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"DeepSeek API error: {error_msg}"
            )

# Initialize tiktoken encoder
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")  # Using GPT-3.5 as a compatible fallback

class TokenTracker:
    def __init__(self):
        self.usage_db = {}
        self.tier_limits = {
            UserTier.FREE: 10000,  # Daily limit for free tier
            UserTier.PRO: 1000000,  # Monthly limit for pro tier
            UserTier.CUSTOM: 5000000,  # Monthly limit for custom tier
        }
        self.token_cost = 0.002  # Cost per 1K tokens

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken encoder"""
        return len(encoding.encode(text))

    async def calculate_token_usage(self, response: dict) -> TokenUsage:
        """Calculate token usage from API response"""
        # Get input tokens from the prompt
        input_tokens = self.count_tokens(response.get("messages", [{}])[-1].get("content", ""))
        
        # Get output tokens from the response
        output_tokens = self.count_tokens(response.get("choices", [{}])[0].get("message", {}).get("content", ""))
        
        total_tokens = input_tokens + output_tokens
        cost = (total_tokens / 1000) * self.token_cost
        
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost
        )

    async def update_usage(self, username: str, tokens_used: int, tier: UserTier):
        """Update user's token usage and handle limits"""
        current_date = datetime.now()
        
        if username not in self.usage_db:
            self.usage_db[username] = {
                "daily_used": 0,
                "monthly_used": 0,
                "last_reset_date": current_date.date()
            }
        
        # Reset daily usage if new day
        if self.usage_db[username]["last_reset_date"] != current_date.date():
            self.usage_db[username]["daily_used"] = 0
            self.usage_db[username]["last_reset_date"] = current_date.date()
            
        # Update usage
        self.usage_db[username]["daily_used"] += tokens_used
        self.usage_db[username]["monthly_used"] += tokens_used
        
        # Check limits
        daily_limit = self.tier_limits[UserTier.FREE] if tier == UserTier.FREE else None
        monthly_limit = self.tier_limits[tier] if tier != UserTier.FREE else None
        
        # Calculate remaining tokens
        daily_remaining = daily_limit - self.usage_db[username]["daily_used"] if daily_limit else None
        monthly_remaining = monthly_limit - self.usage_db[username]["monthly_used"] if monthly_limit else None
        
        # Check if we need to suggest an upgrade
        upgrade_suggested = False
        if tier == UserTier.FREE:
            if daily_remaining and daily_remaining <= 1000:  # Low daily tokens remaining
                upgrade_suggested = True
            elif daily_remaining and daily_remaining <= 2000 and random.random() < 0.3:  # Random chance for more tokens remaining
                upgrade_suggested = True
        
        # If we're suggesting an upgrade, modify the response
        if upgrade_suggested:
            return {
                "message": "You're running low on tokens! Consider upgrading to Pro for unlimited daily usage.",
                "upgrade_suggested": True,
                "current_tier": tier,
                "remaining_tokens": daily_remaining
            }
            
        # If we exceed limits, raise appropriate error
        if daily_limit and self.usage_db[username]["daily_used"] > daily_limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "Daily token limit exceeded. Please upgrade your plan.",
                    "current_tier": tier,
                    "daily_limit": daily_limit,
                    "monthly_limit": monthly_limit
                }
            )
            
        if monthly_limit and self.usage_db[username]["monthly_used"] > monthly_limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "Monthly token limit exceeded. Please upgrade your plan.",
                    "current_tier": tier,
                    "monthly_limit": monthly_limit
                }
            )

    async def get_usage(self, username: str, tier: UserTier) -> UserUsage:
        """Get user's current token usage"""
        usage = self.usage_db.get(username, {
            "daily_used": 0,
            "monthly_used": 0,
            "last_reset_date": datetime.now().date()
        })
        
        daily_limit = self.tier_limits[UserTier.FREE] if tier == UserTier.FREE else None
        monthly_limit = self.tier_limits[tier] if tier != UserTier.FREE else None
        
        return UserUsage(
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
            daily_used=usage["daily_used"],
            monthly_used=usage["monthly_used"],
            remaining_daily=(daily_limit - usage["daily_used"]) if daily_limit else None,
            remaining_monthly=(monthly_limit - usage["monthly_used"]) if monthly_limit else None
        )

# Initialize token tracker
token_tracker = TokenTracker()

# Mock database (replace with real DB in production)
users_db = {}

def get_user_tier(username: str) -> UserTier:
    user = users_db.get(username)
    if not user:
        return UserTier.FREE
    return user.tier

def update_token_usage(username: str, tokens_used: int):
    user = users_db[username]
    current_date = datetime.now()
    
    # Reset daily usage if new day
    if user.last_reset_date and user.last_reset_date.date() != current_date.date():
        user.tokens_used_today = 0
        user.last_reset_date = current_date
    
    # Update usage
    user.tokens_used_today += tokens_used
    user.tokens_used_month += tokens_used
    users_db[username] = user

def check_token_limits(username: str, tokens_needed: int) -> UserUsage:
    user = users_db.get(username)
    if not user:
        return UserUsage(
            daily_limit=10000,
            monthly_limit=0,
            daily_used=0,
            monthly_used=0,
            remaining_daily=10000,
            remaining_monthly=0
        )
    
    daily_remaining = user.daily_token_limit - user.tokens_used_today
    monthly_remaining = user.monthly_token_limit - user.tokens_used_month
    
    return UserUsage(
        daily_limit=user.daily_token_limit,
        monthly_limit=user.monthly_token_limit,
        daily_used=user.tokens_used_today,
        monthly_used=user.tokens_used_month,
        remaining_daily=daily_remaining,
        remaining_monthly=monthly_remaining
    )

def get_user(username: str):
    if username in users_db:
        user_dict = users_db[username]
        return UserInDB(**user_dict)
    return None

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

# Token endpoint
@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        user = authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(data={"sub": user.username})
        await redis_conn.setex(
            f"token:{user.username}",
            int(timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES).total_seconds()),
            access_token
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logging.error(f"Token generation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

@app.post("/register")
async def register_user(user: UserCreate):
    try:
        if user.username in users_db:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
        
        hashed_password = pwd_context.hash(user.password)
        users_db[user.username] = {
            "username": user.username,
            "hashed_password": hashed_password,
            "email": user.email,
            "tier": user.tier,
            "daily_token_limit": 10000,
            "monthly_token_limit": 0,
            "tokens_used_today": 0,
            "tokens_used_month": 0,
            "last_reset_date": None
        }
        return {"message": "User registered successfully"}
    except Exception as e:
        logging.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# Protected route for testing
@app.get("/protected")
async def protected_route(user: dict = Depends(get_current_user)):
    return {"message": "You are authenticated"}

# Updated chat endpoint
@app.post("/chat", dependencies=[Depends(RateLimiter(times=10, minutes=1))])
async def chat(
    chat_request: ChatRequest,
    user: dict = Depends(get_user_or_anonymous)
):
    try:
        # Handle anonymous users
        if user["sub"].startswith("anonymous:"):
            # Skip tier checks for anonymous users
            token = user["sub"].replace("anonymous:", "")
            
            # Make API call
            response = await call_deepseek_api(chat_request.prompt)
            
            # Calculate token usage (no tracking for anonymous users)
            token_usage = await token_tracker.calculate_token_usage(response)
            
            return response
            
        # Original logic for authenticated users
        user_tier = get_user_tier(user["sub"])
        
        # Check freemium quota
        user = users_db.get(user["sub"])
        if user and user.tier == UserTier.FREE:
            daily_remaining = user.daily_token_limit - user.tokens_used_today
            if daily_remaining <= 0:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Daily token limit exceeded. Please upgrade your plan."
                )
        
        # Make API call
        response = await call_deepseek_api(chat_request.prompt)
        
        # Calculate and update token usage
        token_usage = await token_tracker.calculate_token_usage(response)
        usage_result = await token_tracker.update_usage(user["sub"], token_usage.total_tokens, user_tier)
        
        # If an upgrade was suggested, modify the response
        if isinstance(usage_result, dict) and usage_result.get("upgrade_suggested"):
            return {
                "response": usage_result["message"],
                "suggested_upgrade": True,
                "current_tier": usage_result["current_tier"],
                "remaining_tokens": usage_result["remaining_tokens"]
            }
        
        return response
    except HTTPException as e:
        if e.status_code == status.HTTP_402_PAYMENT_REQUIRED:
            return {
                "error": "upgrade_required",
                "message": e.detail,
                "current_tier": user_tier,
                "daily_limit": 10000,
                "monthly_limit": 0
            }
        raise

# Add endpoint to get user's token usage
@app.get("/token-usage")
async def get_token_usage(user: dict = Depends(get_current_user)):
    try:
        user_tier = get_user_tier(user["sub"])
        usage = await token_tracker.get_usage(user["sub"], user_tier)
        return usage
    except Exception as e:
        logging.error(f"Token usage error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# Initialize cost tracking
from datetime import datetime
from typing import Dict, List

class CostTracker:
    def __init__(self):
        self.current_budget = 0.0
        self.total_cost = 0.0
        self.budget_history: List[Dict] = []
        self.alerts: List[Dict] = []
        self.budget_updated_at = datetime.utcnow()

    def set_budget(self, amount: float) -> None:
        self.current_budget = amount
        self.budget_updated_at = datetime.utcnow()
        self.budget_history.append({
            'timestamp': self.budget_updated_at.isoformat(),
            'amount': amount,
            'total_cost': self.total_cost
        })

    def get_budget_status(self) -> Dict:
        return {
            'current_budget': self.current_budget,
            'budget_remaining': self.current_budget - self.total_cost,
            'total_cost': self.total_cost,
            'last_updated': self.budget_updated_at.isoformat()
        }

    def get_budget_history(self) -> List[Dict]:
        return self.budget_history[-10:]  # Return last 10 entries

    def get_budget_alerts(self) -> List[Dict]:
        return self.alerts

    def add_cost(self, cost: float) -> None:
        self.total_cost += cost
        remaining_budget = self.current_budget - self.total_cost
        
        # Add alert if budget is running low
        if remaining_budget <= 0:
            self.alerts.append({
                'timestamp': datetime.utcnow().isoformat(),
                'type': 'critical',
                'message': 'Budget exceeded!'
            })
        elif remaining_budget <= self.current_budget * 0.1:  # 10% remaining
            self.alerts.append({
                'timestamp': datetime.utcnow().isoformat(),
                'type': 'warning',
                'message': 'Budget running low! Only 10% remaining.'
            })

cost_tracker = CostTracker()

# Budget management endpoints
@app.post("/budget")
async def set_budget(request: BudgetRequest):
    try:
        cost_tracker.set_budget(request.amount)
        return {"new_budget": request.amount}
    except Exception as e:
        logging.error(f"Budget set error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting budget: {str(e)}"
        )

@app.get("/budget")
async def get_budget():
    try:
        status = cost_tracker.get_budget_status()
        return {
            "current_budget": status["current_budget"],
            "budget_remaining": status["budget_remaining"],
            "total_cost": status["total_cost"],
            "last_updated": status["last_updated"]
        }
    except Exception as e:
        logging.error(f"Budget get error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting budget: {str(e)}"
        )

@app.get("/budget/history")
async def get_budget_history():
    try:
        history = cost_tracker.get_budget_history()
        return {"history": history}
    except Exception as e:
        logging.error(f"Budget history error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting budget history: {str(e)}"
        )

@app.get("/budget/alerts")
async def get_budget_alerts():
    try:
        alerts = cost_tracker.get_budget_alerts()
        return {"alerts": alerts}
    except Exception as e:
        logging.error(f"Budget alerts error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting budget alerts: {str(e)}"
        )

@app.get("/usage")
async def get_usage():
    try:
        usage = cost_tracker.get_usage()
        return {
            "total_cost": usage["total_cost"],
            "total_tokens": usage["total_tokens"],
            "requests_count": usage["requests_count"]
        }
    except Exception as e:
        logging.error(f"Usage error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting usage: {str(e)}"
        )

@app.get("/usage/projection")
async def get_usage_projection():
    try:
        projection = cost_tracker.get_usage_projection()
        return {
            "avg_cost_per_request": projection["avg_cost_per_request"],
            "estimated_remaining_requests": projection["estimated_remaining_requests"],
            "projected_total_cost": projection["projected_total_cost"]
        }
    except Exception as e:
        logging.error(f"Usage projection error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting usage projection: {str(e)}"
        )

@app.post("/reset")
async def reset_usage():
    try:
        cost_tracker.reset()
        return {"message": "Usage statistics reset successfully"}
    except Exception as e:
        logging.error(f"Reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resetting usage: {str(e)}"
        )

# Health check endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Test endpoints
@app.get("/test/user/{username}")
async def test_user(username: str):
    return {"username": username}

@app.get("/test/token")
async def verify_token(user: dict = Depends(get_current_user)):
    return {"username": user["sub"]}

@app.get("/test/deepseek")
async def test_deepseek_api():
    try:
        # Test API call
        response = await call_deepseek_api("Hello, how are you?")
        return {
            "status": "success",
            "response": response["choices"][0]["message"]["content"],
            "tokens_used": response["usage"]["total_tokens"]
        }
    except Exception as e:
        logging.error(f"DeepSeek test error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DeepSeek API test failed: {str(e)}"
        )

@app.get("/test/redis")
async def test_redis():
    try:
        async with redis.Redis.from_url(os.getenv("REDIS_URL")) as redis_client:
            await redis_client.ping()
            return {"status": "success", "message": "Redis connection working"}
    except Exception as e:
        logging.error(f"Redis connection failed: {e}")
        raise HTTPException(status_code=500, detail="Redis connection failed")

# Upgrade endpoint
@app.post("/upgrade")
async def upgrade_user(user_id: str = Body(...)):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    users_db[user_id]['tier'] = UserTier.PRO
    users_db[user_id]['monthly_token_limit'] = 1000000
    return {"status": "success", "message": "Upgraded to Pro plan"}

# OAuth endpoints
@app.post('/auth/google')
async def auth_google(token: str = Body(...)):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        
        # Create or get user
        user_id = f"google_{idinfo['sub']}"
        if user_id not in users_db:
            users_db[user_id] = {
                'name': idinfo.get('name'),
                'email': idinfo.get('email'),
                'tier': UserTier.FREE,
                'daily_token_limit': 10000,
                'monthly_token_limit': 0,
                'tokens_used_today': 0,
                'tokens_used_month': 0,
                'last_reset_date': None
            }
        
        return {"user_id": user_id, "name": users_db[user_id]['name']}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")

@app.post('/auth/apple')
async def auth_apple(token: str = Body(...)):
    # In production, implement proper Apple ID token verification
    # This is a simplified version for development
    user_id = f"apple_{token[-10:]}"  # Mock user ID
    if user_id not in users_db:
        users_db[user_id] = {
            'name': "Apple User",
            'email': f"{user_id}@example.com",
            'tier': UserTier.FREE,
            'daily_token_limit': 10000,
            'monthly_token_limit': 0,
            'tokens_used_today': 0,
            'tokens_used_month': 0,
            'last_reset_date': None
        }
    return {"user_id": user_id, "name": users_db[user_id]['name']}

# Shutdown handler
@app.on_event("shutdown")
async def shutdown_event():
    await redis_conn.close()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    response = await call_next(request)
    duration = datetime.now() - start_time
    logging.info(
        f"{request.method} {request.url.path} {response.status_code} - {duration.total_seconds():.2f}s"
    )
    return response

import redis
from datetime import datetime

# Redis setup
r = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True
)

DAILY_LIMIT = 1000  # Tokens per day for anonymous users

# Token counting function (placeholder)
async def count_tokens(text: str) -> int:
    """Approximate token count - replace with actual DeepSeek tokenizer"""
    return len(text.split())  # Simple approximation

@app.post("/anonymous-chat")
async def anonymous_chat(chat_request: ChatRequest, request: Request):
    try:
        client_ip = request.client.host
        today = datetime.utcnow().strftime("%Y-%m-%d")
        redis_key = f"anon_usage:{today}:{client_ip}"
        
        # Get current usage
        current_usage = int(r.get(redis_key) or 0)
        
        if current_usage >= DAILY_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Daily limit reached ({DAILY_LIMIT} tokens). Sign in for more access."
            )
        
        # Process request
        response = await call_deepseek_api(chat_request.prompt)
        token_count = await count_tokens(chat_request.prompt + response)
        
        # Update usage with pipeline for atomic operation
        with r.pipeline() as pipe:
            pipe.incrby(redis_key, token_count)
            pipe.expire(redis_key, 86400)  # 24 hours
            pipe.execute()
        
        return {
            "response": response,
            "usage": current_usage + token_count,
            "remaining": max(0, DAILY_LIMIT - (current_usage + token_count))
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Add usage tracking endpoints
@app.post("/track")
async def track_usage(request: Request):
    # Get or create anonymous user ID
    anon_id = request.cookies.get('anon_id') or str(uuid.uuid4())
    
    # Track in Redis with timestamp
    timestamp = datetime.now().isoformat()
    data = await request.json()
    r.hset(f"user:{anon_id}", mapping={
        "last_active": timestamp,
        data['action']: timestamp
    })
    
    # Set cookie for 1 year
    response = JSONResponse({'status': 'tracked'})
    response.set_cookie('anon_id', anon_id, max_age=365*24*60*60)
    return response

def track_action(user_id, action, metadata):
    # Store in database or analytics service
    print(f"Tracked: {user_id} - {action} - {metadata}")

# File tracking endpoint
@app.post("/track")
async def track_event(
    event: dict = Body(...),
    user: dict = Depends(get_current_user)
):
    try:
        # Validate required fields
        if not event.get('event') or not event.get('timestamp'):
            raise HTTPException(status_code=400, detail="Missing required fields")
            
        # Add default values for missing fields
        event.setdefault('metadata', {})
        
        # Log the tracking event
        logging.info(f"Tracking event: {event}")
        
        # Store in database (in production use a proper database)
        if event.get("event") == "file_operation":
            file_path = event.get("filePath")
            operation = event.get("operation")
            
            # Add your file tracking logic here
            # Example: update file metadata in database
            
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Tracking error: {e}")
        raise HTTPException(status_code=500, detail="Tracking failed")

# Anonymous User Models
class AnonymousUser(BaseModel):
    token: str
    created_at: datetime = datetime.utcnow()
    quota_remaining: int = 1000  # Default daily quota
    quota_reset_at: datetime = datetime.utcnow() + timedelta(days=1)

# Anonymous endpoints
@app.post("/api/anonymous/token")
async def generate_anonymous_token():
    """Generate a new anonymous session token with daily quota"""
    token = str(uuid.uuid4())
    async with redis.Redis.from_url(os.getenv("REDIS_URL")) as redis_client:
        await redis_client.hset(
            f"anonymous:{token}",
            mapping={
                "quota_remaining": 1000,
                "quota_reset_at": (datetime.utcnow() + timedelta(days=1)).isoformat()
            }
        )
        await redis_client.expire(f"anonymous:{token}", 86400)  # 24h TTL
    return {"token": token, "quota_remaining": 1000}

# Middleware for anonymous quota checks
@app.middleware("http")
async def check_anonymous_quota(request: Request, call_next):
    if request.url.path.startswith("/api/anonymous/") and request.url.path != "/api/anonymous/token":
        token = request.headers.get("X-Anonymous-Token")
        if not token:
            raise HTTPException(status_code=401, detail="Anonymous token required")
            
        async with redis.Redis.from_url(os.getenv("REDIS_URL")) as redis_client:
            quota = await redis_client.hget(f"anonymous:{token}", "quota_remaining")
            if not quota or int(quota) <= 0:
                raise HTTPException(status_code=429, detail="Daily quota exceeded")
            
            # Decrement quota for each request
            await redis_client.hincrby(f"anonymous:{token}", "quota_remaining", -1)
    
    response = await call_next(request)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
