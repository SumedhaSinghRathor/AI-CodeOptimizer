import os
import json
import time
import requests
import base64
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from tree_sitter_languages import get_parser
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from schemas import RepoRequest, AnalysisResponse, OptimizationSuggestion
from urllib.parse import urlparse
from pydantic import HttpUrl
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

llm = ChatOpenRouter(
    model="deepseek/deepseek-chat",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0,
    max_completion_tokens=600
)

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5"
)

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c"
}

FUNCTION_NODE_TYPES = {
    "python": ["function_definition", "class_definition"],
    "javascript": [
        "function_declaration",
        "method_definition",
        "class_declaration"
    ],
    "java": [
        "method_declaration",
        "class_declaration"
    ],
    "cpp": [
        "function_definition",
        "class_specifier"
    ],
    "c": [
        "function_definition"
    ]
}

COMPLEXITY_ORDER = {
    "O(1)": 1,
    "O(log n)": 2,
    "O(n)": 3,
    "O(n + m)": 4,
    "O(n log n)": 5,
    "O(n^2)": 6,
    "O(n^3)": 7,
    "O(2^n)": 8
}

def is_complexity_improved(original, optimized):
    original = original.strip()
    optimized = optimized.strip()

    if original == optimized:
        return False

    original_rank = COMPLEXITY_ORDER.get(original)
    optimized_rank = COMPLEXITY_ORDER.get(optimized)

    if original_rank and optimized_rank:
        return optimized_rank < original_rank

    return True

def is_meaningful_refactor(original_code, refactored_code):

    original = original_code.strip()
    refactored = refactored_code.strip()

    if original == refactored:
        return False

    similarity = len(
        set(original.split()) &
        set(refactored.split())
    ) / max(len(set(original.split())), 1)

    return similarity < 0.95

def get_language(file_path):
    for ext, lang in LANGUAGE_MAP.items():
        if file_path.endswith(ext):
            return lang
    return None

def extract_ast_chunks(code: str, file_path: str):
    language = get_language(file_path)

    if not language:
        return []

    try:
        parser = get_parser(language)
        source_bytes = code.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node
        chunks = []

        target_nodes = FUNCTION_NODE_TYPES.get(language, [])

        def traverse(node):
            if node.type in target_nodes:

                start = node.start_byte
                end = node.end_byte

                chunk_code = source_bytes[start:end].decode(
                    "utf-8",
                    errors="ignore"
                )

                if len(chunk_code.strip()) > 50:

                    chunks.append({
                        "content": chunk_code,
                        "file_path": file_path,
                        "chunk_type": node.type,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1
                    })

            for child in node.children:
                traverse(child)

        traverse(root)

        if not chunks:

            chunks.append({
                "content": code[:3000],
                "file_path": file_path,
                "chunk_type": "full_file",
                "start_line": 1,
                "end_line": len(code.splitlines())
            })

        return chunks

    except Exception as e:

        print(f"AST parsing failed for {file_path}: {e}")

        return [{
            "content": code[:3000],
            "file_path": file_path,
            "chunk_type": "fallback",
            "start_line": 1,
            "end_line": len(code.splitlines())
        }]

def analyze_complexity(code: str, file_path: str):
    if not file_path.endswith(".py"):
        return {
            "functions": [],
            "maintainability_index": None
        }

    try:
        complexity_results = cc_visit(code)
        maintainability = mi_visit(code, multi=True)
        functions = []

        for item in complexity_results:

            functions.append({
                "name": item.name,
                "complexity": item.complexity,
                "line": item.lineno
            })

        return {
            "functions": functions,
            "maintainability_index": round(maintainability, 2)
        }

    except Exception as e:
        print(f"Radon failed: {e}")

        return {
            "functions": [],
            "maintainability_index": None
        }
        
test_embedding = embeddings.embed_query("test")
print("Embedding dimension:", len(test_embedding))

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
    
    EXCLUDED_DIRS = [
        "node_modules",
        "dist",
        "build",
        ".next",
        "target",
        "__pycache__"
    ]
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("GitHub API error: ", response.text)
        return []
    
    data = response.json()
    
    return [
        file["path"]
        for file in data.get("tree", [])
        if file["path"].endswith((".py", ".js", ".jsx", ".cpp", ".java", ".c")) and not any(
            excluded in file["path"] for excluded in EXCLUDED_DIRS
        )
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

    return content

def build_vector_store(documents, index_path):

    docs = []

    for doc in documents:

        ast_chunks = extract_ast_chunks(
            doc["content"],
            doc["file_path"]
        )

        for chunk in ast_chunks:

            complexity_data = analyze_complexity(
                chunk["content"],
                chunk["file_path"]
            )

            enriched_content = f"""
            File: {chunk['file_path']}

            Chunk Type:
            {chunk['chunk_type']}

            Lines:
            {chunk['start_line']} - {chunk['end_line']}

            Maintainability Index:
            {complexity_data['maintainability_index']}

            Functions:
            {json.dumps(complexity_data['functions'], indent=2)}

            Code:
            {chunk['content']}
            """

            docs.append(
                Document(
                    page_content=enriched_content,
                    metadata={
                        "file_path": chunk["file_path"],
                        "chunk_type": chunk["chunk_type"],
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"]
                    }
                )
            )

    if not docs:
        raise Exception("No valid chunks generated for embeddings")

    print(f"Total AST chunks: {len(docs)}")

    vectorstore = FAISS.from_documents(
        docs,
        embeddings
    )

    vectorstore.save_local(index_path)

    return vectorstore

def load_or_create_vectorstore(documents, owner, repo, branch, commit_sha):
    index_path = os.path.join(FAISS_DIR, f"{owner}_{repo}_{branch}_{commit_sha}")

    if os.path.exists(index_path):
        try:
            return FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        except Exception:
            print("Failed to load FAISS index, rebuilding...")

    return build_vector_store(documents, index_path)

def trim_code(content, max_chars=1500):
    return content[:max_chars]

def retrieve_context(vectorstore, query, k=5):
    docs = vectorstore.similarity_search(query, k=k)
    context = "\n\n".join([
        f"File: {d.metadata.get('file_path')}\n{d.page_content[:250]}"
        for d in docs
    ])

    return context[:2500]

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
    with ThreadPoolExecutor(max_workers=2) as executor:
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
    Analyze this code for Time and Space Complexity improvements.

    File:
    {file_path}

    Static Complexity Analysis:
    {complexity_report}

    Relevant Repository Context:
    {retrieved_context}

    Code:
    {code_content}

    Return:
    - original_complexity
    - optimized_complexity
    - explanation
    - original_code
    - refactored_code

    Rules:
    - Focus ONLY on measurable performance improvements
    - Do NOT suggest stylistic refactors
    - ONLY return suggestions if complexity improves
    - If no optimization exists, return "NO_OPTIMIZATION"
    - Prioritize nested loops, repeated DB/API calls, recursion, and redundant allocations
    - Keep snippets under 30 lines
    - Do not return the entire file
    """)

    chain = prompt | llm.with_structured_output(OptimizationSuggestion)
    

    def process_doc(doc):
        for attempt in range(3):
            try:
                query = f"""
                    Find similar high complexity functions and optimization patterns for:
                    {doc['file_path']}
                """

                retrieved_context = retrieve_context(
                    vectorstore,
                    query=query
                )
                
                complexity_report = analyze_complexity(doc["content"], doc["file_path"])

                response = chain.invoke({
                    "file_path": doc["file_path"],
                    "code_content": trim_code(doc["content"]),
                    "retrieved_context": retrieved_context,
                    "complexity_report": json.dumps(complexity_report, indent=2)
                })

                print("LLM Response:", response)

                return OptimizationSuggestion(
                    file_path=doc["file_path"],
                    original_complexity=response.original_complexity,
                    optimized_complexity=response.optimized_complexity,
                    explanation=response.explanation,
                    original_code=response.original_code,
                    refactored_code=response.refactored_code
                )

            except Exception as e:
                print(f"Attempt {attempt+1} failed for {doc['file_path']}: {e}")
                time.sleep(2)

        return None

    suggestions = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_doc, doc) for doc in documents[:5]]

        for future in as_completed(futures):
            result = future.result()
            
            if result:
                improved = is_complexity_improved(result.optimized_complexity, result.optimized_complexity)
                meaningful = is_meaningful_refactor(result.original_code, result.refactored_code)
                
                if improved and meaningful:
                    suggestions.append(result)
            
            else:
                print(f"Skipped non-improving suggestion for {result.file_path}")
                
    final_result = AnalysisResponse(repo_name=f"{owner}/{repo}", suggestions=suggestions)
                
    with open(cache_path, "w") as f:
        json.dump(final_result.model_dump(), f)

    return final_result