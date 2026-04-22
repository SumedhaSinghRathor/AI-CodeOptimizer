import os
import time
import requests
import base64
import re
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

def load_or_create_vectorstore(documents, owner, repo, branch):
    index_path = os.path.join(FAISS_DIR, f"{owner}_{repo}_{branch}")

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

    if not documents:
        return AnalysisResponse(
            repo_name=f"{owner}/{repo}",
            suggestions=[]
        )

    vectorstore = load_or_create_vectorstore(documents, owner, repo, branch)

    prompt = ChatPromptTemplate.from_template("""
    Analyze the following code from file: {file_path}
                                              
    You are also given additional relevant code context from the repository.

    Context:
    {retrieved_context}
                                              
    Focus ONLY on improving Time and Space Complexity.
    
    Code:
    {code_content}
    """)

    #     IMPORTANT:
    # - Do NOT use markdown
    
    # Output format:
    # {{
    #     "original_complexity": "...",
    #     "optimized_complexity": "...",
    #     "explanation": "...",
    #     "refactored_code": "..."
    # }}

    chain = prompt | llm.with_structured_output(OptimizationSuggestion)
    
    def process_doc(doc, retries=2):
        for attempt in range(retries):
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

                response.file_path = doc["file_path"]
                return response
        
            except Exception as e:
                print(f"Retry {attempt+1} failed for {doc['file_path']}: {e}")
                time.sleep(1)
        
        return None

    suggestions = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_doc, doc) for doc in documents[:5]]

        for future in as_completed(futures):
            result = future.result()
            if result:
                suggestions.append(result)

    return AnalysisResponse(repo_name = f"{owner}/{repo}", suggestions=suggestions)