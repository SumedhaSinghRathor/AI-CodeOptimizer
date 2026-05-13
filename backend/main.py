import os
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from schemas import RepoRequest, AnalysisResponse
from engine import analyze_codebase
from dotenv import load_dotenv
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from auth import create_access_token
import traceback

load_dotenv()
app = FastAPI(title="AI Code Complexity Optimizer")

@app.get("/analyze")
def home():
    return "Backend Running"

@app.get("/auth/github/login")
async def github_login():
    github_auth_url = (f"https://github.com/login/oauth/authorize?client_id={os.getenv('GITHUB_CLIENT_ID')}&scope=repo user")

    return RedirectResponse(github_auth_url)

@app.get("/auth/github/callback")
async def github_callback(code: str):

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={
                "Accept": "application/json"
            },
            data={
                "client_id": os.getenv("GITHUB_CLIENT_ID"),
                "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
                "code": code,
            },
        )

        token_json = token_response.json()

        access_token = token_json.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub OAuth failed"
            )

        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}"
            }
        )

        github_user = user_response.json()

    jwt_token = create_access_token({
        "sub": github_user["login"]
    })

    username = github_user["login"]

    return RedirectResponse(url=f"http://localhost:8501/?token={jwt_token}&username={username}&github_token={access_token}")

security = HTTPBearer()
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/analyze", response_model=AnalysisResponse)
async def start_analysis(request: RepoRequest, user=Depends(verify_token)):
    try:
        result = await run_in_threadpool(analyze_codebase, request)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, port=8000)