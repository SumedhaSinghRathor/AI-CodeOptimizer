import os
from langchain_community.document_loaders import GitLoader
from langchain_openrouter import ChatOpenRouter
from langchain_core.prompts import ChatPromptTemplate
from schemas import RepoRequest, AnalysisResponse, OptimizationSuggesstion
from dotenv import load_dotenv

load_dotenv()

llm = ChatOpenRouter(
    model="deepseek/deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0.1
)

def analyze_codebase(request: RepoRequest) -> AnalysisResponse:
    loader = GitLoader(
        clone_url=str(request.repo_url),
        repo_path='./temp_repo',
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
    
    Provide your response in JSON format matching the OptimizationSuggestion schema.
    """)
    
    for doc in documents[:5]:
        chain = prompt | llm
        response = chain.invoke({
            "file_path": doc.metadata["file_path"],
            "code_content": doc.page_content
        })
        
        suggestions.append(OptimizationSuggesstion(
            file_path=doc.metadata["file_path"],
            original_complexity="O(n^2) predicted",
            optimized_complexity="O(n) proposed",
            explanation="AI-generated optimization suggestion.",
            refactored_code=response.content
        ))
        
    return AnalysisResponse(repo_name=str(request.repo_url), suggestions=suggestions)