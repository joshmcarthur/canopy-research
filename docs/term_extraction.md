# Term Extraction with LLM Support

## Overview

The term extraction service supports LLM-based extraction for better semantic understanding, synonym handling, and concept extraction. It supports **Hugging Face models (recommended)**, **Ollama**, and **OpenAI cloud models**.

## Hugging Face Models (Recommended - Easiest Setup)

### Why Hugging Face?

- **Same as embeddings**: Uses the same `sentence-transformers` models you already use
- **No extra setup**: Just `uv sync --group term-extraction` (or `pip install keybert`)
- **Lightweight**: Small models (~80MB-420MB)
- **Fast**: Runs on CPU efficiently
- **Privacy**: Data stays local
- **Cost**: Free, no API calls

### Recommended Models

Uses the same models as your embeddings, so you can reuse them:

1. **all-MiniLM-L6-v2** (default) - **Recommended**
   - Fast and lightweight (~80MB)
   - Same model as embeddings (if configured)
   - Good quality for keyword extraction

2. **all-mpnet-base-v2**
   - Best quality (~420MB)
   - Same model as embeddings (if configured)
   - Slower but more accurate

3. **all-MiniLM-L12-v2**
   - Balance between speed and quality
   - Medium size (~130MB)

### Setup with Hugging Face

1. **Install KeyBERT** (optional dependency):
   ```bash
   # Using uv (recommended)
   uv sync --group term-extraction
   
   # Or using pip
   pip install keybert
   ```

2. **Configure** (optional - uses same model as embeddings by default):
   ```bash
   export TERM_EXTRACTION_BACKEND=huggingface
   export TERM_EXTRACTION_MODEL=all-MiniLM-L6-v2  # or all-mpnet-base-v2
   ```

That's it! No API keys, no Ollama setup, just works.

## Ollama Models (Alternative Local Option)

### Why Ollama?

- **Larger models**: Better for complex extraction
- **More control**: Full LLM capabilities
- **Privacy**: Data stays on-device
- **Cost**: Free, no API calls

### Recommended Models

1. **Mistral 7B** (`mistral:7b`)
   - Good balance of quality and speed
   - ~4GB RAM required

2. **Llama 3.2 3B** (`llama3.2:3b`)
   - Very fast, optimized for structured outputs
   - ~2GB RAM required

3. **Phi-3 Mini** (`phi3:mini`)
   - Very fast, small model
   - ~2GB RAM required

### Setup with Ollama

1. **Install Ollama**: https://ollama.ai

2. **Pull a model**:
   ```bash
   ollama pull mistral:7b
   ```

3. **Install Python package**:
   ```bash
   pip install ollama
   ```

4. **Configure**:
   ```bash
   export TERM_EXTRACTION_BACKEND=ollama
   export OLLAMA_MODEL=mistral:7b
   ```

## Cloud Models (OpenAI)

### Setup

1. **Set API key**:
   ```bash
   export OPENAI_API_KEY=your_key_here
   ```

2. **Configure backend**:
   ```bash
   export TERM_EXTRACTION_BACKEND=cloud
   export OPENAI_TERM_MODEL=gpt-4o-mini  # optional, defaults to gpt-4o-mini
   ```

## Usage

### Automatic (Default)

The system automatically uses Hugging Face extraction (same as embeddings), falling back to simple extraction if unavailable:

```python
from canopyresearch.services.term_extraction import extract_terms_with_llm

# Uses Hugging Face by default (same model as embeddings)
terms = extract_terms_with_llm("Research on distributed systems and consensus algorithms")
# Returns: ["distributed systems", "consensus algorithms", "distributed computing", ...]
```

### Explicit Control

```python
# Use Hugging Face (default, easiest)
terms = extract_terms_with_llm(
    text="Machine learning research",
    context="workspace description",
    use_local=True,
    model="all-MiniLM-L6-v2"  # or any HF model
)

# Use Ollama
terms = extract_terms_with_llm(
    text="Machine learning research",
    use_local=True,
    model="mistral:7b"
)

# Use cloud OpenAI
terms = extract_terms_with_llm(
    text="Machine learning research",
    use_local=False,
    model="gpt-4o-mini"
)
```

### Document Extraction

```python
from canopyresearch.services.term_extraction import extract_terms_from_document

# Uses LLM by default
terms = extract_terms_from_document(document, use_llm=True)

# Fallback to simple extraction
terms = extract_terms_from_document(document, use_llm=False)
```

## Benefits of LLM Extraction

1. **Semantic Understanding**: Understands context and meaning
2. **Synonym Expansion**: "ML" → "machine learning", "artificial intelligence"
3. **Concept Extraction**: Extracts key concepts, not just keywords
4. **Noise Reduction**: Filters generic terms like "research", "article"
5. **Domain Awareness**: Understands technical vs. general terms

## Fallback Behavior

The system gracefully falls back to simple text extraction if:
- LLM service is unavailable
- API key is missing (for cloud)
- Model fails to respond
- Network issues occur

This ensures the system always works, even without LLM support.

## Caching

Terms are cached in the `WorkspaceSearchTerms` model, so LLM extraction only runs when:
- Workspace is created/updated
- User gives feedback on documents
- Terms are manually refreshed

This minimizes API calls and improves performance.

## Performance Comparison

| Method | Speed | Quality | Cost | Privacy | Setup |
|--------|-------|---------|------|---------|-------|
| Simple extraction | ⭐⭐⭐⭐⭐ | ⭐⭐ | Free | ✅ | None |
| Hugging Face (KeyBERT) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Free | ✅ | `uv sync --group term-extraction` |
| Ollama (Mistral 7B) | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Free | ✅ | Install Ollama |
| Cloud LLM (GPT-4o-mini) | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ~$0.001/request | ❌ | API key |

## Model Selection Guide

**Choose Hugging Face (KeyBERT) if:**
- ✅ You want the easiest setup (just `uv sync --group term-extraction`)
- ✅ You already use sentence-transformers for embeddings
- ✅ You want good quality without complexity
- ✅ You have limited RAM (< 1GB for model)
- ✅ **This is the recommended default**

**Choose Ollama if:**
- You need maximum quality for complex extraction
- You have 4GB+ RAM available
- You want full LLM capabilities
- You're okay with more setup

**Choose cloud if:**
- You need maximum quality
- You don't have local resources
- You're okay with API costs
- You want the latest models

## Troubleshooting

### KeyBERT not found
```bash
# Using uv (recommended)
uv sync --group term-extraction

# Or using pip
pip install keybert
```

### Hugging Face model download issues
- Models download automatically on first use
- Check internet connection
- Models are cached in `~/.cache/huggingface/`
- Can take a few minutes on first run

### Ollama not found
```bash
# Install Ollama from https://ollama.ai
# Then install Python package:
pip install ollama
```

### Model not found (Ollama)
```bash
# Pull the model:
ollama pull mistral:7b
```

### OpenAI errors
- Check `OPENAI_API_KEY` is set
- Verify API key is valid
- Check rate limits

### Fallback to simple extraction
- Check logs for error messages
- Verify model is running (for Ollama)
- Check network connectivity (for cloud)
