import uvicorn
from fastapi import FastAPI, HTTPException
from schemas import RepoRequest, AnalysisResponse
from engine import analyze_codebase
from dotenv import load_dotenv
from fastapi.concurrency import run_in_threadpool
import traceback

load_dotenv()
app = FastAPI(title="AI Code Complexity Optimizer")

@app.get("/analyze")
def home():
    return "Backend Running"

@app.post("/analyze", response_model=AnalysisResponse)
async def start_analysis(request: RepoRequest):
    try:
        result = await run_in_threadpool(analyze_codebase, request)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, port=8000)