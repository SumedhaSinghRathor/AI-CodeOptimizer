import os
import requests
import json
import base64
import re
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_core.prompts import ChatPromptTemplate
from schemas import RepoRequest, AnalysisResponse, OptimizationSuggestion
from urllib.parse import urlparse
from pydantic import HttpUrl

# from langchain_community.document_loaders import GitLoader
# import tempfile

load_dotenv()

llm = ChatOpenRouter(
    model="deepseek/deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0.1
)

def parse_github_url(repo_url: HttpUrl):
    parsed = urlparse(str(repo_url))
    path_parts = parsed.path.strip("/").split("/")
    return path_parts[0], path_parts[1]

def fetch_repo_files(owner, repo, branch="main"):
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("GitHub API error: ", response.text)
        return []
    
    data = response.json()
    
    return [
        file["path"]
        for file in data.get("tree", [])
        if file["path"].endswith((".py", ".js", ".cpp", ".java", ".c"))
    ]
    
def fetch_file_content(owner, repo, file_path):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    
    if "content" not in data:
        return None
    
    try:
        content = base64.b64decode(data["content"]).decode("utf-8")
    except Exception:
        return None
    
    if len(content) > 8000:
        return None

    return content

def clean_llm_json(text: str):
    text = text.strip()
    
    if text.startswith("```"):
        text = re.sub(r"^```json", "", text)
        text = re.sub(r"^```", "", text)
        text = re.sub(r"```$", "", text)
        
    return text.strip()

def analyze_codebase(request: RepoRequest) -> AnalysisResponse:
    owner, repo = parse_github_url(request.repo_url)
    branch = request.branch or "main"

    file_paths = fetch_repo_files(owner, repo, branch)
    print("Total files fetched: ", len(file_paths))

    documents = []

    for path in file_paths[:10]:
        content = fetch_file_content(owner, repo, path)
        if content:
            documents.append({
                "file_path": path,
                "content": content
            })
    
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
    
    chain = prompt | llm.with_structured_output(OptimizationSuggestion)
    
    for doc in documents[:5]:
        response = chain.invoke({
            "file_path": doc["file_path"],
            "code_content": doc["content"]
        })
        
        try:
            cleaned = clean_llm_json(response.content)
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            print("Invalid JSON from LLM: ", response.content)
            continue
        
        required_keys = ["original_complexity", "optimized_complexity", "explanation", "refactored_code"]
        if not all(key in parsed for key in required_keys):
            print("Missing keys:", parsed)
            continue
            
        suggestions.append(OptimizationSuggestion(
            file_path=doc["file_path"],
            original_complexity=parsed["original_complexity"],
            optimized_complexity=parsed["optimized_complexity"],
            explanation=parsed["explanation"],
            refactored_code=parsed["refactored_code"]
        ))
        
        print("Processing:", doc["file_path"])
        print("LLM RAW:", response.content[:200])
        
    print("Owner:", owner, "Repo:", repo)
    print("File paths:", file_paths[:5])
    print("Documents count:", len(documents))
        
    return AnalysisResponse(repo_name=f"{owner}/{repo}", suggestions=suggestions)