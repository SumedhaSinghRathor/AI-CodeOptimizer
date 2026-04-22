from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class RepoRequest(BaseModel):
    repo_url: HttpUrl
    branch: Optional[str] = "main"
    
class OptimizationSuggestion(BaseModel):
    file_path: str
    original_complexity: str
    optimized_complexity: str
    explanation: str
    original_code: str
    refactored_code: str
    
class AnalysisResponse(BaseModel):
    repo_name: str
    suggestions: List[OptimizationSuggestion]
    status: str = "completed"