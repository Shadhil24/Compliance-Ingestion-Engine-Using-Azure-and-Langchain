import os
import glob
import logging
from dotenv import load_dotenv
load_dotenv(override=True)

# document loaders and splitters
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# vector store
from langchain_community.vectorstores import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings

# logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("brand-guardian")

def index_docs():
    '''
    Read the PDF files from the data/pdfs directory
    '''
    # define paths, we look for the data folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_folder = os.path.join(current_dir, "../../backend/data")

    # check the environment variables
    logger.info("="*60)
    logger.info("Environment Configuration Check: ")
    logger.info(f"Azure Search Endpoint: {os.getenv('AZURE_SEARCH_ENDPOINT')}")
    logger.inf(f"Azure OPENAI_API_VERSION: {os.getenv('AZURE_OPENAI_API_VERSION')}")
    logger.info(f"Embedding Deployment : {os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT')}")
    logger.info(f"Azure Search Endpoint: {os.getenv('AZURE_SEARCH_ENDPOINT')}")
    logger.info(f"Azure Search Key: {os.getenv('AZURE_SEARCH_API_KEY')}")
    logger.info("="*60)

    required_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_API_KEY",
        "AZURE_SEARCH_INDEX_NAME"
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        logger.error("Please check your .env file and ensure all required variables are set.")
        return
    
    # initialize the embeddings model : turn text into vector
    try:
        logger.info("Initializing embeddings model...")
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )
        logger.info("Embeddings model initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing embeddings model: {e}")
        logger.error(f"Please verify the environment variables and try again.")
        return
    
    try:
        logger.info("Initializing Azure AI search vector store...")
        embeddings = AzureOpenAIEmbeddings(
            azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
            azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
            index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
            embedding_function=embeddings.embed_query,
        )
        logger.info("Azure AI search vector store initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing Azure AI search vector store: {e}")
        logger.error(f"Please verify the environment variables and try again.")
        return
    # list all PDF files in the data folder
    pdf_files = glob.glob(os.path.join(data_folder, "*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in the data folder. Please add some PDF files to the data folder.")
        return
    logger.info(f"Found {len(pdf_files)} PDF files to index.")

    all_splits = []

    # process each PDF file
    for pdf_file in pdf_files:
        try:  
            logger.info(f"Indexing PDF file: {pdf_file}")
            loader = PyPDFLoader(pdf_file)
            raw_docs = loader.load()
            logger.info(f"Loaded {len(raw_docs)} documents from {pdf_file}")
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            splits = text_splitter.split_documents(raw_docs)
            logger.info(f"Split into {len(splits)} chunks")
            for split in splits:
                split.metadata["source"] = os.path.basename(pdf_file)
            all_splits.extend(splits)
            logger.info(f"Added {len(splits)} chunks to the list.")
            logger.info(f"Current total chunks: {len(all_splits)}")
        except Exception as e:
            logger.error(f"Error processing PDF file {pdf_file}: {e}")
            logger.error(f"Please check the file and try again.")
            continue
        
        # Upload to Azure AI search vector store
        if all_splits:
            logger.info(f"Uploading {len(all_splits)} chunks to Azure AI search vector store...")
            try:
                # azure search accepts batches automatically with this method
                vector_store.add_documents(all_splits)
                logger.info("Chunks uploaded successfully.")
                logger.info("="*60)
                logger.info(f"Total documents indexed: {vector_store.count()}")
                logger.info("="*60)
            except Exception as e:
                logger.error(f"Error uploading chunks to Azure AI search vector store: {e}")
                logger.error(f"Please check the vector store and try again.")
                continue
        else:
            logger.warning("No chunks to upload. Please check the files and try again.")

if __name__ == "__main__":
    index_docs()