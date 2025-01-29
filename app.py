import streamlit as st
from vipas import model, logger
from sentence_transformers import SentenceTransformer
import faiss
import pdfplumber
from docx import Document
import pandas as pd
import numpy as np

class RAGProcessor:
    def __init__(self, model_id):
        self.client = model.ModelClient()
        self.model_id = model_id
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.faiss_index = None
        self.chunks = []
        self.embeddings = None
        self.last_file_name = None

    def preprocess_document(self, file):
        try:
            if file.type == "application/pdf":
                with pdfplumber.open(file) as pdf:
                    text = "".join([page.extract_text() or "" for page in pdf.pages])
            elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                doc = Document(file)
                text = " ".join([para.text for para in doc.paragraphs])
            elif file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                data = pd.read_excel(file)
                text = data.to_string(index=False)
            else:
                st.error("Unsupported file type. Please upload a PDF, DOCX, or Excel file.")
                return ""
            return text
        except Exception as e:
            st.error(f"Error processing file: {e}")
            return ""

    def store_embeddings(self, text, batch_size=32):
        self.chunks = [text[i:i + 500] for i in range(0, len(text), 500)]
        self.chunks = [chunk for chunk in self.chunks if chunk.strip()]

        if not self.chunks:
            st.error("No valid text found in the document.")
            return None

        self.faiss_index = faiss.IndexFlatL2(384)  # Reinitialize FAISS index
        self.embeddings = []

        for i in range(0, len(self.chunks), batch_size):
            batch = self.chunks[i:i + batch_size]
            batch_embeddings = self.embedding_model.encode(batch)
            self.embeddings.extend(batch_embeddings)

        self.embeddings = np.array(self.embeddings)
        self.faiss_index.add(self.embeddings)
        return self.chunks

    def retrieve_context(self, query):
        if self.faiss_index is None or not self.chunks:
            st.error("No document is indexed. Please upload a file first.")
            return ""

        query_embedding = self.embedding_model.encode([query])
        distances, indices = self.faiss_index.search(query_embedding, k=5)  # Retrieve top 5 chunks

        retrieved_chunks = [self.chunks[i] for i in indices[0]]
        return " ".join(retrieved_chunks)

    def query_llm(self, query, context):
        prompt = (
            "You are an expert. Answer the question using the provided context:\n\n"
            f"Context: {context}\n\n"
            f"Question: {query}\n\n"
            "Answer:"
        )
        try:
            response = self.client.predict(model_id=self.model_id, input_data=prompt)
            return response.get("choices", [{}])[0].get("text", "No response text available.")
        except Exception as e:
            st.error(f"Error querying the LLM: {e}")
            return ""

# Use Streamlit session state to persist the processor
if "rag_processor" not in st.session_state:
    st.session_state.rag_processor = RAGProcessor(model_id="mdl-i0595emvlc9n6")

if "response" not in st.session_state:
    st.session_state.response = ""

rag_processor = st.session_state.rag_processor

# Streamlit app
st.markdown(
    """
    <h1 style="text-align: center;">DocQuery-AI</h1>
    """,
    unsafe_allow_html=True
)
# st.write("RAG-based Q&A app using Llama with PDF, DOC, Excel input.")
st.markdown("<h3>RAG-based Q&A app using Llama with PDF, DOC, Excel input.</h3>", unsafe_allow_html=True)
st.write("Upload a document (PDF, DOC, or Excel) under 2 MB and ask questions using the LLM.")

# File upload
uploaded_file = st.file_uploader("Upload a file (PDF, DOC, or Excel):", type=["pdf", "docx", "xlsx"])
if uploaded_file:
    file_size = uploaded_file.size / (1024 * 1024) 
    if file_size > 2:
        st.error("File size exceeds 2MB. Please upload a smaller file.")
    else:
        file_name = uploaded_file.name
        if file_name != rag_processor.last_file_name:
            st.write("Uploading the file...")
        if uploaded_file or file_name == rag_processor.last_file_name:
            # st.write("File Uploaded.")
            st.markdown("<p><strong>File Uploaded.</strong></p>", unsafe_allow_html=True)
   
        submit_button = st.button("Submit", disabled=not bool(uploaded_file), key="submit_button")
        if submit_button and uploaded_file:
            text = rag_processor.preprocess_document(uploaded_file)

            if text:
                # st.write("Generating embeddings and indexing...")
                st.markdown("<p><strong>Generating embeddings and indexing...</strong></p>", unsafe_allow_html=True)
                chunks = rag_processor.store_embeddings(text)

                if chunks:
                    rag_processor.last_file_name = file_name
                    st.success("Document processed and indexed successfully!")

if rag_processor.last_file_name and rag_processor.faiss_index is not None:
    query = st.text_input("Enter your query:")

    # Create columns to adjust alignment
    col1, col2 = st.columns([8, 1])
    with col2:  # Place the button in the right column
        query_button = st.button("Query", key="query_button", type="primary")

    if query and query_button:
        context = rag_processor.retrieve_context(query)
        st.markdown("<p><strong>Generating response from LLM...</strong></p>", unsafe_allow_html=True)

        # Store response in session state instead of displaying it immediately
        st.session_state.response = rag_processor.query_llm(query, context)

# Display stored response from session state
if st.session_state.response:
    st.write("### Response")
    st.write(st.session_state.response)
