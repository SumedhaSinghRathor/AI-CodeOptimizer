import uvicorn
from fastapi import FastAPI, HTTPException
from schemas import RepoRequest, AnalysisResponse
from engine import analyze_codebase
from dotenv import load_dotenv
from fastapi.concurrency import run_in_threadpool

load_dotenv()
app = FastAPI(title="AI Code Complexity Optimizer")

@app.post("/analyze", response_model=AnalysisResponse)
async def start_analysis(request: RepoRequest):
    try:
        result = await run_in_threadpool(analyze_codebase, request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)