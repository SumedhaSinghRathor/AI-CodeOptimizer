import os
import json
import requests
import base64
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
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

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

FAISS_DIR = "faiss_indexes"
os.makedirs(FAISS_DIR, exist_ok=True)

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

def build_vector_store(documents, index_path):
    texts = []
    metadatas = []

    for doc in documents:
        texts.append(doc["content"])
        metadatas.append({"file_path": doc["file_path"]})

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=100
    )

    split_docs = splitter.create_documents(texts, metadatas)

    vectorstore = FAISS.from_documents(split_docs, embeddings)
    vectorstore.save_local(index_path)

    return vectorstore

def load_or_create_vectorstore(documents, owner, repo, branch, commit_sha):
    index_path = os.path.join(FAISS_DIR, f"{owner}_{repo}_{branch}_{commit_sha}")

    if os.path.exists(index_path):
        try:
            return FAISS.load_local(index_path, embeddings)
        except Exception:
            print("Failed to load FAISS index, rebuilding...")

    return build_vector_store(documents, index_path)

def retrieve_context(vectorstore, query, k=3):
    docs = vectorstore.similarity_search(query, k=k)
    MAX_CONTEXT_CHARS = 2000

    context = "\n\n".join([
        f"File: {d.metadata.get('file_path')}\n{d.page_content}"
        for d in docs
    ])

    return context[:MAX_CONTEXT_CHARS]

def get_latest_commit_sha(owner, repo, branch):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("Error fetching commit SHA:", response.text)
        return None
    
    data = response.json()
    return data.get("sha")

CACHE_DIR = "cache"

def get_cache_path(owner, repo, branch, commit_sha):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return f"{CACHE_DIR}/{owner}_{repo}_{branch}_{commit_sha}.json"

def analyze_codebase(request: RepoRequest) -> AnalysisResponse:
    owner, repo = parse_github_url(request.repo_url)
    branch = request.branch or "main"
    
    commit_sha = get_latest_commit_sha(owner, repo, branch)
    
    if not commit_sha:
        raise Exception("Could not fetch commit SHA")
    
    cache_path = get_cache_path(owner, repo, branch, commit_sha)
    
    if os.path.exists(cache_path):
        print("Using cached result...")
        with open(cache_path, "r") as f:
            cached_data = json.load(f)
            return AnalysisResponse(**cached_data)
        
    print("New commit detected. Running optimizer...")

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

    if not documents:
        return AnalysisResponse(
            repo_name=f"{owner}/{repo}",
            suggestions=[]
        )

    vectorstore = load_or_create_vectorstore(documents, owner, repo, branch, commit_sha)

    prompt = ChatPromptTemplate.from_template("""
    Analyze the following code from file: {file_path}
                                              
    You are also given additional relevant code context from the repository.

    Context:
    {retrieved_context}
                                              
    Focus ONLY on improving Time and Space Complexity.
                                              
    STRICT RULES:
    - You MUST return ALL fields: original_complexity, optimized_complexity, explanation, original_code, refactored_code
    - original_code must be the exact snippet from input
    - refactored_code must be the improved version
    - DO NOT omit any field
    - DO NOT return the full file
    - Limit snippets to 5–30 lines
    
    Code:
    {code_content}
    """)

    chain = prompt | llm.with_structured_output(OptimizationSuggestion)
    
    def process_doc(doc):
        try:
            query = f"Optimize time and space complexity in {doc['file_path']}"

            retrieved_context = retrieve_context(
                vectorstore,
                query=query
            )

            response = chain.invoke({
                "file_path": doc["file_path"],
                "code_content": doc["content"],
                "retrieved_context": retrieved_context,
            })

            print("LLM Response: ", response)

            response.file_path = doc["file_path"]
            return response
        
        except Exception:
            return None

    suggestions = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_doc, doc) for doc in documents[:5]]

        for future in as_completed(futures):
            result = future.result()
            if result:
                suggestions.append(result)
                
    final_result = AnalysisResponse(repo_name=f"{owner}/{repo}", suggestions=suggestions)
                
    with open(cache_path, "w") as f:
        json.dump(final_result.model_dump(), f)

    return final_result