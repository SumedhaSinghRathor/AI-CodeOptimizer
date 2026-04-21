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
from concurrent.futures import ThreadPoolExecutor, as_completed

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

    def fetch_single_file(path):
        content = fetch_file_content(owner, repo, path)
        if content:
            return {"file_path": path, "content": content}
        return None

    documents = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_single_file, path) for path in file_paths[:10]]
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                documents.append(result)

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

    def process_doc(doc):
        try:
            response = chain.invoke({
                "file_path": doc["file_path"],
                "code_content": doc["content"]
            })

            cleaned = clean_llm_json(response.content)
            parsed = json.loads(cleaned)

            required_keys = ["original_complexity", "optimized_complexity", "explanation", "refactored_code"]
            if not all(key in parsed for key in required_keys):
                return None

            return OptimizationSuggestion(
                file_path=doc["file_path"],
                original_complexity=parsed["original_complexity"],
                optimized_complexity=parsed["optimized_complexity"],
                explanation=parsed["explanation"],
                refactored_code=parsed["refactored_code"]
            )

        except Exception as e:
            print("Error processing:", doc["file_path"], e)
            return None

    suggestions = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_doc, doc) for doc in documents[:5]]

        for future in as_completed(futures):
            result = future.result()
            if result:
                suggestions.append(result)

    return AnalysisResponse(
        repo_name=f"{owner}/{repo}",
        suggestions=suggestions
    )