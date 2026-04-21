import os
from langchain_community.document_loaders import GitLoader
from langchain_openrouter import ChatOpenRouter
from langchain_core.prompts import ChatPromptTemplate
from schemas import RepoRequest, AnalysisResponse, OptimizationSuggestion
from dotenv import load_dotenv
import json
import tempfile

load_dotenv()

llm = ChatOpenRouter(
    model="deepseek/deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0.1
)

def analyze_codebase(request: RepoRequest) -> AnalysisResponse:
    with tempfile.TemporaryDirectory() as repo_path:
        loader = GitLoader(
            clone_url=str(request.repo_url),
            repo_path=repo_path,
            branch=request.branch,
            file_filter=lambda file_path: file_path.endswith((".py", ".cpp", ".java", ".js", ".c", ".jsx"))
        )
    
    documents = loader.load()
    
    suggestions = []
    
    prompt = ChatPromptTemplate.from_template("""
    Analyze the following code from file: {file_path}
    Focus ONLY on improving Time and Space Complexity.
    
    Code:
    {code_content}
    
    IMPORTANT:
    - Return ONLY valid JSON
    - Do NOT include explanations outside JSON
    - Do NOT use markdown
    - Do NOT wrap in ```json
    
    Output format:
    {{
        "original_complexity": "...",
        "optimized_complexity": "...",
        "explanation": "...",
        "refactored_code": "..."
    }}
    """)
    
    for doc in documents[:5]:
        chain = prompt | llm
        response = chain.invoke({
            "file_path": doc.metadata["file_path"],
            "code_content": doc.page_content
        })
        
        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError:
            print("Invalid JSON from LLM: ", response.content)
        
        suggestions.append(OptimizationSuggestion(
            file_path=doc.metadata["file_path"],
            original_complexity=parsed["original_complexity"],
            optimized_complexity=parsed["optimized_complexity"],
            explanation=parsed["explanation"],
            refactored_code=parsed["refactored_code"]
        ))
        
    return AnalysisResponse(repo_name=str(request.repo_url), suggestions=suggestions)